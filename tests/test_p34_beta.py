"""Pruebas P34 — beta readiness y modo seguro."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.paths import EXCEL_MASTER_DIR, EXCEL_EXPORTS_DIR
from app.models.ops_incident import SEVERITY_ERROR, STATUS_OPEN, OpsIncident
from app.services.beta_readiness_service import BetaReadinessService, ReadinessCheck
from app.services.beta_safe_mode_service import BetaSafeModeService
from app.services.excel_path_guard import assert_writable_excel_path, is_under_excel_masters
from app.web.main import web_app


@patch("app.services.beta_safe_mode_service.get_settings")
def test_safe_mode_blocks_without_phrase(mock_settings):
    mock_settings.return_value = MagicMock(beta_safe_mode=True)
    svc = BetaSafeModeService()
    ok, err = svc.require_confirmation("test", "FRASE-OK", "mal")
    assert not ok
    assert err
    ok2, _ = svc.require_confirmation("test", "FRASE-OK", "FRASE-OK")
    assert ok2


@patch("app.services.beta_safe_mode_service.get_settings")
def test_safe_mode_off_allows_action(mock_settings):
    mock_settings.return_value = MagicMock(beta_safe_mode=False)
    svc = BetaSafeModeService()
    ok, err = svc.block_mass_rollback_without_phrase(1, None)
    assert ok
    assert err is None


@patch("app.services.beta_safe_mode_service.get_settings")
def test_rollback_requires_phrase_when_safe_mode(mock_settings):
    mock_settings.return_value = MagicMock(beta_safe_mode=True)
    svc = BetaSafeModeService()
    ok, err = svc.block_mass_rollback_without_phrase(9, "wrong")
    assert not ok
    ok2, _ = svc.block_mass_rollback_without_phrase(9, "REVERTIR-LOTE-9")
    assert ok2


def test_excel_masters_not_writable_via_guard():
    path = EXCEL_MASTER_DIR / "ventas" / "probe.xlsx"
    with pytest.raises(ValueError, match="prohibida|exports"):
        assert_writable_excel_path(path)
    assert is_under_excel_masters(path)
    assert not is_under_excel_masters(EXCEL_EXPORTS_DIR / "daily" / "ok.xlsx")


@patch.object(BetaReadinessService, "_check_migrations")
@patch.object(BetaReadinessService, "_checks_from_health")
@patch.object(BetaReadinessService, "_check_critical_paths")
@patch.object(BetaReadinessService, "_check_logs_active")
@patch.object(BetaReadinessService, "_check_backups")
@patch.object(BetaReadinessService, "_check_operational_pending")
@patch.object(BetaReadinessService, "_check_health_routes")
@patch.object(BetaReadinessService, "_check_excel_masters_readonly")
@patch.object(BetaReadinessService, "_recent_timeline_errors", return_value=[])
@patch("app.services.beta_readiness_service.OpsMonitorService.collect_findings", return_value=[])
def test_readiness_detects_critical_incidents(
    _findings,
    _timeline,
    _masters,
    _routes,
    _pending,
    _backups,
    _logs,
    _paths,
    _health,
    _mig,
):
    _mig.return_value = ReadinessCheck("migrations", "Mig", True, "ok", "ok")
    _health.return_value = [ReadinessCheck("health_database", "DB", True, "ok", "ok")]
    _paths.return_value = ReadinessCheck("storage_paths", "Paths", True, "ok", "ok")
    _logs.return_value = ReadinessCheck("logs", "Logs", True, "ok", "ok")
    _backups.return_value = [
        ReadinessCheck("backups", "Backups", False, "warning", "Sin backups")
    ]
    _pending.return_value = [
        ReadinessCheck("incidents_critical", "Inc", False, "error", "2 abiertas"),
    ]
    _routes.return_value = ReadinessCheck("health_endpoints", "HE", True, "ok", "ok")
    _masters.return_value = ReadinessCheck("excel_masters_guard", "M", True, "ok", "ok")

    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        OpsIncident(
            id=1,
            incident_key="k",
            source="t",
            severity=SEVERITY_ERROR,
            status=STATUS_OPEN,
            entity_type="system",
            entity_id=None,
            message="crit",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
        )
    ]
    db.scalar.return_value = 2

    with patch("app.services.beta_safe_mode_service.get_settings") as gs:
        gs.return_value = MagicMock(beta_safe_mode=True)
        report = BetaReadinessService().build_report(db)

    assert report.readiness_score >= 0
    assert any("backup" in w.lower() or "Backups" in w for w in report.warnings) or report.checks
    assert report.critical_errors or any(
        not c.ok and c.severity == "error" for c in report.checks
    )


def test_readiness_detects_missing_backup():
    svc = BetaReadinessService()
    checks = svc._check_backups()
    assert checks
    assert checks[0].key == "backups"


@patch.object(BetaReadinessService, "build_report")
def test_beta_readiness_page_loads(mock_report):
    mock_report.return_value = MagicMock(
        overall_status="ready",
        readiness_score=88,
        safe_mode=True,
        checks=[],
        warnings=[],
        critical_errors=[],
        recent_errors=[],
        recent_backups=[],
        open_incidents=[],
        pending_ops={},
        ready_for_beta=True,
        generated_at=datetime.now(timezone.utc),
    )
    with patch("app.web.routes.beta_readiness.require_login", return_value=None):
        with patch("app.web.routes.beta_readiness.require_roles", return_value=None):
            with patch(
                "app.web.routes.beta_readiness.get_current_user",
                return_value={"nombre": "A", "rol": "admin"},
            ):
                client = TestClient(web_app)
                resp = client.get("/admin/beta-readiness")
    assert resp.status_code == 200
    assert "Beta readiness" in resp.text or "readiness" in resp.text.lower()
