import base64
import json
import logging
import uuid
from decimal import Decimal

import httpx
import litellm
from pydantic import BaseModel

from app.config import settings
from app.services import llm_service

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = Decimal("0.80")

MIME_TYPE_MAP = {
    "application/pdf": "document_url",
    "image/png": "image_url",
    "image/jpeg": "image_url",
}


class VatPosition(BaseModel):
    rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal


class LineItem(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal
    vat_rate: Decimal


class OcrResult(BaseModel):
    raw_text: str
    extraction: dict
    confidence: Decimal
    provider: str


_EXTRACTION_JSON_SCHEMA_INVOICE = """\
{
  "document_type": "invoice | credit_note | receipt | other",
  "invoice_number": "string or null",
  "document_date": "YYYY-MM-DD",
  "service_date": "YYYY-MM-DD or null",
  "vendor_name": "string",
  "vendor_address": "string or null",
  "vendor_tax_number": "string or null",
  "vendor_vat_id": "string or null (DE...)",
  "recipient_name": "string or null",
  "net_amount": "decimal number",
  "gross_amount": "decimal number",
  "vat_positions": [
    {"rate": "decimal", "net_amount": "decimal", "vat_amount": "decimal"}
  ],
  "line_items": [
    {"description": "string", "quantity": "decimal or null", "unit_price": "decimal or null", "total_price": "decimal", "vat_rate": "decimal"}
  ],
  "currency": "EUR",
  "payment_due_date": "YYYY-MM-DD or null",
  "iban": "string or null",
  "discount_percent": "decimal or null",
  "discount_days": "integer or null",
  "extraction_confidence": "float 0.0–1.0"
}\
"""

_EXTRACTION_JSON_SCHEMA_BANK = """\
{
  "document_type": "bank_statement",
  "bank_name": "string",
  "account_holder": "string or null",
  "iban": "string or null",
  "bic": "string or null",
  "statement_number": "string or null (Auszug Nr.)",
  "statement_date": "YYYY-MM-DD",
  "period_from": "YYYY-MM-DD or null",
  "period_to": "YYYY-MM-DD or null",
  "opening_balance": "decimal number or null",
  "closing_balance": "decimal number or null",
  "currency": "EUR",
  "transactions": [
    {
      "date": "YYYY-MM-DD (Buchungsdatum)",
      "value_date": "YYYY-MM-DD or null (Wertstellung)",
      "description": "string (Verwendungszweck / Buchungstext)",
      "counterparty": "string or null (Name des Zahlenden/Empfängers)",
      "amount": "decimal (positiv = Gutschrift/Haben, negativ = Belastung/Soll)",
      "transaction_type": "string or null (z.B. Überweisung, Lastschrift, Dauerauftrag, Kartenzahlung, Gebühr)"
    }
  ],
  "extraction_confidence": "float 0.0–1.0"
}\
"""

_EXTRACTION_PROMPT_INVOICE = f"""\
Du bist ein Experte für deutsche Buchhaltungsdokumente. Extrahiere alle relevanten Daten \
aus dem folgenden Dokumenttext und gib sie als JSON zurück.

Antworte NUR mit validem JSON, kein Markdown, keine Erklärungen.

JSON-Schema:
{_EXTRACTION_JSON_SCHEMA_INVOICE}

Regeln:
- Alle Geldbeträge als Dezimalzahlen (z.B. 119.00, nicht "119,00€")
- Datum im Format YYYY-MM-DD
- extraction_confidence: Wie sicher bist du, dass die Extraktion korrekt ist? (0.0–1.0)
- Wenn ein Feld nicht vorhanden ist, setze null
- vendor_name: Immer den vollständigen Firmennamen des Rechnungsstellers
- Bei mehreren MwSt-Sätzen: alle in vat_positions auflisten
"""

_EXTRACTION_PROMPT_BANK_HEADER = """\
Du bist ein Experte für deutsche Kontoauszüge. Extrahiere NUR die Kopfdaten \
(KEINE Transaktionen) aus dem folgenden Kontoauszugstext.

Antworte NUR mit validem JSON, kein Markdown, keine Erklärungen.

JSON-Schema:
{
  "document_type": "bank_statement",
  "bank_name": "string",
  "account_holder": "string or null",
  "iban": "string or null",
  "bic": "string or null",
  "statement_number": "string or null (Auszug Nr.)",
  "statement_date": "YYYY-MM-DD",
  "period_from": "YYYY-MM-DD or null",
  "period_to": "YYYY-MM-DD or null",
  "opening_balance": "decimal number or null",
  "closing_balance": "decimal number or null",
  "currency": "EUR",
  "total_pages": "integer — Anzahl der Seiten die Transaktionen enthalten",
  "extraction_confidence": "float 0.0–1.0"
}
"""

_EXTRACTION_PROMPT_BANK_TRANSACTIONS = """\
Du bist ein Experte für deutsche Kontoauszüge. Extrahiere ALLE Transaktionen \
aus dem folgenden Textabschnitt eines Kontoauszugs.

Antworte NUR mit validem JSON-Array, kein Markdown, keine Erklärungen.

JSON-Schema (Array von Objekten):
[
  {
    "date": "YYYY-MM-DD (Buchungsdatum)",
    "value_date": "YYYY-MM-DD or null (Wertstellung)",
    "description": "string (Verwendungszweck / Buchungstext)",
    "counterparty": "string or null (Name des Zahlenden/Empfängers)",
    "amount": "decimal (positiv = Gutschrift/Haben, negativ = Belastung/Soll)",
    "transaction_type": "string or null (Überweisung, Lastschrift, Dauerauftrag, Kartenzahlung, Gebühr)"
  }
]

Regeln:
- JEDE Transaktion im Text muss im Array erscheinen — keine auslassen
- Beträge als Dezimalzahlen: Gutschriften positiv, Belastungen negativ
- Datum im Format YYYY-MM-DD
- counterparty: Name des Zahlungspartners, wenn erkennbar
- description: Vollständiger Verwendungszweck / Buchungstext
- Wenn keine Transaktionen im Text sind, antworte mit []
"""

_EXTRACTION_PROMPT_BANK = f"""\
Du bist ein Experte für deutsche Kontoauszüge. Extrahiere ALLE Transaktionen \
aus dem folgenden Kontoauszugstext und gib sie als JSON zurück.

Antworte NUR mit validem JSON, kein Markdown, keine Erklärungen.

JSON-Schema:
{_EXTRACTION_JSON_SCHEMA_BANK}

Regeln:
- JEDE einzelne Transaktion auf dem Kontoauszug muss im transactions-Array erscheinen
- Beträge als Dezimalzahlen: Gutschriften positiv, Belastungen negativ
- Datum im Format YYYY-MM-DD
- counterparty: Name des Zahlungspartners, wenn erkennbar
- description: Vollständiger Verwendungszweck / Buchungstext
- transaction_type: Art der Transaktion (Überweisung, Lastschrift, Kartenzahlung, Gebühr, Zinsen, etc.)
- Anfangs- und Endsaldo auslesen falls vorhanden
"""


def _detect_document_type_hint(raw_text: str) -> str:
    """Quick heuristic to detect bank statements before full extraction."""
    lower = raw_text.lower()
    bank_keywords = ["kontoauszug", "bank statement", "auszug nr", "auszugsnr",
                     "anfangssaldo", "endsaldo", "wertstellung", "valuta"]
    if any(kw in lower for kw in bank_keywords):
        return "bank_statement"
    return "invoice"


async def mistral_ocr(file_bytes: bytes, mime_type: str, client_id: str | None = None, db=None) -> OcrResult:
    """Call Mistral OCR API to extract text from a document."""
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    data_uri = f"data:{mime_type};base64,{b64_data}"

    if mime_type == "application/pdf":
        doc_type = "document_url"
    else:
        doc_type = "image_url"

    api_key = settings.mistral_api_key
    if client_id and db:
        resolved = await llm_service.resolve_api_key(uuid.UUID(client_id), db, "mistral")
        if resolved:
            api_key = resolved

    if not api_key:
        raise ValueError(
            "Kein Mistral API-Key konfiguriert. "
            "Bitte unter KI-Einstellungen einen Key hinterlegen oder MISTRAL_API_KEY in .env setzen."
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/ocr",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-ocr-latest",
                "document": {
                    "type": doc_type,
                    doc_type: data_uri,
                },
            },
        )
        response.raise_for_status()
        result = response.json()

    pages = result.get("pages", [])
    raw_text = "\n\n".join(page.get("markdown", "") for page in pages)

    if not raw_text.strip():
        return OcrResult(
            raw_text="",
            extraction={},
            confidence=Decimal("0.00"),
            provider="mistral",
        )

    doc_hint = _detect_document_type_hint(raw_text)
    extraction = await _extract_structured_data_with_claude(raw_text, doc_hint, client_id=client_id, db=db)
    confidence = Decimal(str(extraction.get("extraction_confidence", 0.0)))

    return OcrResult(
        raw_text=raw_text,
        extraction=extraction,
        confidence=confidence,
        provider="mistral",
    )


