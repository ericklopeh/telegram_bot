"""Registro de tipos de job — delega a servicios existentes sin cambiar lógica core."""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _noop(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "noop", "payload_keys": list(payload.keys())}


def _job_sharepoint_sync(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.sharepoint_sync_service import SharePointSyncService

    case_id = payload.get("case_id")
    if not case_id:
        return {"skipped": True, "reason": "missing case_id"}
    svc = SharePointSyncService()
    if hasattr(svc, "sync_case_documents"):
        result = svc.sync_case_documents(db, int(case_id))
        return {"case_id": case_id, "result": str(result)[:500]}
    return {"case_id": case_id, "status": "delegated"}


def _job_import_batch(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    return {"batch_id": batch_id, "status": "queued_for_import_runner"}


def _job_commission_recalc(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.commission_service import CommissionService

    week = payload.get("week_code")
    svc = CommissionService()
    if week and hasattr(svc, "recalculate_week"):
        count = svc.recalculate_week(db, week)
        return {"week_code": week, "recalculated": count}
    return {"status": "no_week_code"}


def _job_bi_refresh(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.analytics_service import AnalyticsService

    svc = AnalyticsService()
    snap = svc.capture_snapshot(db, payload.get("period_label"))
    return {"snapshot_id": snap.get("id")}


def _job_recovery_bulk(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.ops_recovery_service import OpsRecoveryService

    action = payload.get("action", "scan")
    svc = OpsRecoveryService()
    if hasattr(svc, "run_recovery_scan"):
        return svc.run_recovery_scan(db)
    return {"action": action, "status": "ok"}


JOB_HANDLERS: dict[str, Callable[[Session, dict[str, Any]], dict[str, Any]]] = {
    "sharepoint_sync": _job_sharepoint_sync,
    "import_batch": _job_import_batch,
    "export_report": _noop,
    "recovery_bulk": _job_recovery_bulk,
    "commission_recalc": _job_commission_recalc,
    "reconciliation_heavy": _noop,
    "bi_refresh": _job_bi_refresh,
}


def run_job_by_type(db: Session, job_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    handler = JOB_HANDLERS.get(job_type)
    if not handler:
        raise ValueError(f"Tipo de job desconocido: {job_type}")
    return handler(db, payload or {})
