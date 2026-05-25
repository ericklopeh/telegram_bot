"""Rutas ERP consolidado (P27)."""

from __future__ import annotations

import urllib.parse
from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db_session
from app.models.erp_payment import ErpPayment
from app.services.contract_financial_service import ContractFinancialService
from app.services.erp_export_service import ErpExportService
from app.services.erp_reconciliation_service import ErpReconciliationService
from app.services.erp_search_service import ErpSearchService
from app.web.auth import ROLES_ADMIN_SISTEMAS, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/erp/dashboard")
def erp_dashboard(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    kpis = ContractFinancialService().build_dashboard_kpis(db)
    recent = list(
        db.scalars(
            select(ErpPayment).order_by(ErpPayment.created_at.desc()).limit(15)
        ).all()
    )
    q = request.query_params.get("q", "")
    search_hits = ErpSearchService().search(db, q) if q else []

    return templates.TemplateResponse(
        request=request,
        name="erp_dashboard.html",
        context={
            "usuario": usuario,
            "kpis": kpis,
            "recent_payments": recent,
            "search_q": q,
            "search_hits": search_hits,
        },
    )


@router.get("/erp/conciliacion")
def erp_conciliacion(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    report = ErpReconciliationService().build_report(db)
    export_msg = request.query_params.get("export")

    return templates.TemplateResponse(
        request=request,
        name="erp_conciliacion.html",
        context={
            "usuario": usuario,
            "report": report,
            "export_msg": export_msg,
        },
    )


@router.post("/erp/export/ejecutivo")
def erp_export_ejecutivo(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_executive_summary(db)
    return RedirectResponse(
        url=f"/erp/dashboard?success={urllib.parse.quote(f'Export: {path.name}')}",
        status_code=302,
    )


@router.post("/erp/export/vendedores")
def erp_export_vendedores(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_vendedor_summary(db)
    return RedirectResponse(
        url=f"/erp/dashboard?success={urllib.parse.quote(f'Vendedores: {path.name}')}",
        status_code=302,
    )


@router.post("/erp/export/recovery")
def erp_export_recovery(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_recovery(db)
    return RedirectResponse(
        url=f"/erp/dashboard?success={urllib.parse.quote(f'Recovery: {path.name}')}",
        status_code=302,
    )


@router.post("/erp/export/refin")
def erp_export_refin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_refinance(db)
    return RedirectResponse(
        url=f"/erp/dashboard?success={urllib.parse.quote(f'Refin: {path.name}')}",
        status_code=302,
    )


@router.post("/erp/export/cobranza")
def erp_export_cobranza(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_cobranza(db)
    return RedirectResponse(
        url=f"/erp/dashboard?success={urllib.parse.quote(f'Cobranza: {path.name}')}",
        status_code=302,
    )


@router.post("/erp/conciliacion/export")
def erp_export_conciliacion(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied
    path = ErpExportService().export_reconciliation(db)
    return RedirectResponse(
        url=f"/erp/conciliacion?export={urllib.parse.quote(str(path))}",
        status_code=302,
    )
