"""create_case_events_table

Revision ID: f1a2b3c4d5e6
Revises: e232f501bee0
Create Date: 2026-05-11 18:08:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "daf28a31f8c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="system",
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Índices: case_id, event_type, created_at
    op.create_index(
        op.f("ix_case_events_case_id"), "case_events", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_case_events_event_type"), "case_events", ["event_type"], unique=False
    )
    op.create_index(
        op.f("ix_case_events_created_at"), "case_events", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_case_events_actor_user_id"),
        "case_events",
        ["actor_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_case_events_actor_user_id"), table_name="case_events")
    op.drop_index(op.f("ix_case_events_created_at"), table_name="case_events")
    op.drop_index(op.f("ix_case_events_event_type"), table_name="case_events")
    op.drop_index(op.f("ix_case_events_case_id"), table_name="case_events")
    op.drop_table("case_events")
