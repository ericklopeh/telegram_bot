"""P69 — estabilización: smoke, realtime, jobs, performance, flags."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.log_safety import SecretScrubFilter
from app.services.feature_flag_service import FeatureFlagService
from app.services.job_service import JobService
from app.services.performance_service import PerformanceService
from app.services.realtime_service import RealtimeHub, RealtimeService
from app.web.main import web_app


def test_secret_scrub_filter():
    f = SecretScrubFilter()
    rec = type("R", (), {"msg": "password=secret token=abc", "args": ()})()
    assert f.filter(rec) is True
    assert "secret" not in str(rec.msg)


def test_realtime_hub_cleanup_and_heartbeat():
    hub = RealtimeHub()
    hub.publish("activity", "test", {"x": 1})
    assert hub.cleanup_stale_subscribers() >= 0
    hb = hub.heartbeat()
    assert hb["event"] == "ping"
    snap = RealtimeService().build_poll_bundle(["activity"])
    assert "activity" in snap


def test_realtime_rate_limit_safe_publish():
    hub = RealtimeHub()
    for i in range(5):
        hub.publish("activity", f"e{i}", {"n": i})
    assert hub.get_poll_snapshot("activity")["event"] == "e4"


def test_job_reconcile_stale_mock():
    db = MagicMock()
    stale_job = MagicMock()
    stale_job.id = 1
    stale_job.status = "running"
    stale_job.error_message = None
    db.scalars.return_value.all.return_value = [stale_job]
    n = JobService().reconcile_stale_jobs(db)
    assert n == 1
    assert stale_job.status == "pending"


def test_job_cancel_mock():
    db = MagicMock()
    job = MagicMock()
    job.status = "pending"
    job.id = 5
    db.get.return_value = job
    out = JobService().cancel_job(db, 5)
    assert out.status == "cancelled"


def test_performance_summary():
    summary = PerformanceService().build_summary()
    assert "slow_query_threshold_ms" in summary
    assert "caps" in summary


def test_feature_flag_warnings():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None
    warnings = FeatureFlagService().validate_defaults(db)
    assert isinstance(warnings, list)


def test_performance_summary_route():
    with patch("app.web.routes.cohesion.require_login", return_value=None):
        with patch("app.web.routes.cohesion.require_roles", return_value=None):
            client = TestClient(web_app)
            resp = client.get("/admin/performance/summary")
    assert resp.status_code == 200
    assert "generated_at" in resp.json()


def test_realtime_poll_endpoint():
    client = TestClient(web_app)
    resp = client.get("/api/realtime/poll?channels=heartbeat,activity")
    assert resp.status_code == 200
    data = resp.json()
    assert "heartbeat" in data


def test_smoke_script_exists_and_compiles():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "smoke_check_web.py"
    assert path.is_file()
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "def main" in source
