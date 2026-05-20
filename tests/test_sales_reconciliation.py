"""Pruebas conciliación comercial P20."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.sale_capture import (
    REG_STATUS_REGISTERED,
    SALE_STATUS_REGISTERED,
    SaleCapture,
)
from app.services.sales_reconciliation_service import (
    CONCILIATION_ERROR,
    build_reconciliation_report,
)


def _sale(**kwargs) -> SaleCapture:
    s = SaleCapture(
        id=1,
        status=SALE_STATUS_REGISTERED,
        registration_status=REG_STATUS_REGISTERED,
        folio="00099",
        sale_date=datetime.now(timezone.utc).date(),
        vendedor="JUAN",
        cliente="ACME",
        ventas_export_path="/no/existe/ventas.xlsx",
        contratos_export_path=None,
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


@patch("app.services.sales_reconciliation_service.SaleCaptureRepository")
def test_reconciliation_detects_registered_without_ventas_file(mock_repo):
    mock_repo.list_for_reconciliation.return_value = [_sale()]
    report = build_reconciliation_report(MagicMock())
    problems = [i.problem for i in report["issues"]]
    assert any("sin archivo Excel de ventas" in p for p in problems)
    assert report["error_count"] >= 1
    assert report["issues"][0].severity == CONCILIATION_ERROR
