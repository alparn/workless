import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ExportCreateRequest(BaseModel):
    client_id: uuid.UUID
    date_from: date
    date_to: date
    label: str | None = Field(None, max_length=255)


class ExportPreviewRequest(BaseModel):
    client_id: uuid.UUID
    date_from: date
    date_to: date


class ExportPreviewResponse(BaseModel):
    """booking_count / total_amount = freigegebene und korrigierte Buchungen (DATEV-exportierbar)."""

    booking_count: int
    date_from: date
    date_to: date
    total_amount: str
    pending_approval_count: int = 0
    exported_count: int = 0
    rejected_count: int = 0
    documents_with_bookings_count: int = 0


class ExportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    consultant_number: int
    client_number: int
    fiscal_year_start: date
    chart_of_accounts: str
    account_length: int
    date_from: date
    date_to: date
    label: str | None
    storage_path: str | None
    booking_count: int
    is_locked: bool
    created_at: datetime
    downloaded_at: datetime | None
