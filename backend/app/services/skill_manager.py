"""
SkillManager — central service for agent self-learning.

Agents call into this service to persist, query, and reinforce
client-specific skills (booking rules, vendor patterns, corrections).
"""

import logging
import re
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_skill import AgentSkill
from app.services import llm_service

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset({
    "vendor_pattern",
    "account_rule",
    "tax_rule",
    "industry_pattern",
    "correction_pattern",
    "custom",
})

MAX_SKILLS_PER_REQUEST = 8
_CONFIDENCE_INCREMENT = Decimal("0.10")
_MAX_CONFIDENCE = Decimal("0.99")


def _slugify(text: str) -> str:
    """Turn an arbitrary string into a URL-safe key fragment."""
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9äöüß]+", "_", slug)
    return slug.strip("_")[:80]


async def learn_from_correction(
    booking_id: uuid.UUID,
    old_state: dict,
    new_state: dict,
    client_id: uuid.UUID,
    vendor_name: str | None,
    db: AsyncSession,
) -> AgentSkill | None:
    """Analyse a booking correction and persist the lesson as a skill.

    Called when a user edits an AI-generated booking (changes account,
    contra_account, bu_key, etc.).  Uses Claude to distill the diff into
    a human-readable rule.
    """
    changed_fields = {
        k: {"old": old_state.get(k), "new": new_state.get(k)}
        for k in ("account", "contra_account", "bu_key", "amount", "debit_credit", "booking_text")
        if old_state.get(k) != new_state.get(k)
    }
    if not changed_fields:
        return None

    vendor_label = (vendor_name or "Unbekannt").strip()
    skill_key = f"correction:{_slugify(vendor_label)}:{old_state.get('account', 'x')}_to_{new_state.get('account', 'x')}"

    existing = await db.execute(
        select(AgentSkill).where(
            AgentSkill.client_id == client_id,
            AgentSkill.skill_key == skill_key,
            AgentSkill.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        return await confirm_skill_by_key(client_id, skill_key, db)

    prompt = (
        "Du bist ein Buchhaltungsexperte. Ein Benutzer hat eine KI-Buchung korrigiert.\n"
        "Analysiere die Änderung und formuliere eine knappe, wiederverwendbare Regel.\n\n"
        f"Lieferant: {vendor_label}\n"
        f"Geänderte Felder: {changed_fields}\n"
        f"Vorher: {old_state}\n"
        f"Nachher: {new_state}\n\n"
        "Antworte mit genau zwei Zeilen:\n"
        "TITLE: <kurzer Titel der Regel, max 100 Zeichen>\n"
        "RULE: <Markdown-Beschreibung der Regel, 1-3 Sätze>"
    )

    try:
        resp = await llm_service.completion(
            client_id, db,
            operation="skill",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        text = resp.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM call for learn_from_correction failed")
        title = f"Korrektur: {vendor_label} → Konto {new_state.get('account', '?')}"
        text = f"TITLE: {title}\nRULE: Bei {vendor_label} Konto {new_state.get('account')} statt {old_state.get('account')} verwenden."

    title, content = _parse_title_rule(text)
    if not title:
        title = f"Korrektur: {vendor_label}"
    if not content:
        content = f"Änderung: {changed_fields}"

    category = "vendor_pattern" if vendor_name else "correction_pattern"

    skill = AgentSkill(
        client_id=client_id,
        skill_key=skill_key,
        category=category,
        title=title,
        content=content,
        source="booking_correction",
        source_entity_id=booking_id,
        confidence=Decimal("0.60"),
    )
    db.add(skill)
    await db.flush()
    logger.info("Learned skill '%s' from correction of booking %s", skill_key, booking_id)
    return skill


async def learn_from_chat(
    client_id: uuid.UUID,
    title: str,
    content: str,
    category: str,
    db: AsyncSession,
    source_entity_id: uuid.UUID | None = None,
) -> AgentSkill:
    """Persist a rule that the chat agent extracted from a user instruction."""
    if category not in VALID_CATEGORIES:
        category = "custom"

    skill_key = f"chat:{_slugify(title)}"

    existing_result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.client_id == client_id,
            AgentSkill.skill_key == skill_key,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.content = content
        existing.title = title
        existing.category = category
        existing.is_active = True
        existing.confidence = min(existing.confidence + _CONFIDENCE_INCREMENT, _MAX_CONFIDENCE)
        await db.flush()
        logger.info("Updated existing chat skill '%s'", skill_key)
        return existing

    skill = AgentSkill(
        client_id=client_id,
        skill_key=skill_key,
        category=category,
        title=title,
        content=content,
        source="chat_instruction",
        source_entity_id=source_entity_id,
        confidence=Decimal("0.70"),
    )
    db.add(skill)
    await db.flush()
    logger.info("Created chat skill '%s' for client %s", skill_key, client_id)
    return skill


async def learn_from_clarification(
    client_id: uuid.UUID,
    booking_id: uuid.UUID,
    question: str,
    answer: str,
    vendor_name: str | None,
    db: AsyncSession,
) -> AgentSkill | None:
    """Store a clarification answer as a reusable skill."""
    vendor_label = (vendor_name or "transaktion").strip()
    skill_key = f"clarification:{_slugify(vendor_label)}:{_slugify(answer[:40])}"

    existing_result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.client_id == client_id,
            AgentSkill.skill_key == skill_key,
        )
    )
    if existing_result.scalar_one_or_none():
        return await confirm_skill_by_key(client_id, skill_key, db)

    content = (
        f"**Klärung für {vendor_label}**\n\n"
        f"Frage: {question}\n"
        f"Antwort: {answer}\n\n"
        f"Wende diese Information auf zukünftige ähnliche Transaktionen an."
    )
    title = f"Klärung: {vendor_label} — {answer[:60]}"

    skill = AgentSkill(
        client_id=client_id,
        skill_key=skill_key,
        category="correction_pattern",
        title=title,
        content=content,
        source="clarification",
        source_entity_id=booking_id,
        confidence=Decimal("0.65"),
    )
    db.add(skill)
    await db.flush()
    logger.info("Created clarification skill '%s'", skill_key)
    return skill


async def get_relevant_skills(
    client_id: uuid.UUID,
    context: dict,
    db: AsyncSession,
) -> list[str]:
    """Return Markdown texts of the most relevant active skills.

    ``context`` may contain:
      - vendor_name: str
      - account: str
      - contra_account: str
      - document_type: str
      - keywords: list[str]   (extra search terms)
    """
    query = (
        select(AgentSkill)
        .where(
            AgentSkill.client_id == client_id,
            AgentSkill.is_active.is_(True),
        )
        .order_by(
            AgentSkill.confidence.desc(),
            AgentSkill.updated_at.desc(),
        )
        .limit(50)
    )
    result = await db.execute(query)
    all_skills: list[AgentSkill] = list(result.scalars().all())

    if not all_skills:
        return []

    search_tokens = _build_search_tokens(context)
    scored: list[tuple[float, AgentSkill]] = []

    for skill in all_skills:
        score = _score_skill(skill, context, search_tokens)
        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:MAX_SKILLS_PER_REQUEST]

    skill_ids = [s.id for _, s in top]
    if skill_ids:
        await db.execute(
            update(AgentSkill)
            .where(AgentSkill.id.in_(skill_ids))
            .values(usage_count=AgentSkill.usage_count + 1)
        )
        await db.flush()

    return [
        f"### {skill.title}\n{skill.content}"
        for _, skill in top
    ]


