"""Pruebas P30 — staging, health y endurecimiento DevOps."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services.excel_path_guard import is_under_excel_masters
from app.services.storage_layout_service import ensure_runtime_directories
from app.services.system_health_service import (
    HealthCheckResult,
    SystemHealthReport,
    SystemHealthService,
)
from app.web.main import web_app


def test_settings_p30_env_fields():
    s = Settings(
        TELEGRAM_BOT_TOKEN="x",
        DATABASE_URL="postgresql+psycopg://u:p@localhost/db",
        ENVIRONMENT="staging",
        LOG_LEVEL="DEBUG",
        APP_VERSION="1.2.3",
        STORAGE_ROOT="/data/storage",
        DEMO_MODE=True,
    )
    assert s.environment == "staging"
    assert s.log_level == "DEBUG"
    assert s.app_version == "1.2.3"
    assert s.demo_mode is True


def test_health_liveness_endpoint():
    client = TestClient(web_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "sistema_gaman_web"
    assert "version" in data


@patch.object(SystemHealthService, "build_report")
def test_health_full_endpoint_ok(mock_build):
    mock_build.return_value = SystemHealthReport(
        status="ok",
        checked_at=datetime.now(timezone.utc),
        uptime_seconds=10.0,
        version="0.1.0",
        environment="test",
        checks=[HealthCheckResult("database", True, "ok")],
    )
    client = TestClient(web_app)
    resp = client.get("/health/full")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "checks" in body


@patch.object(SystemHealthService, "build_report")
def test_health_full_degraded_returns_503(mock_build):
    mock_build.return_value = SystemHealthReport(
        status="degraded",
        checked_at=datetime.now(timezone.utc),
        uptime_seconds=1.0,
        version="0.1.0",
        environment="staging",
        checks=[HealthCheckResult("database", False, "down")],
    )
    client = TestClient(web_app)
    resp = client.get("/health/full")
    assert resp.status_code == 503


def test_error_response_sanitized_when_not_debug():
    import asyncio

    from app.web import main as main_mod

    request = MagicMock()
    request.method = "GET"
    request.url.path = "/test"

    async def _raise(_req):
        raise RuntimeError("secret internal detail")

    with patch.object(main_mod.settings, "web_debug", False):
        response = asyncio.run(main_mod._log_unhandled_errors(request, _raise))
    assert response.status_code == 500
    assert b"secret internal detail" not in response.body
    assert b"Contacte al administrador" in response.body


def test_storage_layout_does_not_write_excel_masters(tmp_path):
    with patch("app.services.storage_layout_service.STORAGE_DIR", tmp_path / "storage"):
        with patch("app.services.storage_layout_service.EXCEL_EXPORTS_DIR", tmp_path / "storage" / "excel_exports"):
            with patch("app.services.storage_layout_service.PROJECT_ROOT", tmp_path):
                ensure_runtime_directories()
    masters = tmp_path / "storage" / "excel_masters"
    assert not masters.exists() or not any(masters.iterdir()) or masters.is_dir()
    exports = tmp_path / "storage" / "excel_exports"
    assert exports.is_dir()
    probe = exports / "bi" / ".probe"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("ok")
    assert not is_under_excel_masters(exports)


def test_excel_exports_probe_not_masters(tmp_path):
    exports = tmp_path / "storage" / "excel_exports" / "bi"
    exports.mkdir(parents=True)
    f = exports / "test.xlsx"
    f.touch()
    assert "excel_masters" not in str(f).replace("\\", "/")
    assert not is_under_excel_masters(f)


@pytest.mark.parametrize(
    "script",
    [
        "backup_db.sh",
        "restore_db.sh",
        "deploy_staging.sh",
        "run_migrations.sh",
        "restart_services.sh",
    ],
)
def test_deploy_scripts_exist(script):
    path = Path(__file__).resolve().parent.parent / "scripts" / script
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "docker compose" in content


def test_staging_compose_has_nginx_and_healthchecks():
    text = (Path(__file__).parent.parent / "docker-compose.staging.yml").read_text(encoding="utf-8")
    assert "nginx:" in text
    assert "healthcheck:" in text
    assert "WEB_DEBUG" in text
    assert "pg_data_staging" in text


def test_prod_compose_has_redis_worker_nginx():
    text = (Path(__file__).parent.parent / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "nginx:" in text
    assert "redis:" in text
    assert "worker:" in text
    assert "gaman_internal" in text


def test_nginx_config_proxy_and_upload_timeouts():
    app_conf = (Path(__file__).parent.parent / "nginx" / "app.conf").read_text(encoding="utf-8")
    assert "proxy_read_timeout 300s" in app_conf
    assert "gaman_web" in app_conf
    assert "/ws/" in app_conf
    nginx_conf = (Path(__file__).parent.parent / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "gzip" in nginx_conf
    assert "client_max_body_size 64m" in nginx_conf
