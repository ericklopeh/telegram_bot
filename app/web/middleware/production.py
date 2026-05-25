"""P70 — rate limiting y límites de request."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from starlette.responses import JSONResponse, PlainTextResponse

from app.config import get_settings

_buckets: dict[str, list[float]] = defaultdict(list)


async def rate_limit_middleware(request: Request, call_next):
    settings = get_settings()
    if request.url.path.startswith(
        ("/static", "/health", "/ping", "/metrics", "/telegram/webhook")
    ):
        return await call_next(request)

    limit = settings.api_rate_limit_per_min
    if limit <= 0:
        return await call_next(request)

    key = request.client.host if request.client else "unknown"
    if "session" in request.scope and request.session.get("usuario"):
        key = f"user:{request.session['usuario'].get('id', key)}"

    now = time.monotonic()
    window = 60.0
    hits = _buckets[key]
    hits[:] = [t for t in hits if now - t < window]
    if len(hits) >= limit:
        return JSONResponse(
            {"detail": "Demasiadas solicitudes. Intente de nuevo en un minuto."},
            status_code=429,
        )
    hits.append(now)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            max_bytes = settings.max_upload_bytes
            if size > max_bytes:
                return PlainTextResponse(
                    "Archivo demasiado grande.",
                    status_code=413,
                )
        except ValueError:
            pass

    return await call_next(request)
