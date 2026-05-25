"""P36-P45: plataforma enterprise (jobs, activity, notificaciones, tenant, API tokens, índices).

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "l8m9n0o1p2q3"
down_revision: Union[str, Sequence[str], None] = "k7l8m9n0o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("branding_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_code", "companies", ["code"], unique=True)

    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_branches_company_code", "branches", ["company_id", "code"], unique=True)

    op.execute(
        "INSERT INTO companies (code, name, is_default) VALUES ('default', 'Empresa principal', true)"
    )
    op.execute(
        "INSERT INTO branches (company_id, code, name) SELECT id, 'main', 'Sucursal principal' FROM companies WHERE code = 'default'"
    )

    op.add_column("users", sa.Column("company_id", sa.Integer(), server_default="1", nullable=False))
    op.add_column("users", sa.Column("branch_id", sa.Integer(), server_default="1", nullable=False))
    op.create_index("ix_users_company_branch", "users", ["company_id", "branch_id"])

    op.add_column("cases", sa.Column("company_id", sa.Integer(), server_default="1", nullable=False))
    op.add_column("cases", sa.Column("branch_id", sa.Integer(), server_default="1", nullable=False))
    op.create_index("ix_cases_company_branch", "cases", ["company_id", "branch_id"])
    op.create_index("ix_cases_status_updated", "cases", ["current_status", "updated_at"])
    op.create_index("ix_cases_seller_updated", "cases", ["seller_name", "updated_at"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False, index=True),
        sa.Column("payload_json", JSONB, nullable=True),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_label", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="system", nullable=False),
        sa.Column("tone", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("href", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("config_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_prefs_user_channel_event",
        "notification_preferences",
        ["user_id", "channel", "event_type"],
        unique=True,
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("scopes", sa.String(length=512), server_default="read", nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), server_default="120", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_key", sa.String(length=128), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_label", sa.String(length=32), nullable=False),
        sa.Column("metrics_json", JSONB, nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("branch_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_snapshots_key_period",
        "analytics_snapshots",
        ["snapshot_key", "period_label", "company_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("analytics_snapshots")
    op.drop_table("api_tokens")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
    op.drop_table("activity_events")
    op.drop_table("background_jobs")
    op.drop_index("ix_cases_seller_updated", table_name="cases")
    op.drop_index("ix_cases_status_updated", table_name="cases")
    op.drop_index("ix_cases_company_branch", table_name="cases")
    op.drop_column("cases", "branch_id")
    op.drop_column("cases", "company_id")
    op.drop_index("ix_users_company_branch", table_name="users")
    op.drop_column("users", "branch_id")
    op.drop_column("users", "company_id")
    op.drop_table("branches")
    op.drop_table("companies")
