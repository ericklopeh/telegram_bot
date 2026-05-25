"""Rutas BI / dashboard ejecutivo (P29)."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Generator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.services.bi_dashboard_service import BiDashboardService
from app.services.bi_export_service import BiExportService
from app.services.bi_filters import BiFilters
from app.services.case_event_service import BI_DASHBOARD_VIEWED
from app.web.auth import get_current_user, require_login
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_log = logging.getLogger(__name__)
_bi = BiDashboardService()
_export = BiExportService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _filters_from_request(request: Request) -> BiFilters:
    qp = request.query_params
    return BiFilters.from_query(
        fecha_desde=qp.get("fecha_desde"),
        fecha_hasta=qp.get("fecha_hasta"),
        semana=qp.get("semana"),
        qna=qp.get("qna"),
        vendedor=qp.get("vendedor"),
        seccion=qp.get("seccion"),
        tipo_venta=qp.get("tipo_venta"),
        workflow_state=qp.get("workflow_state"),
    )


@router.get("/bi/dashboard")
def bi_dashboard(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    filters = _filters_from_request(request)
    payload = _bi.build_dashboard(db, filters)
    _log.info("event=%s user=%s", BI_DASHBOARD_VIEWED, (usuario or {}).get("username"))

    fq = filters.to_query_dict()
    filter_qs = urllib.parse.urlencode(fq) if fq else ""

    return templates.TemplateResponse(
        request=request,
        name="bi_dashboard.html",
        context={
            "usuario": usuario,
            "payload": payload,
            "filters": filters,
            "filter_query": fq,
            "filter_qs": filter_qs,
            "tab": request.query_params.get("tab", "dashboard"),
            "success_msg": request.query_params.get("success"),
        },
    )


@router.get("/bi/alertas")
def bi_alertas(request: Request, db: Session = Depends(get_web_db)):
    """Alias con foco en alertas operativas."""
    redirect = require_login(request, db)
    if redirect:
        return redirect
    q = dict(request.query_params)
    q["tab"] = "alertas"
    return RedirectResponse(url=f"/bi/dashboard?{urllib.parse.urlencode(q)}", status_code=302)


@router.get("/bi/reportes")
def bi_reportes(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    q = dict(request.query_params)
    q["tab"] = "reportes"
    return RedirectResponse(url=f"/bi/dashboard?{urllib.parse.urlencode(q)}", status_code=302)


def _export_redirect(filters: BiFilters, filename: str) -> str:
    q = filters.to_query_dict()
    q["success"] = f"Export: {filename}"
    q["tab"] = "reportes"
    return f"/bi/dashboard?{urllib.parse.urlencode(q)}"


@router.post("/bi/export/resumen")
def bi_export_resumen(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    filters = _filters_from_request(request)
    path = _export.export_dashboard_resumen(db, filters)
    _bi.clear_cache()
    return RedirectResponse(url=_export_redirect(filters, path.name), status_code=302)


@router.post("/bi/export/ventas_vendedor")
def bi_export_ventas_vendedor(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    filters = _filters_from_request(request)
    path = _export.export_ventas_vendedor(db, filters)
    _bi.clear_cache()
    return RedirectResponse(url=_export_redirect(filters, path.name), status_code=302)


@router.post("/bi/export/recovery")
def bi_export_recovery(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    filters = _filters_from_request(request)
    path = _export.export_recovery(db, filters)
    _bi.clear_cache()
    return RedirectResponse(url=_export_redirect(filters, path.name), status_code=302)


@router.post("/bi/export/pendientes")
def bi_export_pendientes(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    filters = _filters_from_request(request)
    path = _export.export_pendientes(db, filters)
    _bi.clear_cache()
    return RedirectResponse(url=_export_redirect(filters, path.name), status_code=302)
