import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BankAccountCreate(BaseModel):
    account_number: str = Field(..., min_length=1, max_length=10)
    bank_name: str = Field(..., min_length=1, max_length=255)
    iban: str | None = Field(None, max_length=34, pattern=r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$")
    bic: str | None = Field(None, max_length=11)
    is_default: bool = False
    label: str | None = Field(None, max_length=255)


class BankAccountUpdate(BaseModel):
    account_number: str | None = Field(None, min_length=1, max_length=10)
    bank_name: str | None = Field(None, min_length=1, max_length=255)
    iban: str | None = Field(None, max_length=34, pattern=r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$")
    bic: str | None = Field(None, max_length=11)
    is_default: bool | None = None
    label: str | None = Field(None, max_length=255)


class BankAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    account_number: str
    bank_name: str
    iban: str | None
    bic: str | None
    is_default: bool
    label: str | None
    currency: str
    account_type: str
    created_at: datetime
    updated_at: datetime
