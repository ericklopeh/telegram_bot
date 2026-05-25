"""P32: importación histórica desde Excel

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "j6k7l8m9n0o1"
down_revision: Union[str, Sequence[str], None] = "i5j6k7l8m9n0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded", index=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_json", JSONB, nullable=True),
        sa.Column("audit_trail", JSONB, nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_username", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "import_row_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_row_errors_batch_id", "import_row_errors", ["batch_id"])

    op.create_table(
        "imported_sale_references",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("erp_sale_id", sa.Integer(), nullable=True),
        sa.Column("erp_customer_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("folio", sa.String(length=64), nullable=True, index=True),
        sa.Column("contract_code", sa.String(length=64), nullable=True),
        sa.Column("import_key", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["erp_customer_id"], ["customers_customer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["erp_sale_id"], ["sales_sale.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imported_sale_references_batch_id", "imported_sale_references", ["batch_id"])
    op.create_unique_constraint(
        "uq_imported_sale_ref_batch_key", "imported_sale_references", ["batch_id", "import_key"]
    )


def downgrade() -> None:
    op.drop_table("imported_sale_references")
    op.drop_table("import_row_errors")
    op.drop_table("import_batches")
