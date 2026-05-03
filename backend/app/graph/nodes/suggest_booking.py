"""Node 4: Generate booking suggestions using Claude Sonnet.

Handles two document types:
  - Invoices / credit notes / receipts → single-document booking
  - Bank statements → one booking per transaction
"""

import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.prompts import build_bank_statement_prompt, build_invoice_prompt, build_outgoing_invoice_prompt
from app.graph.state import DocumentProcessingState
from app.models.vendor_booking_history import VendorBookingHistory
from app.services import llm_service
from app.services.code_executor import execute_python
from app.services.industry_catalog import build_industry_context
from app.services.skill_manager import get_relevant_skills
from app.services.skills import load_skill

_THINKING_BUDGET = settings.thinking_budget_tokens
_THINKING_CONFIDENCE_THRESHOLD = settings.thinking_confidence_threshold

logger = logging.getLogger(__name__)

_EXECUTE_PYTHON_TOOL = {
    "name": "execute_python",
    "description": (
        "Führe Python-Code aus (verfügbar: pandas, numpy, decimal, json, math, datetime, re). "
        "Nutze es für: Betragsberechnungen, MwSt-Validierung, Rundungsprüfungen, Summenabgleich. "
        "Gib Ergebnisse mit print() aus."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Valider Python-Code"},
        },
        "required": ["code"],
    },
}


# ---------------------------------------------------------------------------
# Node entry-point
# ---------------------------------------------------------------------------

async def suggest_booking(
    state: DocumentProcessingState, db: AsyncSession
) -> dict:
    if state.get("status") == "ocr_failed":
        return {}

    logger.info("Suggesting bookings for document %s", state["document_id"])

    extraction = state.get("extraction") or {}
    doc_type = extraction.get("document_type", "invoice")

    if doc_type == "bank_statement":
        return await _suggest_bank_statement(state, db, extraction)
    if doc_type == "outgoing_invoice":
        return await _suggest_outgoing_invoice(state, db, extraction)
    return await _suggest_invoice(state, db, extraction)


# ---------------------------------------------------------------------------
# Invoice bookings
# ---------------------------------------------------------------------------

async def _suggest_invoice(
    state: DocumentProcessingState, db: AsyncSession, extraction: dict
) -> dict:
    chart = state.get("chart_of_accounts", "SKR03")

    vendor_name = extraction.get("vendor_name", "")
    past_bookings = await _get_vendor_history(db, state["client_id"], vendor_name)
    vendor_context = _format_vendor_context(past_bookings, label="diesen Lieferanten")
    dynamic_skills = await _load_dynamic_skills(db, state["client_id"], extraction)
    industry_ctx = build_industry_context(state.get("industry"), state.get("industry_detail"))

    prompt = build_invoice_prompt(
        skr_skill=load_skill(f"{chart.lower()}.md"),
        vat_skill=load_skill("vat_keys.md"),
        dynamic_skills=dynamic_skills,
        vendor_context=vendor_context,
        extraction=extraction,
        industry_context=industry_ctx,
    )

    cid = uuid.UUID(state["client_id"])
    return await _run_booking_agent(cid, db, prompt, past_bookings)


# ---------------------------------------------------------------------------
# Outgoing invoice bookings (revenue / Einnahme)
# ---------------------------------------------------------------------------

async def _suggest_outgoing_invoice(
    state: DocumentProcessingState, db: AsyncSession, extraction: dict
) -> dict:
    chart = state.get("chart_of_accounts", "SKR03")

    recipient_name = extraction.get("recipient_name", "")
    past_bookings = await _get_vendor_history(db, state["client_id"], recipient_name)
    customer_context = _format_vendor_context(past_bookings, label="diesen Kunden")
    dynamic_skills = await _load_dynamic_skills(db, state["client_id"], extraction)
    industry_ctx = build_industry_context(state.get("industry"), state.get("industry_detail"))

    prompt = build_outgoing_invoice_prompt(
        skr_skill=load_skill(f"{chart.lower()}.md"),
        vat_skill=load_skill("vat_keys.md"),
        dynamic_skills=dynamic_skills,
        customer_context=customer_context,
        extraction=extraction,
        industry_context=industry_ctx,
    )

    cid = uuid.UUID(state["client_id"])
    return await _run_booking_agent(cid, db, prompt, past_bookings)


# ---------------------------------------------------------------------------
# Bank-statement bookings
# ---------------------------------------------------------------------------

