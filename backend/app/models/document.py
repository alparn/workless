import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)

    ocr_provider: Mapped[str | None] = mapped_column(String(50))
    ocr_raw_result: Mapped[dict | None] = mapped_column(JSONB)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    error_details: Mapped[str | None] = mapped_column(Text)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ocr_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client = relationship("Client", back_populates="documents")
    bookings = relationship("Booking", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_document_client", "client_id"),
        Index("idx_document_status", "status"),
    )
