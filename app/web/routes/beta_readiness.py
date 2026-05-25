"""Pantalla beta readiness (P34)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.beta_readiness_service import BetaReadinessService
from app.services.beta_safe_mode_service import BetaSafeModeService
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


@router.get("/admin/beta-readiness")
def beta_readiness_page(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    report = BetaReadinessService().build_report(db)
    safe = BetaSafeModeService()

    return templates.TemplateResponse(
        request=request,
        name="beta_readiness.html",
        context={
            "usuario": usuario,
            "report": report,
            "safe_svc": safe,
        },
    )
