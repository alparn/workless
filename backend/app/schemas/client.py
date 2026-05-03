import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


INDUSTRY_CHOICES = [
    "gastro",
    "it_services",
    "handel",
    "handwerk",
    "immobilien",
    "beratung",
    "gesundheit",
    "logistik",
    "produktion",
    "landwirtschaft",
    "freiberufler",
    "sonstige",
]


class ClientCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    legal_form: str | None = Field(None, max_length=50)
    tax_number: str | None = Field(None, max_length=50)
    vat_id: str | None = Field(None, max_length=20)
    tax_office: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=50)
    industry_detail: str | None = None
    datev_consultant_number: int | None = None
    datev_client_number: int | None = None
    chart_of_accounts: str = Field("SKR03", pattern=r"^SKR0[34]$")
    account_length: int = Field(4, ge=4, le=8)
    fiscal_year_start: date = Field(default_factory=lambda: date(2026, 1, 1))
    default_vat_rate: Decimal = Field(Decimal("19.00"), ge=0, le=100)
    auto_booking_threshold: Decimal = Field(Decimal("0.85"), ge=0, le=1)


class ClientUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    legal_form: str | None = Field(None, max_length=50)
    tax_number: str | None = Field(None, max_length=50)
    vat_id: str | None = Field(None, max_length=20)
    tax_office: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=50)
    industry_detail: str | None = None
    datev_consultant_number: int | None = None
    datev_client_number: int | None = None
    chart_of_accounts: str | None = Field(None, pattern=r"^SKR0[34]$")
    account_length: int | None = Field(None, ge=4, le=8)
    fiscal_year_start: date | None = None
    default_vat_rate: Decimal | None = Field(None, ge=0, le=100)
    auto_booking_threshold: Decimal | None = Field(None, ge=0, le=1)


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    legal_form: str | None
    tax_number: str | None
    vat_id: str | None
    tax_office: str | None
    industry: str | None
    industry_detail: str | None
    datev_consultant_number: int | None
    datev_client_number: int | None
    chart_of_accounts: str
    account_length: int
    fiscal_year_start: date
    default_vat_rate: Decimal
    auto_booking_threshold: Decimal
    created_at: datetime
    updated_at: datetime
