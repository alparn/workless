"""Add LLM config and usage tracking tables

Revision ID: 010
Revises: 009
Create Date: 2026-05-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_config",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("chat_provider", sa.String(30), server_default="anthropic", nullable=False),
        sa.Column("chat_model", sa.String(80), server_default="claude-sonnet-4-20250514", nullable=False),
        sa.Column("booking_provider", sa.String(30), server_default="anthropic", nullable=False),
        sa.Column("booking_model", sa.String(80), server_default="claude-sonnet-4-20250514", nullable=False),
        sa.Column("ocr_provider", sa.String(30), server_default="mistral", nullable=False),
        sa.Column("anthropic_api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("mistral_api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("openai_api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("tavily_api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("use_global_fallback", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("langsmith_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0"),
        sa.Column("output_tokens", sa.Integer(), server_default="0"),
        sa.Column("thinking_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("estimated_cost_eur", sa.Numeric(10, 6), server_default="0"),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_llm_usage_client", "llm_usage_log", ["client_id"])
    op.create_index("idx_llm_usage_client_time", "llm_usage_log", ["client_id", "created_at"])
    op.create_index("idx_llm_usage_operation", "llm_usage_log", ["operation"])


def downgrade() -> None:
    op.drop_index("idx_llm_usage_operation", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_client_time", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_client", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
    op.drop_table("llm_config")
