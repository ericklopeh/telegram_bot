"""document upload tracking fields

Revision ID: 20260426_000003
Revises: 20260422_000002
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_000003"
down_revision: Union[str, Sequence[str], None] = "20260422_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("upload_status", sa.String(length=32), nullable=False, server_default="PENDING_UPLOAD"),
    )
    op.add_column("documents", sa.Column("sharepoint_web_url", sa.String(length=1500), nullable=True))
    op.add_column("documents", sa.Column("upload_error", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("upload_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_documents_upload_status", "documents", ["upload_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_upload_status", table_name="documents")
    op.drop_column("documents", "upload_attempts")
    op.drop_column("documents", "upload_error")
    op.drop_column("documents", "sharepoint_web_url")
    op.drop_column("documents", "upload_status")
