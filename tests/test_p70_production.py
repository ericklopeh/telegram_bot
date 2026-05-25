"""P70 — producción, métricas, Redis fallback, Docker, backups."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.observability.metrics import build_prometheus_text, metrics_json
from app.services.redis_client import RedisEnterprise
from app.web.main import web_app


def test_production_settings_secure_cookies():
    s = Settings(
        TELEGRAM_BOT_TOKEN="x",
        DATABASE_URL="postgresql+psycopg://u:p@localhost/db",
        ENVIRONMENT="production",
        WEB_DEBUG=False,
    )
    assert s.session_https_only is True
    assert s.is_production is True


def test_metrics_endpoint():
    client = TestClient(web_app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "gaman_up" in resp.text


def test_metrics_json_helper():
    data = metrics_json()
    assert "uptime_seconds" in data


def test_redis_fallback_without_url():
    with patch("app.services.redis_client.get_settings") as mock_s:
        mock_s.return_value.redis_url = ""
        r = RedisEnterprise()
        assert r.available() is False
        assert r.publish("activity", {"ok": True}) is False


def test_docker_compose_prod_structure():
    text = (Path(__file__).parent.parent / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "nginx:" in text
    assert "web:" in text
    assert "db:" in text
    assert "restart: always" in text
    assert "healthcheck:" in text
    assert "gaman_internal" in text


def test_nginx_prod_websocket():
    conf = (Path(__file__).parent.parent / "nginx" / "app.prod.conf").read_text(encoding="utf-8")
    assert "/ws/" in conf
    assert "proxy_buffering off" in conf
    assert "128m" in conf


def test_prod_backup_scripts_exist():
    root = Path(__file__).parent.parent / "scripts"
    for name in ("prod_backup.sh", "prod_restore.sh", "prod_verify_backup.sh", "go_live_check.py"):
        assert (root / name).is_file()


def test_go_live_check_compiles():
    path = Path(__file__).parent.parent / "scripts" / "go_live_check.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_web_debug_sanitized_500():
    import asyncio
    from unittest.mock import MagicMock

    from app.web import main as main_mod

    request = MagicMock()
    request.method = "GET"
    request.url.path = "/x"

    async def boom(_):
        raise RuntimeError("internal-secret-token")

    with patch.object(main_mod.settings, "web_debug", False):
        resp = asyncio.run(main_mod._log_unhandled_errors(request, boom))
    assert resp.status_code == 500
    assert b"internal-secret" not in resp.body


@pytest.mark.parametrize("path", ["/health", "/ping"])
def test_health_endpoints(path):
    client = TestClient(web_app)
    assert client.get(path).status_code == 200
