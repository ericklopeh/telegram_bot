"""Rutas enterprise avanzado P47-P60."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Generator

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.services.ai_ops_service import AiOpsService
from app.services.attachment_service import AttachmentService
from app.services.calendar_service import CalendarService
from app.services.comment_service import CommentService
from app.services.compliance_service import ComplianceService
from app.services.feature_flag_service import FeatureFlagService
from app.services.realtime_service import RealtimeService, get_realtime_hub
from app.services.report_builder_service import ReportBuilderService
from app.services.rule_engine import RuleEngine
from app.services.saas_tenant_service import SaasTenantService
from app.services.signature_service import SignatureService
from app.services.template_service import TemplateService
from app.services.warehouse_service import WarehouseService
from app.web.auth import get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_log = logging.getLogger(__name__)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


async def _ws_channel(websocket: WebSocket, channel: str) -> None:
    await websocket.accept()
    hub = get_realtime_hub()
    queue = await hub.subscribe(channel)
    try:
        while True:
            data = await queue.get()
            await websocket.send_text(RealtimeService.format_ws_message(data))
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(channel, queue)


@router.websocket("/ws/activity")
async def ws_activity(websocket: WebSocket):
    await _ws_channel(websocket, "activity")


@router.websocket("/ws/jobs")
async def ws_jobs(websocket: WebSocket):
    await _ws_channel(websocket, "jobs")


@router.websocket("/ws/ops")
async def ws_ops(websocket: WebSocket):
    await _ws_channel(websocket, "ops")


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    await _ws_channel(websocket, "notifications")


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await _ws_channel(websocket, "dashboard")


@router.get("/api/realtime/poll")
def realtime_poll(channels: str = Query("activity,jobs,ops")):
    chs = [c.strip() for c in channels.split(",") if c.strip()]
    return RealtimeService().build_poll_bundle(chs)


@router.get("/casos/{case_id}/comments")
def case_comments_list(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    comments = CommentService().list_for_case(db, case_id)
    return JSONResponse({"comments": comments})


@router.post("/casos/{case_id}/comments")
def case_comments_add(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
    body: str = Form(...),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    comment = CommentService().add_comment(
        db,
        case_id,
        body=body,
        author_user_id=user.get("id"),
        author_label=user.get("nombre") or user.get("username") or "Usuario",
        company_id=user.get("company_id", 1),
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return JSONResponse({"id": comment.id, "status": "ok"})


@router.get("/calendar")
def calendar_page(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    svc = CalendarService()
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "usuario": user,
            "events": svc.calendar_events(db, company_id=user.get("company_id", 1)),
            "sla": svc.sla_summary(db, company_id=user.get("company_id", 1)),
        },
    )


@router.get("/tasks")
def tasks_page(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    tasks = CalendarService().list_tasks(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "tasks.html", {"usuario": user, "tasks": tasks}
    )


@router.get("/tasks/my")
def my_tasks(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    tasks = CalendarService().list_tasks(
        db, assigned_user_id=user.get("id"), company_id=user.get("company_id", 1)
    )
    return templates.TemplateResponse(
        request, "tasks.html", {"usuario": user, "tasks": tasks, "mine": True}
    )


@router.post("/tasks/create")
def tasks_create(
    request: Request,
    db: Session = Depends(get_web_db),
    title: str = Form(...),
    description: str = Form(""),
    case_id: int | None = Form(None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    CalendarService().create_task(
        db,
        title=title,
        description=description or None,
        case_id=case_id,
        assigned_user_id=user.get("id"),
        assigned_label=user.get("nombre"),
        created_by=user.get("username"),
        company_id=user.get("company_id", 1),
    )
    db.commit()
    return RedirectResponse("/tasks", status_code=302)


@router.get("/admin/rules")
def admin_rules(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    engine = RuleEngine()
    engine.seed_defaults(db)
    db.commit()
    rules = engine.list_rules(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "admin_rules.html", {"usuario": user, "rules": rules}
    )


@router.get("/reports/builder")
def report_builder(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    svc = ReportBuilderService()
    return templates.TemplateResponse(
        request,
        "report_builder.html",
        {"usuario": user, "sources": svc.AVAILABLE_SOURCES},
    )


@router.get("/reports/saved")
def reports_saved(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    reports = ReportBuilderService().list_saved(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "reports_saved.html", {"usuario": user, "reports": reports}
    )


@router.post("/reports/run")
def reports_run(
    request: Request,
    db: Session = Depends(get_web_db),
    source: str = Form("cases"),
    columns: str = Form("public_id,client_name,current_status"),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    definition = {
        "source": source,
        "columns": [c.strip() for c in columns.split(",") if c.strip()],
    }
    rows = ReportBuilderService().run_report(db, definition)
    csv_data = ReportBuilderService().export_csv(rows)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


@router.get("/admin/feature-flags")
def feature_flags_admin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    svc = FeatureFlagService()
    svc.seed_defaults(db)
    db.commit()
    flags = svc.list_flags(db)
    return templates.TemplateResponse(
        request, "feature_flags.html", {"usuario": user, "flags": flags}
    )


@router.post("/admin/feature-flags/toggle")
def feature_flags_toggle(
    request: Request,
    db: Session = Depends(get_web_db),
    flag_key: str = Form(...),
    enabled: bool = Form(False),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    FeatureFlagService().set_flag(db, flag_key, enabled)
    db.commit()
    return RedirectResponse("/admin/feature-flags", status_code=302)


@router.get("/admin/compliance")
def compliance_admin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    entries = ComplianceService().list_audit(db, limit=80)
    return templates.TemplateResponse(
        request, "compliance.html", {"usuario": user, "entries": entries}
    )


@router.get("/admin/compliance/export")
def compliance_export(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    rows = ComplianceService().export_audit_csv_rows(db)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


@router.get("/admin/warehouse")
def warehouse_admin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    snaps = WarehouseService().list_snapshots(db)
    return templates.TemplateResponse(
        request, "warehouse.html", {"usuario": user, "snapshots": snaps}
    )


@router.post("/admin/warehouse/capture")
def warehouse_capture(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    WarehouseService().capture_all_domains(db, company_id=user.get("company_id", 1))
    db.commit()
    return RedirectResponse("/admin/warehouse", status_code=302)


@router.get("/admin/ai-ops")
def ai_ops_page(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    svc = AiOpsService()
    return templates.TemplateResponse(
        request,
        "ai_ops.html",
        {
            "usuario": user,
            "suggestions": svc.recovery_suggestions(db),
            "anomalies": svc.detect_anomalies(db),
            "insights": svc.bi_insights(db),
        },
    )


@router.get("/admin/tenants")
def tenants_admin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    tenants = SaasTenantService().list_tenants(db)
    return templates.TemplateResponse(
        request, "tenants.html", {"usuario": user, "tenants": tenants}
    )


@router.post("/attachments/upload")
async def attachment_upload(
    request: Request,
    db: Session = Depends(get_web_db),
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    file: UploadFile = File(...),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    data = await file.read()
    att = AttachmentService().store_file(
        db,
        filename=file.filename or "file",
        data=data,
        mime_type=file.content_type,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by=user.get("username"),
        company_id=user.get("company_id", 1),
    )
    db.commit()
    return JSONResponse({"id": att.id, "filename": att.filename})
