"""Vista web: control comercial (ventas, contratos, autorizaciones) — P18."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.commercial_report_service import build_commercial_report_payload
from app.web.auth import get_current_user, require_login, web_should_scope_vendedor_cases
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/reportes/comercial")
def control_comercial(
    request: Request,
    db: Session = Depends(get_web_db),
    tab: str = Query(default="ventas"),
    ventas_vendedor: str | None = Query(default=None),
    ventas_qna: str | None = Query(default=None),
    ventas_semana: str | None = Query(default=None),
    ventas_cliente: str | None = Query(default=None),
    ventas_rfc: str | None = Query(default=None),
    ventas_tipo: str | None = Query(default=None),
    contratos_vendedor: str | None = Query(default=None),
    contratos_qna: str | None = Query(default=None),
    contratos_cliente: str | None = Query(default=None),
    contratos_folio: str | None = Query(default=None),
    auth_q: str | None = Query(default=None),
    auth_vendedor: str | None = Query(default=None),
    auth_qna: str | None = Query(default=None),
    auth_desde: str | None = Query(default=None),
    auth_hasta: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)

    if web_should_scope_vendedor_cases(usuario or {}):
        nombre = (usuario or {}).get("nombre")
        if nombre:
            if not ventas_vendedor:
                ventas_vendedor = nombre
            if not contratos_vendedor:
                contratos_vendedor = nombre
            if not auth_vendedor:
                auth_vendedor = nombre

    payload = build_commercial_report_payload(
        db,
        usuario,
        tab=tab,
        ventas_vendedor=ventas_vendedor,
        ventas_qna=ventas_qna,
        ventas_semana=ventas_semana,
        ventas_cliente=ventas_cliente,
        ventas_rfc=ventas_rfc,
        ventas_tipo=ventas_tipo,
        contratos_vendedor=contratos_vendedor,
        contratos_qna=contratos_qna,
        contratos_cliente=contratos_cliente,
        contratos_folio=contratos_folio,
        auth_q=auth_q,
        auth_vendedor=auth_vendedor,
        auth_qna=auth_qna,
        auth_desde=auth_desde,
        auth_hasta=auth_hasta,
    )

    filtros = {
        "tab": payload["tab"],
        "ventas_vendedor": ventas_vendedor or "",
        "ventas_qna": ventas_qna or "",
        "ventas_semana": ventas_semana or "",
        "ventas_cliente": ventas_cliente or "",
        "ventas_rfc": ventas_rfc or "",
        "ventas_tipo": ventas_tipo or "",
        "contratos_vendedor": contratos_vendedor or "",
        "contratos_qna": contratos_qna or "",
        "contratos_cliente": contratos_cliente or "",
        "contratos_folio": contratos_folio or "",
        "auth_q": auth_q or "",
        "auth_vendedor": auth_vendedor or "",
        "auth_qna": auth_qna or "",
        "auth_desde": auth_desde or "",
        "auth_hasta": auth_hasta or "",
    }

    return templates.TemplateResponse(
        request=request,
        name="commercial_reports.html",
        context={
            "usuario": usuario,
            "filtros": filtros,
            "payload": payload,
            "ventas": payload["ventas"],
            "contratos": payload["contratos"],
            "autorizaciones": payload["autorizaciones"],
            "opciones_ventas": payload["opciones_ventas"],
            "opciones_contratos": payload["opciones_contratos"],
            "opciones_auth": payload["opciones_auth"],
            "limit": payload["limit"],
        },
    )
