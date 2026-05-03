from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class ClarificationItem(BaseModel):
    booking_id: UUID
    document_id: UUID
    document_filename: str
    amount: Decimal
    debit_credit: str
    document_date: date
    booking_text: str | None
    clarification_category: str
    clarification_question: str
    clarification_answer: str | None = None
    clarification_resolved: bool = False
    clarification_resolved_at: datetime | None = None
    clarification_resolved_by: str | None = None

    model_config = {"from_attributes": True}


class ClarificationResolveRequest(BaseModel):
    answer: str


class DocumentClarificationGroup(BaseModel):
    document_id: UUID
    document_filename: str
    uploaded_at: datetime
    open_count: int
    resolved_count: int
    items: list[ClarificationItem]


class EmailDraft(BaseModel):
    subject: str
    body_text: str


class ClarificationListResponse(BaseModel):
    client_id: UUID
    company_name: str
    total_count: int
    open_count: int
    resolved_count: int
    groups: list[DocumentClarificationGroup]
    email_draft: EmailDraft
