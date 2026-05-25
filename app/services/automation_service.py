"""P62 — motor de automatizaciones TRIGGER → CONDITION → ACTION."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import AutomationExecution, AutomationFlow
from app.services.rule_engine import _eval_conditions

log = logging.getLogger(__name__)


class AutomationService:
    def list_flows(self, db: Session, *, company_id: int = 1) -> list[AutomationFlow]:
        return list(
            db.scalars(
                select(AutomationFlow)
                .where(AutomationFlow.company_id == company_id)
                .order_by(AutomationFlow.id)
            ).all()
        )

    def process_trigger(
        self,
        db: Session,
        trigger_type: str,
        context: dict[str, Any],
        *,
        company_id: int = 1,
    ) -> list[dict[str, Any]]:
        flows = list(
            db.scalars(
                select(AutomationFlow).where(
                    AutomationFlow.enabled.is_(True),
                    AutomationFlow.trigger_type == trigger_type,
                    AutomationFlow.company_id == company_id,
                )
            ).all()
        )
        results = []
        for flow in flows:
            if flow.conditions_json and not _eval_conditions(flow.conditions_json, context):
                continue
            applied = self._run_actions(db, flow, context)
            ex = AutomationExecution(
                flow_id=flow.id,
                trigger_type=trigger_type,
                status="completed",
                context_json=context,
                result_json={"actions": applied},
            )
            db.add(ex)
            db.flush()
            results.append({"flow_key": flow.flow_key, "actions": applied})
        if results:
            try:
                from app.services.realtime_service import RealtimeService

                RealtimeService().publish_ops("automation", {"trigger": trigger_type, "results": results})
            except Exception:
                pass
        return results

    def _run_actions(
        self,
        db: Session,
        flow: AutomationFlow,
        context: dict[str, Any],
    ) -> list[str]:
        actions = (flow.actions_json or {}).get("actions") or []
        applied: list[str] = []
        for action in actions:
            atype = action.get("type", "")
            if atype == "notify":
                try:
                    from app.services.notification_center_service import NotificationCenterService

                    NotificationCenterService().push(
                        db,
                        title=action.get("title", flow.name),
                        body=action.get("body", ""),
                        tone=action.get("tone", "info"),
                        href=context.get("href"),
                    )
                    applied.append("notify")
                except Exception:
                    pass
            elif atype == "create_task":
                try:
                    from app.services.calendar_service import CalendarService

                    CalendarService().create_task(
                        db,
                        title=action.get("title", f"Tarea auto: {flow.name}"),
                        description=action.get("body"),
                        case_id=context.get("case_id"),
                        company_id=flow.company_id,
                    )
                    applied.append("create_task")
                except Exception:
                    pass
            elif atype == "create_incident":
                try:
                    from app.services.compliance_service import ComplianceService

                    ComplianceService().record_event(
                        db,
                        event_type="automation_incident",
                        message=action.get("message", flow.name),
                        severity=action.get("severity", "warn"),
                        entity_type=context.get("entity_type"),
                        entity_id=context.get("entity_id"),
                    )
                    applied.append("create_incident")
                except Exception:
                    pass
            elif atype == "enqueue_job":
                try:
                    from app.services.job_service import JobService

                    JobService().enqueue(
                        db,
                        action.get("job_type", "recovery_bulk"),
                        payload=context,
                        run_async=True,
                    )
                    applied.append("enqueue_job")
                except Exception:
                    pass
            elif atype == "webhook":
                applied.append("webhook_queued")
            else:
                applied.append(atype)
        return applied

    def seed_defaults(self, db: Session) -> None:
        defaults = [
            {
                "flow_key": "sp_failed_notify",
                "name": "SharePoint fallido → notificar",
                "trigger_type": "sharepoint_failed",
                "conditions_json": None,
                "actions_json": {
                    "actions": [
                        {
                            "type": "notify",
                            "title": "SharePoint falló",
                            "body": "Revisar caso en ops",
                            "tone": "danger",
                        }
                    ]
                },
            },
            {
                "flow_key": "sla_task",
                "name": "SLA excedido → tarea",
                "trigger_type": "sla_exceeded",
                "actions_json": {
                    "actions": [{"type": "create_task", "title": "Seguimiento SLA"}]
                },
            },
            {
                "flow_key": "import_done_snapshot",
                "name": "Import OK → snapshot",
                "trigger_type": "import_completed",
                "actions_json": {
                    "actions": [{"type": "enqueue_job", "job_type": "bi_refresh"}]
                },
            },
        ]
        for spec in defaults:
            if db.scalar(select(AutomationFlow).where(AutomationFlow.flow_key == spec["flow_key"])):
                continue
            db.add(AutomationFlow(**spec, company_id=1))
        db.flush()
