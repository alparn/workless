import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardStats(BaseModel):
    document_count: int
    booking_count: int
    pending_reviews: int
    approved_bookings: int
    exported_bookings: int
    total_export_batches: int


class ActivityEntry(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    performed_by: str | None
    created_at: datetime
    summary: str


class MonthlyAmount(BaseModel):
    month: str
    expenses: Decimal
    revenue: Decimal


class AccountBreakdown(BaseModel):
    account: str
    label: str
    total: Decimal


class TopVendor(BaseModel):
    name: str
    total: Decimal
    count: int


class FinancialDashboard(BaseModel):
    monthly: list[MonthlyAmount]
    accounts: list[AccountBreakdown]
    vendors: list[TopVendor]
    total_expenses: Decimal
    total_revenue: Decimal
    period_from: str
    period_to: str
