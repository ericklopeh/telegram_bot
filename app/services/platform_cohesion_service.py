"""P61 — hub de cohesión: activity + realtime + rules + automations + compliance + inbox."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.activity_feed_service import ActivityFeedService
from app.services.realtime_service import RealtimeService

log = logging.getLogger(__name__)

# Mapeo acción → canales realtime
_ACTION_CHANNELS: dict[str, list[str]] = {
    "workflow": ["pipeline", "activity", "dashboard"],
    "sharepoint": ["sharepoint", "ops", "activity"],
    "job": ["jobs", "activity"],
    "import": ["ops", "activity", "dashboard"],
    "export": ["activity"],
    "recovery": ["ops", "activity"],
    "comment": ["activity"],
    "task": ["ops", "activity"],
    "rule": ["activity"],
    "signature": ["activity"],
    "attachment": ["activity"],
    "notification": ["activity"],
    "analytics": ["dashboard", "activity"],
    "ai": ["activity"],
    "tenant": ["activity"],
    "document": ["activity", "pipeline"],
    "sale": ["activity", "dashboard"],
    "commission": ["activity", "dashboard"],
}


def _infer_category(action: str) -> str:
    a = (action or "").lower()
    for key in _ACTION_CHANNELS:
        if key in a:
            return key
    return "activity"


class PlatformCohesionService:
    """Punto único para emitir eventos de plataforma integrados."""

    def emit(
        self,
        db: Session,
        *,
        action: str,
        title: str,
        entity_type: str,
        entity_id: int | None = None,
        detail: str | None = None,
        actor_user_id: int | None = None,
        actor_label: str | None = None,
        source: str = "system",
        tone: str = "info",
        severity: str | None = None,
        metadata: dict[str, Any] | None = None,
        href: str | None = None,
        company_id: int | None = None,
        rule_trigger: str | None = None,
        rule_context: dict[str, Any] | None = None,
        automation_trigger: str | None = None,
        automation_context: dict[str, Any] | None = None,
        compliance_before: dict[str, Any] | None = None,
        compliance_after: dict[str, Any] | None = None,
        notify_user_id: int | None = None,
        skip_automation: bool = False,
    ) -> None:
        settings = get_settings()
        cid = company_id or settings.default_company_id
        meta = dict(metadata or {})
        if severity:
            meta["severity"] = severity

        try:
            ActivityFeedService().record(
                db,
                event_type=action,
                title=title,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail,
                actor_user_id=actor_user_id,
                actor_label=actor_label or "Sistema",
                source=source,
                tone=tone if tone != "info" else ("danger" if severity == "critical" else tone),
                href=href,
                metadata=meta,
                company_id=cid,
            )
        except Exception:
            log.debug("Activity record falló", exc_info=True)

        rt = RealtimeService()
        payload = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "severity": severity,
        }
        category = _infer_category(action)
        for ch in _ACTION_CHANNELS.get(category, ["activity"]):
            rt.publish(ch, action, payload)

        if compliance_before is not None or compliance_after is not None:
            try:
                from app.services.compliance_service import ComplianceService

                ComplianceService().record_audit(
                    db,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    actor_label=actor_label,
                    before=compliance_before,
                    after=compliance_after,
                    company_id=cid,
                )
            except Exception:
                log.debug("Compliance audit falló", exc_info=True)

        if rule_trigger and rule_context is not None:
            try:
                from app.services.rule_engine import RuleEngine

                RuleEngine().evaluate(
                    db,
                    rule_trigger,
                    rule_context,
                    company_id=cid,
                    source_action=action,
                )
            except Exception:
                log.debug("Rule evaluate falló", exc_info=True)

        if automation_trigger and not skip_automation:
            try:
                from app.services.automation_service import AutomationService

                AutomationService().process_trigger(
                    db,
                    automation_trigger,
                    automation_context or {},
                    company_id=cid,
                )
            except Exception:
                log.debug("Automation trigger falló", exc_info=True)

        if notify_user_id or severity in ("warn", "critical"):
            try:
                from app.services.notification_center_service import NotificationCenterService

                NotificationCenterService().push(
                    db,
                    title=title,
                    body=detail,
                    tone=tone,
                    href=href,
                    user_id=notify_user_id,
                )
            except Exception:
                log.debug("Notification inbox falló", exc_info=True)


def safe_cohesion_emit(db: Session, **kwargs: Any) -> None:
    """Hook seguro para servicios legacy sin romper flujos P19–P60."""
    try:
        PlatformCohesionService().emit(db, **kwargs)
    except Exception:
        log.debug("safe_cohesion_emit falló", exc_info=True)
