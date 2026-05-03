import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.state import DocumentProcessingState
from app.models.client import Client
from app.services import llm_service
from app.services.skills import load_skill

logger = logging.getLogger(__name__)


async def classify_document(state: DocumentProcessingState, db=None) -> dict:
    """Node 3: Classify the document type using Claude with document_types skill."""
    if state.get("status") == "ocr_failed":
        return {}

    logger.info("Classifying document %s", state["document_id"])

    document_types_skill = load_skill("document_types.md")
    extraction = state.get("extraction") or {}
    client_id = state["client_id"]

    client_context = await _build_client_context(db, client_id) if db else ""

    user_content = (
        f"{document_types_skill}\n\n"
        "---\n\n"
        f"{client_context}"
        "Analysiere die folgenden extrahierten Dokumentdaten und klassifiziere "
        "den Dokumenttyp. Antworte NUR mit validem JSON:\n"
        '{"document_type": "invoice|outgoing_invoice|credit_note|receipt|bank_statement|other", '
        '"classification_confidence": 0.0-1.0, '
        '"reasoning": "Kurze Begründung"}\n\n'
        "WICHTIG: Prüfe ob der Rechnungssteller (vendor_name) mit dem Mandanten "
        "übereinstimmt. Wenn ja → outgoing_invoice (Ausgangsrechnung/Einnahme). "
        "Vergleiche auch vendor_tax_number und vendor_vat_id mit den Mandanten-Stammdaten.\n\n"
        f"Extrahierte Daten:\n{json.dumps(extraction, default=str, indent=2)}"
    )

    if db:
        response = await llm_service.completion(
            uuid.UUID(client_id), db,
            operation="classify",
            messages=[{"role": "user", "content": user_content}],
            max_tokens=1024,
        )
        response_text = response.choices[0].message.content
    else:
        from anthropic import AsyncAnthropic
        from app.config import settings
        anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": user_content}],
        )
        response_text = message.content[0].text
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        classification = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse classification response: %s", response_text[:300])
        classification = {
            "document_type": extraction.get("document_type", "other"),
            "classification_confidence": 0.5,
            "reasoning": "Fallback: Could not parse classification response",
        }

    updated_extraction = {**extraction}
    if classification.get("document_type"):
        updated_extraction["document_type"] = classification["document_type"]

    return {
        "extraction": updated_extraction,
        "status": "classified",
    }


async def _build_client_context(db: AsyncSession, client_id: str) -> str:
    """Build a context string with client master data for classification."""
    try:
        client = await db.get(Client, uuid.UUID(client_id))
    except Exception:
        logger.warning("Could not load client %s for classification context", client_id)
        return ""

    if not client:
        return ""

    parts = [f"Mandantenname: {client.company_name}"]
    if client.legal_form:
        parts.append(f"Rechtsform: {client.legal_form}")
    if client.tax_number:
        parts.append(f"Steuernummer: {client.tax_number}")
    if client.vat_id:
        parts.append(f"USt-IdNr.: {client.vat_id}")

    return "## Mandanten-Stammdaten\n" + "\n".join(parts) + "\n\n---\n\n"
