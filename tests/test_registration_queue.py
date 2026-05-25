"""Pruebas cola de registro P20 (sin BD real)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.sale_capture import (
    REG_STATUS_PENDING_REGISTRATION,
    REG_STATUS_PROCESSING_REGISTRATION,
    REG_STATUS_REGISTERED,
    REG_STATUS_REGISTRATION_FAILED,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_REGISTERED,
    SaleCapture,
    can_retry_registration,
)
from app.models.user import UserRole
from app.services.registration_queue_service import RegistrationQueueService
from app.services.sale_action_guard_service import get_sale_action_permissions


def _sale(**kwargs) -> SaleCapture:
    s = SaleCapture(
        id=1,
        status="pending_validation",
        registration_status=REG_STATUS_PENDING_REGISTRATION,
        folio="00001",
        sale_date=datetime.now(timezone.utc).date(),
        vendedor="JUAN",
        cliente="CLIENTE TEST",
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


@patch("app.services.registration_queue_service.SaleCaptureRepository")
@patch("app.services.registration_queue_service.log_event")
def test_process_marks_registered_on_excel_ok(mock_log, mock_repo):
    db = MagicMock()
    sale = _sale(case_id=10)
    mock_repo.get_by_id.return_value = sale
    mock_repo.save = MagicMock()

    svc = RegistrationQueueService()
    with patch.object(svc.excel, "prepare_operation_workbooks", return_value=(MagicMock(), MagicMock())):
        with patch.object(
            svc.excel,
            "append_sale_to_workbooks",
            return_value={
                "ventas_path": "/tmp/v.xlsx",
                "contratos_path": "/tmp/c.xlsx",
                "ventas_row": 7,
                "contratos_row": 3,
                "contratos_sheet": "JUAN",
            },
        ):
            updated, result, err = svc.process_sale_capture_registration(
                db, 1, {"id": 1, "rol": UserRole.ADMIN.value}
            )

    assert err is None
    assert result is not None
    assert updated.registration_status == REG_STATUS_REGISTERED
    assert updated.status == SALE_STATUS_REGISTERED
    assert updated.registration_error is None
    assert updated.registration_attempts == 1


@patch("app.services.registration_queue_service.SaleCaptureRepository")
@patch("app.services.registration_queue_service.log_event")
def test_process_marks_failed_on_excel_error(mock_log, mock_repo):
    from app.services.excel_registry_service import ExcelRegistryError

    db = MagicMock()
    sale = _sale(case_id=10)
    mock_repo.get_by_id.return_value = sale

    svc = RegistrationQueueService()
    with patch.object(svc.excel, "prepare_operation_workbooks", side_effect=ExcelRegistryError("bloqueado", code="file_locked")):
        updated, result, err = svc.process_sale_capture_registration(
            db, 1, {"id": 1, "rol": UserRole.ADMIN.value}
        )

    assert result is None
    assert err == "bloqueado"
    assert updated.registration_status == REG_STATUS_REGISTRATION_FAILED
    assert updated.status == SALE_STATUS_EXPORT_FAILED
    assert updated.registration_error == "bloqueado"
    assert updated.export_error == "bloqueado"


@patch("app.services.registration_queue_service.SaleCaptureRepository")
@patch("app.services.registration_queue_service.log_event")
def test_retry_increments_attempts(mock_log, mock_repo):
    db = MagicMock()
    sale = _sale(
        case_id=10,
        registration_status=REG_STATUS_REGISTRATION_FAILED,
        status=SALE_STATUS_EXPORT_FAILED,
        registration_attempts=1,
    )
    mock_repo.get_by_id.return_value = sale

    svc = RegistrationQueueService()
    with patch.object(svc, "process_sale_capture_registration") as proc:
        proc.return_value = (sale, {}, None)
        svc.retry_sale_capture_registration(db, 1, {"id": 1, "rol": UserRole.ADMIN.value})
    proc.assert_called_once()


@patch("app.services.sale_action_guard_service.get_settings")
def test_vendor_cannot_retry_permission(mock_settings):
    mock_settings.return_value.web_rbac_relaxed = False
    sale = _sale(
        registration_status=REG_STATUS_REGISTRATION_FAILED,
        status=SALE_STATUS_EXPORT_FAILED,
    )
    perms = get_sale_action_permissions(
        MagicMock(),
        {"rol": UserRole.VENDEDOR.value, "id": 99},
        sale,
    )
    assert perms.can_retry_registration is False


def test_admin_can_retry_when_failed():
    sale = _sale(
        registration_status=REG_STATUS_REGISTRATION_FAILED,
        status=SALE_STATUS_EXPORT_FAILED,
    )
    perms = get_sale_action_permissions(
        MagicMock(),
        {"rol": UserRole.ADMIN.value, "id": 1},
        sale,
    )
    assert perms.can_retry_registration is True
    assert can_retry_registration(sale) is True


def test_pending_registration_not_retryable():
    sale = _sale(registration_status=REG_STATUS_PENDING_REGISTRATION)
    assert can_retry_registration(sale) is False
