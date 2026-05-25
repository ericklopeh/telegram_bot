"""P36 — rendimiento, cache ligero y profiling de consultas."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Generator, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T")

_cache_lock = Lock()
_memory_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_query_stats: list[dict[str, Any]] = []
_stats_lock = Lock()
_engine_listeners_installed = False


@dataclass
class PaginationResult:
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


@dataclass
class PerformanceReport:
    slow_queries: list[dict[str, Any]] = field(default_factory=list)
    cache_entries: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slow_queries": self.slow_queries[-50:],
            "cache_entries": self.cache_entries,
            "generated_at": self.generated_at,
        }


def paginate(items: list[T], page: int = 1, page_size: int = 25) -> PaginationResult:
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    total = len(items)
    start = (page - 1) * page_size
    chunk = items[start : start + page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginationResult(
        items=chunk,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def cache_get(key: str) -> Any | None:
    settings = get_settings()
    now = time.time()
    with _cache_lock:
        entry = _memory_cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < now:
            _memory_cache.pop(key, None)
            return None
        _memory_cache.move_to_end(key)
        return value


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    settings = get_settings()
    ttl = ttl if ttl is not None else settings.cache_ttl_seconds
    expires_at = time.time() + max(5, ttl)
    with _cache_lock:
        _memory_cache[key] = (expires_at, value)
        _memory_cache.move_to_end(key)
        while len(_memory_cache) > 256:
            _memory_cache.popitem(last=False)


def cache_invalidate(prefix: str) -> None:
    with _cache_lock:
        keys = [k for k in _memory_cache if k.startswith(prefix)]
        for k in keys:
            _memory_cache.pop(k, None)


@contextmanager
def timed_operation(label: str) -> Generator[None, None, None]:
    """Mide duración de bloques de código (servicios, imports, sync)."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        threshold = get_settings().slow_query_ms
        if elapsed_ms >= threshold:
            log.warning("Operación lenta [%s]: %.1f ms", label, elapsed_ms)
            _record_stat(label, elapsed_ms, kind="operation")


def _record_stat(label: str, elapsed_ms: float, kind: str = "sql") -> None:
    with _stats_lock:
        _query_stats.append(
            {
                "label": label,
                "elapsed_ms": round(elapsed_ms, 2),
                "kind": kind,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if len(_query_stats) > 500:
            del _query_stats[:100]


def install_slow_query_logging(engine: Engine | None = None) -> None:
    """Registra listeners SQLAlchemy para detectar consultas lentas."""
    global _engine_listeners_installed
    if _engine_listeners_installed:
        return
    from app.db.session import engine as default_engine

    target = engine or default_engine
    threshold = get_settings().slow_query_ms

    @event.listens_for(target, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(target, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        starts = conn.info.get("query_start_time")
        if not starts:
            return
        elapsed_ms = (time.perf_counter() - starts.pop()) * 1000
        if elapsed_ms >= threshold:
            snippet = " ".join(statement.split())[:200]
            log.warning("Query lenta (%.1f ms): %s", elapsed_ms, snippet)
            _record_stat(snippet, elapsed_ms, kind="sql")

    _engine_listeners_installed = True


class PerformanceService:
    """Métricas y utilidades de escalabilidad para dashboard/BI."""

    def __init__(self) -> None:
        install_slow_query_logging()

    def cached(self, key: str, factory: Callable[[], T], ttl: int | None = None) -> T:
        hit = cache_get(key)
        if hit is not None:
            return hit
        value = factory()
        cache_set(key, value, ttl=ttl)
        return value

    def build_report(self) -> PerformanceReport:
        with _stats_lock:
            slow = [s for s in _query_stats if s["elapsed_ms"] >= get_settings().slow_query_ms]
        with _cache_lock:
            entries = len(_memory_cache)
        return PerformanceReport(
            slow_queries=slow[-50:],
            cache_entries=entries,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def optimize_session_reads(self, db: Session, stmt, *, limit: int | None = None):
        """Ejecuta select con límite explícito para evitar cargas masivas."""
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.scalars(stmt).all())
