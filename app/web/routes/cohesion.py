"""P61-P68 — cohesión enterprise: cockpit, copilot, palette, workflow visual, UX."""

from __future__ import annotations

import csv
import io
from typing import Generator

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.services.activity_feed_service import ActivityFeedService
from app.services.ai_ops_service import AiOpsService
from app.services.automation_service import AutomationService
from app.services.command_palette_service import CommandPaletteService
from app.services.compliance_service import ComplianceService
from app.services.notification_center_service import NotificationCenterService
from app.services.rule_engine import RuleEngine
from app.services.supervisor_cockpit_service import SupervisorCockpitService
from app.web.auth import get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR
from app.web.services.workflow_visualization import build_workflow_pipeline
from app.repositories.case_repository import CaseRepository

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/activity")
def activity_page_enhanced(
    request: Request,
    db: Session = Depends(get_web_db),
    entity_type: str | None = None,
    tone: str | None = None,
    source: str | None = None,
    grouped: bool = Query(True),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    cid = user.get("company_id", 1)
    svc = ActivityFeedService()
    if grouped:
        feed = svc.list_feed_grouped(
            db, limit=60, company_id=cid, entity_type=entity_type, tone=tone, source=source
        )
    else:
        feed = svc.list_feed(
            db, limit=60, company_id=cid, entity_type=entity_type, tone=tone, source=source
        )
    return templates.TemplateResponse(
        request,
        "activity_feed.html",
        {
            "usuario": user,
            "feed": feed,
            "grouped": grouped,
            "entity_type": entity_type,
            "tone": tone,
            "source": source,
        },
    )


@router.get("/supervisor/cockpit")
def supervisor_cockpit(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(
        request, db, ["admin", "sistemas", "autorizacion", "compras"]
    )
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    data = SupervisorCockpitService().build(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "supervisor_cockpit.html", {"usuario": user, "cockpit": data}
    )


@router.get("/workflow/visual")
def workflow_visual(
    request: Request,
    db: Session = Depends(get_web_db),
    case_id: int | None = None,
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    cases_preview = []
    if case_id:
        case = CaseRepository.get_by_id(db, case_id)
        if case:
            cases_preview.append(
                {
                    "case": case,
                    "pipeline": build_workflow_pipeline(db, case),
                }
            )
    else:
        from sqlalchemy import select
        from app.models.case import Case

        recent = list(db.scalars(select(Case).order_by(Case.updated_at.desc()).limit(8)).all())
        for c in recent:
            cases_preview.append({"case": c, "pipeline": build_workflow_pipeline(db, c)})
    return templates.TemplateResponse(
        request,
        "workflow_visual.html",
        {"usuario": user, "cases_preview": cases_preview, "case_id": case_id},
    )


@router.get("/api/command-palette")
def command_palette_api(
    request: Request,
    q: str = "",
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    return CommandPaletteService().search(db, q)


@router.get("/ai/copilot")
def ai_copilot(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    briefing = AiOpsService().copilot_briefing(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "ai_copilot.html", {"usuario": user, "briefing": briefing}
    )


@router.get("/admin/compliance-center")
def compliance_center(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    center = ComplianceService().build_compliance_center(
        db, company_id=user.get("company_id", 1)
    )
    return templates.TemplateResponse(
        request, "compliance_center.html", {"usuario": user, "center": center}
    )


@router.get("/admin/compliance-center/export")
def compliance_center_export(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    rows = ComplianceService().export_audit_csv_rows(db)
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=compliance_center.csv"},
    )


@router.get("/admin/automations")
def automations_admin(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    svc = AutomationService()
    svc.seed_defaults(db)
    db.commit()
    flows = svc.list_flows(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request, "automations.html", {"usuario": user, "flows": flows}
    )


@router.get("/admin/rules/simulator")
def rules_simulator(
    request: Request,
    db: Session = Depends(get_web_db),
    trigger: str = Query("sale_validation"),
    seccion: str = Query("21"),
    monto: float = Query(20000),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    user = get_current_user(request, db)
    engine = RuleEngine()
    engine.seed_defaults(db)
    ctx = {"seccion": seccion, "monto": monto, "entity_type": "sale"}
    fired = engine.simulate(db, trigger, ctx, company_id=user.get("company_id", 1))
    logs = engine.recent_logs(db, limit=20)
    rules = engine.list_rules(db, company_id=user.get("company_id", 1))
    return templates.TemplateResponse(
        request,
        "rules_simulator.html",
        {
            "usuario": user,
            "trigger": trigger,
            "context": ctx,
            "fired": fired,
            "logs": logs,
            "rules": rules,
        },
    )


@router.post("/admin/rules/toggle")
def rules_toggle(
    request: Request,
    db: Session = Depends(get_web_db),
    rule_key: str = Form(...),
    enabled: bool = Form(False),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    RuleEngine().set_rule_enabled(db, rule_key, enabled)
    db.commit()
    return RedirectResponse("/admin/rules/simulator", status_code=302)


@router.get("/api/notifications")
def notifications_api(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    svc = NotificationCenterService()
    return JSONResponse(
        {
            "unread": svc.unread_count(db, user_id=user.get("id")),
            "items": svc.list_recent(db, user_id=user.get("id")),
        }
    )


@router.post("/api/notifications/{nid}/read")
def notification_read(nid: int, request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    NotificationCenterService().mark_read(db, nid)
    db.commit()
    return JSONResponse({"ok": True})
