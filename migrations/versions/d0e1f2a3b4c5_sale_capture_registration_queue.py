"""P20: cola de registro formal en sale_captures

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sale_captures",
        sa.Column(
            "registration_status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        "sale_captures",
        sa.Column("registration_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "sale_captures",
        sa.Column(
            "registration_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "sale_captures",
        sa.Column("last_registration_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sale_captures_registration_status",
        "sale_captures",
        ["registration_status"],
    )
    # Sincronizar desde status legacy
    op.execute(
        """
        UPDATE sale_captures SET registration_status = status
        WHERE status IN ('draft', 'pending_validation', 'registered')
        """
    )
    op.execute(
        """
        UPDATE sale_captures SET registration_status = 'registration_failed'
        WHERE status = 'export_failed'
        """
    )
    op.execute(
        """
        UPDATE sale_captures SET registration_error = export_error
        WHERE export_error IS NOT NULL AND registration_error IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sale_captures_registration_status", table_name="sale_captures")
    op.drop_column("sale_captures", "last_registration_attempt_at")
    op.drop_column("sale_captures", "registration_attempts")
    op.drop_column("sale_captures", "registration_error")
    op.drop_column("sale_captures", "registration_status")
