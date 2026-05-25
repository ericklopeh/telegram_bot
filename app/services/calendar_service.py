"""P49 — agenda, tareas operativas y SLA visual."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import OperationalTask, TaskReminder
from app.services.realtime_service import RealtimeService


class CalendarService:
    def list_tasks(
        self,
        db: Session,
        *,
        status: str | None = None,
        assigned_user_id: int | None = None,
        company_id: int = 1,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(OperationalTask).where(OperationalTask.company_id == company_id)
        if status:
            stmt = stmt.where(OperationalTask.status == status)
        if assigned_user_id:
            stmt = stmt.where(OperationalTask.assigned_user_id == assigned_user_id)
        stmt = stmt.order_by(OperationalTask.due_at.asc().nulls_last()).limit(limit)
        return [self._serialize_task(t) for t in db.scalars(stmt).all()]

    def create_task(
        self,
        db: Session,
        *,
        title: str,
        description: str | None = None,
        due_at: datetime | None = None,
        case_id: int | None = None,
        assigned_user_id: int | None = None,
        assigned_label: str | None = None,
        sla_hours: int | None = 24,
        created_by: str | None = None,
        company_id: int = 1,
    ) -> OperationalTask:
        task = OperationalTask(
            title=title,
            description=description,
            due_at=due_at or (datetime.now(timezone.utc) + timedelta(hours=sla_hours or 24)),
            case_id=case_id,
            assigned_user_id=assigned_user_id,
            assigned_label=assigned_label,
            sla_hours=sla_hours,
            created_by=created_by,
            company_id=company_id,
        )
        db.add(task)
        db.flush()
        if task.due_at:
            db.add(
                TaskReminder(
                    task_id=task.id,
                    remind_at=task.due_at - timedelta(hours=2),
                    channel="internal",
                )
            )
        RealtimeService().publish_ops("task_created", {"task_id": task.id})
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="task_created",
                title=title,
                entity_type="task",
                entity_id=task.id,
                actor_label=created_by,
                source="calendar",
                href="/calendar",
                company_id=company_id,
            )
        except Exception:
            pass
        return task

    def calendar_events(self, db: Session, *, company_id: int = 1) -> list[dict[str, Any]]:
        tasks = self.list_tasks(db, company_id=company_id)
        events = []
        for t in tasks:
            if t.get("due_at"):
                events.append(
                    {
                        "id": f"task-{t['id']}",
                        "title": t["title"],
                        "start": t["due_at"],
                        "type": "task",
                        "status": t["status"],
                        "href": f"/tasks?highlight={t['id']}",
                    }
                )
        return events

    def sla_summary(self, db: Session, *, company_id: int = 1) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        tasks = list(
            db.scalars(
                select(OperationalTask).where(
                    OperationalTask.company_id == company_id,
                    OperationalTask.status == "open",
                )
            ).all()
        )
        overdue = sum(1 for t in tasks if t.due_at and t.due_at < now)
        due_soon = sum(
            1 for t in tasks if t.due_at and now <= t.due_at <= now + timedelta(hours=24)
        )
        return {"open": len(tasks), "overdue": overdue, "due_soon": due_soon}

    def _serialize_task(self, t: OperationalTask) -> dict[str, Any]:
        return {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "case_id": t.case_id,
            "assigned_label": t.assigned_label,
            "sla_hours": t.sla_hours,
        }
