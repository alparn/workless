import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    original_filename: str
    storage_path: str
    mime_type: str
    file_size_bytes: int | None

    ocr_provider: str | None
    ocr_confidence: Decimal | None
    extraction: dict | None

    status: str
    error_details: str | None

    uploaded_at: datetime
    ocr_completed_at: datetime | None
    approved_at: datetime | None


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int | None
    status: str
    uploaded_at: datetime
    ocr_completed_at: datetime | None
    approved_at: datetime | None
