"""Pruebas P29 — BI / dashboard ejecutivo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.bi_dashboard_service import (
    BiDashboardService,
    BiKpiCard,
    BiOperationalAlert,
)
from app.services.bi_export_service import BiExportService
from app.services.bi_filters import BiFilters
from app.services.case_event_service import BI_REPORT_EXPORTED, BI_DASHBOARD_VIEWED
from app.services.contract_financial_service import ErpDashboardKpis
from app.services.excel_path_guard import is_under_excel_masters


def test_bi_filters_cache_key_changes_with_vendedor():
    f1 = BiFilters(vendedor="Ana")
    f2 = BiFilters(vendedor="Luis")
    assert f1.cache_key() != f2.cache_key()


def test_bi_filters_from_query_parses_dates():
    f = BiFilters.from_query(fecha_desde="2026-01-15", fecha_hasta="2026-05-01", vendedor="Test")
    assert f.fecha_desde == date(2026, 1, 15)
    assert f.fecha_hasta == date(2026, 5, 1)
    assert f.vendedor == "Test"


@patch.object(BiDashboardService, "_build_dashboard_uncached")
def test_build_dashboard_uses_cache(mock_build):
    svc = BiDashboardService()
    svc.clear_cache()
    payload = MagicMock()
    mock_build.return_value = payload
    db = MagicMock()
    filters = BiFilters()
    assert svc.build_dashboard(db, filters) is payload
    assert svc.build_dashboard(db, filters) is payload
    mock_build.assert_called_once()


def test_kpis_use_erp_financial_service():
    from app.services.contract_financial_service import ContractFinancialService

    fin = MagicMock(spec=ContractFinancialService)
    fin.build_dashboard_kpis.return_value = ErpDashboardKpis(
        active_contracts=3,
        total_balance=Decimal("5000"),
        total_refinanced=Decimal("200"),
        total_recovery_pct=Decimal("45"),
        overdue_amount=Decimal("100"),
        recent_payments_count=2,
        top_vendedores=[],
        top_secciones=[],
    )
    svc = BiDashboardService()
    svc._financial = fin
    svc._reconciliation = MagicMock()
    svc._reconciliation.build_report.return_value = MagicMock(issues=[])

    db = MagicMock()
    db.scalar.return_value = Decimal("0")
    db.execute.return_value.all.return_value = []
    db.scalars.return_value.unique.return_value.all.return_value = []
    db.scalars.return_value.all.return_value = []

    with patch.object(svc, "_sum_sales", return_value=Decimal("10000")):
        with patch.object(svc, "_chart_group_sales", return_value={"labels": [], "values": []}):
            with patch.object(svc, "_chart_workflow", return_value={"labels": [], "values": []}):
                with patch.object(svc, "_chart_sharepoint", return_value={"labels": [], "values": []}):
                    with patch.object(svc, "_chart_recovery_vendedor", return_value={"labels": [], "values": []}):
                        with patch.object(svc, "_filter_options", return_value={}):
                            payload = svc._build_dashboard_uncached(db, BiFilters())

    recovery_kpi = next(k for k in payload.kpis if k.key == "recovery")
    assert recovery_kpi.value == "45%"
    fin.build_dashboard_kpis.assert_called_once_with(db)


def test_operational_alerts_detect_negative_balance():
    svc = BiDashboardService()
    db = MagicMock()
    db.scalar.side_effect = [0, 0, 0, 0, 0]
    svc._reconciliation = MagicMock()
    issue = MagicMock()
    issue.code = "NEGATIVE_BALANCE"
    issue.severity = "error"
    issue.message = "saldo negativo"
    svc._reconciliation.build_report.return_value = MagicMock(issues=[issue])

    with patch.object(svc, "_count_documents", return_value=0):
        with patch.object(svc, "_count_stale_cases", return_value=0):
            alerts = svc.build_operational_alerts(db, BiFilters())
    assert any(a.code == "NEGATIVE_BALANCE" for a in alerts)


def test_bi_export_not_under_excel_masters(tmp_path):
    bi_root = tmp_path / "excel_exports"
    with patch("app.services.bi_export_service.EXCEL_EXPORTS_DIR", bi_root):
        with patch("app.services.bi_export_service.assert_writable_excel_path"):
            svc = BiExportService()
            svc.dashboard = MagicMock()
            kpi = BiKpiCard("a", "L", "1", "h", "/x")
            svc.dashboard.build_dashboard.return_value = MagicMock(
                kpis=[kpi],
                alerts=[],
                charts={"ventas_vendedor": {"labels": ["A"], "values": [1]}},
                rankings={"top_recovery": [], "mas_pendientes": []},
            )
            path = svc.export_dashboard_resumen(MagicMock(), BiFilters())
    assert "excel_masters" not in str(path).replace("\\", "/")
    assert not is_under_excel_masters(path)


def test_bi_event_constants_defined():
    assert BI_REPORT_EXPORTED == "BI_REPORT_EXPORTED"
    assert BI_DASHBOARD_VIEWED == "BI_DASHBOARD_VIEWED"


@patch.object(BiDashboardService, "_chart_group_sales")
@patch.object(BiDashboardService, "_sum_sales")
def test_filters_affect_sales_aggregation(mock_sum, mock_chart):
    mock_sum.return_value = Decimal("999")
    mock_chart.return_value = {"labels": ["V1"], "values": [999.0]}
    svc = BiDashboardService()
    svc._financial = MagicMock()
    svc._financial.build_dashboard_kpis.return_value = ErpDashboardKpis(
        active_contracts=0,
        total_balance=Decimal("0"),
        total_refinanced=Decimal("0"),
        total_recovery_pct=Decimal("0"),
        overdue_amount=Decimal("0"),
        recent_payments_count=0,
        top_vendedores=[],
        top_secciones=[],
    )
    svc._reconciliation = MagicMock()
    svc._reconciliation.build_report.return_value = MagicMock(issues=[])
    db = MagicMock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []
    db.scalars.return_value.unique.return_value.all.return_value = []
    db.scalars.return_value.all.return_value = []

    with patch.object(svc, "_chart_workflow", return_value={"labels": [], "values": []}):
        with patch.object(svc, "_chart_sharepoint", return_value={"labels": [], "values": []}):
            with patch.object(svc, "_chart_recovery_vendedor", return_value={"labels": [], "values": []}):
                with patch.object(svc, "_filter_options", return_value={}):
                    with patch.object(svc, "build_operational_alerts", return_value=[]):
                        svc._build_dashboard_uncached(db, BiFilters(vendedor="Ana"))
    mock_sum.assert_called()
    call_filters = mock_sum.call_args[0][1]
    assert call_filters.vendedor == "Ana"
