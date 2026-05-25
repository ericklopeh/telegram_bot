"""P69 — índices de estabilización y performance.

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
"""

from typing import Sequence, Union

from alembic import op


revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, Sequence[str], None] = "n0o1p2q3r4s5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_activity_events_company_created",
        "activity_events",
        ["company_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_background_jobs_status_scheduled",
        "background_jobs",
        ["status", "scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_background_jobs_running_started",
        "background_jobs",
        ["status", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_running_started", table_name="background_jobs")
    op.drop_index("ix_background_jobs_status_scheduled", table_name="background_jobs")
    op.drop_index("ix_activity_events_company_created", table_name="activity_events")
