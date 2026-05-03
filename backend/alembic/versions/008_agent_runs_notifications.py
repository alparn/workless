"""Create agent_run and agent_notification tables

Revision ID: 008
Revises: 007
Create Date: 2026-04-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_type", sa.String(50), nullable=False),
        sa.Column("target_entity_type", sa.String(50), nullable=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), server_default="running", nullable=False),
        sa.Column("strategy", sa.String(100), nullable=True),
        sa.Column("attempt_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("items_checked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_fixed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_flagged", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("idx_agent_run_client", "agent_run", ["client_id"])
    op.create_index("idx_agent_run_type", "agent_run", ["run_type"])
    op.create_index("idx_agent_run_status", "agent_run", ["status"])
    op.create_index("idx_agent_run_started", "agent_run", ["started_at"])

    op.create_table(
        "agent_notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", sa.String(20), server_default="info", nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=True),
        sa.Column("action_data", postgresql.JSONB(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_notification_client", "agent_notification", ["client_id"])
    op.create_index(
        "idx_notification_unread", "agent_notification", ["client_id", "is_read"],
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_index("idx_notification_severity", "agent_notification", ["severity"])
    op.create_index("idx_notification_created", "agent_notification", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_notification_created", "agent_notification")
    op.drop_index("idx_notification_severity", "agent_notification")
    op.drop_index("idx_notification_unread", "agent_notification")
    op.drop_index("idx_notification_client", "agent_notification")
    op.drop_table("agent_notification")

    op.drop_index("idx_agent_run_started", "agent_run")
    op.drop_index("idx_agent_run_status", "agent_run")
    op.drop_index("idx_agent_run_type", "agent_run")
    op.drop_index("idx_agent_run_client", "agent_run")
    op.drop_table("agent_run")
