"""Rutas web: listado de autorizaciones SNTE aprobadas/generadas."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.web.auth import get_current_user, require_login
from app.web.paths import TEMPLATES_DIR
from app.web.services.approved_authorizations import (
    list_approved_authorizations,
    list_filter_options,
)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/autorizaciones/aprobadas")
def autorizaciones_aprobadas(
    request: Request,
    db: Session = Depends(get_web_db),
    q: str | None = Query(default=None, description="Cliente, RFC o folio"),
    vendedor: str | None = Query(default=None),
    qna: str | None = Query(default=None),
    fecha_desde: str | None = Query(default=None),
    fecha_hasta: str | None = Query(default=None),
    tipo_venta: str | None = Query(default=None),
    estado: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    filtros = {
        "q": q or "",
        "vendedor": vendedor or "",
        "qna": qna or "",
        "fecha_desde": fecha_desde or "",
        "fecha_hasta": fecha_hasta or "",
        "tipo_venta": tipo_venta or "",
        "estado": estado or "",
    }
    filas = list_approved_authorizations(
        db,
        usuario,
        q=q,
        vendedor=vendedor,
        qna=qna,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo_venta=tipo_venta,
        estado=estado,
    )
    opciones = list_filter_options(db, usuario)

    return templates.TemplateResponse(
        request=request,
        name="approved_authorizations.html",
        context={
            "usuario": usuario,
            "filas": filas,
            "filtros": filtros,
            "opciones": opciones,
            "total": len(filas),
        },
    )
