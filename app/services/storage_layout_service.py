"""Asegura estructura de directorios storage/logs (P30)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.paths import EXCEL_EXPORTS_DIR, PROJECT_ROOT, STORAGE_DIR

log = logging.getLogger(__name__)

_REQUIRED_UNDER_STORAGE = (
    "cases",
    "imports",
    "excel_exports",
    "excel_exports/daily",
    "excel_exports/operations",
    "excel_exports/imports",
    "excel_exports/erp",
    "excel_exports/bi",
    "commission_exports",
    "pedidos",
    "revisiones",
    "templates",
)


def ensure_runtime_directories() -> list[str]:
    """Crea carpetas operativas; no escribe en excel_masters."""
    created: list[str] = []
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    for sub in _REQUIRED_UNDER_STORAGE:
        path = STORAGE_DIR / sub
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))

    EXCEL_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logs_root = PROJECT_ROOT / "logs"
    for sub in ("", "archive"):
        path = logs_root if not sub else logs_root / sub
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))

    if created:
        log.info("Directorios creados: %s", ", ".join(created))
    return created
