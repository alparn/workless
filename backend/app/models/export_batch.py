import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExportBatch(Base):
    __tablename__ = "export_batch"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client.id"), nullable=False
    )

    consultant_number: Mapped[int] = mapped_column(Integer, nullable=False)
    client_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_year_start: Mapped[date] = mapped_column(Date, nullable=False)
    chart_of_accounts: Mapped[str] = mapped_column(String(10), nullable=False)
    account_length: Mapped[int] = mapped_column(Integer, nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))

    storage_path: Mapped[str | None] = mapped_column(String(500))
    booking_count: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client = relationship("Client", back_populates="export_batches")
    bookings = relationship("Booking", back_populates="export_batch")

    __table_args__ = (
        Index("idx_export_batch_client", "client_id"),
    )
