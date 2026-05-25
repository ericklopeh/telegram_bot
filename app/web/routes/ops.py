"""Panel operativo, incidencias y recovery (P33)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.ops_incident import SEVERITY_CRITICAL, SEVERITY_ERROR
from app.services.beta_safe_mode_service import BetaSafeModeService
from app.services.ops_monitor_service import OpsMonitorService
from app.services.ops_recovery_service import OpsRecoveryService
from app.web.auth import ROLES_ADMIN_SISTEMAS, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_monitor = OpsMonitorService()
_recovery = OpsRecoveryService()
_safe = BetaSafeModeService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _redirect_ops(msg: str | None = None, error: str | None = None) -> RedirectResponse:
    url = "/ops"
    if msg:
        url += f"?msg={msg}"
    elif error:
        url += f"?error={error}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/ops")
def ops_dashboard(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    dashboard = _monitor.build_dashboard(db, sync=True)
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="ops_dashboard.html",
        context={
            "usuario": usuario,
            "dashboard": dashboard,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
            "beta_safe_mode": _safe.is_enabled(),
            "phrase_mass_sharepoint": _safe.phrase_mass_sharepoint(),
            "phrase_mass_commissions": _safe.phrase_mass_commissions(),
        },
    )


@router.get("/ops/incidents")
def ops_incidents(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    status_filter = request.query_params.get("status")
    incidents = _monitor.list_incidents(db, status=status_filter, limit=200)

    return templates.TemplateResponse(
        request=request,
        name="ops_incidents.html",
        context={
            "usuario": usuario,
            "incidents": incidents,
            "status_filter": status_filter,
            "msg": request.query_params.get("msg"),
            "beta_safe_mode": _safe.is_enabled(),
            "safe_svc": _safe,
        },
    )


@router.post("/ops/incidents/{incident_id}/ack")
def ops_incident_ack(
    request: Request,
    incident_id: int,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    inc = _recovery.acknowledge_incident(db, incident_id, username=usuario.get("username"))
    if not inc:
        db.rollback()
        return RedirectResponse(url="/ops/incidents?error=Incidencia+no+encontrada", status_code=302)
    db.commit()
    return RedirectResponse(url="/ops/incidents?msg=Incidencia+reconocida", status_code=302)


@router.post("/ops/incidents/{incident_id}/resolve")
def ops_incident_resolve(
    request: Request,
    incident_id: int,
    db: Session = Depends(get_web_db),
    confirm_text: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    inc_row = _monitor.get_incident(db, incident_id)
    if inc_row and inc_row.severity in (SEVERITY_CRITICAL, SEVERITY_ERROR):
        ok, err = _safe.require_confirmation(
            "resolve_critical_incident",
            _safe.phrase_resolve_incident(incident_id),
            confirm_text,
            entity_type="ops_incident",
            entity_id=incident_id,
            username=usuario.get("username"),
        )
        if not ok:
            return RedirectResponse(url=f"/ops/incidents?error={err}", status_code=302)

    inc = _recovery.resolve_incident(db, incident_id, username=usuario.get("username"))
    if not inc:
        db.rollback()
        return RedirectResponse(url="/ops/incidents?error=Incidencia+no+encontrada", status_code=302)
    db.commit()
    return RedirectResponse(url="/ops/incidents?msg=Incidencia+resuelta", status_code=302)


@router.post("/ops/retry/sharepoint")
def ops_retry_sharepoint(
    request: Request,
    db: Session = Depends(get_web_db),
    case_id: int | None = Form(None),
    document_id: int | None = Form(None),
    confirm_text: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    if case_id is None and document_id is None:
        ok, err = _safe.require_confirmation(
            "retry_sharepoint_mass",
            _safe.phrase_mass_sharepoint(),
            confirm_text,
            username=usuario.get("username"),
        )
        if not ok:
            return _redirect_ops(error=err or "Confirmación requerida")

    result = _recovery.retry_sharepoint(
        db,
        case_id=case_id,
        document_id=document_id,
        username=usuario.get("username"),
        user_id=usuario.get("user_id"),
    )
    db.commit()
    if result.ok:
        return _redirect_ops(msg=result.message.replace(" ", "+"))
    return _redirect_ops(error=result.message.replace(" ", "+"))


@router.post("/ops/rebuild/conciliation")
def ops_rebuild_conciliation(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    result = _recovery.rebuild_conciliation(db, username=usuario.get("username"))
    db.commit()
    if result.ok:
        return _redirect_ops(msg="Conciliacion+recalculada")
    return _redirect_ops(error=result.message[:120])


@router.post("/ops/recalculate/commissions")
def ops_recalculate_commissions(
    request: Request,
    db: Session = Depends(get_web_db),
    sale_capture_id: int | None = Form(None),
    confirm_text: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    if sale_capture_id is None:
        ok, err = _safe.require_confirmation(
            "recalculate_commissions_mass",
            _safe.phrase_mass_commissions(),
            confirm_text,
            username=usuario.get("username"),
        )
        if not ok:
            return _redirect_ops(error=err or "Confirmación requerida")

    result = _recovery.recalculate_commissions(
        db,
        sale_capture_id=sale_capture_id,
        user=usuario,
    )
    db.commit()
    if result.ok:
        return _redirect_ops(msg=result.message.replace(" ", "+")[:80])
    return _redirect_ops(error=result.message[:120])


@router.post("/ops/regenerate/export/{sale_capture_id}")
def ops_regenerate_export(
    request: Request,
    sale_capture_id: int,
    db: Session = Depends(get_web_db),
    confirm_text: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    ok, err = _safe.require_confirmation(
        "regenerate_export",
        _safe.phrase_regenerate_export(sale_capture_id),
        confirm_text,
        entity_type="sale_capture",
        entity_id=sale_capture_id,
        username=usuario.get("username"),
    )
    if not ok:
        return _redirect_ops(error=err or "Confirmación requerida")

    result = _recovery.regenerate_sale_export(db, sale_capture_id, user=usuario)
    db.commit()
    if result.ok:
        return _redirect_ops(msg=f"Export+OK+venta+{sale_capture_id}")
    return _redirect_ops(error=result.message[:120])


@router.post("/ops/revalidate/checklist/{case_id}")
def ops_revalidate_checklist(
    request: Request,
    case_id: int,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    result = _recovery.revalidate_document_checklist(db, case_id, user=usuario)
    db.commit()
    if result.ok:
        return _redirect_ops(msg="Checklist+revalidado")
    return _redirect_ops(error=result.message[:120])


@router.post("/ops/retry/import/{batch_id}")
def ops_retry_import(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    result = _recovery.retry_failed_import(db, batch_id, username=usuario.get("username"))
    db.commit()
    if result.ok:
        return RedirectResponse(url=f"/imports/{batch_id}/preview?msg=Preview+OK", status_code=302)
    return RedirectResponse(url=f"/imports?error={result.message[:80]}", status_code=302)
