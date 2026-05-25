"""P27: tablas ERP histórico + contratos consolidados

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i5j6k7l8m9n0"
down_revision: Union[str, Sequence[str], None] = "h4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers_customer",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rfc", sa.String(length=32), nullable=True),
        sa.Column("curp", sa.String(length=32), nullable=True),
        sa.Column("seccion", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_customer_name", "customers_customer", ["name"])
    op.create_index("ix_customers_customer_rfc", "customers_customer", ["rfc"])
    op.create_index("ix_customers_customer_curp", "customers_customer", ["curp"])

    op.create_table(
        "sales_sale",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=64), nullable=True),
        sa.Column("contract_code", sa.String(length=64), nullable=True),
        sa.Column("vendedor", sa.String(length=255), nullable=True),
        sa.Column("seccion", sa.String(length=128), nullable=True),
        sa.Column("sale_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers_customer.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_sale_customer_id", "sales_sale", ["customer_id"])
    op.create_index("ix_sales_sale_folio", "sales_sale", ["folio"])
    op.create_index("ix_sales_sale_contract_code", "sales_sale", ["contract_code"])

    op.create_table(
        "sales_saleitem",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales_sale.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_saleitem_sale_id", "sales_saleitem", ["sale_id"])

    op.create_table(
        "payments_installment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales_sale.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_installment_sale_id", "payments_installment", ["sale_id"])

    op.create_table(
        "payments_payment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("installment_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("payment_method", sa.String(length=64), nullable=True),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales_sale.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installment_id"], ["payments_installment.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_payment_sale_id", "payments_payment", ["sale_id"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sales_sale_id", sa.Integer(), nullable=True),
        sa.Column("sale_capture_id", sa.Integer(), nullable=True),
        sa.Column("case_id", sa.Integer(), nullable=True),
        sa.Column("contract_code", sa.String(length=64), nullable=True),
        sa.Column("folio", sa.String(length=64), nullable=True),
        sa.Column("original_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("current_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("refinanced_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active", index=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers_customer.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_sale_id"], ["sales_sale.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sale_capture_id"], ["sale_captures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sales_sale_id", name="uq_contracts_sales_sale_id"),
        sa.UniqueConstraint("sale_capture_id", name="uq_contracts_sale_capture_id"),
    )
    op.create_index("ix_contracts_customer_id", "contracts", ["customer_id"])
    op.create_index("ix_contracts_folio", "contracts", ["folio"])
    op.create_index("ix_contracts_contract_code", "contracts", ["contract_code"])

    op.create_table(
        "contract_installments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("payments_installment_id", sa.Integer(), nullable=True),
        sa.Column("installment_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payments_installment_id"], ["payments_installment.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contract_installments_contract_id", "contract_installments", ["contract_id"])

    op.create_table(
        "refinance_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("previous_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("refinanced_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("new_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refinance_operations_contract_id", "refinance_operations", ["contract_id"])


def downgrade() -> None:
    op.drop_table("refinance_operations")
    op.drop_table("contract_installments")
    op.drop_table("contracts")
    op.drop_table("payments_payment")
    op.drop_table("payments_installment")
    op.drop_table("sales_saleitem")
    op.drop_table("sales_sale")
    op.drop_table("customers_customer")
