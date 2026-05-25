"""P81 — RBAC y auditoría."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.security.rbac import Permission, RbacRole, normalize_rbac_role, role_has_permission
from app.services.rbac_service import RbacService
from app.web.main import web_app


def test_normalize_legacy_roles():
    assert normalize_rbac_role("sistemas") == RbacRole.ADMIN
    assert normalize_rbac_role("compras") == RbacRole.SUPERVISOR
    assert normalize_rbac_role("vendedor") == RbacRole.VENDEDOR
    assert normalize_rbac_role("consulta") == RbacRole.READONLY


def test_permission_matrix():
    assert role_has_permission("admin", Permission.DELETE)
    assert role_has_permission("autorizacion", Permission.APPROVE)
    assert role_has_permission("vendedor", Permission.CREATE)
    assert not role_has_permission("vendedor", Permission.APPROVE)
    assert not role_has_permission("consulta", Permission.EDIT)
    assert role_has_permission("consulta", Permission.DOWNLOAD)


def test_rbac_relaxed_grants_all():
    svc = RbacService()
    with patch.object(svc, "is_relaxed", return_value=True):
        assert svc.has_permission({"rol": "consulta"}, Permission.DELETE)


def test_audit_route_requires_login():
    client = TestClient(web_app)
    resp = client.get("/admin/audit", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_webhook_not_affected_by_rbac_middleware():
    paths = {getattr(r, "path", None) for r in web_app.routes}
    assert "/admin/audit" in paths
    assert "/telegram/webhook" in paths


def test_p81_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P81_RBAC_AND_AUDIT.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "supervisor" in text.lower()
    assert "audit" in text.lower()


def test_telegram_webhook_still_works_with_secret():
    with patch("app.web.routes.telegram_webhook.get_settings") as mock_settings:
        mock_settings.return_value = Settings.model_construct(
            telegram_bot_token="123456789:AAFakeTokenForTestsOnly",
            database_url="postgresql+psycopg://u:p@localhost/db",
            web_session_secret="x" * 32,
            telegram_webhook_secret="sec",
        )
        with patch(
            "app.web.routes.telegram_webhook.process_telegram_update_payload",
            new_callable=AsyncMock,
        ):
            client = TestClient(web_app)
            resp = client.post(
                "/telegram/webhook",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "sec"},
            )
    assert resp.status_code == 200
