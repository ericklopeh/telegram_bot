"""Pruebas P33 — monitoreo operativo y recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.paths import EXCEL_MASTER_DIR, EXCEL_EXPORTS_DIR
from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.models.ops_incident import (
    SEVERITY_ERROR,
    STATUS_ACKNOWLEDGED,
    STATUS_OPEN,
    STATUS_RESOLVED,
    OpsIncident,
)
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture
from app.services.excel_path_guard import is_under_excel_masters
from app.services.ops_monitor_service import OpsFinding, OpsMonitorService, incident_key
from app.services.ops_recovery_service import OpsRecoveryService
from app.web.main import web_app


def test_incident_key_stable():
    k = incident_key("sharepoint", "document", 5, "sharepoint.failed")
    assert k == "sharepoint:document:5:sharepoint.failed"


@patch.object(OpsMonitorService, "collect_findings")
def test_detect_sharepoint_failed_finding(mock_collect):
    mock_collect.return_value = [
        OpsFinding(
            source="sharepoint",
            code="sharepoint.failed",
            severity=SEVERITY_ERROR,
            entity_type="document",
            entity_id=12,
            message="Doc fallido",
        )
    ]
    db = MagicMock()
    db.scalar.return_value = None
    db.flush = MagicMock()
    svc = OpsMonitorService()
    n, _ = svc.sync_incidents(db, mock_collect.return_value)
    assert db.add.called
    added = db.add.call_args[0][0]
    assert added.source == "sharepoint"
    assert added.status == STATUS_OPEN


@patch.object(OpsMonitorService, "_findings_recent_errors", return_value=[])
@patch.object(OpsMonitorService, "_findings_storage_paths", return_value=[])
@patch.object(OpsMonitorService, "_findings_documents_invalid", return_value=[])
@patch.object(OpsMonitorService, "_findings_workflow_blocked", return_value=[])
@patch.object(OpsMonitorService, "_findings_sales_without_export", return_value=[])
@patch.object(OpsMonitorService, "_findings_imports_failed", return_value=[])
@patch("app.web.services.operational_review_service.OperationalReviewService.build_report")
def test_detect_sale_without_commission_finding(mock_report, *_patches):
    from app.web.services.operational_review_service import ReviewItem

    mock_report.return_value = MagicMock(
        generated_at=datetime.now(timezone.utc),
        sections={
            "comisiones_pendientes": [
                ReviewItem(
                    title="F-1",
                    detail="sin comisión",
                    severity="warning",
                    url="/comisiones",
                    entity_id=7,
                )
            ]
        },
        totals={"comisiones_pendientes": 1},
        critical_count=0,
    )
    findings = OpsMonitorService().collect_findings(MagicMock())
    assert any(f.code == "sale.no_commission" for f in findings)


@patch("app.web.services.operational_review_service.OperationalReviewService.build_report")
def test_detect_stale_case_via_review(mock_report):
    from app.web.services.operational_review_service import ReviewItem

    mock_report.return_value = MagicMock(
        sections={
            "casos_atorados": [
                ReviewItem(
                    title="STALE",
                    detail="sin movimiento >24h",
                    severity="warning",
                    url="/casos/3",
                    entity_id=3,
                )
            ]
        }
    )
    findings = OpsMonitorService()._findings_from_review(MagicMock())
    assert any(f.code == "case.stale_24h" for f in findings)


def test_ack_and_resolve_incident():
    db = MagicMock()
    inc = OpsIncident(
        id=1,
        incident_key="k",
        source="test",
        severity=SEVERITY_ERROR,
        status=STATUS_OPEN,
        entity_type="system",
        entity_id=None,
        message="test",
    )
    db.get.return_value = inc
    svc = OpsRecoveryService()
    out = svc.acknowledge_incident(db, 1, username="admin")
    assert out.status == STATUS_ACKNOWLEDGED
    out2 = svc.resolve_incident(db, 1, username="admin")
    assert out2.status == STATUS_RESOLVED
    assert out2.resolved_by == "admin"


@patch("app.services.ops_recovery_service.SharePointSyncService")
def test_retry_sharepoint_does_not_raise(mock_sp):
    mock_sp.return_value.retry_all_failed.return_value = [
        MagicMock(ok=True, document_id=1, error=None),
    ]
    db = MagicMock()
    result = OpsRecoveryService().retry_sharepoint(db, limit=5)
    assert result.ok
    mock_sp.return_value.retry_all_failed.assert_called_once()


@patch("app.services.ops_recovery_service.RegistrationQueueService")
def test_regenerate_export_uses_retry_registration(mock_reg):
    sale = SaleCapture(
        id=4,
        folio="R-1",
        sale_date=datetime(2026, 1, 1).date(),
        vendedor="V",
        cliente="C",
        status="registered",
        registration_status=REG_STATUS_REGISTERED,
    )
    sale.ventas_export_path = str(EXCEL_EXPORTS_DIR / "daily" / "ventas_test.xlsx")
    updated = sale
    updated.ventas_export_path = str(EXCEL_EXPORTS_DIR / "operations" / "out.xlsx")
    mock_reg.return_value.retry_sale_capture_registration.return_value = (updated, None)

    db = MagicMock()
    with patch(
        "app.services.ops_recovery_service.SaleCaptureRepository.get_by_id",
        return_value=sale,
    ):
        result = OpsRecoveryService().regenerate_sale_export(db, 4, user={"rol": "admin"})
    assert result.ok
    path = result.details.get("ventas_export_path", "")
    assert "excel_exports" in str(path).replace("\\", "/")
    assert not is_under_excel_masters(path)


def test_regenerate_export_blocks_master_path():
    sale = SaleCapture(
        id=5,
        folio="R-2",
        sale_date=datetime(2026, 1, 1).date(),
        vendedor="V",
        cliente="C",
        status="registered",
        registration_status=REG_STATUS_REGISTERED,
    )
    sale.ventas_export_path = str(EXCEL_MASTER_DIR / "ventas" / "bad.xlsx")
    db = MagicMock()
    with patch(
        "app.services.ops_recovery_service.SaleCaptureRepository.get_by_id",
        return_value=sale,
    ):
        result = OpsRecoveryService().regenerate_sale_export(db, 5, user={"rol": "admin"})
    assert not result.ok
    assert "maestro" in result.message.lower()


@patch.object(OpsMonitorService, "build_dashboard")
def test_ops_page_loads(mock_dash):
    mock_dash.return_value = MagicMock(
        health_status="ok",
        health_checks_failed=[],
        counts={
            "critical": 0,
            "warning": 0,
            "pending": 0,
            "open_incidents": 0,
            "sharepoint_failed": 0,
            "imports_failed": 0,
            "exports_failed": 0,
            "sales_pending": 0,
            "docs_pending": 0,
            "total_findings": 0,
        },
        critical_items=[],
        warning_items=[],
        pending_items=[],
        recent_failures=[],
        recommended_actions=[],
        open_incidents=0,
        sla_cases=[],
        generated_at=datetime.now(timezone.utc),
    )
    with patch("app.web.routes.ops.require_login", return_value=None):
        with patch("app.web.routes.ops.require_roles", return_value=None):
            with patch(
                "app.web.routes.ops.get_current_user",
                return_value={"nombre": "Admin", "rol": "admin", "user_id": 1},
            ):
                client = TestClient(web_app)
                resp = client.get("/ops")
    assert resp.status_code == 200
    assert "Operación" in resp.text or "Monitoreo" in resp.text
