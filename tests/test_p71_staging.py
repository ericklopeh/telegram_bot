"""P71 — staging readiness: smoke /health sin BD."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.web.main import web_app


def test_health_endpoint_exists_and_ok():
    """Smoke: liveness para load balancers y Render/Heroku health checks."""
    client = TestClient(web_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "sistema_gaman_web"
    assert "version" in body


def test_ping_endpoint_ok():
    client = TestClient(web_app)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_health_route_registered_in_app():
    paths = {getattr(r, "path", None) for r in web_app.routes}
    assert "/health" in paths
    assert "/health/full" in paths


def test_staging_example_env_template_exists():
    root = Path(__file__).resolve().parent.parent
    assert (root / ".env.staging.example").is_file()
    text = (root / ".env.staging.example").read_text(encoding="utf-8")
    assert "ENVIRONMENT=staging" in text
    assert "your_telegram_bot_token_here" in text
    assert "change_me_staging_db_password" in text
    assert "8682526788" not in text


def test_p71_staging_deploy_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P71_STAGING_DEPLOY.md"
    assert doc.is_file()
    content = doc.read_text(encoding="utf-8")
    assert "/health" in content
    assert "Heroku" in content
    assert "Render" in content
    assert "docker-compose.staging.yml" in content
