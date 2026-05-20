"""Panel administrativo del workflow P22."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.case_event import CaseEvent
from app.services.case_event_service import (
    WORKFLOW_DEPENDENCY_MISSING,
    WORKFLOW_TRANSITION_BLOCKED,
)
from app.services.workflow_state_service import WORKFLOW_STATE_LABELS, WORKFLOW_LINEAR_ORDER
from app.services.workflow_transition_service import ALLOWED_TRANSITIONS as TRANS_MAP
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


@router.get("/admin/workflow")
def admin_workflow_panel(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    blocked = list(
        db.scalars(
            select(CaseEvent)
            .where(
                CaseEvent.event_type.in_(
                    (WORKFLOW_TRANSITION_BLOCKED, WORKFLOW_DEPENDENCY_MISSING)
                )
            )
            .order_by(CaseEvent.created_at.desc())
            .limit(30)
        ).all()
    )

    transitions_display = []
    for src in WORKFLOW_LINEAR_ORDER:
        targets = sorted(TRANS_MAP.get(src, frozenset()))
        if targets:
            transitions_display.append(
                {
                    "from": WORKFLOW_STATE_LABELS.get(src, src),
                    "to": [WORKFLOW_STATE_LABELS.get(t, t) for t in targets],
                }
            )
    transitions_display.append(
        {
            "from": "En compulsa",
            "to": ["Aprobado", "Corrección", "Rechazado"],
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin_workflow.html",
        context={
            "usuario": usuario,
            "states": [(s, WORKFLOW_STATE_LABELS.get(s, s)) for s in WORKFLOW_LINEAR_ORDER],
            "transitions": transitions_display,
            "blocked_events": blocked,
            "snte_rule": "SNTE solo tras APROBADO (compulsa OK). No en PREP_AUTORIZACION.",
        },
    )
