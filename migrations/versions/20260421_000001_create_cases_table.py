"""create cases table

Revision ID: 20260421_000001
Revises:
Create Date: 2026-04-21 00:00:01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260421_000001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("temp_folio", sa.String(length=64), nullable=True),
        sa.Column("official_folio", sa.String(length=64), nullable=True),
        sa.Column("current_status", sa.String(length=64), nullable=False),
        sa.Column("visible_status", sa.String(length=64), nullable=False),
        sa.Column("seller_name", sa.String(length=255), nullable=True),
        sa.Column("week_code", sa.String(length=32), nullable=False),
        sa.Column("folder_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("temp_folio", name="uq_cases_temp_folio"),
        sa.UniqueConstraint("official_folio", name="uq_cases_official_folio"),
    )
    op.create_index("ix_cases_case_type", "cases", ["case_type"])
    op.create_index("ix_cases_client_name", "cases", ["client_name"])
    op.create_index("ix_cases_current_status", "cases", ["current_status"])
    op.create_index("ix_cases_visible_status", "cases", ["visible_status"])


def downgrade() -> None:
    op.drop_index("ix_cases_visible_status", table_name="cases")
    op.drop_index("ix_cases_current_status", table_name="cases")
    op.drop_index("ix_cases_client_name", table_name="cases")
    op.drop_index("ix_cases_case_type", table_name="cases")
    op.drop_table("cases")
