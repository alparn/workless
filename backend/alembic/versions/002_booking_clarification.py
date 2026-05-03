"""Add clarification fields to booking table

Revision ID: 002
Revises: 001
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("booking", sa.Column("needs_clarification", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("booking", sa.Column("clarification_category", sa.String(50), nullable=True))
    op.add_column("booking", sa.Column("clarification_question", sa.Text(), nullable=True))
    op.create_index("idx_booking_clarification", "booking", ["needs_clarification"])


def downgrade() -> None:
    op.drop_index("idx_booking_clarification", "booking")
    op.drop_column("booking", "clarification_question")
    op.drop_column("booking", "clarification_category")
    op.drop_column("booking", "needs_clarification")
