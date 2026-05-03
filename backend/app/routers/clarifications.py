import io
import logging
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.schemas.clarification import (
    ClarificationItem,
    ClarificationListResponse,
    ClarificationResolveRequest,
    DocumentClarificationGroup,
    EmailDraft,
)
from app.services.skill_manager import learn_from_clarification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/clients/{client_id}/clarifications", tags=["clarifications"])

_CATEGORY_LABELS = {
    "cash_deposit": "Bareinzahlung",
    "cash_withdrawal": "Barauszahlung",
    "owner_transfer": "Zahlung Gesellschafter/Inhaber",
    "vague_reference": "Unklarer Verwendungszweck",
    "unknown_private_person": "Unbekannte Privatperson",
    "loan_indicator": "Mögliches Darlehen",
    "large_unidentified": "Hoher ungeklärter Betrag",
}


def _booking_to_item(booking: Booking, document: Document) -> ClarificationItem:
    return ClarificationItem(
        booking_id=booking.id,
        document_id=booking.document_id,
        document_filename=document.original_filename,
        amount=booking.amount,
        debit_credit=booking.debit_credit,
        document_date=booking.document_date,
        booking_text=booking.booking_text,
        clarification_category=booking.clarification_category or "vague_reference",
        clarification_question=booking.clarification_question or "",
        clarification_answer=booking.clarification_answer,
        clarification_resolved=booking.clarification_resolved,
        clarification_resolved_at=booking.clarification_resolved_at,
        clarification_resolved_by=booking.clarification_resolved_by,
    )


async def _load_clarifications(
    db: AsyncSession,
    client_id: uuid.UUID,
    *,
    include_resolved: bool = True,
) -> tuple[Client, list[tuple[Booking, Document]]]:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    query = (
        select(Booking, Document)
        .join(Document, Booking.document_id == Document.id)
        .where(Booking.client_id == client_id)
        .where(Booking.needs_clarification == True)  # noqa: E712
    )

    if not include_resolved:
        query = query.where(Booking.clarification_resolved == False)  # noqa: E712

    query = query.order_by(Document.uploaded_at.desc(), Booking.document_date.desc())
    result = await db.execute(query)
    return client, list(result.all())


def _group_by_document(
    rows: list[tuple[Booking, Document]],
) -> list[DocumentClarificationGroup]:
    doc_map: dict[uuid.UUID, dict] = {}
    doc_items: dict[uuid.UUID, list[ClarificationItem]] = defaultdict(list)

    for booking, document in rows:
        doc_id = document.id
        if doc_id not in doc_map:
            doc_map[doc_id] = {
                "document_id": doc_id,
                "document_filename": document.original_filename,
                "uploaded_at": document.uploaded_at,
            }
        doc_items[doc_id].append(_booking_to_item(booking, document))

    groups = []
    for doc_id, meta in doc_map.items():
        items = doc_items[doc_id]
        open_count = sum(1 for i in items if not i.clarification_resolved)
        resolved_count = sum(1 for i in items if i.clarification_resolved)
        groups.append(
            DocumentClarificationGroup(
                document_id=meta["document_id"],
                document_filename=meta["document_filename"],
                uploaded_at=meta["uploaded_at"],
                open_count=open_count,
                resolved_count=resolved_count,
                items=items,
            )
        )

    return groups


@router.get("", response_model=ClarificationListResponse)
async def list_clarifications(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClarificationListResponse:
    client, rows = await _load_clarifications(db, client_id, include_resolved=True)

    groups = _group_by_document(rows)
    total = sum(g.open_count + g.resolved_count for g in groups)
    open_total = sum(g.open_count for g in groups)
    resolved_total = sum(g.resolved_count for g in groups)

    open_items = [
        item for g in groups for item in g.items if not item.clarification_resolved
    ]
    email_draft = _build_email_draft(client.company_name, open_items)

    return ClarificationListResponse(
        client_id=client_id,
        company_name=client.company_name,
        total_count=total,
        open_count=open_total,
        resolved_count=resolved_total,
        groups=groups,
        email_draft=email_draft,
    )


@router.post("/{booking_id}/resolve", response_model=ClarificationItem)
async def resolve_clarification(
    client_id: uuid.UUID,
    booking_id: uuid.UUID,
    payload: ClarificationResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> ClarificationItem:
    booking = await db.get(Booking, booking_id)
    if booking is None or booking.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if not booking.needs_clarification:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This booking has no clarification question",
        )

    if booking.clarification_resolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This clarification has already been resolved",
        )

    booking.clarification_answer = payload.answer.strip()
    booking.clarification_resolved = True
    booking.clarification_resolved_at = datetime.now(timezone.utc)
    booking.clarification_resolved_by = "user"

    db.add(AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="clarification_resolved",
        performed_by="user",
        new_state={
            "clarification_answer": booking.clarification_answer,
            "clarification_resolved": True,
        },
    ))

    document = await db.get(Document, booking.document_id)
    vendor_name = None
    if document and document.extraction:
        vendor_name = document.extraction.get("vendor_name")
        counterparty = None
        for t in document.extraction.get("transactions", []):
            if (t.get("counterparty") or "").strip():
                counterparty = t["counterparty"].strip()
                break
        vendor_name = vendor_name or counterparty

    try:
        await learn_from_clarification(
            client_id=client_id,
            booking_id=booking.id,
            question=booking.clarification_question or "",
            answer=booking.clarification_answer,
            vendor_name=vendor_name,
            db=db,
        )
    except Exception:
        logger.exception("Skill learning from clarification failed for booking %s", booking.id)

    await db.flush()
    await db.refresh(booking)

    return _booking_to_item(booking, document)


