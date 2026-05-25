"""Workers y registro de jobs en background (P37)."""

from app.jobs.registry import JOB_HANDLERS, run_job_by_type

__all__ = ["JOB_HANDLERS", "run_job_by_type"]
