"""P37/P69 — cola de jobs en BD con ejecución async, retries e idempotencia."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.registry import run_job_by_type
from app.models.platform import BackgroundJob

log = logging.getLogger(__name__)

JOB_TYPES = (
    "sharepoint_sync",
    "import_batch",
    "export_report",
    "recovery_bulk",
    "commission_recalc",
    "reconciliation_heavy",
    "bi_refresh",
)

JOB_TIMEOUT_SECONDS = 900
STALE_RUNNING_MINUTES = 30


class JobService:
    def enqueue(
        self,
        db: Session,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        created_by: str | None = None,
        priority: int = 5,
        company_id: int | None = None,
        run_async: bool | None = None,
    ) -> BackgroundJob:
        if job_type not in JOB_TYPES:
            raise ValueError(f"job_type inválido: {job_type}")
        settings = get_settings()
        job = BackgroundJob(
            job_type=job_type,
            status="pending",
            payload_json=payload or {},
            created_by=created_by,
            priority=priority,
            company_id=company_id or settings.default_company_id,
        )
        db.add(job)
        db.flush()
        try:
            from app.services.platform_cohesion_service import PlatformCohesionService

            PlatformCohesionService().emit(
                db,
                action="job_enqueued",
                title=f"Job encolado: {job_type}",
                entity_type="job",
                entity_id=job.id,
                source="jobs",
                tone="info",
                href="/jobs",
                automation_trigger=None,
                skip_automation=True,
            )
        except Exception:
            pass

        should_async = run_async if run_async is not None else settings.jobs_async_enabled
        if should_async:
            self._dispatch_async(job.id)
        else:
            self.process_job(db, job.id)

        return job

    def _dispatch_async(self, job_id: int) -> None:
        if self._try_rq_enqueue(job_id):
            return
        thread = threading.Thread(target=self._run_job_in_new_session, args=(job_id,), daemon=True)
        thread.start()

    def _try_rq_enqueue(self, job_id: int) -> bool:
        settings = get_settings()
        if not settings.redis_url:
            return False
        try:
            from redis import Redis
            from rq import Queue

            conn = Redis.from_url(settings.redis_url)
            q = Queue("gaman", connection=conn)
            q.enqueue("app.services.job_service.run_rq_worker", job_id)
            return True
        except Exception:
            log.debug("RQ no disponible; usando thread local", exc_info=True)
            return False

    def _run_job_in_new_session(self, job_id: int) -> None:
        from app.db.session import session_scope

        with session_scope() as db:
            try:
                self.process_job(db, job_id)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Job %s falló en worker", job_id)

    def process_job(self, db: Session, job_id: int) -> BackgroundJob:
        job = db.get(BackgroundJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} no encontrado")
        if job.status == "completed":
            return job
        if job.status == "running":
            log.info("Job %s ya en ejecución; omitiendo duplicado", job_id)
            return job
        if job.status in ("failed", "cancelled"):
            return job
        if job.status != "pending":
            return job

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts = (job.attempts or 0) + 1
        db.flush()

        started = time.monotonic()
        try:
            result = run_job_by_type(db, job.job_type, job.payload_json or {})
            elapsed = time.monotonic() - started
            if elapsed > JOB_TIMEOUT_SECONDS:
                raise TimeoutError(f"Job excedió {JOB_TIMEOUT_SECONDS}s")
            job.status = "completed"
            job.result_json = result
            job.error_message = None
            log.info("Job %s completado en %.1fs", job_id, elapsed)
            try:
                from app.observability.metrics import inc

                inc("jobs_processed_total")
            except Exception:
                pass
        except Exception as exc:
            job.error_message = str(exc)[:2000]
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status = "pending"
            log.exception("Job %s error (intento %s)", job_id, job.attempts)
        finally:
            job.finished_at = datetime.now(timezone.utc)
            db.flush()
            try:
                from app.services.realtime_service import RealtimeService

                RealtimeService().publish_jobs(
                    "job_finished",
                    {"job_id": job_id, "status": job.status},
                )
            except Exception:
                pass
        return job

    def reconcile_stale_jobs(self, db: Session, *, stale_minutes: int = STALE_RUNNING_MINUTES) -> int:
        """Resetea jobs 'running' huérfanos (P69)."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        stmt = select(BackgroundJob).where(
            BackgroundJob.status == "running",
            BackgroundJob.started_at < cutoff,
        )
        stale = list(db.scalars(stmt).all())
        for job in stale:
            job.status = "pending"
            job.error_message = (job.error_message or "")[:500] + " [stale reset P69]"
            job.finished_at = datetime.now(timezone.utc)
            log.warning("Job %s reset por stale running", job.id)
        if stale:
            db.flush()
        return len(stale)

    def cancel_job(self, db: Session, job_id: int) -> BackgroundJob:
        job = db.get(BackgroundJob, job_id)
        if not job:
            raise ValueError("Job no encontrado")
        if job.status in ("completed", "failed", "cancelled"):
            return job
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = "Cancelado por usuario"
        db.flush()
        return job

    def process_pending(self, db: Session, limit: int = 10) -> int:
        self.reconcile_stale_jobs(db)
        stmt = (
            select(BackgroundJob)
            .where(BackgroundJob.status == "pending")
            .order_by(BackgroundJob.priority.asc(), BackgroundJob.id.asc())
            .limit(min(limit, 25))
        )
        jobs = list(db.scalars(stmt).all())
        for job in jobs:
            self.process_job(db, job.id)
        return len(jobs)

    def list_jobs(
        self,
        db: Session,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[BackgroundJob]:
        limit = min(max(1, limit), 100)
        stmt = select(BackgroundJob).order_by(BackgroundJob.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(BackgroundJob.status == status)
        return list(db.scalars(stmt).all())

    def get_job(self, db: Session, job_id: int) -> BackgroundJob | None:
        return db.get(BackgroundJob, job_id)

    def retry_job(self, db: Session, job_id: int) -> BackgroundJob:
        job = db.get(BackgroundJob, job_id)
        if not job:
            raise ValueError("Job no encontrado")
        if job.status == "running":
            raise ValueError("Job aún en ejecución")
        job.status = "pending"
        job.error_message = None
        job.finished_at = None
        job.started_at = None
        db.flush()
        self._dispatch_async(job.id)
        return job


def run_rq_worker(job_id: int) -> None:
    """Entrypoint para worker RQ externo."""
    from app.db.session import session_scope

    svc = JobService()
    with session_scope() as db:
        svc.process_job(db, job_id)
        db.commit()
