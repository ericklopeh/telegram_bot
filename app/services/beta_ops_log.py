"""Logging operativo beta / modo seguro (P34)."""

from __future__ import annotations

import logging

from app.core.logging_setup import log_ops_action

log = logging.getLogger("app.beta_ops")

SAFE_MODE_BLOCKED = "SAFE_MODE_BLOCKED"
MASS_ACTION_CONFIRMED = "MASS_ACTION_CONFIRMED"
BETA_WARNING_TRIGGERED = "BETA_WARNING_TRIGGERED"


def log_safe_mode_blocked(
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    reason: str,
) -> None:
    log_ops_action(
        log,
        logging.WARNING,
        f"{SAFE_MODE_BLOCKED}: {action} — {reason}",
        action=SAFE_MODE_BLOCKED,
        entity_type=entity_type,
        entity_id=entity_id,
        result="blocked",
        blocked_action=action,
        reason=reason,
    )


def log_mass_action_confirmed(
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    username: str | None = None,
) -> None:
    log_ops_action(
        log,
        logging.INFO,
        f"{MASS_ACTION_CONFIRMED}: {action}",
        action=MASS_ACTION_CONFIRMED,
        entity_type=entity_type,
        entity_id=entity_id,
        result="confirmed",
        username=username or "",
        mass_action=action,
    )


def log_beta_warning(code: str, message: str, **extra: object) -> None:
    log_ops_action(
        log,
        logging.WARNING,
        f"{BETA_WARNING_TRIGGERED}: {code} — {message}",
        action=BETA_WARNING_TRIGGERED,
        result="warning",
        warning_code=code,
        **extra,
    )