@router.post("/{booking_id}/reopen", response_model=ClarificationItem)
async def reopen_clarification(
    client_id: uuid.UUID,
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClarificationItem:
    booking = await db.get(Booking, booking_id)
    if booking is None or booking.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if not booking.clarification_resolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This clarification is not resolved",
        )

    booking.clarification_answer = None
    booking.clarification_resolved = False
    booking.clarification_resolved_at = None
    booking.clarification_resolved_by = None

    db.add(AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="clarification_reopened",
        performed_by="user",
    ))

    await db.flush()
    await db.refresh(booking)

    document = await db.get(Document, booking.document_id)
    return _booking_to_item(booking, document)


@router.get("/pdf")
async def download_clarification_pdf(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    client, rows = await _load_clarifications(db, client_id, include_resolved=False)

    groups = _group_by_document(rows)
    pdf_bytes = _build_pdf(client.company_name, groups)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"Rueckfragen_{client.company_name.replace(' ', '_')}_{today}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_email_draft(company_name: str, open_items: list[ClarificationItem]) -> EmailDraft:
    today = date.today().strftime("%d.%m.%Y")
    subject = f"Rückfragen zu Ihren Kontoauszügen — {company_name}"

    if not open_items:
        return EmailDraft(subject=subject, body_text="Keine offenen Rückfragen vorhanden.")

    lines = [
        f"Betreff: {subject}",
        "",
        "Sehr geehrte Damen und Herren,",
        "",
        "im Rahmen der laufenden Buchführung haben wir einige Positionen aus Ihren Kontoauszügen "
        "identifiziert, die wir ohne weitere Informationen nicht eindeutig zuordnen können.",
        "Wir bitten Sie, folgende Punkte zu klären:",
        "",
    ]

    for i, item in enumerate(open_items, 1):
        category_label = _CATEGORY_LABELS.get(item.clarification_category, item.clarification_category)
        amount_str = f"{item.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
        lines.append(f"Position {i} — {category_label} ({item.document_date.strftime('%d.%m.%Y')}, {amount_str})")
        lines.append(item.clarification_question)
        lines.append("")

    lines += [
        "Bitte teilen Sie uns die entsprechenden Informationen möglichst zeitnah mit, "
        "damit wir Ihre Buchführung vollständig abschließen können.",
        "",
        "Bei Fragen stehen wir Ihnen gerne zur Verfügung.",
        "",
        "Mit freundlichen Grüßen",
        "",
        "[Unterschrift Steuerberater/Buchhalter]",
        "[Kanzlei]",
        "[Datum: " + today + "]",
    ]

    return EmailDraft(subject=subject, body_text="\n".join(lines))


_DEJAVU_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _build_pdf(
    company_name: str,
    groups: list[DocumentClarificationGroup],
) -> bytes:
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError:
        logger.error("fpdf2 not installed — returning plain text fallback")
        return b"Keine PDF-Bibliothek verfuegbar."

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    if os.path.exists(_DEJAVU_PATHS[0]):
        pdf.add_font("DejaVu", "", _DEJAVU_PATHS[0])
        pdf.add_font("DejaVu", "B", _DEJAVU_PATHS[1])
        font_family = "DejaVu"
    else:
        logger.warning("DejaVu fonts not found — falling back to Helvetica (no Unicode)")
        font_family = "Helvetica"

    pdf.add_page()

    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, f"Rückfragen: {company_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(font_family, "", 10)
    pdf.cell(0, 6, f"Erstellt am: {date.today().strftime('%d.%m.%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    total_open = sum(g.open_count for g in groups)
    if total_open == 0:
        pdf.set_font(font_family, "", 11)
        pdf.cell(0, 8, "Keine offenen Rückfragen vorhanden.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return bytes(pdf.output())

    pdf.set_font(font_family, "B", 11)
    pdf.cell(0, 8, f"Offene Positionen: {total_open}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    question_num = 0
    for group in groups:
        open_items = [i for i in group.items if not i.clarification_resolved]
        if not open_items:
            continue

        pdf.set_font(font_family, "B", 11)
        pdf.set_fill_color(220, 230, 245)
        pdf.cell(
            0, 8,
            f"  Beleg: {group.document_filename}",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True,
        )
        pdf.ln(2)

        for item in open_items:
            question_num += 1
            category_label = _CATEGORY_LABELS.get(item.clarification_category, item.clarification_category)
            amount_str = f"{item.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

            pdf.set_font(font_family, "B", 10)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(
                0, 7,
                f"  {question_num}.  {item.document_date.strftime('%d.%m.%Y')}  |  {amount_str}  |  {category_label}",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True,
            )
            pdf.set_font(font_family, "", 10)
            pdf.set_x(14)
            pdf.multi_cell(0, 6, item.clarification_question, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.set_font(font_family, "", 9)
            pdf.set_text_color(120, 120, 120)
            pdf.set_x(14)
            pdf.cell(0, 5, "Antwort: ____________________________________________", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)

        pdf.ln(2)

    return bytes(pdf.output())
