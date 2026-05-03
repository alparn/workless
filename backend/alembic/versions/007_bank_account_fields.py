"""Add currency and account_type to bank_account

Revision ID: 007
Revises: 006
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bank_account",
        sa.Column("currency", sa.String(3), server_default=sa.text("'EUR'"), nullable=False),
    )
    op.add_column(
        "bank_account",
        sa.Column("account_type", sa.String(30), server_default=sa.text("'checking'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bank_account", "account_type")
    op.drop_column("bank_account", "currency")
