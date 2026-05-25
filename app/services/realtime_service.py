"""P47/P61 — realtime: WebSocket hub, Redis pub/sub opcional, polling."""

from __future__ import annotations

import asyncio
import json
import logging
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


class RealtimeHub:
    """Broker en memoria por canal; Redis opcional para multi-worker."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._last_payload: dict[str, dict[str, Any]] = {}
        self._redis = None

    def _redis_client(self):
        if self._redis is not False and self._redis is None:
            url = get_settings().redis_url
            if url:
                try:
                    from redis import Redis

                    self._redis = Redis.from_url(url, decode_responses=True)
                    self._redis.ping()
                except Exception:
                    self._redis = False
                    log.debug("Redis realtime no disponible", exc_info=True)
            else:
                self._redis = False
        return self._redis if self._redis is not False else None

    def _redis_publish(self, channel: str, message: dict[str, Any]) -> None:
        client = self._redis_client()
        if not client:
            return
        try:
            client.publish(f"gaman:rt:{channel}", json.dumps(message, default=str))
        except Exception:
            log.debug("Redis publish falló", exc_info=True)

    async def subscribe(self, channel: str) -> asyncio.Queue:
        if channel not in CHANNELS:
            channel = "activity"
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        self._subscribers[channel].append(q)
        cached = self._last_payload.get(channel)
        if cached:
            await q.put(cached)
        return q

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(channel, [])
        if queue in subs:
            subs.remove(queue)

    def publish(self, channel: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if channel not in CHANNELS:
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
