from typing import TypedDict


class DocumentProcessingState(TypedDict):
    document_id: str
    client_id: str
    file_path: str
    mime_type: str

    ocr_result: dict | None
    ocr_provider: str | None
    ocr_confidence: float

    extraction: dict | None

    resolved_bank_account: str | None
    resolved_bank_name: str | None
    bank_iban_matched: bool
    bank_match_method: str | None
    bank_match_confidence: float
    bank_needs_review: bool
    bank_alternative_accounts: list[dict]
    bank_resolution_reasoning: str | None

    suggested_bookings: list[dict]
    booking_confidence: float
    booking_reasoning: str

    past_bookings: list[dict]

    chart_of_accounts: str
    industry: str | None
    industry_detail: str | None

    status: str
    error: str | None
