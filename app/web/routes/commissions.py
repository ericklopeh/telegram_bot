"""Vista y operaciones de comisiones (P21)."""

from __future__ import annotations

import urllib.parse
from typing import Generator

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from app.db.session import get_db_session
from app.models.commission import PAYMENT_STATUS_CANCELLED, PAYMENT_STATUS_PAID, PAYMENT_STATUS_PENDING
from app.repositories.commission_repository import CommissionRepository
from app.services.commission_export_service import build_commission_excel, build_commission_pdf
from app.services.commission_service import CommissionService, CommissionServiceError
from app.web.auth import (
    ROLES_AUTORIZACION_SNTE,
    get_current_user,
    require_login,
    require_roles,
    web_should_scope_vendedor_cases,
)
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

PAYMENT_STATUS_LABELS = {
    PAYMENT_STATUS_PENDING: "Pendiente",
    PAYMENT_STATUS_PAID: "Pagada",
    PAYMENT_STATUS_CANCELLED: "Cancelada",
}


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _export_filters(
    *,
    vendedor: str | None,
    qna: str | None,
    semana: str | None,
    estado: str | None,
) -> dict:
    return {
        "seller_name": vendedor or None,
        "qna": qna or None,
        "week": semana or None,
        "payment_status": estado or None,
    }


@router.get("/comisiones")
def listar_comisiones(
    request: Request,
    db: Session = Depends(get_web_db),
    vendedor: str | None = Query(default=None),
    qna: str | None = Query(default=None),
    semana: str | None = Query(default=None),
    estado: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if web_should_scope_vendedor_cases(usuario or {}):
        vendedor = usuario.get("nombre")

    filtros = _export_filters(vendedor=vendedor, qna=qna, semana=semana, estado=estado)
    comisiones = CommissionRepository.list_commissions(db, **filtros)
    svc = CommissionService()
    dashboard = svc.build_dashboard_payload(db)

    return templates.TemplateResponse(
        request=request,
        name="commissions_list.html",
        context={
            "usuario": usuario,
            "comisiones": comisiones,
            "dashboard": dashboard,
            "vendedores": CommissionRepository.list_sellers(db),
            "semanas": CommissionRepository.list_weeks(db),
            "filtros": {
                "vendedor": vendedor or "",
                "qna": qna or "",
                "semana": semana or "",
                "estado": estado or "",
            },
            "payment_status_labels": PAYMENT_STATUS_LABELS,
            "can_manage": (usuario or {}).get("rol") in ROLES_AUTORIZACION_SNTE,
            "success_msg": request.query_params.get("success"),
            "error_msg": request.query_params.get("error"),
        },
    )


@router.get("/comisiones/exportar/excel")
def exportar_comisiones_excel(
    request: Request,
    db: Session = Depends(get_web_db),
    vendedor: str | None = Query(default=None),
    qna: str | None = Query(default=None),
    semana: str | None = Query(default=None),
    estado: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if web_should_scope_vendedor_cases(usuario or {}):
        vendedor = usuario.get("nombre")

    path = build_commission_excel(
        db, **_export_filters(vendedor=vendedor, qna=qna, semana=semana, estado=estado)
    )
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/comisiones/exportar/pdf")
def exportar_comisiones_pdf(
    request: Request,
    db: Session = Depends(get_web_db),
    vendedor: str | None = Query(default=None),
    qna: str | None = Query(default=None),
    semana: str | None = Query(default=None),
    estado: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if web_should_scope_vendedor_cases(usuario or {}):
        vendedor = usuario.get("nombre")

    pdf_bytes = build_commission_pdf(
        db, **_export_filters(vendedor=vendedor, qna=qna, semana=semana, estado=estado)
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="comisiones_resumen.pdf"'},
    )


@router.post("/comisiones/{commission_id}/marcar-pagada")
async def marcar_comision_pagada(
    commission_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
    notes: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    svc = CommissionService()
    try:
        svc.mark_paid(db, commission_id, usuario or {}, notes=notes or None)
        db.commit()
        msg = urllib.parse.quote("Comisión marcada como pagada.")
        return RedirectResponse(url=f"/comisiones?success={msg}", status_code=302)
    except CommissionServiceError as exc:
        db.rollback()
        err = urllib.parse.quote(str(exc))
        return RedirectResponse(url=f"/comisiones?error={err}", status_code=302)


@router.post("/comisiones/{commission_id}/cancelar")
async def cancelar_comision(
    commission_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
    notes: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    svc = CommissionService()
    try:
        svc.cancel(db, commission_id, usuario or {}, notes=notes or None)
        db.commit()
        msg = urllib.parse.quote("Comisión cancelada.")
        return RedirectResponse(url=f"/comisiones?success={msg}", status_code=302)
    except CommissionServiceError as exc:
        db.rollback()
        err = urllib.parse.quote(str(exc))
        return RedirectResponse(url=f"/comisiones?error={err}", status_code=302)
