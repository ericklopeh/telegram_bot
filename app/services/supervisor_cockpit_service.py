"""P63 — cockpit operacional supervisor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.case import Case
from app.models.enterprise_advanced import OperationalTask
from app.models.import_batch import ImportBatch
from app.models.ops_incident import OpsIncident
from app.models.platform import BackgroundJob
from app.services.activity_feed_service import ActivityFeedService
from app.services.performance_service import PerformanceService


class SupervisorCockpitService:
    def build(self, db: Session, *, company_id: int = 1) -> dict[str, Any]:
        perf = PerformanceService()
        return perf.cached(
            f"cockpit:{company_id}",
            lambda: self._build_uncached(db, company_id=company_id),
            ttl=30,
        )

    def _build_uncached(self, db: Session, *, company_id: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=24)

        critical_cases = list(
            db.scalars(
                select(Case)
                .where(Case.updated_at < stale_cutoff)
                .order_by(Case.updated_at.asc())
                .limit(12)
            ).all()
        )

        sp_failed = list(
            db.scalars(
                select(Case)
                .where(Case.current_status.ilike("%SHAREPOINT%FAIL%"))
                .limit(8)
            ).all()
        )[:8]

        overdue_tasks = db.scalar(
            select(func.count(OperationalTask.id)).where(
                OperationalTask.status == "open",
                OperationalTask.due_at < now,
            )
        ) or 0

        failed_jobs = list(
            db.scalars(
                select(BackgroundJob)
                .where(BackgroundJob.status == "failed")
                .order_by(BackgroundJob.id.desc())
                .limit(8)
            ).all()
        )

        failed_imports = list(
            db.scalars(
                select(ImportBatch)
                .where(ImportBatch.status == "failed")
                .order_by(ImportBatch.id.desc())
                .limit(6)
            ).all()
        )

        open_incidents = db.scalar(
            select(func.count(OpsIncident.id)).where(OpsIncident.status == "OPEN")
        ) or 0

        seller_heatmap = db.execute(
            select(Case.seller_name, func.count(Case.id))
            .where(Case.seller_name.isnot(None))
            .group_by(Case.seller_name)
            .order_by(func.count(Case.id).desc())
            .limit(10)
        ).all()

        activity = ActivityFeedService().list_feed(db, limit=15, company_id=company_id)

        return {
            "kpis": {
                "casos_criticos": len(critical_cases),
                "sharepoint_failed": len(sp_failed),
                "tareas_vencidas": overdue_tasks,
                "jobs_fallidos": len(failed_jobs),
                "imports_fallidos": len(failed_imports),
                "incidentes_abiertos": open_incidents,
            },
            "critical_cases": [
                {
                    "public_id": c.public_id,
                    "client": c.client_name,
                    "status": c.current_status,
                    "href": f"/casos/{c.id}",
                }
                for c in critical_cases
            ],
            "sp_failed": [
                {"public_id": c.public_id, "href": f"/casos/{c.id}"} for c in sp_failed
            ],
            "failed_jobs": [
                {"id": j.id, "type": j.job_type, "error": (j.error_message or "")[:80]}
                for j in failed_jobs
            ],
            "failed_imports": [
                {"id": i.id, "file": i.original_filename} for i in failed_imports
            ],
            "seller_heatmap": [
                {"seller": s, "count": n, "intensity": min(100, n * 10)} for s, n in seller_heatmap if s
            ],
            "activity": activity,
            "recovery_links": [
                {"label": "Panel Ops", "href": "/ops"},
                {"label": "Jobs", "href": "/jobs"},
                {"label": "Incidencias", "href": "/ops/incidents"},
            ],
        }
