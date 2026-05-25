"""Pruebas P47-P60 — enterprise avanzado."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services.ai_ops_service import AiOpsService
from app.services.feature_flag_service import FeatureFlagService
from app.services.realtime_service import RealtimeService, get_realtime_hub
from app.services.rule_engine import RuleEngine, _eval_conditions
from app.web.main import web_app


def test_realtime_publish_and_poll():
    hub = get_realtime_hub()
    RealtimeService().publish_jobs("updated", {"id": 1})
    snap = hub.get_poll_snapshot("jobs")
    assert snap["event"] == "updated"
    bundle = RealtimeService().build_poll_bundle(["jobs"])
    assert "jobs" in bundle


def test_rule_engine_conditions():
    ctx = {"seccion": "21", "monto": 20000}
    spec = {
        "mode": "all",
        "conditions": [
            {"field": "seccion", "op": "eq", "value": "21"},
            {"field": "monto", "op": "gt", "value": 15000},
        ],
    }
    assert _eval_conditions(spec, ctx) is True


def test_ai_ops_classify():
    r = AiOpsService().classify_incident("SharePoint upload failed")
    assert r["category"] == "integration"


def test_feature_flag_defaults_without_db():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None
    assert FeatureFlagService().is_enabled(db, "realtime_ws") is True
    assert FeatureFlagService().is_enabled(db, "unknown_flag_xyz") is False


def test_realtime_poll_api():
    client = TestClient(web_app)
    resp = client.get("/api/realtime/poll?channels=activity,ops")
    assert resp.status_code == 200
    assert "activity" in resp.json()


@patch("app.web.routes.enterprise_advanced.RuleEngine")
def test_admin_rules_page(mock_engine):
    mock_engine.return_value.list_rules.return_value = []
    mock_engine.return_value.seed_defaults.return_value = None
    with patch("app.web.routes.enterprise_advanced.require_login", return_value=None):
        with patch("app.web.routes.enterprise_advanced.require_roles", return_value=None):
            with patch(
                "app.web.routes.enterprise_advanced.get_current_user",
                return_value={"rol": "admin", "company_id": 1},
            ):
                client = TestClient(web_app)
                resp = client.get("/admin/rules")
    assert resp.status_code == 200
    assert "Motor de reglas" in resp.text


@patch("app.web.routes.enterprise_advanced.CalendarService")
def test_calendar_page(mock_cal):
    mock_cal.return_value.calendar_events.return_value = []
    mock_cal.return_value.sla_summary.return_value = {"open": 0, "overdue": 0, "due_soon": 0}
    with patch("app.web.routes.enterprise_advanced.require_login", return_value=None):
        with patch(
            "app.web.routes.enterprise_advanced.get_current_user",
            return_value={"rol": "vendedor", "company_id": 1},
        ):
            client = TestClient(web_app)
            resp = client.get("/calendar")
    assert resp.status_code == 200


def test_rule_engine_evaluate_empty_db():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    fired = RuleEngine().evaluate(db, "sale_validation", {"monto": 1})
    assert fired == []
