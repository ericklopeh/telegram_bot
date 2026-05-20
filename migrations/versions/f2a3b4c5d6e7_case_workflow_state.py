"""P22: workflow_state en cases

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("workflow_state", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_cases_workflow_state", "cases", ["workflow_state"])
    op.execute(
        """
        UPDATE cases SET workflow_state = 'PEDIDO_RECIBIDO'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'Recibido'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'PREP_AUTORIZACION'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'En preparación de autorización'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'SNTE_GENERADO'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'Autorización generada'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'EN_COMPULSA'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status IN ('En compulsa', 'Pendiente de compulsa')
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'APROBADO'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'Compulsa OK'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'CORRECCION'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'Corrección solicitada'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'RECHAZADO'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status = 'Rechazado'
        """
    )
    op.execute(
        """
        UPDATE cases SET workflow_state = 'CERRADO'
        WHERE case_type = 'pedido' AND workflow_state IS NULL
        AND current_status IN ('Cerrado', 'Compra realizada')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_cases_workflow_state", table_name="cases")
    op.drop_column("cases", "workflow_state")
