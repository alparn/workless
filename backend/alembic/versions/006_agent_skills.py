"""Create agent_skill table

Revision ID: 006
Revises: 005
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_skill",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_key", sa.String(100), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), server_default=sa.text("0.50"), nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_unique_constraint("uq_agent_skill_client_key", "agent_skill", ["client_id", "skill_key"])
    op.create_index("idx_agent_skill_client", "agent_skill", ["client_id"])
    op.create_index("idx_agent_skill_category", "agent_skill", ["client_id", "category"])
    op.create_index(
        "idx_agent_skill_active",
        "agent_skill",
        ["client_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_skill_active", "agent_skill")
    op.drop_index("idx_agent_skill_category", "agent_skill")
    op.drop_index("idx_agent_skill_client", "agent_skill")
    op.drop_constraint("uq_agent_skill_client_key", "agent_skill", type_="unique")
    op.drop_table("agent_skill")
