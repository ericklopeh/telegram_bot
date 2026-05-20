"""Conciliación comercial BD vs Excel exportado (P20-E)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.sales_reconciliation_service import build_reconciliation_report
from app.web.auth import ROLES_AUTORIZACION_SNTE, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/control/conciliacion")
def conciliacion_comercial(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    report = build_reconciliation_report(db)

    return templates.TemplateResponse(
        request=request,
        name="commercial_reconciliation.html",
        context={
            "usuario": usuario,
            "report": report,
        },
    )
