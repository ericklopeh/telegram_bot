"""P37 — cola de jobs en BD con ejecución async opcional (thread / Redis RQ)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
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
            except Exception:
                log.exception("Job %s falló en worker", job_id)

    def process_job(self, db: Session, job_id: int) -> BackgroundJob:
        job = db.get(BackgroundJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} no encontrado")
        if job.status in ("completed", "running"):
            return job

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.flush()

        try:
            result = run_job_by_type(db, job.job_type, job.payload_json or {})
            job.status = "completed"
            job.result_json = result
            job.error_message = None
        except Exception as exc:
            job.error_message = str(exc)[:2000]
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status = "pending"
            log.exception("Job %s error", job_id)
        finally:
            job.finished_at = datetime.now(timezone.utc)
            db.flush()
        return job

    def process_pending(self, db: Session, limit: int = 10) -> int:
        stmt = (
            select(BackgroundJob)
            .where(BackgroundJob.status == "pending")
            .order_by(BackgroundJob.priority.asc(), BackgroundJob.id.asc())
            .limit(limit)
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
        job.status = "pending"
        job.error_message = None
        job.finished_at = None
        db.flush()
        self._dispatch_async(job.id)
        return job


def run_rq_worker(job_id: int) -> None:
    """Entrypoint para worker RQ externo."""
    from app.db.session import session_scope

    svc = JobService()
    with session_scope() as db:
        svc.process_job(db, job_id)
