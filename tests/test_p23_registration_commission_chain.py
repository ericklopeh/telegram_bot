"""P23: cadena registro exitoso → comisión sin duplicar."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models.commission import PAYMENT_STATUS_PENDING
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture
from app.services.commission_service import CommissionService
from app.services.registration_queue_service import RegistrationQueueService


def _sale(**kwargs) -> SaleCapture:
    s = SaleCapture(
        id=42,
        status="pending_validation",
        registration_status="pending_registration",
        folio="00042",
        sale_date=datetime.now(timezone.utc).date(),
        vendedor="MARIA LOPEZ",
        cliente="CLIENTE E2E",
        total_venta=Decimal("10000"),
        case_id=7,
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


@patch("app.services.registration_queue_service.CommissionService")
@patch("app.services.registration_queue_service.SaleCaptureRepository")
@patch("app.services.registration_queue_service.log_event")
def test_registration_triggers_commission_ensure(mock_log, mock_repo, mock_comm_cls):
    db = MagicMock()
    sale = _sale()
    mock_repo.get_by_id.return_value = sale
    mock_comm = mock_comm_cls.return_value
    mock_comm.ensure_commission_for_registered_sale.return_value = MagicMock()

    svc = RegistrationQueueService()
    with patch.object(svc.excel, "prepare_operation_workbooks", return_value=(MagicMock(), MagicMock())):
        with patch.object(
            svc.excel,
            "append_sale_to_workbooks",
            return_value={
                "ventas_path": "/tmp/v.xlsx",
                "contratos_path": "/tmp/c.xlsx",
                "ventas_row": 10,
                "contratos_row": 5,
                "contratos_sheet": "MARIA",
            },
        ):
            with patch(
                "app.services.workflow_transition_service.recalculate_case_workflow_state"
            ):
                sale_out, _, err = svc.process_sale_capture_registration(
                    db, 42, {"id": 1, "rol": "admin"}
                )

    assert err is None
    assert sale_out.registration_status == REG_STATUS_REGISTERED
    mock_comm.ensure_commission_for_registered_sale.assert_called_once()


@patch("app.services.commission_service.CommissionRepository")
@patch("app.services.commission_service.log_event")
def test_commission_not_duplicated_when_pending_exists(mock_log, mock_repo):
    db = MagicMock()
    sale = _sale(registration_status=REG_STATUS_REGISTERED, status="registered")
    existing = MagicMock()
    existing.id = 99
    existing.payment_status = PAYMENT_STATUS_PENDING
    existing.sale_capture_id = 42
    mock_repo.get_by_sale_capture_id.return_value = existing

    svc = CommissionService()
    result = svc.generate_commission(db, sale)
    assert result.id == 99
    mock_repo.create.assert_not_called()
