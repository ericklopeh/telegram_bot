"""P81 — consulta de auditoría RBAC (admin)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.security.rbac import Permission
from app.services.compliance_service import ComplianceService
from app.services.rbac_service import RbacService
from app.web.auth import get_current_user, require_login
from app.web.paths import TEMPLATES_DIR
from app.web.rbac_helpers import rbac_flags_for_user, require_permission

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_compliance = ComplianceService()
_rbac = RbacService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/admin/audit")
def audit_log(
    request: Request,
    db: Session = Depends(get_web_db),
    limit: int = 100,
):
    denied = require_login(request, db)
    if denied:
        return denied
    perm_denied = require_permission(
        request,
        db,
        Permission.VIEW_AUDIT,
        action="view_audit_log",
        entity_type="audit",
    )
    if perm_denied:
        return perm_denied

    usuario = get_current_user(request, db)
    company_id = (usuario or {}).get("company_id") or 1
    entries = _compliance.list_audit(db, limit=min(limit, 500), company_id=company_id)

    return templates.TemplateResponse(
        request=request,
        name="rbac_audit.html",
        context={
            "usuario": usuario,
            "entries": entries,
            "rbac_flags": rbac_flags_for_user(usuario),
            "limit": limit,
        },
    )
