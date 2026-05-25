"""Inicialización de logging estructurado (P30)."""

from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar
from pathlib import Path

import yaml

from app.core.paths import PROJECT_ROOT

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")
_ops_entity_type_ctx: ContextVar[str] = ContextVar("ops_entity_type", default="-")
_ops_entity_id_ctx: ContextVar[str] = ContextVar("ops_entity_id", default="-")
_ops_action_ctx: ContextVar[str] = ContextVar("ops_action", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        record.correlation_id = correlation_id_ctx.get(request_id_ctx.get("-"))
        record.entity_type = _ops_entity_type_ctx.get("-")
        record.entity_id = _ops_entity_id_ctx.get("-")
        record.action = _ops_action_ctx.get("-")
        for attr in ("result", "elapsed_ms"):
            if not hasattr(record, attr):
                setattr(record, attr, "-")
        return True


def setup_logging(log_level: str = "INFO", *, use_yaml: bool = True) -> None:
    """Configura handlers de archivo con rotación bajo logs/."""
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = PROJECT_ROOT / "config" / "logging.yaml"
    if use_yaml and yaml_path.is_file():
        with yaml_path.open(encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))

    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))


def set_request_id(request_id: str) -> None:
    rid = request_id or "-"
    request_id_ctx.set(rid)
    correlation_id_ctx.set(rid)


def set_ops_log_context(
    *,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    action: str | None = None,
) -> None:
    if entity_type:
        _ops_entity_type_ctx.set(str(entity_type))
    if entity_id is not None:
        _ops_entity_id_ctx.set(str(entity_id))
    if action:
        _ops_action_ctx.set(str(action))


def log_ops_action(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    result: str = "ok",
    elapsed_ms: float | None = None,
    **extra: object,
) -> None:
    """Log estructurado para acciones de recovery/ops (P33)."""
    payload: dict[str, object] = {
        "action": action,
        "result": result,
        "correlation_id": correlation_id_ctx.get("-"),
    }
    if entity_type:
        payload["entity_type"] = entity_type
    if entity_id is not None:
        payload["entity_id"] = entity_id
    if elapsed_ms is not None:
        payload["elapsed_ms"] = round(elapsed_ms, 2)
    payload.update(extra)
    logger.log(
        level,
        message,
        extra={
            "action": action,
            "result": result,
            "entity_type": entity_type or "-",
            "entity_id": str(entity_id) if entity_id is not None else "-",
            "elapsed_ms": round(elapsed_ms, 2) if elapsed_ms is not None else "-",
            **{k: v for k, v in payload.items() if k not in ("action", "result")},
        },
    )
