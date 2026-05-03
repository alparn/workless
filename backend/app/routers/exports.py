import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, case, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.booking import Booking
from app.models.export_batch import ExportBatch
from app.schemas.export import (
    ExportBatchResponse,
    ExportCreateRequest,
    ExportPreviewRequest,
    ExportPreviewResponse,
)
from app.services.datev_export import EXPORTABLE_BOOKING_STATUSES, create_export_batch

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


@router.post("/datev", response_model=ExportBatchResponse, status_code=status.HTTP_201_CREATED)
async def create_datev_export(
    payload: ExportCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ExportBatch:
    try:
        batch = await create_export_batch(
            db=db,
            client_id=payload.client_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            label=payload.label,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return batch


@router.post("/preview", response_model=ExportPreviewResponse)
async def preview_export(
    payload: ExportPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ExportPreviewResponse:
    period = and_(
        Booking.client_id == payload.client_id,
        Booking.document_date >= payload.date_from,
        Booking.document_date <= payload.date_to,
    )

    agg = await db.execute(
        select(
            sqlfunc.coalesce(
                sqlfunc.sum(
                    case(
                        (Booking.status.in_(EXPORTABLE_BOOKING_STATUSES), 1),
                        else_=0,
                    )
                ),
                0,
            ),
            sqlfunc.coalesce(
                sqlfunc.sum(case((Booking.status == "suggested", 1), else_=0)),
                0,
            ),
            sqlfunc.coalesce(
                sqlfunc.sum(case((Booking.status == "exported", 1), else_=0)),
                0,
            ),
            sqlfunc.coalesce(
                sqlfunc.sum(case((Booking.status == "rejected", 1), else_=0)),
                0,
            ),
            sqlfunc.coalesce(
                sqlfunc.sum(
                    case(
                        (
                            Booking.status.in_(EXPORTABLE_BOOKING_STATUSES),
                            Booking.amount,
                        ),
                        else_=None,
                    )
                ),
                Decimal("0"),
            ),
        ).where(period)
    )
    row = agg.one()

    docs = await db.execute(
        select(sqlfunc.count(sqlfunc.distinct(Booking.document_id))).where(period)
    )
    documents_with_bookings = int(docs.scalar_one())

    def _as_int(v: object) -> int:
        if isinstance(v, Decimal):
            return int(v)
        return int(v)

    approved_n = _as_int(row[0])
    return ExportPreviewResponse(
        booking_count=approved_n,
        date_from=payload.date_from,
        date_to=payload.date_to,
        total_amount=str(row[4]),
        pending_approval_count=_as_int(row[1]),
        exported_count=_as_int(row[2]),
        rejected_count=_as_int(row[3]),
        documents_with_bookings_count=documents_with_bookings,
    )


@router.get("/{batch_id}/download")
async def download_export(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    batch = await db.get(ExportBatch, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export batch not found",
        )

    if not batch.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )

    file_path = Path(batch.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file missing from storage",
        )

    batch.downloaded_at = datetime.now(timezone.utc)
    await db.flush()

    filename = f"EXTF_{batch.date_from.isoformat()}_{batch.date_to.isoformat()}.csv"
    return FileResponse(
        path=str(file_path),
        media_type="text/csv; charset=cp1252",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("", response_model=list[ExportBatchResponse])
async def list_exports(
    client_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ExportBatch]:
    query = select(ExportBatch).order_by(ExportBatch.created_at.desc())

    if client_id is not None:
        query = query.where(ExportBatch.client_id == client_id)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{batch_id}", response_model=ExportBatchResponse)
async def get_export(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExportBatch:
    batch = await db.get(ExportBatch, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export batch not found",
        )
    return batch
