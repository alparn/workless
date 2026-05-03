"""Document processing workflow built with LangGraph.

Node sequence:
  ocr_extract → [ocr_fallback] → classify / resolve_bank_account → suggest_booking → persist
"""

import logging
import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.nodes.classify import classify_document
from app.graph.nodes.ocr import ocr_extract
from app.graph.nodes.ocr_fallback import ocr_fallback
from app.graph.nodes.persist import persist_results
from app.graph.nodes.resolve_bank_account import resolve_bank_account
from app.graph.nodes.suggest_booking import suggest_booking
from app.graph.state import DocumentProcessingState
from app.models.client import Client
from app.models.document import Document
from app.services.ocr_service import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def _after_ocr(state: DocumentProcessingState) -> str:
    if state.get("status") == "ocr_failed":
        return "persist"
    if state.get("ocr_confidence", 0) < float(CONFIDENCE_THRESHOLD):
        return "ocr_fallback"
    return _route_by_doc_type(state)


def _after_fallback(state: DocumentProcessingState) -> str:
    return _route_by_doc_type(state)


def _route_by_doc_type(state: DocumentProcessingState) -> str:
    extraction = state.get("extraction") or {}
    if extraction.get("document_type") == "bank_statement":
        return "resolve_bank_account"
    return "classify"


# ---------------------------------------------------------------------------
# Graph wiring (single source of truth)
# ---------------------------------------------------------------------------

_ROUTING_AFTER_OCR = {
    "ocr_fallback": "ocr_fallback",
    "classify": "classify",
    "resolve_bank_account": "resolve_bank_account",
    "persist": "persist",
}

_ROUTING_AFTER_FALLBACK = {
    "classify": "classify",
    "resolve_bank_account": "resolve_bank_account",
}


def _build_graph(
    ocr_fn=ocr_extract,
    fallback_fn=ocr_fallback,
    classify_fn=classify_document,
    resolve_bank_fn=None,
    suggest_fn=None,
    persist_fn=None,
) -> StateGraph:
    """Wire the state graph once.  Callers inject db-bound closures."""
    graph = StateGraph(DocumentProcessingState)

    graph.add_node("ocr_extract", ocr_fn)
    graph.add_node("ocr_fallback", fallback_fn)
    graph.add_node("classify", classify_fn)
    graph.add_node("resolve_bank_account", resolve_bank_fn or _noop)
    graph.add_node("suggest_booking", suggest_fn or _noop)
    graph.add_node("persist", persist_fn or _noop)

    graph.set_entry_point("ocr_extract")
    graph.add_conditional_edges("ocr_extract", _after_ocr, _ROUTING_AFTER_OCR)
    graph.add_conditional_edges("ocr_fallback", _after_fallback, _ROUTING_AFTER_FALLBACK)
    graph.add_edge("classify", "suggest_booking")
    graph.add_edge("resolve_bank_account", "suggest_booking")
    graph.add_edge("suggest_booking", "persist")
    graph.add_edge("persist", END)

    return graph


async def _noop(state: DocumentProcessingState) -> dict:
    return {}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    """Return an un-compiled graph with placeholder nodes (for inspection / testing)."""
    return _build_graph()


async def run_document_workflow(
    document_id: uuid.UUID,
    db: AsyncSession,
) -> DocumentProcessingState:
    document = await db.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} not found")

    client = await db.get(Client, document.client_id)
    if client is None:
        raise ValueError(f"Client {document.client_id} not found")

    document.status = "ocr_processing"
    await db.flush()

    async def _ocr_with_db(state: DocumentProcessingState) -> dict:
        return await ocr_extract(state, db)

    async def _fallback_with_db(state: DocumentProcessingState) -> dict:
        return await ocr_fallback(state, db)

    async def _classify_with_db(state: DocumentProcessingState) -> dict:
        return await classify_document(state, db)

    async def _resolve_with_db(state: DocumentProcessingState) -> dict:
        return await resolve_bank_account(state, db)

    async def _suggest_with_db(state: DocumentProcessingState) -> dict:
        return await suggest_booking(state, db)

    async def _persist_with_db(state: DocumentProcessingState) -> dict:
        return await persist_results(state, db)

    graph = _build_graph(
        ocr_fn=_ocr_with_db,
        fallback_fn=_fallback_with_db,
        classify_fn=_classify_with_db,
        resolve_bank_fn=_resolve_with_db,
        suggest_fn=_suggest_with_db,
        persist_fn=_persist_with_db,
    )
    compiled = graph.compile()

    initial_state: DocumentProcessingState = {
        "document_id": str(document_id),
        "client_id": str(document.client_id),
        "file_path": document.storage_path,
        "mime_type": document.mime_type,
        "ocr_result": None,
        "ocr_provider": None,
        "ocr_confidence": 0.0,
        "extraction": None,
        "resolved_bank_account": None,
        "resolved_bank_name": None,
        "bank_iban_matched": False,
        "bank_match_method": None,
        "bank_match_confidence": 0.0,
        "bank_needs_review": False,
        "bank_alternative_accounts": [],
        "bank_resolution_reasoning": None,
        "suggested_bookings": [],
        "booking_confidence": 0.0,
        "booking_reasoning": "",
        "past_bookings": [],
        "chart_of_accounts": client.chart_of_accounts or "SKR03",
        "industry": client.industry,
        "industry_detail": client.industry_detail,
        "status": "ocr_processing",
        "error": None,
    }

    logger.info("Starting document workflow for %s", document_id)
    final_state = await compiled.ainvoke(initial_state)
    logger.info(
        "Document workflow completed for %s — status: %s",
        document_id, final_state.get("status"),
    )
    return final_state
