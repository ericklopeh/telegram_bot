"""P70 — worker async: procesa jobs pendientes en loop."""

from __future__ import annotations

import logging
import os
import time

from app.core.logging_setup import setup_logging
from app.config import get_settings

log = logging.getLogger(__name__)

POLL_SECONDS = int(os.environ.get("WORKER_POLL_SECONDS", "15"))


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("Worker iniciado env=%s poll=%ss", settings.environment, POLL_SECONDS)

    from app.db.session import session_scope
    from app.services.job_service import JobService

    svc = JobService()
    while True:
        try:
            with session_scope() as db:
                stale = svc.reconcile_stale_jobs(db)
                if stale:
                    log.warning("Jobs stale reseteados: %s", stale)
                n = svc.process_pending(db, limit=5)
                db.commit()
                if n:
                    log.info("Procesados %s jobs", n)
        except Exception:
            log.exception("Ciclo worker falló")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
