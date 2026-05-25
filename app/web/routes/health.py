"""Endpoints de health operativo (P30)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.services.system_health_service import SystemHealthService

router = APIRouter(tags=["health"])


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health_liveness():
    """Liveness: proceso web activo (sin BD)."""
    svc = SystemHealthService()
    return {
        "status": "ok",
        "service": "sistema_gaman_web",
        "version": svc.version,
    }


@router.get("/health/full")
def health_full(db: Session = Depends(get_web_db)):
    """Readiness: DB, storage, Graph config, plantillas."""
    report = SystemHealthService().build_report(db, full=True)
    body = report.to_dict(full=True)
    status_code = 200 if report.status == "ok" else 503
    return JSONResponse(content=body, status_code=status_code)


@router.get("/metrics")
def metrics_endpoint():
    """Prometheus text exposition (P70)."""
    settings = get_settings()
    if not settings.metrics_enabled:
        return JSONResponse({"detail": "metrics disabled"}, status_code=404)
    from app.observability.metrics import build_prometheus_text

    return PlainTextResponse(build_prometheus_text(), media_type="text/plain; version=0.0.4")
