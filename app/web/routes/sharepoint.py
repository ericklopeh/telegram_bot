"""Rutas SharePoint / Graph P25."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.models.case import Case
from app.services.sharepoint_graph_client import GraphConfigError
from app.services.sharepoint_sync_service import SharePointSyncService
from app.web.auth import ROLES_ADMIN_SISTEMAS, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
log = logging.getLogger(__name__)
_sync = SharePointSyncService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.post("/casos/{case_id}/sharepoint/sync")
def sync_case_sharepoint(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    try:
        results = _sync.sync_case_documents(
            db,
            case_id,
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
        )
        db.commit()
        ok_n = sum(1 for r in results if r.ok)
        fail_n = len(results) - ok_n
        msg = f"Sincronización: {ok_n} OK, {fail_n} fallidos."
        return RedirectResponse(
            url=f"/casos/{case_id}/documentos?success={urllib.parse.quote(msg)}",
            status_code=302,
        )
    except GraphConfigError as exc:
        db.rollback()
        return RedirectResponse(
            url=f"/casos/{case_id}/documentos?error={urllib.parse.quote(str(exc))}",
            status_code=302,
        )


@router.post("/casos/{case_id}/sharepoint/retry")
def retry_case_sharepoint(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    results = _sync.retry_failed_for_case(
        db,
        case_id,
        actor_user_id=usuario.get("id"),
        actor_role=usuario.get("rol"),
    )
    db.commit()
    msg = f"Reintentos: {sum(1 for r in results if r.ok)} OK de {len(results)}."
    return RedirectResponse(
        url=f"/casos/{case_id}/documentos?success={urllib.parse.quote(msg)}",
        status_code=302,
    )


@router.get("/admin/sharepoint")
def admin_sharepoint_panel(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    buckets = _sync.list_admin_buckets(db)
    config_error = None
    try:
        _sync.graph.validate_config()
    except GraphConfigError as exc:
        config_error = str(exc)

    def _enrich(docs):
        out = []
        for d in docs:
            case = db.get(Case, d.case_id)
            out.append({"doc": d, "case": case})
        return out

    return templates.TemplateResponse(
        request=request,
        name="admin_sharepoint.html",
        context={
            "usuario": usuario,
            "pending": _enrich(buckets["pending"]),
            "failed": _enrich(buckets["failed"]),
            "ok_recent": _enrich(buckets["ok"]),
            "config_error": config_error,
        },
    )


@router.post("/admin/sharepoint/retry-failed")
def admin_retry_failed_sharepoint(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    results = _sync.retry_all_failed(
        db,
        actor_user_id=usuario.get("id"),
        actor_role=usuario.get("rol"),
    )
    db.commit()
    msg = f"Reintentados {len(results)} documentos; OK: {sum(1 for r in results if r.ok)}."
    return RedirectResponse(
        url=f"/admin/sharepoint?success={urllib.parse.quote(msg)}",
        status_code=302,
    )
