"""P76 — observabilidad y métricas."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.web.main import web_app


def test_metrics_endpoint_when_enabled():
    client = TestClient(web_app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "gaman_up" in resp.text


def test_metrics_disabled_returns_404():
    from unittest.mock import patch

    with patch("app.web.routes.health.get_settings") as mock_s:
        mock_s.return_value = Settings.model_construct(
            telegram_bot_token="123456789:AAFakeTokenForTestsOnly",
            database_url="postgresql+psycopg://u:p@localhost/db",
            web_session_secret="x" * 32,
            metrics_enabled=False,
        )
        client = TestClient(web_app)
        resp = client.get("/metrics")
    assert resp.status_code == 404


def test_p76_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P76_OBSERVABILITY_MONITORING.md"
    text = doc.read_text(encoding="utf-8")
    assert "/health" in text
    assert "/metrics" in text
