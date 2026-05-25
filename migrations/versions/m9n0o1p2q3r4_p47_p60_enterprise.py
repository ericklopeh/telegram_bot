"""P47-P60: enterprise avanzado (realtime, comments, rules, SaaS, compliance).

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "m9n0o1p2q3r4"
down_revision: Union[str, Sequence[str], None] = "l8m9n0o1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(length=32), server_default="case", nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_label", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions_json", JSONB, nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_comments_case_id", "case_comments", ["case_id"])

    op.create_table(
        "comment_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comment_id", sa.Integer(), sa.ForeignKey("case_comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "operational_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(length=32), server_default="followup", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False, index=True),
        sa.Column("priority", sa.String(length=16), server_default="normal", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_label", sa.String(length=128), nullable=True),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "task_reminders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("operational_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("channel", sa.String(length=32), server_default="internal", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dynamic_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("trigger_event", sa.String(length=64), nullable=False, index=True),
        sa.Column("conditions_json", JSONB, nullable=False),
        sa.Column("actions_json", JSONB, nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dynamic_rules_rule_key", "dynamic_rules", ["rule_key"], unique=True)

    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("definition_json", JSONB, nullable=False),
        sa.Column("shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "digital_signatures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=False, index=True),
        sa.Column("signer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signer_label", sa.String(length=255), nullable=False),
        sa.Column("signer_role", sa.String(length=64), nullable=True),
        sa.Column("signature_hash", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="signed", nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "signed_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signature_id", sa.Integer(), sa.ForeignKey("digital_signatures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_path", sa.String(length=1000), nullable=False),
        sa.Column("document_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dynamic_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("template_type", sa.String(length=32), nullable=False),
        sa.Column("active_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dynamic_templates_key", "dynamic_templates", ["template_key"], unique=True)

    op.create_table(
        "template_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("dynamic_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variables_json", JSONB, nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("attachment_type", sa.String(length=32), server_default="file", nullable=False),
        sa.Column("uploaded_by", sa.String(length=128), nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "attachment_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=False, index=True),
        sa.Column("relation_role", sa.String(length=32), server_default="evidence", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_label", sa.String(length=128), nullable=True),
        sa.Column("before_json", JSONB, nullable=True),
        sa.Column("after_json", JSONB, nullable=True),
        sa.Column("immutable_hash", sa.String(length=128), nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "compliance_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("severity", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "daily_metrics_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("domain", sa.String(length=32), nullable=False, index=True),
        sa.Column("metrics_json", JSONB, nullable=False),
        sa.Column("company_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_daily_metrics_date_domain_co",
        "daily_metrics_snapshots",
        ["snapshot_date", "domain", "company_id"],
        unique=True,
    )

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flag_key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("environment", sa.String(length=32), server_default="all", nullable=False),
        sa.Column("config_json", JSONB, nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feature_flags_key_env", "feature_flags", ["flag_key", "environment"], unique=True)

    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("branding_json", JSONB, nullable=True),
        sa.Column("limits_json", JSONB, nullable=True),
        sa.Column("config_json", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tenant_storage_paths",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path_key", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_storage_co_key", "tenant_storage_paths", ["company_id", "path_key"], unique=True)

    op.execute(
        """
        INSERT INTO tenant_settings (company_id, slug, display_name, branding_json, limits_json)
        SELECT id, code, name, branding_json, '{"max_users": 500, "max_storage_gb": 100}'::jsonb
        FROM companies WHERE code = 'default'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    for t in (
        "tenant_storage_paths",
        "tenant_settings",
        "feature_flags",
        "daily_metrics_snapshots",
        "compliance_events",
        "audit_entries",
        "attachment_relations",
        "attachments",
        "template_versions",
        "dynamic_templates",
        "signed_documents",
        "digital_signatures",
        "saved_reports",
        "dynamic_rules",
        "task_reminders",
        "operational_tasks",
        "comment_attachments",
        "case_comments",
    ):
        op.drop_table(t)
