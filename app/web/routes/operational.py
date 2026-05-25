"""Revisión operativa y UX (P31)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.web.auth import get_current_user, require_login
from app.web.jinja_helpers import register_web_template_filters
from app.web.paths import TEMPLATES_DIR
from app.web.services.operational_review_service import OperationalReviewService

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
register_web_template_filters(templates)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/operacion/revision")
def revision_operativa(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    report = OperationalReviewService().build_report(db)

    return templates.TemplateResponse(
        request=request,
        name="operational_review.html",
        context={
            "usuario": usuario,
            "report": report,
        },
    )