async def _suggest_bank_statement(
    state: DocumentProcessingState, db: AsyncSession, extraction: dict
) -> dict:
    chart = state.get("chart_of_accounts", "SKR03")
    transactions = extraction.get("transactions", [])

    if not transactions:
        logger.warning("Bank statement has no transactions for %s", state["document_id"])
        return {
            "suggested_bookings": [],
            "booking_confidence": 0.0,
            "booking_reasoning": "Keine Transaktionen im Kontoauszug gefunden",
            "past_bookings": [],
            "status": "booking_suggested",
        }

    bank_account = state.get("resolved_bank_account")
    bank_name = state.get("resolved_bank_name") or extraction.get("bank_name", "")

    if not bank_account:
        bank_account = "1200" if chart.upper() == "SKR03" else "1800"
        logger.warning(
            "No resolved bank account for %s — falling back to %s",
            state["document_id"], bank_account,
        )

    all_vendor_history = await _collect_counterparty_history(db, state["client_id"], transactions)
    vendor_context = _format_vendor_context(all_vendor_history, label="bekannte Gegenparteien")
    bank_resolution_note = _format_resolution_note(state)
    dynamic_skills = await _load_dynamic_skills(db, state["client_id"], extraction)
    industry_ctx = build_industry_context(state.get("industry"), state.get("industry_detail"))

    prompt = build_bank_statement_prompt(
        skr_skill=load_skill(f"{chart.lower()}.md"),
        vat_skill=load_skill("vat_keys.md"),
        dynamic_skills=dynamic_skills,
        bank_account=bank_account,
        bank_name=bank_name,
        vendor_context=vendor_context,
        bank_resolution_note=bank_resolution_note,
        transactions=transactions,
        industry_context=industry_ctx,
    )

    cid = uuid.UUID(state["client_id"])
    return await _run_booking_agent(cid, db, prompt, all_vendor_history)


# ---------------------------------------------------------------------------
# Agentic tool-use loop
# ---------------------------------------------------------------------------

async def _run_booking_agent(
    client_id: uuid.UUID, db: AsyncSession, prompt: str, past_bookings: list[dict]
) -> dict:
    result = await _run_agent_loop(client_id, db, prompt, past_bookings, use_thinking=False)

    confidence = result.get("booking_confidence", 0.0)
    if confidence < _THINKING_CONFIDENCE_THRESHOLD and result.get("status") != "booking_failed":
        logger.info(
            "Booking confidence %.2f < %.2f — retrying with extended thinking",
            confidence, _THINKING_CONFIDENCE_THRESHOLD,
        )
        thinking_prompt = (
            f"{prompt}\n\n---\n\n"
            "WICHTIG: Ein vorheriger Versuch ergab eine niedrige Konfidenz "
            f"({confidence:.0%}). Denke besonders gründlich nach über:\n"
            "- Korrekte Kontenzuordnung laut Kontenrahmen\n"
            "- BU-Schlüssel und MwSt-Behandlung\n"
            "- Ob Klärungsbedarf besteht\n"
            "Begründe deine Entscheidungen ausführlich im 'reasoning'-Feld."
        )
        result = await _run_agent_loop(client_id, db, thinking_prompt, past_bookings, use_thinking=True)

    return result


