"""Política de reintentos para Graph (P25.1)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from app.config import Settings, get_settings


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_seconds: float
    max_sleep_seconds: float = 60.0

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> RetryPolicy:
        s = settings or get_settings()
        max_retries = getattr(s, "ms_graph_max_retries", 5)
        base = getattr(s, "ms_graph_retry_base_seconds", 1.0)
        try:
            max_retries = int(max_retries)
        except (TypeError, ValueError):
            max_retries = 5
        try:
            base = float(base)
        except (TypeError, ValueError):
            base = 1.0
        return cls(
            max_attempts=max(max_retries, 1),
            base_seconds=max(base, 0.25),
        )

    def sleep_before_retry(self, attempt: int, *, retry_after: float | None = None) -> None:
        """attempt: 0-based index del reintento que sigue."""
        if retry_after is not None and retry_after > 0:
            time.sleep(min(retry_after, self.max_sleep_seconds))
            return
        # exponential backoff + jitter
        delay = min(self.base_seconds * (2**attempt), self.max_sleep_seconds)
        jitter = random.uniform(0, delay * 0.2)
        time.sleep(delay + jitter)
