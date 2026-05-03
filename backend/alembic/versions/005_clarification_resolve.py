"""Add clarification resolve fields to booking

Revision ID: 005
Revises: 004
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("booking", sa.Column("clarification_answer", sa.Text(), nullable=True))
    op.add_column(
        "booking",
        sa.Column("clarification_resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("booking", sa.Column("clarification_resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("booking", sa.Column("clarification_resolved_by", sa.String(50), nullable=True))

    op.create_index(
        "idx_booking_clarification_open",
        "booking",
        ["client_id"],
        postgresql_where=sa.text("needs_clarification = true AND clarification_resolved = false"),
    )


def downgrade() -> None:
    op.drop_index("idx_booking_clarification_open", "booking")
    op.drop_column("booking", "clarification_resolved_by")
    op.drop_column("booking", "clarification_resolved_at")
    op.drop_column("booking", "clarification_resolved")
    op.drop_column("booking", "clarification_answer")
