import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VendorBookingHistory(Base):
    __tablename__ = "vendor_booking_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client.id"), nullable=False
    )
    vendor_name_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    account: Mapped[str] = mapped_column(String(10), nullable=False)
    contra_account: Mapped[str] = mapped_column(String(10), nullable=False)
    bu_key: Mapped[str | None] = mapped_column(String(4))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    last_booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client = relationship("Client", back_populates="vendor_booking_history")

    __table_args__ = (
        UniqueConstraint(
            "client_id", "vendor_name_normalized", "account", "contra_account",
            name="uq_vendor_booking_combo",
        ),
        Index("idx_vendor_history", "client_id", "vendor_name_normalized"),
    )
