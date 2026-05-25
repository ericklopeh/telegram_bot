"""Pruebas P35 — dashboard operacional (UI, sin lógica de negocio)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.domain import constants as C
from app.models.case import Case
from app.web.main import web_app
from app.web.services.dashboard_ui_service import (
    build_hero_kpis,
    build_ops_alert_rows,
    build_ops_center_items,
    build_pipeline_columns,
    build_recent_cases_rows,
    enrich_pipeline_with_cases,
)

_SAMPLE_METRICAS = {
    "total_abiertos": 12,
    "pendientes_autorizacion": 3,
    "autorizaciones_generadas": 5,
    "pendientes_compulsa": 2,
    "compulsa_ok": 7,
    "prep_sin_excel_snte": 1,
    "docs_upload_failed": 4,
    "docs_pending_upload": 6,
    "pedidos_checklist_incompleto": 8,
    "pedidos_checklist_incompleto_capped": False,
    "sla_abiertos_sin_act_24h": 2,
    "sla_prep_aut_mas_24h": 1,
    "sla_compulsa_mas_24h": 0,
}

_SAMPLE_DAILY = {
    "nuevos_casos": 1,
    "listos_autorizacion": 2,
    "pendientes_ocr": 0,
    "sharepoint_fallidos": 1,
    "stale_24h": 2,
}


def _case_row(**kwargs) -> dict:
    case = Case(
        id=kwargs.get("id", 1),
        public_id=kwargs.get("public_id", "PED-1"),
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name=kwargs.get("client_name", "Cliente"),
        current_status=kwargs.get("status", C.ST_PED_PREP_AUT),
        visible_status=C.VISIBLE_EN_PEDIDO,
        week_code="SEM_1",
        folder_path="/tmp",
        seller_name="V",
    )
    case.updated_at = datetime(2026, 5, 19, tzinfo=timezone.utc)
    return {
        "case": case,
        "siguiente_accion": kwargs.get("action", "seguimiento"),
        "sharepoint_estado": kwargs.get("sp", "—"),
        "checklist_ok": kwargs.get("checklist_ok", True),
        "autorizacion_generada": False,
        "sin_avance_24h": kwargs.get("stale", False),
        "antiguedad_label": "2 h",
    }


def test_build_hero_kpis_six_items_with_trends():
    kpis = build_hero_kpis(_SAMPLE_METRICAS, _SAMPLE_DAILY)
    assert len(kpis) == 6
    assert all(k.trend for k in kpis)
    assert all(k.spark_value >= 0 for k in kpis)
    assert all(k.spark_color for k in kpis)
    assert kpis[0].key == "abiertos"


def test_build_pipeline_columns_six_stages():
    cols = build_pipeline_columns(_SAMPLE_METRICAS)
    assert len(cols) == 6
    assert cols[0].short_label == "PREP AUT"


def test_enrich_pipeline_assigns_cases():
    cols = build_pipeline_columns(_SAMPLE_METRICAS)
    rows = [
        _case_row(id=1, public_id="A", status=C.ST_PED_PREP_AUT),
        _case_row(id=2, public_id="B", sp="fallido", action="error SharePoint"),
    ]
    enriched = enrich_pipeline_with_cases(cols, rows)
    prep = next(c for c in enriched if c.key == "prep_aut")
    sp = next(c for c in enriched if c.key == "sharepoint")
    assert len(prep.recent_cases) >= 1
    assert sp.recent_cases[0].public_id == "B"
    assert sp.recent_cases[0].sla_tone in ("danger", "warn", "success")


def test_build_ops_alert_rows_from_alerts():
    alert = MagicMock(
        alert_type="sharepoint_failed",
        severity="danger",
        message="Fallo de subida",
        case_id=9,
        case=MagicMock(public_id="PED-9"),
        updated_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
    )
    rows = build_ops_alert_rows([alert], _SAMPLE_METRICAS, _SAMPLE_DAILY)
    assert rows[0]["severity_label"] == "Crítico"
    assert rows[0]["case_label"] == "PED-9"
    assert rows[0]["recovery_href"]
    assert rows[0]["time_label"]


def test_build_ops_center_items():
    items = build_ops_center_items(_SAMPLE_METRICAS, _SAMPLE_DAILY)
    assert any(i["key"] == "sp_failed" for i in items)


def test_build_recent_cases_rows_stage_labels():
    rows = build_recent_cases_rows([_case_row(public_id="PED-X")], limit=5)
    assert rows[0]["stage_label"]
    assert rows[0]["stage_tone"]
    assert rows[0]["time_ago"]
    assert rows[0]["sla_badge"] in ("24h+", "OK")


@patch("app.web.routes.dashboard.NotificationRuleEngine")
@patch("app.web.routes.dashboard._build_resumen_vendedores", return_value=[])
@patch("app.web.routes.dashboard._build_pending_table", return_value=[])
@patch("app.web.routes.dashboard._build_metrics")
def test_dashboard_p35_sections_render(mock_metrics, _pend, _resumen, mock_engine_cls):
    mock_metrics.return_value = {
        **_SAMPLE_METRICAS,
        "por_estado": [],
        "sla_edad_media_abiertos_horas": 10.5,
        "sla_caso_mas_antiguo_abierto": None,
    }
    mock_engine_cls.return_value.get_active_alerts_for_dashboard.return_value = ([], _SAMPLE_DAILY)

    with patch("app.web.routes.dashboard.require_login", return_value=None):
        with patch(
            "app.web.routes.dashboard.get_current_user",
            return_value={"nombre": "Admin", "rol": "admin"},
        ):
            client = TestClient(web_app)
            resp = client.get("/dashboard")

    assert resp.status_code == 200
    html = resp.text
    assert "dash-hero-kpi" in html
    assert "dash-kanban-col" in html
    assert "dash-alert-list" in html
    assert "dash-summary-grid" in html
    assert "dash-charts-grid" in html
    assert "dash-hero-spark-canvas" in html
    assert "data-spark-value" in html
    assert "Recovery" in html
    assert "Casos recientes" in html
    assert "Pipeline operacional" in html


@patch("app.web.routes.dashboard.NotificationRuleEngine")
@patch("app.web.routes.dashboard._build_resumen_vendedores", return_value=[])
@patch("app.web.routes.dashboard._build_pending_table", return_value=[])
@patch("app.web.routes.dashboard._build_metrics")
def test_dashboard_navigation_links_intact(mock_metrics, _pend, _resumen, mock_engine_cls):
    mock_metrics.return_value = {
        **_SAMPLE_METRICAS,
        "por_estado": [],
        "sla_edad_media_abiertos_horas": None,
        "sla_caso_mas_antiguo_abierto": None,
    }
    mock_engine_cls.return_value.get_active_alerts_for_dashboard.return_value = ([], {})

    with patch("app.web.routes.dashboard.require_login", return_value=None):
        with patch(
            "app.web.routes.dashboard.get_current_user",
            return_value={"nombre": "T", "rol": "admin"},
        ):
            client = TestClient(web_app)
            resp = client.get("/dashboard?filter=prep_aut")

    assert resp.status_code == 200
    assert 'href="/dashboard?filter=prep_aut"' in resp.text
    assert 'href="/casos"' in resp.text
    assert 'href="/erp/dashboard"' in resp.text


def test_dashboard_requires_login_without_session():
    client = TestClient(web_app)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (302, 307, 401, 403)
