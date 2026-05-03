"""Resolve the correct bank ledger account for a bank-statement document.

Uses a cascading strategy:
  1. IBAN exact match
  2. IBAN fuzzy match (OCR tolerance)
  3. BIC match
  4. Bank-name match (single hit)
  5. LLM-assisted resolution (ambiguous)
  6. Auto-provision new account (valid IBAN, no match)
  7. Default / fallback
"""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.state import DocumentProcessingState
from app.models.bank_account import BankAccount
from app.services.bank_matching import (
    MatchResult,
    get_default_account,
    next_account_number,
    normalize_iban,
    try_bank_name,
    try_bic,
    try_iban_exact,
    try_iban_fuzzy,
)
from app.services.skills import load_skill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public node entry-point
# ---------------------------------------------------------------------------

async def resolve_bank_account(
    state: DocumentProcessingState, db: AsyncSession
) -> dict:
    extraction = state.get("extraction") or {}
    if extraction.get("document_type") != "bank_statement":
        return {}
    if state.get("status") == "ocr_failed":
        return {}

    logger.info("Resolving bank account for document %s", state["document_id"])

    client_id = state["client_id"]
    chart = state.get("chart_of_accounts", "SKR03")
    accounts = await _fetch_accounts(db, client_id)

    stmt_iban = extraction.get("iban")
    stmt_bic = extraction.get("bic")
    stmt_bank = extraction.get("bank_name", "")

    if not accounts:
        logger.info("No bank accounts configured — auto-provisioning for client %s", client_id)
        new = await _auto_provision(db, client_id, chart, [], stmt_iban, stmt_bic, stmt_bank)
        return _to_state(new, "auto_provisioned", 0.95, chart, [new], reasoning=(
            f"Erstes Bankkonto {new.account_number} automatisch angelegt "
            f"für {stmt_bank} (IBAN: {new.iban})"
        ))

    result = _run_deterministic_cascade(accounts, stmt_iban, stmt_bic, stmt_bank, chart)
    if result is not None:
        return _match_to_state(result, chart, accounts)

    if stmt_bank and len(try_bank_name(accounts, stmt_bank)) > 1:
        return await _llm_resolve(state, accounts, chart, db)

    if len(accounts) > 1 and not stmt_iban:
        return await _llm_resolve(state, accounts, chart, db)

    if stmt_iban:
        new = await _auto_provision(db, client_id, chart, accounts, stmt_iban, stmt_bic, stmt_bank)
        return _to_state(new, "auto_provisioned", 0.95, chart, [*accounts, new], reasoning=(
            f"Neue Bank erkannt: {stmt_bank} (IBAN: {new.iban}). "
            f"Sachkonto {new.account_number} automatisch angelegt."
        ))

    default = get_default_account(accounts)
    if default:
        return _to_state(default, "default", 0.60, chart, accounts, needs_review=True, reasoning=(
            f"Keine IBAN/BIC/Bankname-Übereinstimmung. "
            f"Standard-Bankkonto {default.account_number} ({default.bank_name}) verwendet."
        ))

    return _to_state(accounts[0], "default", 0.50, chart, accounts, needs_review=True, reasoning=(
        f"Kein Match möglich, erstes Konto {accounts[0].account_number} verwendet"
    ))


# ---------------------------------------------------------------------------
# Deterministic cascade (pure, no IO)
# ---------------------------------------------------------------------------

def _run_deterministic_cascade(
    accounts: list[BankAccount],
    iban: str | None,
    bic: str | None,
    bank_name: str,
    chart: str,
) -> MatchResult | None:
    if iban:
        result = try_iban_exact(accounts, iban)
        if result:
            return result
        result = try_iban_fuzzy(accounts, iban)
        if result:
            return result

    if bic:
        result = try_bic(accounts, bic)
        if result:
            return result

    if bank_name:
        name_hits = try_bank_name(accounts, bank_name)
        if len(name_hits) == 1:
            return MatchResult(
                account=name_hits[0],
                method="bank_name",
                confidence=0.75,
                reasoning=(
                    f"Bankname '{bank_name}' matched eindeutig "
                    f"'{name_hits[0].bank_name}' (Konto {name_hits[0].account_number})"
                ),
            )

    return None


# ---------------------------------------------------------------------------
# LLM-assisted resolution (ambiguous cases)
# ---------------------------------------------------------------------------

