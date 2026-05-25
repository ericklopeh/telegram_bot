"""P33: incidencias operativas y observabilidad

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "k7l8m9n0o1p2"
down_revision: Union[str, Sequence[str], None] = "j6k7l8m9n0o1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("incident_key", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, index=True),
        sa.Column("severity", sa.String(length=16), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN", index=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", JSONB, nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ops_incidents_incident_key", "ops_incidents", ["incident_key"], unique=True)


def downgrade() -> None:
    op.drop_table("ops_incidents")
