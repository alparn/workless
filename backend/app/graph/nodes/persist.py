import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.state import DocumentProcessingState
from app.models.agent_skill import AgentSkill
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.document import Document
from app.models.vendor_booking_history import VendorBookingHistory

AUTO_SKILL_THRESHOLD = 3

logger = logging.getLogger(__name__)


async def persist_results(
    state: DocumentProcessingState, db: AsyncSession
) -> dict:
    """Node 5: Persist bookings, update document, write audit logs, update vendor history."""
    document_id = state["document_id"]
    client_id = state["client_id"]

    if state.get("status") in ("ocr_failed", "booking_failed"):
        await _update_document_error(db, document_id, state)
        return {"status": state["status"]}

    logger.info("Persisting results for document %s", document_id)

    document = await db.get(Document, uuid.UUID(document_id))
    if document is None:
        return {"status": "error", "error": "Document not found in database"}

    document.ocr_provider = state.get("ocr_provider")
    document.ocr_raw_result = state.get("ocr_result")
    document.extraction = state.get("extraction")
    document.ocr_confidence = (
        Decimal(str(state["ocr_confidence"])) if state.get("ocr_confidence") else None
    )
    document.ocr_completed_at = datetime.now(timezone.utc)
    document.status = "booking_suggested"

    db.add(AuditLog(
        entity_type="document",
        entity_id=uuid.UUID(document_id),
        action="ai_ocr",
        performed_by="ai",
        new_state={
            "ocr_provider": state.get("ocr_provider"),
            "ocr_confidence": state.get("ocr_confidence"),
            "status": "ocr_complete",
        },
        ai_details={
            "provider": state.get("ocr_provider"),
            "confidence": state.get("ocr_confidence"),
        },
    ))

    extraction = state.get("extraction") or {}
    vendor_name = extraction.get("vendor_name", "")
    bookings_data = state.get("suggested_bookings", [])

    default_date_str = extraction.get("document_date") or extraction.get("statement_date")
    default_date = datetime.now(timezone.utc).date()
    if default_date_str:
        try:
            default_date = datetime.strptime(default_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    for booking_dict in bookings_data:
        try:
            amount = Decimal(str(booking_dict.get("amount", 0)))
        except (InvalidOperation, TypeError, ValueError):
            logger.warning("Invalid amount in booking suggestion, skipping")
            continue

        booking_date_str = booking_dict.get("document_date")
        if booking_date_str:
            try:
                doc_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                doc_date = default_date
        else:
            doc_date = default_date

        raw_tax_hints = booking_dict.get("tax_hints")
        tax_hints = raw_tax_hints if isinstance(raw_tax_hints, dict) else None

        booking = Booking(
            document_id=uuid.UUID(document_id),
            client_id=uuid.UUID(client_id),
            amount=amount,
            debit_credit=booking_dict.get("debit_credit", "S"),
            account=str(booking_dict.get("account", "")),
            contra_account=str(booking_dict.get("contra_account", "")),
            bu_key=booking_dict.get("bu_key"),
            document_date=doc_date,
            reference_1=(booking_dict.get("reference_1") or "")[:36] or None,
            booking_text=str(booking_dict.get("booking_text", ""))[:60],
            suggested_by="ai",
            ai_confidence=Decimal(str(state.get("booking_confidence", 0))),
            ai_reasoning=booking_dict.get("reasoning"),
            needs_clarification=bool(booking_dict.get("needs_clarification", False)),
            clarification_category=booking_dict.get("clarification_category"),
            clarification_question=booking_dict.get("clarification_question"),
            tax_hints=tax_hints,
            status="suggested",
        )
        db.add(booking)
        await db.flush()

        audit_new_state = {
            "amount": str(amount),
            "debit_credit": booking.debit_credit,
            "account": booking.account,
            "contra_account": booking.contra_account,
            "bu_key": booking.bu_key,
            "booking_text": booking.booking_text,
            "status": "suggested",
        }
        if tax_hints:
            audit_new_state["tax_hints"] = tax_hints

        db.add(AuditLog(
            entity_type="booking",
            entity_id=booking.id,
            action="ai_booking",
            performed_by="ai",
            new_state=audit_new_state,
            ai_details={
                "confidence": state.get("booking_confidence"),
                "reasoning": booking_dict.get("reasoning"),
                "model": "claude-sonnet-4-20250514",
            },
        ))

        effective_vendor = vendor_name or (booking_dict.get("counterparty") or "")
        if effective_vendor and booking.account:
            await _update_vendor_history(
                db,
                client_id=client_id,
                vendor_name=effective_vendor,
                account=booking.account,
                contra_account=booking.contra_account,
                bu_key=booking.bu_key,
            )
            try:
                await _maybe_auto_create_skill(
                    db,
                    client_id=client_id,
                    vendor_name=effective_vendor,
                    account=booking.account,
                    contra_account=booking.contra_account,
                    bu_key=booking.bu_key,
                )
            except Exception:
                logger.exception("Auto-skill creation failed for vendor '%s'", effective_vendor)

    await db.flush()

    return {"status": "booking_suggested"}


async def _update_document_error(
    db: AsyncSession, document_id: str, state: DocumentProcessingState
) -> None:
    """Update a document with error status."""
    document = await db.get(Document, uuid.UUID(document_id))
    if document is None:
        return
    document.status = state.get("status", "error")
    document.error_details = state.get("error")
    if state.get("ocr_provider"):
        document.ocr_provider = state["ocr_provider"]
    if state.get("ocr_confidence"):
        document.ocr_confidence = Decimal(str(state["ocr_confidence"]))
    await db.flush()


async def _update_vendor_history(
    db: AsyncSession,
    client_id: str,
    vendor_name: str,
    account: str,
    contra_account: str,
    bu_key: str | None,
) -> None:
    """Insert or update vendor booking history using an upsert."""
    normalized = vendor_name.strip().lower()

    stmt = pg_insert(VendorBookingHistory).values(
        client_id=uuid.UUID(client_id),
        vendor_name_normalized=normalized,
        account=account,
        contra_account=contra_account,
        bu_key=bu_key,
        occurrence_count=1,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_vendor_booking_combo",
        set_={
            "occurrence_count": VendorBookingHistory.occurrence_count + 1,
            "last_booked_at": func.now(),
            "bu_key": bu_key,
        },
    )
    await db.execute(stmt)


async def _maybe_auto_create_skill(
    db: AsyncSession,
    client_id: str,
    vendor_name: str,
    account: str,
    contra_account: str,
    bu_key: str | None,
) -> None:
    """Auto-create a vendor_pattern skill when a vendor reaches the booking threshold."""
    normalized = vendor_name.strip().lower()
    client_uuid = uuid.UUID(client_id)

    result = await db.execute(
        select(VendorBookingHistory)
        .where(
            VendorBookingHistory.client_id == client_uuid,
            VendorBookingHistory.vendor_name_normalized == normalized,
            VendorBookingHistory.account == account,
            VendorBookingHistory.contra_account == contra_account,
        )
    )
    history = result.scalar_one_or_none()

    if not history or history.occurrence_count < AUTO_SKILL_THRESHOLD:
        return

    slug = normalized.replace(" ", "_")[:50]
    skill_key = f"auto:vendor:{slug}:{account}"

    existing = await db.execute(
        select(AgentSkill).where(
            AgentSkill.client_id == client_uuid,
            AgentSkill.skill_key == skill_key,
        )
    )
    if existing.scalar_one_or_none():
        return

    vendor_display = vendor_name.strip()
    bu_note = f", BU-Schlüssel {bu_key}" if bu_key else ""
    content = (
        f"**{vendor_display}** wird standardmäßig auf Konto **{account}** "
        f"(Gegenkonto {contra_account}{bu_note}) gebucht. "
        f"Dieses Muster wurde {history.occurrence_count}x bestätigt."
    )

    skill = AgentSkill(
        client_id=client_uuid,
        skill_key=skill_key,
        category="vendor_pattern",
        title=f"{vendor_display} → Konto {account}",
        content=content,
        source="auto_detected",
        confidence=Decimal("0.75"),
    )
    db.add(skill)
    await db.flush()
    logger.info(
        "Auto-created vendor skill '%s' after %d occurrences",
        skill_key, history.occurrence_count,
    )
