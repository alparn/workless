"""Add bank_account table

Revision ID: 004
Revises: 003
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_number", sa.String(10), nullable=False),
        sa.Column("bank_name", sa.String(255), nullable=False),
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("client_id", "account_number", name="uq_client_account_number"),
        sa.UniqueConstraint("client_id", "iban", name="uq_client_iban"),
    )
    op.create_index("idx_bank_account_client", "bank_account", ["client_id"])
    op.create_index("idx_bank_account_iban", "bank_account", ["client_id", "iban"])


def downgrade() -> None:
    op.drop_index("idx_bank_account_iban", "bank_account")
    op.drop_index("idx_bank_account_client", "bank_account")
    op.drop_table("bank_account")
