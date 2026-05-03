import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.state import DocumentProcessingState
from app.services.ocr_service import mistral_ocr
from app.services.storage import get_file

logger = logging.getLogger(__name__)


async def ocr_extract(state: DocumentProcessingState, db: AsyncSession | None = None) -> dict:
    """Node 1: Run Mistral OCR on the uploaded document."""
    logger.info("OCR extract started for document %s", state["document_id"])

    try:
        file_bytes = await get_file(state["file_path"])
        result = await mistral_ocr(
            file_bytes, state["mime_type"],
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
        logger.exception("OCR extraction failed for document %s", state["document_id"])
        return {
            "status": "ocr_failed",
            "error": str(e),
            "ocr_confidence": 0.0,
        }