async def claude_vision_ocr(
    file_bytes: bytes, mime_type: str, doc_type_hint: str = "invoice",
    client_id: str | None = None, db=None,
) -> OcrResult:
    """Use Claude Vision as fallback for documents where Mistral OCR had low confidence."""
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    if mime_type == "application/pdf":
        content_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64_data,
            },
        }
    else:
        content_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": b64_data,
            },
        }

    if doc_type_hint == "bank_statement":
        text_prompt = (
            "Dies ist ein Kontoauszug. Extrahiere zuerst den Rohtext aus dem Dokument — "
            "lies JEDE Zeile, JEDE Transaktion. Gib dann das Ergebnis als JSON zurück.\n\n"
            f"{_EXTRACTION_PROMPT_BANK}\n\n"
            "Antworte NUR mit validem JSON."
        )
        max_tokens = 16384
    else:
        text_prompt = (
            f"{_EXTRACTION_PROMPT_INVOICE}\n\n"
            "Analysiere das Dokument und extrahiere alle Daten.\n\n"
            "WICHTIG: Prüfe zuerst, ob es sich um einen Kontoauszug handelt. "
            "Wenn ja, verwende dieses Schema stattdessen:\n"
            f"{_EXTRACTION_JSON_SCHEMA_BANK}\n\n"
            "Antworte NUR mit validem JSON."
        )
        max_tokens = 8192

    if client_id and db:
        response = await llm_service.completion(
            uuid.UUID(client_id), db,
            operation="ocr",
            messages=[{
                "role": "user",
                "content": [content_block, {"type": "text", "text": text_prompt}],
            }],
            max_tokens=max_tokens,
        )
        response_text = response.choices[0].message.content
    else:
        from anthropic import AsyncAnthropic
        anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [content_block, {"type": "text", "text": text_prompt}],
            }],
        )
        response_text = message.content[0].text
    extraction = _parse_json_response(response_text)
    if isinstance(extraction, list):
        extraction = {"document_type": "bank_statement", "transactions": extraction, "extraction_confidence": 0.8}
    confidence = Decimal(str(extraction.get("extraction_confidence", 0.85)))

    return OcrResult(
        raw_text=response_text,
        extraction=extraction,
        confidence=confidence,
        provider="claude_vision",
    )


