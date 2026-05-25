"""P47/P61/P69 — realtime: WebSocket hub, Redis pub/sub opcional, polling, hardening."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

CHANNELS = (
    "activity",
    "jobs",
    "ops",
    "pipeline",
    "sharepoint",
    "dashboard",
    "notifications",
    "heartbeat",
)

_MAX_SUBSCRIBERS_PER_CHANNEL = 256
_PUBLISH_RATE_WINDOW_SEC = 1.0
_MAX_PUBLISH_PER_WINDOW = 120


class RealtimeHub:
    """Broker en memoria por canal; Redis opcional para multi-worker."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._last_payload: dict[str, dict[str, Any]] = {}
        self._publish_timestamps: list[float] = []

    def _redis_publish(self, channel: str, message: dict[str, Any]) -> None:
        try:
            from app.services.redis_client import get_redis_enterprise

            get_redis_enterprise().publish(channel, message)
        except Exception:
            log.debug("Redis publish falló", exc_info=True)

    def _allow_publish(self) -> bool:
        """Rate limit básico global anti-flood."""
        now = time.monotonic()
        self._publish_timestamps = [
            t for t in self._publish_timestamps if now - t < _PUBLISH_RATE_WINDOW_SEC
        ]
        if len(self._publish_timestamps) >= _MAX_PUBLISH_PER_WINDOW:
            log.warning("Realtime publish rate limit alcanzado")
            return False
        self._publish_timestamps.append(now)
        return True

    async def subscribe(self, channel: str) -> asyncio.Queue:
        if channel not in CHANNELS:
            channel = "activity"
        self.cleanup_stale_subscribers(channel)
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        subs = self._subscribers[channel]
        if len(subs) >= _MAX_SUBSCRIBERS_PER_CHANNEL:
            subs.pop(0)
        subs.append(q)
        cached = self._last_payload.get(channel)
        if cached:
            try:
                await q.put(cached)
            except asyncio.QueueFull:
                pass
        return q

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(channel, [])
        if queue in subs:
            subs.remove(queue)

    def cleanup_stale_subscribers(self, channel: str | None = None) -> int:
        """Elimina colas llenas o huérfanas (P69)."""
        channels = [channel] if channel else list(self._subscribers.keys())
        removed = 0
        for ch in channels:
            kept: list[asyncio.Queue] = []
            for q in self._subscribers.get(ch, []):
                if q.qsize() >= q.maxsize:
                    removed += 1
                    continue
                kept.append(q)
            self._subscribers[ch] = kept
        return removed

    def publish(self, channel: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if channel not in CHANNELS:
            return
        if not self._allow_publish():
            return
        message = {
            "channel": channel,
            "event": event_type,
            "payload": payload or {},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._last_payload[channel] = message
        for q in list(self._subscribers.get(channel, [])):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass
        self._redis_publish(channel, message)
        try:
            from app.observability.metrics import inc

            inc("realtime_publish_total")
        except Exception:
            pass

    def get_poll_snapshot(self, channel: str) -> dict[str, Any]:
        return self._last_payload.get(channel) or {
            "channel": channel,
            "event": "idle",
            "payload": {},
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def heartbeat(self) -> dict[str, Any]:
        msg = {
            "channel": "heartbeat",
            "event": "ping",
            "payload": {"ok": True},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._last_payload["heartbeat"] = msg
        return msg


_hub = RealtimeHub()


def get_realtime_hub() -> RealtimeHub:
    return _hub


class RealtimeService:
    def publish(self, channel: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        get_realtime_hub().publish(channel, event_type, payload)

    def publish_activity(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("activity", event_type, payload)

    def publish_jobs(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("jobs", event_type, payload)

    def publish_ops(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("ops", event_type, payload)

    def publish_pipeline(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("pipeline", event_type, payload)

    def publish_sharepoint(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("sharepoint", event_type, payload)

    def publish_dashboard(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("dashboard", event_type, payload)

    def publish_notifications(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.publish("notifications", event_type, payload)

    def build_poll_bundle(self, channels: list[str] | None = None) -> dict[str, Any]:
        hub = get_realtime_hub()
        chs = channels or list(CHANNELS)
        bundle = {ch: hub.get_poll_snapshot(ch) for ch in chs if ch in CHANNELS}
        bundle["heartbeat"] = hub.heartbeat()
        return bundle

    @staticmethod
    def format_ws_message(data: dict[str, Any]) -> str:
        return json.dumps(data, default=str)
