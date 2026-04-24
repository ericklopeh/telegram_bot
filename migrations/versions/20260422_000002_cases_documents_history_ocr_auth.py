"""cases public_id seller chat history documents ocr auth jobs

Revision ID: 20260422_000002
Revises: 20260421_000001
Create Date: 2026-04-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260422_000002"
down_revision: Union[str, Sequence[str], None] = "20260421_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("public_id", sa.String(length=64), nullable=True))
    op.add_column("cases", sa.Column("seller_telegram_chat_id", sa.BigInteger(), nullable=True))
    op.execute("UPDATE cases SET public_id = 'LEGACY-' || id::text WHERE public_id IS NULL")
    op.alter_column("cases", "public_id", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint("uq_cases_public_id", "cases", ["public_id"])
    op.create_index("ix_cases_seller_telegram", "cases", ["seller_telegram_chat_id"])

    op.create_table(
        "case_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=64), nullable=True),
        sa.Column("new_status", sa.String(length=64), nullable=False),
        sa.Column("action_source", sa.String(length=32), server_default="telegram", nullable=False),
        sa.Column("action_user", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_history_case_id", "case_history", ["case_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("stored_filename", sa.String(length=500), nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("replaced_document_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])
    op.create_index("ix_documents_document_type", "documents", ["document_type"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_documents_active_case_type
        ON documents (case_id, document_type)
        WHERE is_active = true;
        """
    )

    op.create_table(
        "ocr_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("parsed_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_results_document_id", "ocr_results", ["document_id"])

    op.create_table(
        "authorization_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(length=255), nullable=True),
        sa.Column("output_path", sa.String(length=1000), nullable=True),
        sa.Column("generation_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authorization_jobs_case_id", "authorization_jobs", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_authorization_jobs_case_id", table_name="authorization_jobs")
    op.drop_table("authorization_jobs")

    op.drop_index("ix_ocr_results_document_id", table_name="ocr_results")
    op.drop_table("ocr_results")

    op.execute("DROP INDEX IF EXISTS uq_documents_active_case_type")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_case_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_case_history_case_id", table_name="case_history")
    op.drop_table("case_history")

    op.drop_index("ix_cases_seller_telegram", table_name="cases")
    op.drop_constraint("uq_cases_public_id", "cases", type_="unique")
    op.drop_column("cases", "seller_telegram_chat_id")
    op.drop_column("cases", "public_id")