async def _extract_structured_data_with_claude(
    raw_text: str, doc_type_hint: str = "invoice",
    client_id: str | None = None, db=None,
) -> dict:
    """Use Claude to structure raw OCR text into the extraction schema."""
    if doc_type_hint == "bank_statement":
        return await _extract_bank_statement_two_pass(raw_text, client_id=client_id, db=db)
    return await _extract_single_document(raw_text, _EXTRACTION_PROMPT_INVOICE, client_id=client_id, db=db)


async def _extract_single_document(
    raw_text: str, prompt: str,
    client_id: str | None = None, db=None,
) -> dict:
    """Single-pass extraction for invoices and other simple documents."""
    if client_id and db:
        response = await llm_service.completion(
            uuid.UUID(client_id), db,
            operation="ocr",
            messages=[{"role": "user", "content": f"{prompt}\n\nDokumenttext:\n\n{raw_text}"}],
            max_tokens=8192,
        )
        return _parse_json_response(response.choices[0].message.content)

    from anthropic import AsyncAnthropic
    anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": f"{prompt}\n\nDokumenttext:\n\n{raw_text}"}],
    )
    return _parse_json_response(message.content[0].text)


async def _extract_bank_statement_two_pass(raw_text: str, client_id: str | None = None, db=None) -> dict:
    """Two-pass extraction for bank statements: header first, then transactions per page.

    This is more reliable than extracting everything in one giant JSON because:
    1. Smaller, focused prompts produce better results
    2. Page-by-page extraction doesn't hit token limits
    3. Each extraction can be validated independently
    """
    async def _call_llm(prompt_text: str, max_tok: int) -> str:
        if client_id and db:
            resp = await llm_service.completion(
                uuid.UUID(client_id), db,
                operation="ocr",
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=max_tok,
            )
            return resp.choices[0].message.content
        from anthropic import AsyncAnthropic
        anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tok,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return msg.content[0].text

    logger.info("Bank statement extraction — pass 1: header")
    header_text = await _call_llm(
        f"{_EXTRACTION_PROMPT_BANK_HEADER}\n\nKontoauszugstext:\n\n{raw_text[:4000]}",
        2048,
    )
    header = _parse_json_response(header_text)
    logger.info(
        "Bank statement header: %s / %s / %s",
        header.get("bank_name"), header.get("iban"), header.get("statement_number"),
    )

    # --- Pass 2: Extract transactions in chunks ---
    pages = _split_into_chunks(raw_text, max_chars=6000)
    logger.info("Bank statement extraction — pass 2: %d chunk(s)", len(pages))

    all_transactions: list[dict] = []
    for i, chunk in enumerate(pages):
        tx_text = await _call_llm(
            f"{_EXTRACTION_PROMPT_BANK_TRANSACTIONS}\n\nTextabschnitt {i + 1}/{len(pages)}:\n\n{chunk}",
            8192,
        )
        parsed = _parse_json_response(tx_text)

        if isinstance(parsed, list):
            all_transactions.extend(parsed)
        elif isinstance(parsed, dict) and "transactions" in parsed:
            all_transactions.extend(parsed["transactions"])
        elif isinstance(parsed, dict) and not parsed.get("error"):
            all_transactions.append(parsed)

        logger.info("Chunk %d/%d: %d transactions extracted", i + 1, len(pages), len(all_transactions))

    # --- Deduplicate transactions (same date + amount + counterparty) ---
    all_transactions = _deduplicate_transactions(all_transactions)

    # --- Combine header + transactions ---
    result = {
        "document_type": "bank_statement",
        "bank_name": header.get("bank_name", ""),
        "account_holder": header.get("account_holder"),
        "iban": header.get("iban"),
        "bic": header.get("bic"),
        "statement_number": header.get("statement_number"),
        "statement_date": header.get("statement_date", ""),
        "period_from": header.get("period_from"),
        "period_to": header.get("period_to"),
        "opening_balance": header.get("opening_balance"),
        "closing_balance": header.get("closing_balance"),
        "currency": header.get("currency", "EUR"),
        "transactions": all_transactions,
        "extraction_confidence": min(
            float(header.get("extraction_confidence", 0.8)),
            0.95 if all_transactions else 0.3,
        ),
    }

    logger.info(
        "Bank statement extraction complete: %d transactions, confidence %.2f",
        len(all_transactions), result["extraction_confidence"],
    )
    return result


