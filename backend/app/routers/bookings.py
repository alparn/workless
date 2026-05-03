import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.document import Document
from app.schemas.booking import (
    BatchApproveRequest,
    BatchApproveResponse,
    BookingResponse,
    BookingUpdate,
    BookingWithDocumentResponse,
)
from app.services.skill_manager import learn_from_correction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


async def _get_vendor_name_for_booking(booking: Booking, db: AsyncSession) -> str | None:
    """Extract vendor name from the parent document's extraction data."""
    doc = await db.get(Document, booking.document_id)
    if not doc or not doc.extraction:
        return None
    return doc.extraction.get("vendor_name")


def _booking_snapshot(booking: Booking) -> dict:
    return {
        "account": booking.account,
        "contra_account": booking.contra_account,
        "bu_key": booking.bu_key,
        "amount": str(booking.amount),
        "debit_credit": booking.debit_credit,
        "booking_text": booking.booking_text,
        "status": booking.status,
        "cost_center_1": booking.cost_center_1,
        "cost_center_2": booking.cost_center_2,
    }


@router.get("", response_model=list[BookingResponse])
async def list_bookings(
    client_id: uuid.UUID | None = Query(None),
    booking_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[BookingResponse]:
    query = (
        select(Booking)
        .options(selectinload(Booking.document))
        .order_by(Booking.created_at.desc())
    )

    if client_id is not None:
        query = query.where(Booking.client_id == client_id)
    if booking_status is not None:
        query = query.where(Booking.status == booking_status)

    result = await db.execute(query)
    bookings = result.scalars().all()

    responses = []
    for b in bookings:
        extraction = b.document.extraction if b.document else None
        bank_name = None
        bank_iban = None
        if extraction and extraction.get("document_type") == "bank_statement":
            bank_name = extraction.get("bank_name")
            bank_iban = extraction.get("iban")

        responses.append(BookingResponse(
            **{c.key: getattr(b, c.key) for c in Booking.__table__.columns},
            bank_name=bank_name,
            bank_iban=bank_iban,
        ))

    return responses


@router.get("/review", response_model=list[BookingWithDocumentResponse])
async def list_review_queue(
    client_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[BookingWithDocumentResponse]:
    query = (
        select(Booking)
        .where(Booking.status == "suggested")
        .options(selectinload(Booking.document))
        .order_by(Booking.created_at.desc())
    )

    if client_id is not None:
        query = query.where(Booking.client_id == client_id)

    result = await db.execute(query)
    bookings = result.scalars().all()

    responses = []
    for b in bookings:
        extraction = b.document.extraction if b.document else None
        bank_name = None
        bank_iban = None
        if extraction and extraction.get("document_type") == "bank_statement":
            bank_name = extraction.get("bank_name")
            bank_iban = extraction.get("iban")

        responses.append(BookingWithDocumentResponse(
            **{c.key: getattr(b, c.key) for c in Booking.__table__.columns},
            document_filename=b.document.original_filename if b.document else None,
            document_extraction=b.document.extraction if b.document else None,
            document_status=b.document.status if b.document else None,
            bank_name=bank_name,
            bank_iban=bank_iban,
        ))
    return responses


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    return booking


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: uuid.UUID,
    payload: BookingUpdate,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status not in ("suggested", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit a booking with status '{booking.status}'.",
        )

    previous_state = _booking_snapshot(booking)
    was_ai_suggested = booking.suggested_by in ("ai", "ai_agent")
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(booking, field, value)

    new_state = _booking_snapshot(booking)

    audit = AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="updated",
        performed_by="user",
        previous_state=previous_state,
        new_state=new_state,
    )
    db.add(audit)

    if was_ai_suggested:
        vendor_name = await _get_vendor_name_for_booking(booking, db)
        try:
            await learn_from_correction(
                booking_id=booking.id,
                old_state=previous_state,
                new_state=new_state,
                client_id=booking.client_id,
                vendor_name=vendor_name,
                db=db,
            )
        except Exception:
            logger.exception("Skill learning from correction failed for booking %s", booking.id)

    await db.flush()
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/approve", response_model=BookingResponse)
async def approve_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status not in ("suggested", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve a booking with status '{booking.status}'.",
        )

    previous_state = _booking_snapshot(booking)
    booking.status = "approved"
    booking.approved_at = datetime.now(timezone.utc)
    new_state = _booking_snapshot(booking)

    audit = AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="approved",
        performed_by="user",
        previous_state=previous_state,
        new_state=new_state,
    )
    db.add(audit)

    await _maybe_approve_document(booking.document_id, db)

    await db.flush()
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/reject", response_model=BookingResponse)
async def reject_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status not in ("suggested",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject a booking with status '{booking.status}'.",
        )

    previous_state = _booking_snapshot(booking)
    booking.status = "rejected"
    new_state = _booking_snapshot(booking)

    audit = AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="rejected",
        performed_by="user",
        previous_state=previous_state,
        new_state=new_state,
    )
    db.add(audit)

    await db.flush()
    await db.refresh(booking)
    return booking


@router.post("/batch-approve", response_model=BatchApproveResponse)
async def batch_approve(
    payload: BatchApproveRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchApproveResponse:
    result = await db.execute(
        select(Booking).where(
            Booking.id.in_(payload.booking_ids),
            Booking.status.in_(["suggested", "rejected"]),
        )
    )
    bookings = list(result.scalars().all())

    if not bookings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approvable bookings found for the given IDs.",
        )

    now = datetime.now(timezone.utc)
    approved_ids: list[uuid.UUID] = []
    document_ids: set[uuid.UUID] = set()

    for booking in bookings:
        previous_state = _booking_snapshot(booking)
        booking.status = "approved"
        booking.approved_at = now

        audit = AuditLog(
            entity_type="booking",
            entity_id=booking.id,
            action="approved",
            performed_by="user",
            previous_state=previous_state,
            new_state=_booking_snapshot(booking),
        )
        db.add(audit)
        approved_ids.append(booking.id)
        document_ids.add(booking.document_id)

    for doc_id in document_ids:
        await _maybe_approve_document(doc_id, db)

    await db.flush()

    return BatchApproveResponse(
        approved_count=len(approved_ids),
        booking_ids=approved_ids,
    )


async def _maybe_approve_document(document_id: uuid.UUID, db: AsyncSession) -> None:
    """Mark parent document as approved when no booking is still a pending suggestion."""
    result = await db.execute(
        select(Booking).where(
            Booking.document_id == document_id,
            Booking.status == "suggested",
        )
    )
    remaining = result.scalars().first()
    if remaining is None:
        document = await db.get(Document, document_id)
        if document is not None and document.status != "approved":
            document.status = "approved"
            document.approved_at = datetime.now(timezone.utc)
