"""Pruebas dependencias workflow P22."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.domain import constants as C
from app.models.case import Case
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture
from app.services.workflow_dependency_service import (
    WorkflowContext,
    can_action_generate_snte,
    can_action_register_sale,
    check_dependencies_for_state,
    highest_achievable_state,
)
from app.services.workflow_state_service import (
    WF_APROBADO,
    WF_PEDIDO_RECIBIDO,
    WF_PREP_AUTORIZACION,
    WF_REGISTRADO,
    WF_SHAREPOINT_OK,
    WF_SNTE_PENDIENTE,
)


def _case(**kwargs) -> Case:
    c = Case(
        id=1,
        public_id="PED-001",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Test",
        current_status=C.ST_PED_COMPULSA_OK,
        workflow_state=WF_APROBADO,
        visible_status="En pedido",
        week_code="S1",
        folder_path="/tmp",
    )
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_snte_blocked_before_aprobado():
    ctx = WorkflowContext(
        case=_case(current_status=C.ST_PED_PREP_AUT, workflow_state=WF_PREP_AUTORIZACION),
        checklist_ok=True,
    )
    ok, reason = can_action_generate_snte(ctx)
    assert ok is False
    assert "APROBADO" in (reason or "")


def test_snte_allowed_when_aprobado():
    ctx = WorkflowContext(
        case=_case(workflow_state=WF_APROBADO, current_status=C.ST_PED_COMPULSA_OK),
        checklist_ok=True,
    )
    ok, reason = can_action_generate_snte(ctx)
    assert ok is True
    assert reason is None


def test_register_blocked_without_sharepoint():
    ctx = WorkflowContext(
        case=_case(workflow_state=WF_APROBADO),
        sharepoint_ok=False,
    )
    ok, reason = can_action_register_sale(ctx)
    assert ok is False
    assert "SHAREPOINT_OK" in (reason or "")


def test_register_allowed_with_sharepoint_ok():
    sale = SaleCapture(
        id=1,
        status="pending_validation",
        registration_status="pending_validation",
        folio="00001",
        sale_date=__import__("datetime").date.today(),
        vendedor="V",
        cliente="C",
    )
    ctx = WorkflowContext(
        case=_case(workflow_state=WF_SHAREPOINT_OK),
        sharepoint_ok=True,
        sale=sale,
    )
    ok, _ = can_action_register_sale(ctx)
    assert ok is True


def test_registrado_requires_registered_sale():
    sale = SaleCapture(
        id=1,
        status="registered",
        registration_status=REG_STATUS_REGISTERED,
        folio="00001",
        sale_date=__import__("datetime").date.today(),
        vendedor="V",
        cliente="C",
        total_venta=Decimal("1000"),
    )
    ctx = WorkflowContext(
        case=_case(),
        sharepoint_ok=True,
        sale=sale,
        has_snte_excel=True,
        has_snte_pdf=True,
    )
    missing = check_dependencies_for_state(ctx, WF_REGISTRADO)
    assert not missing


def test_highest_achievable_at_least_pedido():
    ctx = WorkflowContext(
        case=_case(
            current_status=C.ST_PED_RECIBIDO,
            workflow_state=WF_PEDIDO_RECIBIDO,
        )
    )
    assert highest_achievable_state(ctx) == WF_PEDIDO_RECIBIDO