def _split_into_chunks(text: str, max_chars: int = 6000) -> list[str]:
    """Split text into chunks, preferring page breaks (double newline)."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 3:
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars // 3:
            split_at = max_chars

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()

    return [c for c in chunks if c.strip()]


def _deduplicate_transactions(transactions: list[dict]) -> list[dict]:
    """Remove duplicate transactions that may appear across chunk boundaries."""
    seen: set[str] = set()
    unique: list[dict] = []

    for tx in transactions:
        key = f"{tx.get('date')}|{tx.get('amount')}|{tx.get('counterparty', '')}|{tx.get('description', '')[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(tx)

    if len(unique) < len(transactions):
        logger.info("Deduplicated %d → %d transactions", len(transactions), len(unique))

    return unique


def _sanitize_json_string(text: str) -> str:
    """Escape unescaped control characters inside JSON string values."""
    result = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in ('\n', '\r', '\t'):
            result.append({'\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
            continue
        result.append(ch)
    return ''.join(result)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()
            stripped = stripped[:-3]
    return stripped.strip()


def _parse_json_response(text: str) -> dict | list:
    """Parse a JSON response, handling potential markdown fencing.

    Returns a dict or list depending on the JSON content.
    """
    cleaned = _strip_markdown_fences(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(_sanitize_json_string(cleaned))
    except json.JSONDecodeError:
        pass

    # Last resort: try to find JSON within the text
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue

    logger.error("Failed to parse JSON from LLM response: %s", text[:500])
    return {
        "extraction_confidence": 0.0,
        "error": "Failed to parse extraction response",
    }
