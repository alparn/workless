import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentRun(Base):
    """Protokoll für jeden autonomen Agent-Lauf."""
    __tablename__ = "agent_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client.id", ondelete="CASCADE"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_type: Mapped[str | None] = mapped_column(String(50))
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    status: Mapped[str] = mapped_column(String(30), default="running")
    strategy: Mapped[str | None] = mapped_column(String(100))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)

    result_summary: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    items_checked: Mapped[int] = mapped_column(Integer, default=0)
    items_fixed: Mapped[int] = mapped_column(Integer, default=0)
    items_flagged: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    client = relationship("Client")

    __table_args__ = (
        Index("idx_agent_run_client", "client_id"),
        Index("idx_agent_run_type", "run_type"),
        Index("idx_agent_run_status", "status"),
        Index("idx_agent_run_started", "started_at"),
    )
