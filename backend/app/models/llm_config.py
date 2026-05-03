import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LlmConfig(Base):
    __tablename__ = "llm_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    chat_provider: Mapped[str] = mapped_column(String(30), default="anthropic")
    chat_model: Mapped[str] = mapped_column(String(80), default="claude-sonnet-4-20250514")
    booking_provider: Mapped[str] = mapped_column(String(30), default="anthropic")
    booking_model: Mapped[str] = mapped_column(String(80), default="claude-sonnet-4-20250514")
    ocr_provider: Mapped[str] = mapped_column(String(30), default="mistral")

    anthropic_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    mistral_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    openai_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    tavily_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)

    use_global_fallback: Mapped[bool] = mapped_column(Boolean, default=True)
    langsmith_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client = relationship("Client", backref="llm_config", uselist=False)
