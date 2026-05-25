"""P40 — feed de actividad global y por entidad."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.case_event import CaseEvent
from app.models.platform import ActivityEvent
from app.services.performance_service import PerformanceService


def _time_ago(dt: datetime | None) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "ahora"
    if mins < 60:
        return f"hace {mins} min"
    hours = mins // 60
    if hours < 48:
        return f"hace {hours} h"
    return f"hace {delta.days} d"


def _initials(label: str | None) -> str:
    if not label:
        return "?"
    parts = label.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return label[:2].upper()


class ActivityFeedService:
    def record(
        self,
        db: Session,
        *,
        event_type: str,
        title: str,
        entity_type: str,
        entity_id: int | None = None,
        detail: str | None = None,
        actor_user_id: int | None = None,
        actor_label: str | None = None,
        source: str = "system",
        tone: str = "info",
        href: str | None = None,
        metadata: dict[str, Any] | None = None,
        company_id: int | None = None,
        branch_id: int | None = None,
    ) -> ActivityEvent:
        settings = get_settings()
        ev = ActivityEvent(
            event_type=event_type,
            title=title,
            detail=detail,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            source=source,
            tone=tone,
            href=href,
            metadata_json=metadata,
            company_id=company_id or settings.default_company_id,
            branch_id=branch_id or settings.default_branch_id,
        )
        db.add(ev)
        db.flush()
        from app.services.performance_service import cache_invalidate

        cache_invalidate("activity:")
        try:
            from app.services.realtime_service import RealtimeService

            RealtimeService().publish_activity(
                event_type,
                {"entity_type": entity_type, "entity_id": entity_id, "title": title},
            )
        except Exception:
            pass
        return ev

    def list_feed_grouped(
        self,
        db: Session,
        *,
        limit: int = 50,
        company_id: int | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        rows = self.list_feed(db, limit=limit, company_id=company_id, **filters)
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = row.get("entity_type") or "other"
            groups.setdefault(key, []).append(row)
        return [
            {
                "entity_type": et,
                "label": et.replace("_", " ").title(),
                "count": len(items),
                "items": items,
            }
            for et, items in groups.items()
        ]

    def list_feed(
        self,
        db: Session,
        *,
        limit: int = 40,
        entity_type: str | None = None,
        entity_id: int | None = None,
        actor_user_id: int | None = None,
        company_id: int | None = None,
        tone: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        cache_key = f"activity:{entity_type}:{entity_id}:{actor_user_id}:{tone}:{source}:{limit}"
        from app.services.performance_service import cache_get, cache_set

        hit = cache_get(cache_key)
        if hit is not None:
            return hit

        rows = self._query_feed(
            db,
            limit=limit * 2,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            company_id=company_id,
            tone=tone,
            source=source,
            event_type=event_type,
        )
        if tone:
            rows = [r for r in rows if r.get("tone") == tone]
        if source:
            rows = [r for r in rows if r.get("source") == source]
        rows = rows[:limit]
        if len(rows) < limit:
            rows = self._merge_case_events(db, rows, limit=limit)

        cache_set(cache_key, rows, ttl=30)
        return rows

    def _query_feed(
        self,
        db: Session,
        *,
        limit: int,
        entity_type: str | None,
        entity_id: int | None,
        actor_user_id: int | None,
        company_id: int | None,
        tone: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(limit)
        if entity_type:
            stmt = stmt.where(ActivityEvent.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ActivityEvent.entity_id == entity_id)
        if actor_user_id is not None:
            stmt = stmt.where(ActivityEvent.actor_user_id == actor_user_id)
        if company_id is not None:
            stmt = stmt.where(ActivityEvent.company_id == company_id)
        if tone:
            stmt = stmt.where(ActivityEvent.tone == tone)
        if source:
            stmt = stmt.where(ActivityEvent.source == source)
        if event_type:
            stmt = stmt.where(ActivityEvent.event_type == event_type)

        events = list(db.scalars(stmt).all())
        return [self._serialize(ev) for ev in events]

    def _merge_case_events(
        self,
        db: Session,
        existing: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        seen_ids = {r["id"] for r in existing if r.get("source_table") == "activity_events"}
        stmt = select(CaseEvent).order_by(CaseEvent.created_at.desc()).limit(limit)
        case_events = list(db.scalars(stmt).all())
        merged = list(existing)
        for ce in case_events:
            key = f"ce-{ce.id}"
            if key in seen_ids:
                continue
            merged.append(
                {
                    "id": key,
                    "event_type": ce.event_type,
                    "title": ce.message or ce.event_type.replace("_", " ").title(),
                    "detail": ce.message,
                    "entity_type": "case",
                    "entity_id": ce.case_id,
                    "actor_label": ce.actor_role or "system",
                    "initials": _initials(ce.actor_role),
                    "source": ce.source or "system",
                    "tone": "warn" if "error" in (ce.event_type or "") else "info",
                    "href": f"/casos/{ce.case_id}",
                    "time_ago": _time_ago(ce.created_at),
                    "created_at": ce.created_at.isoformat() if ce.created_at else None,
                    "source_table": "case_events",
                }
            )
        merged.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return merged[:limit]

    def _serialize(self, ev: ActivityEvent) -> dict[str, Any]:
        label = ev.actor_label or "Sistema"
        meta = ev.metadata_json or {}
        severity = meta.get("severity")
        return {
            "id": ev.id,
            "event_type": ev.event_type,
            "title": ev.title,
            "detail": ev.detail,
            "entity_type": ev.entity_type,
            "entity_id": ev.entity_id,
            "actor_label": label,
            "initials": _initials(label),
            "source": ev.source,
            "tone": ev.tone,
            "severity": severity,
            "badge": severity or ev.tone,
            "href": ev.href,
            "time_ago": _time_ago(ev.created_at),
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "source_table": "activity_events",
            "metadata": meta,
        }

    def sync_from_case_event(self, db: Session, case_event: CaseEvent) -> ActivityEvent:
        return self.record(
            db,
            event_type=case_event.event_type,
            title=case_event.message or case_event.event_type,
            entity_type="case",
            entity_id=case_event.case_id,
            detail=case_event.message,
            actor_user_id=case_event.actor_user_id,
            actor_label=case_event.actor_role,
            source=case_event.source or "system",
            tone="warn" if "fail" in case_event.event_type else "info",
            href=f"/casos/{case_event.case_id}",
            metadata=case_event.metadata_json,
        )