async def _llm_resolve(
    state: DocumentProcessingState,
    all_accounts: list[BankAccount],
    chart: str,
    db: AsyncSession | None = None,
) -> dict:
    extraction = state.get("extraction") or {}
    skill = load_skill("bank_account_resolution.md")

    accounts_info = [
        {
            "account_number": a.account_number,
            "bank_name": a.bank_name,
            "iban": a.iban or "",
            "bic": a.bic or "",
            "is_default": a.is_default,
            "label": a.label or "",
        }
        for a in all_accounts
    ]

    statement_info = {
        k: extraction.get(k, "")
        for k in ("bank_name", "iban", "bic", "account_holder",
                   "statement_number", "period_from", "period_to")
    }

    prompt = (
        f"{skill}\n\n---\n\n"
        "Ordne den folgenden Kontoauszug dem richtigen Sachkonto zu.\n\n"
        f"Kontenrahmen: {chart}\n\n"
        f"Konfigurierte Bankkonten des Mandanten:\n{json.dumps(accounts_info, indent=2)}\n\n"
        f"Kontoauszug-Informationen:\n{json.dumps(statement_info, indent=2)}\n\n"
        "Antworte NUR mit dem JSON gemäß dem Format im Skill oben."
    )

    from app.services import llm_service

    client_id = state["client_id"]
    response = await llm_service.completion(
        uuid.UUID(client_id), db,
        operation="bank_resolution",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    response_text = response.choices[0].message.content or ""

    try:
        parsed = _parse_json_response(response_text)
    except (json.JSONDecodeError, IndexError):
        logger.error("LLM bank resolution parse failed: %s", response_text[:300])
        fallback = get_default_account(all_accounts) or all_accounts[0]
        return _to_state(fallback, "default", 0.50, chart, all_accounts,
                         needs_review=True, reasoning="LLM-Zuordnung fehlgeschlagen")

    matched = next((a for a in all_accounts if a.account_number == parsed.get("resolved_account")), None)
    confidence = float(parsed.get("confidence", 0.5))

    return _to_state(
        matched, parsed.get("match_method", "llm_assisted"),
        confidence, chart, all_accounts,
        needs_review=parsed.get("needs_review", confidence < 0.8),
        alternatives=parsed.get("alternative_accounts", []),
        reasoning=parsed.get("reasoning", "LLM-unterstützte Zuordnung"),
    )


# ---------------------------------------------------------------------------
# Auto-provisioning
# ---------------------------------------------------------------------------

async def _auto_provision(
    db: AsyncSession,
    client_id: str,
    chart: str,
    existing: list[BankAccount],
    iban: str | None,
    bic: str | None,
    bank_name: str,
) -> BankAccount:
    account_number = next_account_number(existing, chart)
    normalized_iban = normalize_iban(iban) if iban else None

    new = BankAccount(
        client_id=uuid.UUID(client_id),
        account_number=account_number,
        bank_name=bank_name or f"Bank {account_number}",
        iban=normalized_iban,
        bic=bic.replace(" ", "").upper() if bic else None,
        is_default=len(existing) == 0,
        label="Auto-erkannt aus Kontoauszug",
    )
    db.add(new)
    await db.flush()

    logger.info(
        "Auto-provisioned bank account %s (%s, IBAN: %s) for client %s",
        account_number, bank_name, normalized_iban, client_id,
    )
    return new


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_accounts(db: AsyncSession, client_id: str) -> list[BankAccount]:
    result = await db.execute(
        select(BankAccount)
        .where(BankAccount.client_id == client_id)
        .order_by(BankAccount.is_default.desc(), BankAccount.account_number)
    )
    return list(result.scalars().all())


def _match_to_state(m: MatchResult, chart: str, all_accounts: list[BankAccount]) -> dict:
    return _to_state(
        m.account, m.method, m.confidence, chart, all_accounts,
        needs_review=m.needs_review, reasoning=m.reasoning,
    )


def _to_state(
    account: BankAccount | None,
    method: str,
    confidence: float,
    chart: str,
    all_accounts: list[BankAccount],
    *,
    needs_review: bool = False,
    alternatives: list[dict] | None = None,
    reasoning: str = "",
) -> dict:
    if account:
        return {
            "resolved_bank_account": account.account_number,
            "resolved_bank_name": account.bank_name,
            "bank_iban_matched": method in ("iban_exact", "iban_fuzzy"),
            "bank_match_method": method,
            "bank_match_confidence": confidence,
            "bank_needs_review": needs_review,
            "bank_alternative_accounts": alternatives or [],
            "bank_resolution_reasoning": reasoning,
        }

    fallback_account = "1200" if chart.upper() == "SKR03" else "1800"
    return {
        "resolved_bank_account": fallback_account,
        "resolved_bank_name": "",
        "bank_iban_matched": False,
        "bank_match_method": "fallback",
        "bank_match_confidence": 0.3,
        "bank_needs_review": True,
        "bank_alternative_accounts": alternatives or [],
        "bank_resolution_reasoning": reasoning or "Kein passendes Konto gefunden",
    }


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return json.loads(cleaned.strip())
