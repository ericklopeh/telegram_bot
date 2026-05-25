"""Rutas plataforma enterprise P36-P45."""

from __future__ import annotations

import csv
import io
import logging
from typing import Generator

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.services.activity_feed_service import ActivityFeedService
from app.services.analytics_service import AnalyticsService
from app.services.enterprise_notification_service import EnterpriseNotificationService
from app.services.global_search_service import GlobalSearchService
from app.services.job_service import JOB_TYPES, JobService
from app.services.performance_service import PerformanceService
from app.services.role_dashboard_service import RoleDashboardService
from app.services.tenant_service import TenantService
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


@router.get("/jobs")
def jobs_panel(
    request: Request,
    db: Session = Depends(get_web_db),
    status: str | None = None,
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    jobs = JobService().list_jobs(db, status=status)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "usuario": user,
            "jobs": jobs,
            "job_types": JOB_TYPES,
            "status_filter": status,
        },
    )


@router.post("/jobs/enqueue")
def jobs_enqueue(
    request: Request,
    db: Session = Depends(get_web_db),
    job_type: str = Form(...),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    JobService().enqueue(db, job_type, payload={}, created_by=user.get("username"), run_async=True)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/jobs?enqueued=1", status_code=302)


@router.post("/jobs/{job_id}/retry")
def jobs_retry(
    request: Request,
    job_id: int,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    JobService().retry_job(db, job_id)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/jobs", status_code=302)


@router.get("/activity")
def activity_page(
    request: Request,
    db: Session = Depends(get_web_db),
    entity_type: str | None = None,
    entity_id: int | None = None,
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    ctx = TenantService().resolve_from_session(user)
    feed = ActivityFeedService().list_feed(
        db,
        limit=50,
        entity_type=entity_type,
        entity_id=entity_id,
        company_id=ctx.company_id,
    )
    return templates.TemplateResponse(
        request,
        "activity.html",
        {
            "usuario": user,
            "feed": feed,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )


@router.get("/search")
def search_page(
    request: Request,
    db: Session = Depends(get_web_db),
    q: str = "",
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    results = GlobalSearchService().search(db, q) if q.strip() else {"query": "", "groups": [], "total": 0}
    return templates.TemplateResponse(
        request,
        "search.html",
        {"usuario": user, "results": results, "q": q},
    )


@router.get("/api/search")
def search_api(
    request: Request,
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    return GlobalSearchService().search(db, q)


@router.get("/mi-dashboard")
def vendor_dashboard(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    seller = user.get("nombre")
    data = RoleDashboardService().build_vendor_dashboard(
        db,
        seller_name=seller,
        user_id=user.get("id"),
    )
    return templates.TemplateResponse(
        request,
        "mi_dashboard.html",
        {"usuario": user, "dash": data},
    )


@router.get("/supervisor/dashboard")
def supervisor_dashboard(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    role_redirect = require_roles(request, db, ["admin", "sistemas", "autorizacion", "compras"])
    if role_redirect:
        return role_redirect
    data = RoleDashboardService().build_supervisor_dashboard(db)
    return templates.TemplateResponse(
        request,
        "supervisor_dashboard.html",
        {"usuario": user, "dash": data},
    )


@router.get("/analytics/avanzado")
def analytics_advanced(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    ctx = TenantService().resolve_from_session(user)
    data = AnalyticsService().build_advanced_dashboard(db, company_id=ctx.company_id)
    snapshots = AnalyticsService().list_snapshots(db)
    return templates.TemplateResponse(
        request,
        "analytics_advanced.html",
        {
            "usuario": user,
            "analytics": data,
            "snapshots": snapshots,
        },
    )


@router.get("/analytics/export")
def analytics_export(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    rows = AnalyticsService().export_analytics_csv_rows(db)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analytics_export.csv"},
    )


@router.get("/admin/performance")
def performance_admin(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    user = get_current_user(request, db)
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    report = PerformanceService().build_report()
    return templates.TemplateResponse(
        request,
        "performance.html",
        {"usuario": user, "report": report.to_dict()},
    )


@router.get("/admin/notifications/test")
def notifications_test(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    role_redirect = require_roles(request, db, ["admin", "sistemas"])
    if role_redirect:
        return role_redirect
    EnterpriseNotificationService().notify_operational_event(
        db,
        "critical_incident",
        "Prueba de notificación enterprise (P38)",
    )
    db.commit()
    return JSONResponse({"status": "queued"})
