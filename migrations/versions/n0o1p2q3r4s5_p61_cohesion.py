"""P61 — cohesión plataforma (automations, rule logs, notifications inbox).

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "n0o1p2q3r4s5"
down_revision: Union[str, Sequence[str], None] = "m9n0o1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_flows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flow_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("conditions_json", JSONB, nullable=True),
        sa.Column("actions_json", JSONB, nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_flows_key", "automation_flows", ["flow_key"], unique=True)

    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flow_id", sa.Integer(), sa.ForeignKey("automation_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="completed", nullable=False),
        sa.Column("context_json", JSONB, nullable=True),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rule_execution_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=False, index=True),
        sa.Column("trigger_event", sa.String(length=64), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("context_json", JSONB, nullable=True),
        sa.Column("actions_applied", JSONB, nullable=True),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notification_inbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("tone", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("href", sa.String(length=512), nullable=True),
        sa.Column("read", sa.Boolean(), server_default=sa.text("false"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_activity_events_created", "activity_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activity_events_created", table_name="activity_events")
    op.drop_table("notification_inbox")
    op.drop_table("rule_execution_logs")
    op.drop_table("automation_executions")
    op.drop_table("automation_flows")
