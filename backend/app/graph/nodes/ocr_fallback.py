import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.state import DocumentProcessingState
from app.services.ocr_service import claude_vision_ocr
from app.services.storage import get_file

logger = logging.getLogger(__name__)


async def ocr_fallback(state: DocumentProcessingState, db: AsyncSession | None = None) -> dict:
    """Node 2 (conditional): Run Claude Vision OCR when Mistral confidence is too low."""
    logger.info(
        "OCR fallback triggered for document %s (confidence: %.2f)",
        state["document_id"],
        state["ocr_confidence"],
    )

    try:
        file_bytes = await get_file(state["file_path"])
        extraction = state.get("extraction") or {}
        doc_hint = extraction.get("document_type", "invoice")
        result = await claude_vision_ocr(
            file_bytes, state["mime_type"], doc_type_hint=doc_hint,
            client_id=state.get("client_id"), db=db,
        )

        return {
            "ocr_result": {
                "raw_text": result.raw_text,
                "extraction": result.extraction,
            },
            "ocr_provider": result.provider,
            "ocr_confidence": float(result.confidence),
            "extraction": result.extraction,
            "status": "ocr_complete",
        }
    except Exception as e:
        logger.exception("OCR fallback failed for document %s", state["document_id"])
        return {
            "status": "ocr_failed",
            "error": str(e),
        }
