"""Pruebas P61-P68 — cohesión enterprise."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services.automation_service import AutomationService
from app.services.command_palette_service import CommandPaletteService
from app.services.platform_cohesion_service import PlatformCohesionService, safe_cohesion_emit
from app.services.realtime_service import RealtimeService
from app.services.rule_engine import RuleEngine, _eval_conditions
from app.web.main import web_app


def test_platform_cohesion_emit_mock_db():
    db = MagicMock()
    PlatformCohesionService().emit(
        db,
        action="test_event",
        title="Test",
        entity_type="case",
        entity_id=1,
        skip_automation=True,
    )


def test_safe_cohesion_emit_swallows_errors():
    db = MagicMock()
    db.add.side_effect = RuntimeError("boom")
    safe_cohesion_emit(db, action="x", title="t", entity_type="case")


def test_realtime_notifications_channel():
    RealtimeService().publish_notifications("ping", {"ok": True})
    snap = RealtimeService().build_poll_bundle(["notifications"])
    assert "notifications" in snap


def test_command_palette_actions():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    r = CommandPaletteService().search(db, "")
    assert len(r["actions"]) >= 5


def test_rule_simulator_conditions():
    assert _eval_conditions(
        {"mode": "all", "conditions": [{"field": "monto", "op": "gt", "value": 100}]},
        {"monto": 200},
    )


@patch("app.web.routes.cohesion.SupervisorCockpitService")
def test_cockpit_page(mock_cockpit):
    mock_cockpit.return_value.build.return_value = {
        "kpis": {"casos_criticos": 0},
        "critical_cases": [],
        "activity": [],
        "seller_heatmap": [],
        "recovery_links": [],
        "sp_failed": [],
        "failed_jobs": [],
        "failed_imports": [],
    }
    with patch("app.web.routes.cohesion.require_login", return_value=None):
        with patch("app.web.routes.cohesion.require_roles", return_value=None):
            with patch(
                "app.web.routes.cohesion.get_current_user",
                return_value={"rol": "admin", "company_id": 1},
            ):
                client = TestClient(web_app)
                resp = client.get("/supervisor/cockpit")
    assert resp.status_code == 200
    assert "Centro operacional" in resp.text


def test_command_palette_api():
    with patch("app.web.routes.cohesion.require_login", return_value=None):
        with patch("app.web.routes.cohesion.CommandPaletteService") as mock_cp:
            mock_cp.return_value.search.return_value = {"actions": [], "groups": []}
            client = TestClient(web_app)
            resp = client.get("/api/command-palette?q=dash")
    assert resp.status_code == 200


def test_automation_process_empty():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    assert AutomationService().process_trigger(db, "unknown_trigger", {}) == []


def test_rule_engine_evaluate_empty():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    assert RuleEngine().evaluate(db, "sale_validation", {"monto": 1}) == []
