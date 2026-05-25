"""Centro de notificaciones UI (toasts + inbox)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import NotificationInbox
from app.services.realtime_service import RealtimeService


class NotificationCenterService:
    def push(
        self,
        db: Session,
        *,
        title: str,
        body: str | None = None,
        tone: str = "info",
        href: str | None = None,
        user_id: int | None = None,
    ) -> NotificationInbox:
        row = NotificationInbox(
            user_id=user_id,
            title=title,
            body=body,
            tone=tone,
            href=href,
        )
        db.add(row)
        db.flush()
        RealtimeService().publish_notifications(
            "new",
            {"id": row.id, "title": title, "tone": tone},
        )
        return row

    def unread_count(self, db: Session, user_id: int | None = None) -> int:
        stmt = select(func.count(NotificationInbox.id)).where(NotificationInbox.read.is_(False))
        if user_id:
            stmt = stmt.where(
                (NotificationInbox.user_id == user_id) | (NotificationInbox.user_id.is_(None))
            )
        return db.scalar(stmt) or 0

    def list_recent(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        stmt = select(NotificationInbox).order_by(NotificationInbox.created_at.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(
                (NotificationInbox.user_id == user_id) | (NotificationInbox.user_id.is_(None))
            )
        return [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "tone": n.tone,
                "href": n.href,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in db.scalars(stmt).all()
        ]

    def mark_read(self, db: Session, notification_id: int) -> None:
        db.execute(
            update(NotificationInbox)
            .where(NotificationInbox.id == notification_id)
            .values(read=True)
        )
