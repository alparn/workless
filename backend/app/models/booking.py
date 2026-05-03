import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Booking(Base):
    __tablename__ = "booking"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client.id"), nullable=False
    )
    export_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("export_batch.id")
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    debit_credit: Mapped[str] = mapped_column(String(1), nullable=False)
    account: Mapped[str] = mapped_column(String(10), nullable=False)
    contra_account: Mapped[str] = mapped_column(String(10), nullable=False)
    bu_key: Mapped[str | None] = mapped_column(String(4))
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_1: Mapped[str | None] = mapped_column(String(36))
    reference_2: Mapped[str | None] = mapped_column(String(12))
    booking_text: Mapped[str | None] = mapped_column(String(60))
    cost_center_1: Mapped[str | None] = mapped_column(String(36))
    cost_center_2: Mapped[str | None] = mapped_column(String(36))

    suggested_by: Mapped[str] = mapped_column(String(50), default="ai")
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    ai_reasoning: Mapped[str | None] = mapped_column(Text)

    needs_clarification: Mapped[bool] = mapped_column(default=False)
    clarification_category: Mapped[str | None] = mapped_column(String(50))
    clarification_question: Mapped[str | None] = mapped_column(Text)
    clarification_answer: Mapped[str | None] = mapped_column(Text)
    clarification_resolved: Mapped[bool] = mapped_column(default=False)
    clarification_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clarification_resolved_by: Mapped[str | None] = mapped_column(String(50))

    tax_hints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="suggested")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document = relationship("Document", back_populates="bookings")
    client = relationship("Client", back_populates="bookings")
    export_batch = relationship("ExportBatch", back_populates="bookings")

    __table_args__ = (
        CheckConstraint("debit_credit IN ('S', 'H')", name="ck_booking_debit_credit"),
        Index("idx_booking_document", "document_id"),
        Index("idx_booking_client", "client_id"),
        Index("idx_booking_status", "status"),
    )
