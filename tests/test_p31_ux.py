"""Pruebas P31 — UX operativa y revisión guiada."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.domain import constants as C
from app.models.case import Case
from app.services.action_guard_service import CaseActionState
from app.services.case_document_service import DocumentSummary
from app.services.excel_path_guard import is_under_excel_masters
from app.web.main import web_app
from app.web.services.case_guided_flow import build_case_guided_flow
from app.web.services.operational_review_service import OperationalReviewService, ReviewItem
from app.web.services.operational_tracking import ACCION_FALTA_PEDIDO
from app.web.services.user_friendly_errors import friendly_error_message


def _case() -> Case:
    c = Case(
        id=9,
        public_id="PED-UX",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Cliente UX",
        current_status=C.ST_PED_RECIBIDO,
        visible_status=C.VISIBLE_EN_PEDIDO,
        week_code="SEM_10",
        folder_path="/tmp",
        seller_name="Vendedor",
    )
    c.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    c.updated_at = datetime(2026, 5, 19, tzinfo=timezone.utc)
    return c


def _guard(**kwargs) -> CaseActionState:
    defaults = dict(
        case_id=9,
        public_id="PED-UX",
        order_type=C.ORDER_TYPE_MUEBLE,
        current_status=C.ST_PED_RECIBIDO,
        missing_doc_types=[C.DOC_PEDIDO],
    )
    defaults.update(kwargs)
    return CaseActionState(**defaults)


@patch("app.web.services.case_guided_flow.build_tracking_contexts")
def test_guided_flow_suggests_document_upload(mock_ctx):
    case = _case()
    ctx = MagicMock()
    ctx.present = set()
    ctx.sp_failed = False
    ctx.sharepoint_estado = "pendiente"
    mock_ctx.return_value = {9: ctx}

    db = MagicMock()
    db.scalar.return_value = None
    case_svc = MagicMock()

    flow = build_case_guided_flow(
        db,
        case,
        _guard(),
        doc_summary=DocumentSummary(complete=0, pending=0, invalid=0, missing=2),
        case_svc=case_svc,
    )
    assert "pedido" in flow.next_action.lower() or "documento" in flow.next_action.lower()
    assert "/casos/9/documentos" in flow.cta_url
    assert flow.missing_docs_labels


def test_friendly_error_graph():
    msg = friendly_error_message("GraphApiError 403 Forbidden tenant")
    assert "SharePoint" in msg or "Graph" in msg


def test_friendly_error_excel():
    msg = friendly_error_message("registration_failed export excel", category="excel")
    assert "Excel" in msg


@patch.object(OperationalReviewService, "build_report")
def test_operational_revision_page_loads(mock_report):
    mock_report.return_value = MagicMock(
        generated_at=datetime.now(timezone.utc),
        sections={"casos_atorados": []},
        totals={"casos_atorados": 0},
        critical_count=0,
    )
    with patch("app.web.routes.operational.require_login", return_value=None):
        with patch("app.web.routes.operational.get_current_user", return_value={"nombre": "T", "rol": "admin"}):
            client = TestClient(web_app)
            resp = client.get("/operacion/revision")
    assert resp.status_code == 200
    assert "Revisión operativa" in resp.text


def _scalars_result(items):
    m = MagicMock()
    m.all.return_value = items
    return m


@patch("app.web.services.operational_review_service.BiDashboardService")
@patch("app.web.services.operational_review_service.ErpReconciliationService")
def test_operational_review_report_structure(mock_recon_cls, mock_bi_cls):
    svc = OperationalReviewService()
    db = MagicMock()
    stale = _case()
    stale.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    calls = {"n": 0}

    def _scalars(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _scalars_result([stale])
        return _scalars_result([])

    db.scalars.side_effect = _scalars
    db.execute.return_value.all.return_value = []
    mock_recon_cls.return_value.build_report.return_value = MagicMock(issues=[])
    mock_bi_cls.return_value.build_operational_alerts.return_value = []

    report = svc.build_report(db)
    assert report.totals.get("casos_atorados", 0) >= 1


def test_main_pages_return_login_redirect_without_session():
    client = TestClient(web_app)
    for path in ("/casos", "/ventas", "/erp/dashboard", "/bi/dashboard", "/comisiones"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 307, 401, 403)


def test_exports_path_not_excel_masters():
    p = __import__("pathlib").Path("/app/storage/excel_exports/bi/test.xlsx")
    assert not is_under_excel_masters(p)
