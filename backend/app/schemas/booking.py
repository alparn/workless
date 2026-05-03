import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BookingUpdate(BaseModel):
    account: str | None = Field(None, max_length=10)
    contra_account: str | None = Field(None, max_length=10)
    bu_key: str | None = Field(None, max_length=4)
    booking_text: str | None = Field(None, max_length=60)
    amount: Decimal | None = Field(None, gt=0)
    debit_credit: str | None = Field(None, pattern=r"^[SH]$")
    cost_center_1: str | None = Field(None, max_length=36)
    cost_center_2: str | None = Field(None, max_length=36)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    client_id: uuid.UUID
    export_batch_id: uuid.UUID | None

    amount: Decimal
    debit_credit: str
    account: str
    contra_account: str
    bu_key: str | None
    document_date: date
    reference_1: str | None
    reference_2: str | None
    booking_text: str | None
    cost_center_1: str | None
    cost_center_2: str | None

    suggested_by: str
    ai_confidence: Decimal | None
    ai_reasoning: str | None

    status: str

    created_at: datetime
    approved_at: datetime | None
    exported_at: datetime | None

    bank_name: str | None = None
    bank_iban: str | None = None

    tax_hints: dict | None = None


class BookingWithDocumentResponse(BookingResponse):
    """Booking enriched with document extraction data for the review UI."""
    document_filename: str | None = None
    document_extraction: dict | None = None
    document_status: str | None = None


class BatchApproveRequest(BaseModel):
    booking_ids: list[uuid.UUID] = Field(..., min_length=1)


class BatchApproveResponse(BaseModel):
    approved_count: int
    booking_ids: list[uuid.UUID]
