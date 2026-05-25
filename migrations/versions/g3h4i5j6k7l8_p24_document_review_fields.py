"""P24: campos de revisión, OCR y versionado en documents

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("documents", sa.Column("uploaded_by", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("validated_by", sa.String(length=255), nullable=True))
    op.add_column(
        "documents",
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("documents", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "ocr_status",
            sa.String(length=32),
            nullable=False,
            server_default="OCR_PENDING",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ocr_extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("documents", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_review_status", "documents", ["review_status"])
    op.create_index("ix_documents_ocr_status", "documents", ["ocr_status"])
    op.execute(
        """
        UPDATE documents SET review_status = 'VALID'
        WHERE is_active = true AND review_status = 'PENDING_REVIEW'
        """
    )
    op.execute(
        """
        UPDATE documents SET review_status = 'REPLACED'
        WHERE is_active = false
        """
    )


def downgrade() -> None:
    op.drop_index("ix_documents_ocr_status", table_name="documents")
    op.drop_index("ix_documents_review_status", table_name="documents")
    for col in (
        "updated_at",
        "created_at",
        "ocr_confidence",
        "ocr_extracted_data",
        "ocr_status",
        "rejection_reason",
        "validated_at",
        "validated_by",
        "uploaded_by",
        "version",
        "review_status",
        "size_bytes",
    ):
        op.drop_column("documents", col)
