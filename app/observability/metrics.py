"""P70 — métricas Prometheus-ready (text/plain)."""

from __future__ import annotations

import time
from typing import Any

from app.config import get_settings
from app.services.realtime_service import get_realtime_hub

_start = time.monotonic()
_counters: dict[str, float] = {
    "http_requests_total": 0,
    "jobs_processed_total": 0,
    "websocket_messages_total": 0,
    "realtime_publish_total": 0,
}


def inc(name: str, value: float = 1.0) -> None:
    _counters[name] = _counters.get(name, 0) + value


def build_prometheus_text() -> str:
    settings = get_settings()
    hub = get_realtime_hub()
    subs = sum(len(v) for v in hub._subscribers.values())
    lines = [
        "# HELP gaman_up Proceso web activo",
        "# TYPE gaman_up gauge",
        "gaman_up 1",
        "# HELP gaman_uptime_seconds Tiempo desde arranque métricas",
        "# TYPE gaman_uptime_seconds gauge",
        f"gaman_uptime_seconds {time.monotonic() - _start:.2f}",
        "# HELP gaman_environment_info Entorno",
        "# TYPE gaman_environment_info gauge",
        f'gaman_environment_info{{env="{settings.environment}"}} 1',
        "# HELP gaman_redis_available Redis conectado",
        "# TYPE gaman_redis_available gauge",
    ]
    try:
        from app.services.redis_client import get_redis_enterprise

        redis_ok = 1 if get_redis_enterprise().ping() else 0
    except Exception:
        redis_ok = 0
    lines.append(f"gaman_redis_available {redis_ok}")
    lines.extend(
        [
            "# HELP gaman_websocket_subscribers Suscriptores WS en memoria",
            "# TYPE gaman_websocket_subscribers gauge",
            f"gaman_websocket_subscribers {subs}",
        ]
    )
    for key, val in sorted(_counters.items()):
        lines.append(f"# TYPE {key} counter")
        lines.append(f"{key} {val}")
    return "\n".join(lines) + "\n"


def metrics_json() -> dict[str, Any]:
    settings = get_settings()
    return {
        "uptime_seconds": round(time.monotonic() - _start, 1),
        "environment": settings.environment,
        "counters": dict(_counters),
        "redis_url_configured": bool(settings.redis_url),
    }
