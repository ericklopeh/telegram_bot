"""Inicialización de logging estructurado (P30)."""

from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar
from pathlib import Path

import yaml

from app.core.paths import PROJECT_ROOT

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
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
    request_id_ctx.set(request_id or "-")
