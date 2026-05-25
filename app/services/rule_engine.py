"""P50 — motor de reglas dinámicas configurables."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import DynamicRule, RuleExecutionLog
from app.services.compliance_service import ComplianceService

log = logging.getLogger(__name__)


def _get_nested(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _eval_condition(cond: dict[str, Any], context: dict[str, Any]) -> bool:
    field = cond.get("field", "")
    op = cond.get("op", "eq")
    expected = cond.get("value")
    actual = _get_nested(context, field) if "." in field else context.get(field)

    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "gt":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if op == "gte":
        try:
            return float(actual) >= float(expected)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    if op == "in":
        return actual in (expected or [])
    if op == "contains":
        return str(expected) in str(actual or "")
    return False


def _eval_conditions(spec: dict[str, Any], context: dict[str, Any]) -> bool:
    mode = spec.get("mode", "all")
    conditions = spec.get("conditions") or []
    if not conditions:
        return True
    results = [_eval_condition(c, context) for c in conditions]
    if mode == "any":
        return any(results)
    return all(results)


class RuleEngine:
    def list_rules(self, db: Session, *, company_id: int = 1) -> list[DynamicRule]:
        return list(
            db.scalars(
                select(DynamicRule)
                .where(DynamicRule.company_id == company_id)
                .order_by(DynamicRule.priority.asc())
            ).all()
        )

    def evaluate(
        self,
        db: Session,
        trigger_event: str,
        context: dict[str, Any],
        *,
        company_id: int = 1,
        simulated: bool = False,
        source_action: str | None = None,
        skip_cohesion_emit: bool = False,
    ) -> list[dict[str, Any]]:
        rules = list(
            db.scalars(
                select(DynamicRule)
                .where(
                    DynamicRule.enabled.is_(True),
                    DynamicRule.trigger_event == trigger_event,
                    DynamicRule.company_id == company_id,
                )
                .order_by(DynamicRule.priority.asc())
            ).all()
        )
        fired: list[dict[str, Any]] = []
        for rule in rules:
            matched = _eval_conditions(rule.conditions_json or {}, context)
            actions_result: list[str] = []
            if matched and not simulated:
                actions_result = self._apply_actions(db, rule, context)
            self._log_execution(
                db,
                rule.rule_key,
                trigger_event,
                matched,
                context,
                actions_result,
                simulated=simulated,
            )
            if matched:
                fired.append(
                    {
                        "rule_key": rule.rule_key,
                        "name": rule.name,
                        "actions": actions_result,
                        "priority": rule.priority,
                    }
                )
        if fired and not skip_cohesion_emit and not simulated:
            try:
                from app.services.platform_cohesion_service import PlatformCohesionService

                PlatformCohesionService().emit(
                    db,
                    action="rule_engine_fired",
                    title=f"Reglas ejecutadas ({trigger_event})",
                    entity_type=context.get("entity_type", "system"),
                    entity_id=context.get("entity_id"),
                    detail=", ".join(r["rule_key"] for r in fired),
                    source="rule_engine",
                    tone="warn",
                    metadata={"fired": fired, "source_action": source_action},
                    skip_automation=True,
                )
            except Exception:
                pass
        return fired

    def simulate(self, db: Session, trigger_event: str, context: dict[str, Any], **kwargs) -> list[dict[str, Any]]:
        return self.evaluate(db, trigger_event, context, simulated=True, **kwargs)

    def set_rule_enabled(self, db: Session, rule_key: str, enabled: bool) -> DynamicRule | None:
        rule = db.scalar(select(DynamicRule).where(DynamicRule.rule_key == rule_key))
        if not rule:
            return None
        rule.enabled = enabled
        db.flush()
        return rule

    def recent_logs(self, db: Session, limit: int = 50) -> list[dict[str, Any]]:
        rows = list(
            db.scalars(
                select(RuleExecutionLog).order_by(RuleExecutionLog.created_at.desc()).limit(limit)
            ).all()
        )
        return [
            {
                "rule_key": r.rule_key,
                "trigger": r.trigger_event,
                "matched": r.matched,
                "simulated": r.simulated,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def _log_execution(
        self,
        db: Session,
        rule_key: str,
        trigger: str,
        matched: bool,
        context: dict[str, Any],
        actions: list[str],
        *,
        simulated: bool,
    ) -> None:
        try:
            db.add(
                RuleExecutionLog(
                    rule_key=rule_key,
                    trigger_event=trigger,
                    matched=matched,
                    context_json=context,
                    actions_applied={"actions": actions} if actions else None,
                    simulated=simulated,
                )
            )
            db.flush()
        except Exception:
            log.debug("No se pudo registrar rule_execution_log", exc_info=True)

    def _apply_actions(
        self,
        db: Session,
        rule: DynamicRule,
        context: dict[str, Any],
    ) -> list[str]:
        actions = (rule.actions_json or {}).get("actions") or []
        applied: list[str] = []
        for action in actions:
            atype = action.get("type", "")
            if atype == "require_supervisor":
                applied.append("supervisor_required")
            elif atype == "require_double_validation":
                applied.append("double_validation")
            elif atype == "block_transition":
                applied.append(f"blocked:{action.get('reason', 'rule')}")
            elif atype == "notify":
                applied.append(f"notify:{action.get('channel', 'internal')}")
            elif atype == "compliance_log":
                ComplianceService().record_event(
                    db,
                    event_type=action.get("event_type", "rule_triggered"),
                    message=action.get("message", rule.name),
                    severity=action.get("severity", "info"),
                    entity_type=context.get("entity_type"),
                    entity_id=context.get("entity_id"),
                )
            else:
                applied.append(atype)
        return applied

    def seed_defaults(self, db: Session) -> None:
        defaults = [
            {
                "rule_key": "sec21_high_amount",
                "name": "Sección 21 monto alto",
                "trigger_event": "sale_validation",
                "conditions_json": {
                    "mode": "all",
                    "conditions": [
                        {"field": "seccion", "op": "eq", "value": "21"},
                        {"field": "monto", "op": "gt", "value": 15000},
                    ],
                },
                "actions_json": {
                    "actions": [{"type": "require_supervisor"}],
                },
            },
            {
                "rule_key": "loan_double_check",
                "name": "Préstamo alto doble validación",
                "trigger_event": "sale_validation",
                "conditions_json": {
                    "mode": "all",
                    "conditions": [{"field": "prestamo", "op": "gt", "value": 50000}],
                },
                "actions_json": {
                    "actions": [{"type": "require_double_validation"}],
                },
            },
        ]
        for spec in defaults:
            exists = db.scalar(select(DynamicRule).where(DynamicRule.rule_key == spec["rule_key"]))
            if exists:
                continue
            db.add(DynamicRule(**spec, description="Regla demo P50"))
        db.flush()
