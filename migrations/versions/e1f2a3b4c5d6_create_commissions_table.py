"""P21: tabla commissions

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sale_capture_id", sa.Integer(), nullable=False),
        sa.Column("seller_name", sa.String(length=255), nullable=False),
        sa.Column("vendor_code", sa.String(length=64), nullable=True),
        sa.Column("qna", sa.String(length=32), nullable=True),
        sa.Column("week", sa.String(length=32), nullable=True),
        sa.Column("sale_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("commission_percentage", sa.Numeric(6, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "payment_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["sale_capture_id"], ["sale_captures.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_capture_id"),
    )
    op.create_index("ix_commissions_seller_name", "commissions", ["seller_name"])
    op.create_index("ix_commissions_qna", "commissions", ["qna"])
    op.create_index("ix_commissions_week", "commissions", ["week"])
    op.create_index("ix_commissions_payment_status", "commissions", ["payment_status"])


def downgrade() -> None:
    op.drop_index("ix_commissions_payment_status", table_name="commissions")
    op.drop_index("ix_commissions_week", table_name="commissions")
    op.drop_index("ix_commissions_qna", table_name="commissions")
    op.drop_index("ix_commissions_seller_name", table_name="commissions")
    op.drop_table("commissions")
