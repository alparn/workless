"""Initial schema — all 6 tables

Revision ID: 001
Revises:
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("legal_form", sa.String(50), nullable=True),
        sa.Column("tax_number", sa.String(50), nullable=True),
        sa.Column("vat_id", sa.String(20), nullable=True),
        sa.Column("tax_office", sa.String(255), nullable=True),
        sa.Column("datev_consultant_number", sa.Integer(), nullable=True),
        sa.Column("datev_client_number", sa.Integer(), nullable=True),
        sa.Column("chart_of_accounts", sa.String(10), server_default="SKR03", nullable=False),
        sa.Column("account_length", sa.Integer(), server_default="4", nullable=False),
        sa.Column("fiscal_year_start", sa.Date(), server_default="2026-01-01", nullable=False),
        sa.Column("default_vat_rate", sa.Numeric(4, 2), server_default="19.00", nullable=False),
        sa.Column("auto_booking_threshold", sa.Numeric(3, 2), server_default="0.85", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("ocr_provider", sa.String(50), nullable=True),
        sa.Column("ocr_raw_result", postgresql.JSONB(), nullable=True),
        sa.Column("extraction", postgresql.JSONB(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("status", sa.String(50), server_default="uploaded", nullable=False),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ocr_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_document_client", "document", ["client_id"])
    op.create_index("idx_document_status", "document", ["status"])

    op.create_table(
        "export_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consultant_number", sa.Integer(), nullable=False),
        sa.Column("client_number", sa.Integer(), nullable=False),
        sa.Column("fiscal_year_start", sa.Date(), nullable=False),
        sa.Column("chart_of_accounts", sa.String(10), nullable=False),
        sa.Column("account_length", sa.Integer(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("booking_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"]),
    )
    op.create_index("idx_export_batch_client", "export_batch", ["client_id"])

    op.create_table(
        "booking",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("debit_credit", sa.String(1), nullable=False),
        sa.Column("account", sa.String(10), nullable=False),
        sa.Column("contra_account", sa.String(10), nullable=False),
        sa.Column("bu_key", sa.String(4), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("reference_1", sa.String(36), nullable=True),
        sa.Column("reference_2", sa.String(12), nullable=True),
        sa.Column("booking_text", sa.String(60), nullable=True),
        sa.Column("cost_center_1", sa.String(36), nullable=True),
        sa.Column("cost_center_2", sa.String(36), nullable=True),
        sa.Column("suggested_by", sa.String(50), server_default="ai", nullable=False),
        sa.Column("ai_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), server_default="suggested", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"]),
        sa.ForeignKeyConstraint(["export_batch_id"], ["export_batch.id"]),
        sa.CheckConstraint("debit_credit IN ('S', 'H')", name="ck_booking_debit_credit"),
    )
    op.create_index("idx_booking_document", "booking", ["document_id"])
    op.create_index("idx_booking_client", "booking", ["client_id"])
    op.create_index("idx_booking_status", "booking", ["status"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("performed_by", sa.String(100), nullable=True),
        sa.Column("previous_state", postgresql.JSONB(), nullable=True),
        sa.Column("new_state", postgresql.JSONB(), nullable=True),
        sa.Column("ai_details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("idx_audit_time", "audit_log", [sa.text("created_at DESC")])

    op.create_table(
        "vendor_booking_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_name_normalized", sa.String(255), nullable=False),
        sa.Column("account", sa.String(10), nullable=False),
        sa.Column("contra_account", sa.String(10), nullable=False),
        sa.Column("bu_key", sa.String(4), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_booked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"]),
        sa.UniqueConstraint(
            "client_id", "vendor_name_normalized", "account", "contra_account",
            name="uq_vendor_booking_combo",
        ),
    )
    op.create_index("idx_vendor_history", "vendor_booking_history", ["client_id", "vendor_name_normalized"])


def downgrade() -> None:
    op.drop_table("vendor_booking_history")
    op.drop_table("audit_log")
    op.drop_table("booking")
    op.drop_table("export_batch")
    op.drop_table("document")
    op.drop_table("client")
