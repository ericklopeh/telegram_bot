"""P74 — endpoint webhook Telegram."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.bot.webhook_processor import verify_webhook_secret
from app.config import Settings
from app.web.main import web_app


def test_verify_webhook_secret():
    assert verify_webhook_secret("abc", "abc") is True
    assert verify_webhook_secret("wrong", "abc") is False
    assert verify_webhook_secret(None, "abc") is False
    assert verify_webhook_secret("x", "") is False


def test_webhook_route_registered():
    paths = {getattr(r, "path", None) for r in web_app.routes}
    assert "/telegram/webhook" in paths


def test_webhook_disabled_without_secret():
    with patch("app.web.routes.telegram_webhook.get_settings") as mock_settings:
        mock_settings.return_value = Settings.model_construct(
            telegram_bot_token="123456789:AAFakeTokenForTestsOnly",
            database_url="postgresql+psycopg://u:p@localhost/db",
            web_session_secret="x" * 32,
            telegram_webhook_secret="",
        )
        client = TestClient(web_app)
        resp = client.post("/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 503


def test_webhook_forbidden_wrong_secret():
    with patch("app.web.routes.telegram_webhook.get_settings") as mock_settings:
        mock_settings.return_value = Settings.model_construct(
            telegram_bot_token="123456789:AAFakeTokenForTestsOnly",
            database_url="postgresql+psycopg://u:p@localhost/db",
            web_session_secret="x" * 32,
            telegram_webhook_secret="expected-secret",
        )
        client = TestClient(web_app)
        resp = client.post("/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 403


def test_webhook_ok_with_secret_and_mock_processor():
    with patch("app.web.routes.telegram_webhook.get_settings") as mock_settings:
        mock_settings.return_value = Settings.model_construct(
            telegram_bot_token="123456789:AAFakeTokenForTestsOnly",
            database_url="postgresql+psycopg://u:p@localhost/db",
            web_session_secret="x" * 32,
            telegram_webhook_secret="expected-secret",
        )
        with patch(
            "app.web.routes.telegram_webhook.process_telegram_update_payload",
            new_callable=AsyncMock,
        ) as mock_proc:
            client = TestClient(web_app)
            resp = client.post(
                "/telegram/webhook",
                json={"update_id": 99},
                headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
            )
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    mock_proc.assert_awaited_once()


def test_telegram_set_webhook_script_exists():
    script = Path(__file__).resolve().parent.parent / "scripts" / "telegram_set_webhook.sh"
    assert script.is_file()
