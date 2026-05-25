"""P70 — cliente Redis enterprise con fallback seguro en memoria."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

_memory_pubsub: dict[str, list[dict[str, Any]]] = {}
_client: Any = False
_last_ping: float = 0.0


class RedisEnterprise:
    """Pub/sub, cache y coordinación; sin Redis usa memoria local."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def available(self) -> bool:
        return self._client() is not None

    def _client(self) -> Any | None:
        global _client, _last_ping
        if _client is not False:
            return _client if _client is not None else None
        url = (self._settings.redis_url or "").strip()
        if not url:
            _client = None
            return None
        try:
            from redis import Redis

            c = Redis.from_url(url, decode_responses=True, socket_connect_timeout=3)
            c.ping()
            _client = c
            _last_ping = time.monotonic()
            log.info("Redis enterprise conectado")
            return c
        except Exception:
            log.warning("Redis no disponible; fallback en memoria", exc_info=True)
            _client = None
            return None

    def ping(self) -> bool:
        c = self._client()
        if not c:
            return False
        try:
            return bool(c.ping())
        except Exception:
            return False

    def publish(self, channel: str, message: dict[str, Any]) -> bool:
        payload = json.dumps(message, default=str)
        c = self._client()
        if c:
            try:
                c.publish(f"gaman:rt:{channel}", payload)
                return True
            except Exception:
                log.debug("Redis publish falló", exc_info=True)
        _memory_pubsub.setdefault(channel, []).append(message)
        if len(_memory_pubsub[channel]) > 200:
            _memory_pubsub[channel] = _memory_pubsub[channel][-100:]
        return False

    def cache_get(self, key: str) -> str | None:
        c = self._client()
        if not c:
            return None
        try:
            return c.get(f"gaman:cache:{key}")
        except Exception:
            return None

    def cache_set(self, key: str, value: str, ttl: int = 60) -> None:
        c = self._client()
        if not c:
            return
        try:
            c.setex(f"gaman:cache:{key}", max(5, ttl), value)
        except Exception:
            log.debug("Redis cache_set falló", exc_info=True)


def get_redis_enterprise() -> RedisEnterprise:
    return RedisEnterprise()
