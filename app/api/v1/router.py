"""Router API v1 — casos, ventas, workflow, BI, search."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import require_scope, resolve_api_token
from app.db.session import get_db_session
from app.models.case import Case
from app.models.platform import ApiToken
from app.services.analytics_service import AnalyticsService
from app.services.global_search_service import GlobalSearchService
from app.services.job_service import JobService

api_v1_router = APIRouter(prefix="/api/v1", tags=["api-v1"])


def get_api_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def get_token(
    db: Session = Depends(get_api_db),
    authorization: str | None = Header(None, alias="Authorization"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> ApiToken:
    return resolve_api_token(db, authorization, x_api_key)


@api_v1_router.get("/health")
def api_health():
    return {"status": "ok", "version": "v1"}


@api_v1_router.get("/casos")
def api_list_cases(
    q: str | None = Query(None),
    limit: int = Query(25, le=100),
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "read")
    stmt = select(Case).order_by(Case.updated_at.desc()).limit(limit)
    if q:
        stmt = stmt.where(Case.public_id.ilike(f"%{q}%"))
    if token.company_id:
        stmt = stmt.where(Case.company_id == token.company_id)
    rows = list(db.scalars(stmt).all())
    return {
        "items": [
            {
                "id": c.id,
                "public_id": c.public_id,
                "client_name": c.client_name,
                "status": c.current_status,
                "seller_name": c.seller_name,
            }
            for c in rows
        ]
    }


@api_v1_router.get("/casos/{case_id}")
def api_get_case(
    case_id: int,
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "read")
    case = db.get(Case, case_id)
    if not case:
        return {"error": "not_found"}
    return {
        "id": case.id,
        "public_id": case.public_id,
        "client_name": case.client_name,
        "status": case.current_status,
        "workflow_state": case.workflow_state,
    }


@api_v1_router.get("/search")
def api_search(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "read")
    return GlobalSearchService().search(db, q)


@api_v1_router.get("/bi/summary")
def api_bi_summary(
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "read")
    return AnalyticsService().build_advanced_dashboard(db, company_id=token.company_id)


@api_v1_router.get("/jobs")
def api_jobs(
    status: str | None = None,
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "admin")
    jobs = JobService().list_jobs(db, status=status)
    return {
        "items": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
    }


@api_v1_router.post("/jobs/{job_type}")
def api_enqueue_job(
    job_type: str,
    db: Session = Depends(get_api_db),
    token: ApiToken = Depends(get_token),
):
    require_scope(token, "write")
    job = JobService().enqueue(db, job_type, payload={}, created_by=token.name)
    return {"id": job.id, "status": job.status}
