"""P70 — scheduler: snapshots, analytics refresh, jobs programados."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.core.logging_setup import setup_logging

log = logging.getLogger(__name__)

INTERVAL_SEC = int(os.environ.get("SCHEDULER_INTERVAL_SEC", "3600"))


def _tick() -> None:
    from app.db.session import session_scope
    from app.services.job_service import JobService

    now = datetime.now(timezone.utc)
    label = now.strftime("%Y-%m-%d %H:%M")

    with session_scope() as db:
        jobs = JobService()
        jobs.enqueue(db, "bi_refresh", {"period_label": label}, created_by="scheduler")
        jobs.enqueue(
            db,
            "export_report",
            {"kind": "warehouse_snapshot", "scheduled": True},
            created_by="scheduler",
            priority=8,
        )
        try:
            from app.services.analytics_service import AnalyticsService

            AnalyticsService().capture_snapshot(db, label)
        except Exception:
            log.debug("Snapshot analytics inline falló", exc_info=True)
        db.commit()
    log.info("Scheduler tick OK label=%s", label)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    if os.environ.get("SCHEDULER_ENABLED", "").lower() not in ("1", "true", "yes"):
        log.info("Scheduler deshabilitado (SCHEDULER_ENABLED)")
        return
    log.info("Scheduler iniciado interval=%ss", INTERVAL_SEC)
    while True:
        try:
            _tick()
        except Exception:
            log.exception("Scheduler tick falló")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
