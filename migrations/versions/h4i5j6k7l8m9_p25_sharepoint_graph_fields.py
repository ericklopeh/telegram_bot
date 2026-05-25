"""P25: campos SharePoint Graph en documents

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, Sequence[str], None] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sharepoint_drive_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("sharepoint_item_id", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("sharepoint_folder_path", sa.String(length=1500), nullable=True),
    )
    op.execute(
        """
        UPDATE documents SET upload_status = 'SHAREPOINT_OK'
        WHERE upload_status = 'UPLOADED'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE documents SET upload_status = 'UPLOADED'
        WHERE upload_status = 'SHAREPOINT_OK'
        """
    )
    op.drop_column("documents", "sharepoint_folder_path")
    op.drop_column("documents", "sharepoint_item_id")
    op.drop_column("documents", "sharepoint_drive_id")
