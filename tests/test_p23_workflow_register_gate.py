"""P23: gates de workflow para SNTE y registro de venta."""

from decimal import Decimal

from app.domain import constants as C
from app.models.case import Case
from app.models.sale_capture import SaleCapture
from app.services.workflow_dependency_service import (
    WorkflowContext,
    can_action_generate_snte,
    can_action_register_sale,
)
from app.services.workflow_state_service import WF_APROBADO, WF_PREP_AUTORIZACION, WF_SHAREPOINT_OK
from app.services.workflow_transition_service import is_transition_allowed


def _case(**kwargs) -> Case:
    c = Case(
        id=1,
        public_id="PED-001",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Test",
        current_status=C.ST_PED_PREP_AUT,
        workflow_state=WF_PREP_AUTORIZACION,
        visible_status="En pedido",
        week_code="S1",
        folder_path="/tmp",
    )
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_snte_transition_blocked_before_aprobado():
    assert not is_transition_allowed(WF_PREP_AUTORIZACION, "SNTE_PENDIENTE")
    assert not is_transition_allowed(WF_PREP_AUTORIZACION, "SNTE_GENERADO")


def test_snte_transition_allowed_from_aprobado():
    assert is_transition_allowed(WF_APROBADO, "SNTE_PENDIENTE")


def test_register_sale_blocked_without_sharepoint():
    ctx = WorkflowContext(case=_case(workflow_state=WF_APROBADO), sharepoint_ok=False)
    ok, reason = can_action_register_sale(ctx)
    assert ok is False
    assert reason and "SHAREPOINT_OK" in reason


def test_register_sale_allowed_with_sharepoint():
    import datetime

    sale = SaleCapture(
        id=1,
        status="pending_validation",
        registration_status="pending_validation",
        folio="00001",
        sale_date=datetime.date.today(),
        vendedor="V",
        cliente="C",
    )
    ctx = WorkflowContext(
        case=_case(workflow_state=WF_SHAREPOINT_OK),
        sharepoint_ok=True,
        sale=sale,
    )
    ok, reason = can_action_register_sale(ctx)
    assert ok is True
    assert reason is None


def test_generate_snte_blocked_in_prep_autorizacion():
    ctx = WorkflowContext(case=_case(), checklist_ok=True)
    ok, reason = can_action_generate_snte(ctx)
    assert ok is False
    assert reason and "APROBADO" in reason
