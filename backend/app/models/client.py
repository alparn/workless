import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Client(Base):
    __tablename__ = "client"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_form: Mapped[str | None] = mapped_column(String(50))
    tax_number: Mapped[str | None] = mapped_column(String(50))
    vat_id: Mapped[str | None] = mapped_column(String(20))
    tax_office: Mapped[str | None] = mapped_column(String(255))

    industry: Mapped[str | None] = mapped_column(String(50))
    industry_detail: Mapped[str | None] = mapped_column(Text)

    datev_consultant_number: Mapped[int | None] = mapped_column(Integer)
    datev_client_number: Mapped[int | None] = mapped_column(Integer)
    chart_of_accounts: Mapped[str] = mapped_column(String(10), default="SKR03")
    account_length: Mapped[int] = mapped_column(Integer, default=4)
    fiscal_year_start: Mapped[date] = mapped_column(Date, default=date(2026, 1, 1))

    default_vat_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("19.00"))
    auto_booking_threshold: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.85"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bank_accounts = relationship("BankAccount", back_populates="client", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="client", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="client")
    export_batches = relationship("ExportBatch", back_populates="client")
    vendor_booking_history = relationship("VendorBookingHistory", back_populates="client")
    agent_skills = relationship("AgentSkill", back_populates="client", cascade="all, delete-orphan")