async def confirm_skill(
    skill_id: uuid.UUID,
    db: AsyncSession,
) -> AgentSkill | None:
    """Raise confidence when a skill-informed suggestion gets accepted."""
    skill = await db.get(AgentSkill, skill_id)
    if not skill:
        return None
    skill.confidence = min(skill.confidence + _CONFIDENCE_INCREMENT, _MAX_CONFIDENCE)
    await db.flush()
    logger.info("Confirmed skill %s, confidence now %s", skill_id, skill.confidence)
    return skill


async def confirm_skill_by_key(
    client_id: uuid.UUID,
    skill_key: str,
    db: AsyncSession,
) -> AgentSkill | None:
    """Raise confidence by skill_key (convenience wrapper)."""
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.client_id == client_id,
            AgentSkill.skill_key == skill_key,
            AgentSkill.is_active.is_(True),
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        return None
    skill.confidence = min(skill.confidence + _CONFIDENCE_INCREMENT, _MAX_CONFIDENCE)
    await db.flush()
    return skill


async def deactivate_skill(
    skill_id: uuid.UUID,
    db: AsyncSession,
) -> AgentSkill | None:
    """Soft-delete a skill that causes bad suggestions."""
    skill = await db.get(AgentSkill, skill_id)
    if not skill:
        return None
    skill.is_active = False
    await db.flush()
    logger.info("Deactivated skill %s", skill_id)
    return skill


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_search_tokens(context: dict) -> set[str]:
    """Extract lowercase search tokens from the booking context."""
    tokens: set[str] = set()
    for key in ("vendor_name", "account", "contra_account", "document_type"):
        val = context.get(key)
        if val:
            tokens.update(str(val).lower().split())
    for kw in context.get("keywords", []):
        tokens.update(str(kw).lower().split())
    return tokens


def _score_skill(
    skill: AgentSkill,
    context: dict,
    search_tokens: set[str],
) -> float:
    """Score a skill's relevance to the current context (higher = better)."""
    score = 0.0

    vendor_name = (context.get("vendor_name") or "").strip().lower()
    skill_content_lower = skill.content.lower()
    skill_key_lower = skill.skill_key.lower()

    if vendor_name and vendor_name in skill_key_lower:
        score += 10.0
    elif vendor_name and vendor_name in skill_content_lower:
        score += 5.0

    if skill.category == "vendor_pattern" and vendor_name:
        if _slugify(vendor_name) in skill_key_lower:
            score += 8.0

    account = context.get("account", "")
    contra = context.get("contra_account", "")
    if account and account in skill_content_lower:
        score += 3.0
    if contra and contra in skill_content_lower:
        score += 2.0

    if search_tokens:
        hits = sum(1 for t in search_tokens if t in skill_content_lower)
        score += hits * 1.5

    score += float(skill.confidence) * 2.0

    if skill.category in ("account_rule", "tax_rule"):
        score += 1.0

    return score


def _parse_title_rule(text: str) -> tuple[str, str]:
    """Parse 'TITLE: ...\nRULE: ...' from Claude's response."""
    title = ""
    rule = ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped[6:].strip()
        elif stripped.upper().startswith("RULE:"):
            rule = stripped[5:].strip()
    return title, rule
