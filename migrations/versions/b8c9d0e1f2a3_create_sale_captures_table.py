"""create_sale_captures_table (P19)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sale_captures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("folio", sa.String(length=32), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("vendedor", sa.String(length=255), nullable=False),
        sa.Column("seccion", sa.String(length=128), nullable=True),
        sa.Column("qna", sa.String(length=32), nullable=True),
        sa.Column("cliente", sa.String(length=255), nullable=False),
        sa.Column("rfc", sa.String(length=20), nullable=True),
        sa.Column("codigo", sa.String(length=64), nullable=True),
        sa.Column("producto", sa.Text(), nullable=True),
        sa.Column("tipo_venta", sa.String(length=64), nullable=True),
        sa.Column("plazo", sa.Integer(), nullable=True),
        sa.Column("costo", sa.Numeric(14, 2), nullable=True),
        sa.Column("venta", sa.Numeric(14, 2), nullable=True),
        sa.Column("venta_refinanciamiento", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_venta", sa.Numeric(14, 2), nullable=True),
        sa.Column("precio_comision", sa.Numeric(14, 2), nullable=True),
        sa.Column("venta_sin_agregado", sa.Numeric(14, 2), nullable=True),
        sa.Column("recuperacion", sa.Numeric(14, 2), nullable=True),
        sa.Column("tipo_cotizacion", sa.String(length=32), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("semana", sa.String(length=32), nullable=True),
        sa.Column("case_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("validated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("ventas_export_path", sa.String(length=500), nullable=True),
        sa.Column("contratos_export_path", sa.String(length=500), nullable=True),
        sa.Column("ventas_excel_row", sa.Integer(), nullable=True),
        sa.Column("contratos_excel_row", sa.Integer(), nullable=True),
        sa.Column("contratos_sheet", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["validated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folio"),
    )
    op.create_index("ix_sale_captures_status", "sale_captures", ["status"])
    op.create_index("ix_sale_captures_vendedor", "sale_captures", ["vendedor"])
    op.create_index("ix_sale_captures_cliente", "sale_captures", ["cliente"])
    op.create_index("ix_sale_captures_rfc", "sale_captures", ["rfc"])
    op.create_index("ix_sale_captures_case_id", "sale_captures", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_sale_captures_case_id", table_name="sale_captures")
    op.drop_index("ix_sale_captures_rfc", table_name="sale_captures")
    op.drop_index("ix_sale_captures_cliente", table_name="sale_captures")
    op.drop_index("ix_sale_captures_vendedor", table_name="sale_captures")
    op.drop_index("ix_sale_captures_status", table_name="sale_captures")
    op.drop_table("sale_captures")