async def _run_agent_loop(
    client_id: uuid.UUID,
    db: AsyncSession,
    prompt: str,
    past_bookings: list[dict],
    use_thinking: bool = False,
) -> dict:
    messages: list[dict] = [{"role": "user", "content": prompt}]

    thinking_cfg = None
    max_tokens = 16384
    if use_thinking:
        thinking_cfg = {"type": "enabled", "budget_tokens": _THINKING_BUDGET}
        max_tokens = 16384 + _THINKING_BUDGET

    for turn in range(10):
        response = await llm_service.completion(
            client_id, db,
            operation="suggest_booking",
            messages=messages,
            max_tokens=max_tokens,
            tools=[_EXECUTE_PYTHON_TOOL],
            thinking=thinking_cfg,
        )

        choice = response.choices[0]
        if choice.finish_reason in ("stop", "end_turn"):
            text = choice.message.content or ""

            if not text.strip():
                logger.warning("Agent ended turn without text output (turn %d) — requesting JSON", turn)
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": (
                        "Du hast keinen JSON-Output geliefert. "
                        "Bitte antworte JETZT NUR mit dem vollständigen JSON-Objekt im geforderten Format. "
                        "Keine Erklärungen, nur valides JSON."
                    ),
                })
                continue

            return _parse_booking_response(text, past_bookings)

        tool_calls = choice.message.tool_calls or []
        assistant_msg: dict = {
            "role": "assistant",
            "content": choice.message.content or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        tool_results = []
        for tc in tool_calls:
            if tc.function.name == "execute_python":
                args = json.loads(tc.function.arguments)
                logger.info("Agent executing Python (len=%d)", len(args.get("code", "")))
                result = await execute_python(args["code"])
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
        messages.extend(tool_results)

    logger.error("Booking agent exceeded max turns")
    return {
        "suggested_bookings": [],
        "booking_confidence": 0.0,
        "booking_reasoning": "Agent exceeded maximum turns",
        "past_bookings": past_bookings,
        "status": "booking_failed",
        "error": "Agent exceeded maximum turns",
    }


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _sanitize_json_string(text: str) -> str:
    """Escape unescaped control characters inside JSON string values."""
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in ('\n', '\r', '\t'):
            result.append({'\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
            continue
        result.append(ch)
    return ''.join(result)


def _parse_booking_response(response_text: str, past_bookings: list[dict]) -> dict:
    result = _try_parse_json(response_text)
    if result is None:
        logger.error("Failed to parse booking suggestion: %s", response_text[:500])
        return {
            "suggested_bookings": [],
            "booking_confidence": 0.0,
            "booking_reasoning": "Failed to parse AI response",
            "past_bookings": past_bookings,
            "status": "booking_failed",
            "error": "Failed to parse booking suggestion from AI",
        }

    return {
        "suggested_bookings": result.get("bookings", []),
        "booking_confidence": float(result.get("overall_confidence", 0.0)),
        "booking_reasoning": result.get("overall_reasoning", ""),
        "past_bookings": past_bookings,
        "status": "booking_suggested",
    }


def _try_parse_json(text: str) -> dict | None:
    """Robustly extract a JSON object from LLM output that may contain prose."""
    cleaned = _strip_markdown_fences(text)
    for candidate in [cleaned, _sanitize_json_string(cleaned)]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    match = re.search(r'\{[\s\S]*"bookings"\s*:\s*\[[\s\S]*\]\s*[\s\S]*\}', text)
    if match:
        raw = match.group(0)
        for candidate in [raw, _sanitize_json_string(raw)]:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    brace_start = text.find('{')
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    raw = text[brace_start:i + 1]
                    for candidate in [raw, _sanitize_json_string(raw)]:
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            pass
                    break

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_vendor_history(
    db: AsyncSession, client_id: str, vendor_name: str
) -> list[dict]:
    normalized = vendor_name.strip().lower()
    if not normalized:
        return []
    result = await db.execute(
        select(VendorBookingHistory)
        .where(VendorBookingHistory.client_id == client_id)
        .where(VendorBookingHistory.vendor_name_normalized == normalized)
        .order_by(VendorBookingHistory.occurrence_count.desc())
        .limit(5)
    )
    return [
        {
            "account": row.account,
            "contra_account": row.contra_account,
            "bu_key": row.bu_key,
            "occurrence_count": row.occurrence_count,
        }
        for row in result.scalars().all()
    ]


async def _collect_counterparty_history(
    db: AsyncSession, client_id: str, transactions: list[dict]
) -> list[dict]:
    counterparties = {
        (t.get("counterparty") or "").strip()
        for t in transactions
        if (t.get("counterparty") or "").strip()
    }
    all_history: list[dict] = []
    for name in counterparties:
        history = await _get_vendor_history(db, client_id, name)
        all_history.extend({**h, "vendor": name} for h in history)
    return all_history


def _format_vendor_context(history: list[dict], *, label: str) -> str:
    if not history:
        return ""
    return (
        f"\n\n## Frühere Buchungen für {label}\n"
        "Nutze diese als Orientierung für die Kontenzuordnung:\n"
        f"{json.dumps(history, default=str, indent=2)}"
    )


def _format_resolution_note(state: DocumentProcessingState) -> str:
    if not state.get("bank_needs_review"):
        return ""
    method = state.get("bank_match_method", "unknown")
    conf = state.get("bank_match_confidence", 0.0)
    reasoning = state.get("bank_resolution_reasoning", "")
    note = (
        f"\n\n⚠️ HINWEIS: Bankkonto-Zuordnung unsicher "
        f"(Methode: {method}, Konfidenz: {conf:.0%}). "
        f"Reasoning: {reasoning}"
    )
    alternatives = state.get("bank_alternative_accounts", [])
    if alternatives:
        note += f"\nAlternativen: {json.dumps(alternatives, default=str)}"
    return note


async def _load_dynamic_skills(
    db: AsyncSession, client_id: str, extraction: dict
) -> str:
    context: dict = {
        "vendor_name": extraction.get("vendor_name", ""),
        "document_type": extraction.get("document_type", ""),
    }
    counterparties = {
        (t.get("counterparty") or "").strip()
        for t in extraction.get("transactions", [])
        if (t.get("counterparty") or "").strip()
    }
    if counterparties:
        context["keywords"] = list(counterparties)

    try:
        skills = await get_relevant_skills(uuid.UUID(client_id), context, db)
    except Exception:
        logger.exception("Failed to load dynamic skills for client %s", client_id)
        return ""

    if not skills:
        return ""

    return f"## Mandantenspezifische Regeln (gelernt)\n\n{''.join(skills)}\n\n---\n\n"
