import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.storage import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    delete_file,
    get_file,
    save_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _run_workflow_background(document_id: uuid.UUID) -> None:
    """Run the LangGraph document processing workflow in the background,
    then trigger an LLM review of the resulting bookings."""
    from app.graph.workflow import run_document_workflow
    from app.services.llm_reviewer import run_llm_review

    async with async_session() as db:
        try:
            final_state = await run_document_workflow(document_id, db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Background workflow failed for document %s", document_id)
            document = await db.get(Document, document_id)
            if document is not None:
                document.status = "ocr_failed"
                document.error_details = "Workflow execution failed unexpectedly"
                await db.commit()
            return

    if final_state.get("status") == "booking_suggested":
        async with async_session() as db:
            try:
                client_id = uuid.UUID(final_state["client_id"])
                await run_llm_review(
                    db, client_id,
                    trigger="document_processed",
                    document_id=document_id,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception(
                    "LLM review failed after document %s", document_id
                )


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    client_id: uuid.UUID = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> Document:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
            headers={"X-Error-Code": "CLIENT_NOT_FOUND"},
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, PNG, JPG.",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    storage_path = await save_file(
        client_id=client_id,
        file_bytes=file_bytes,
        original_filename=file.filename or "unknown",
    )

    document = Document(
        client_id=client_id,
        original_filename=file.filename or "unknown",
        storage_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(file_bytes),
        status="uploaded",
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    background_tasks.add_task(_run_workflow_background, document.id)

    return document


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Re-trigger the full AI processing workflow for an existing document.

    Cleans up previous bookings (only non-exported ones), resets the document
    state, and starts a fresh workflow run.
    """
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.status == "exported":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exportierte Dokumente können nicht erneut verarbeitet werden.",
        )

    if document.status == "ocr_processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dokument wird bereits verarbeitet.",
        )

    exported_bookings = await db.execute(
        select(Booking.id)
        .where(Booking.document_id == document_id)
        .where(Booking.status == "exported")
        .limit(1)
    )
    if exported_bookings.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dokument hat bereits exportierte Buchungen.",
        )

    previous_state = {
        "status": document.status,
        "ocr_provider": document.ocr_provider,
        "ocr_confidence": str(document.ocr_confidence) if document.ocr_confidence else None,
        "error_details": document.error_details,
    }

    deleted = await db.execute(
        delete(Booking).where(Booking.document_id == document_id)
    )
    deleted_count = deleted.rowcount

    document.status = "ocr_processing"
    document.error_details = None
    document.ocr_provider = None
    document.ocr_raw_result = None
    document.extraction = None
    document.ocr_confidence = None
    document.ocr_completed_at = None

    db.add(AuditLog(
        entity_type="document",
        entity_id=document_id,
        action="reprocess",
        performed_by="user",
        previous_state=previous_state,
        new_state={"status": "ocr_processing", "deleted_bookings": deleted_count},
    ))

    await db.flush()
    await db.refresh(document)

    logger.info(
        "Reprocessing document %s (deleted %d old bookings)",
        document_id, deleted_count,
    )

    background_tasks.add_task(_run_workflow_background, document.id)

    return document


@router.get("", response_model=list[DocumentListResponse])
async def list_documents(
    client_id: uuid.UUID | None = Query(None),
    document_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    query = select(Document).order_by(Document.uploaded_at.desc())

    if client_id is not None:
        query = query.where(Document.client_id == client_id)
    if document_status is not None:
        query = query.where(Document.status == document_status)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve the original uploaded file (PDF/image) for in-browser viewing."""
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    try:
        file_bytes = await get_file(document.storage_path)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found on disk")

    return Response(
        content=file_bytes,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{document_id}/detail")
async def get_document_detail(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Full document detail including extraction data and all bookings."""
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    result = await db.execute(
        select(Booking)
        .where(Booking.document_id == document_id)
        .order_by(Booking.document_date, Booking.created_at)
    )
    bookings = list(result.scalars().all())

    return {
        "document": {
            "id": str(document.id),
            "client_id": str(document.client_id),
            "original_filename": document.original_filename,
            "mime_type": document.mime_type,
            "file_size_bytes": document.file_size_bytes,
            "ocr_provider": document.ocr_provider,
            "ocr_confidence": str(document.ocr_confidence) if document.ocr_confidence else None,
            "extraction": document.extraction,
            "status": document.status,
            "error_details": document.error_details,
            "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
            "ocr_completed_at": document.ocr_completed_at.isoformat() if document.ocr_completed_at else None,
            "approved_at": document.approved_at.isoformat() if document.approved_at else None,
        },
        "bookings": [
            {
                "id": str(b.id),
                "amount": str(b.amount),
                "debit_credit": b.debit_credit,
                "account": b.account,
                "contra_account": b.contra_account,
                "bu_key": b.bu_key,
                "document_date": b.document_date.isoformat() if b.document_date else None,
                "booking_text": b.booking_text,
                "reference_1": b.reference_1,
                "suggested_by": b.suggested_by,
                "ai_confidence": str(b.ai_confidence) if b.ai_confidence else None,
                "ai_reasoning": b.ai_reasoning,
                "status": b.status,
                "needs_clarification": b.needs_clarification,
                "clarification_question": b.clarification_question,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bookings
        ],
        "booking_count": len(bookings),
    }


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.status in ("approved", "booked", "exported"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a document that has already been approved.",
        )

    await delete_file(document.storage_path)
    await db.delete(document)
