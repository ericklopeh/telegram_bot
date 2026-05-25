"""Pruebas P36-P45 — plataforma enterprise."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.v1.auth import generate_token, hash_token
from app.services.global_search_service import GlobalSearchService
from app.services.job_service import JOB_TYPES, JobService
from app.services.performance_service import PerformanceService, paginate
from app.services.tenant_service import TenantService
from app.web.main import web_app


def test_paginate_and_cache():
    items = list(range(30))
    page = paginate(items, page=2, page_size=10)
    assert page.total == 30
    assert len(page.items) == 10
    assert page.page == 2

    perf = PerformanceService()
    perf.cached("k1", lambda: {"a": 1}, ttl=60)
    assert perf.cached("k1", lambda: {"b": 2}, ttl=60)["a"] == 1


def test_job_types_registry():
    assert "sharepoint_sync" in JOB_TYPES
    assert "bi_refresh" in JOB_TYPES


def test_global_search_short_query():
    db = MagicMock()
    result = GlobalSearchService().search(db, "a")
    assert result["total"] == 0
    assert result["groups"] == []


def test_tenant_default_context():
    ctx = TenantService().default_context()
    assert ctx.company_id >= 1
    assert ctx.branch_id >= 1


def test_api_token_hash():
    raw, hashed = generate_token()
    assert hash_token(raw) == hashed
    assert len(raw) > 20


@patch("app.web.routes.platform.JobService")
def test_jobs_page_renders(mock_job_svc):
    mock_job_svc.return_value.list_jobs.return_value = []
    with patch("app.web.routes.platform.require_login", return_value=None):
        with patch("app.web.routes.platform.require_roles", return_value=None):
            with patch(
                "app.web.routes.platform.get_current_user",
                return_value={"nombre": "Admin", "rol": "admin"},
            ):
                client = TestClient(web_app)
                resp = client.get("/jobs")
    assert resp.status_code == 200
    assert "Cola de trabajos" in resp.text


@patch("app.web.routes.platform.GlobalSearchService")
def test_search_page(mock_search):
    mock_search.return_value.search.return_value = {
        "query": "PED",
        "groups": [{"key": "cases", "label": "Casos", "count": 1, "entries": []}],
        "total": 1,
    }
    with patch("app.web.routes.platform.require_login", return_value=None):
        with patch(
            "app.web.routes.platform.get_current_user",
            return_value={"nombre": "T", "rol": "vendedor"},
        ):
            client = TestClient(web_app)
            resp = client.get("/search?q=PED")
    assert resp.status_code == 200
    assert "Búsqueda global" in resp.text


def test_api_v1_health_public():
    client = TestClient(web_app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["version"] == "v1"


def test_api_v1_requires_token():
    client = TestClient(web_app)
    resp = client.get("/api/v1/casos")
    assert resp.status_code == 401


@patch("app.web.routes.platform.RoleDashboardService")
def test_mi_dashboard(mock_role):
    mock_role.return_value.build_vendor_dashboard.return_value = {
        "role": "vendedor",
        "kpis": {"mis_casos": 2},
        "cases": [],
        "sla_alerts": [],
    }
    with patch("app.web.routes.platform.require_login", return_value=None):
        with patch(
            "app.web.routes.platform.get_current_user",
            return_value={"nombre": "V", "rol": "vendedor", "id": 1},
        ):
            client = TestClient(web_app)
            resp = client.get("/mi-dashboard")
    assert resp.status_code == 200
    assert "Mi operación" in resp.text


def test_job_enqueue_invalid_type():
    db = MagicMock()
    try:
        JobService().enqueue(db, "invalid_type_xyz")
        assert False, "expected ValueError"
    except ValueError:
        pass
