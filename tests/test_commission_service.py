"""Pruebas servicio de comisiones P21."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.commission import PAYMENT_STATUS_PENDING, Commission
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture
from app.services.commission_service import (
    CommissionService,
    CommissionServiceError,
    calculate_commission,
)
from app.services.commission_rules import DEFAULT_COMMISSION_PERCENTAGE, JUAN_MANUEL_PERCENTAGE


def _sale(**kwargs) -> SaleCapture:
    s = SaleCapture(
        id=1,
        status="registered",
        registration_status=REG_STATUS_REGISTERED,
        folio="00100",
        sale_date=datetime.now(timezone.utc).date(),
        vendedor="MARIA",
        cliente="CLIENTE",
        total_venta=Decimal("10000"),
        case_id=5,
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_calculate_commission_juan_manuel():
    sale = _sale(vendedor="Juan Manuel", total_venta=Decimal("1000"))
    pct, amt, base = calculate_commission(sale)
    assert pct == JUAN_MANUEL_PERCENTAGE
    assert base == Decimal("1000.00")
    assert amt == Decimal("600.00")


def test_calculate_commission_default_46():
    sale = _sale(vendedor="OTRO VENDEDOR", total_venta=Decimal("1000"))
    pct, amt, _ = calculate_commission(sale)
    assert pct == DEFAULT_COMMISSION_PERCENTAGE
    assert amt == Decimal("460.00")


@patch("app.services.commission_service.CommissionRepository")
@patch("app.services.commission_service.log_event")
def test_generate_commission_creates_once(mock_log, mock_repo):
    db = MagicMock()
    sale = _sale()
    mock_repo.get_by_sale_capture_id.return_value = None
    mock_repo.create.side_effect = lambda db, c: c

    svc = CommissionService()
    c1 = svc.generate_commission(db, sale, {"id": 1, "rol": "admin"})
    assert c1.payment_status == PAYMENT_STATUS_PENDING
    assert c1.commission_amount == Decimal("4600.00")
    mock_repo.create.assert_called_once()
    mock_log.assert_called()


@patch("app.services.commission_service.CommissionRepository")
@patch("app.services.commission_service.log_event")
def test_generate_commission_no_duplicate_updates_pending(mock_log, mock_repo):
    db = MagicMock()
    sale = _sale()
    existing = Commission(
        id=9,
        sale_capture_id=1,
        seller_name="MARIA",
        sale_amount=Decimal("10000"),
        commission_percentage=Decimal("46"),
        commission_amount=Decimal("4600"),
        payment_status=PAYMENT_STATUS_PENDING,
    )
    mock_repo.get_by_sale_capture_id.return_value = existing

    svc = CommissionService()
    c2 = svc.generate_commission(db, sale)
    assert c2.id == 9
    mock_repo.create.assert_not_called()
    mock_log.assert_called()


@patch("app.services.commission_service.CommissionRepository")
def test_generate_blocks_when_paid(mock_repo):
    db = MagicMock()
    sale = _sale()
    mock_repo.get_by_sale_capture_id.return_value = Commission(
        id=1,
        sale_capture_id=1,
        seller_name="X",
        sale_amount=Decimal("1"),
        commission_percentage=Decimal("46"),
        commission_amount=Decimal("0.46"),
        payment_status="paid",
    )
    svc = CommissionService()
    with pytest.raises(CommissionServiceError):
        svc.generate_commission(db, sale)
