"""Validación de rutas Excel: maestros solo lectura, escritura solo en exports (P23)."""

from __future__ import annotations

from pathlib import Path

from app.core.paths import EXCEL_EXPORTS_DIR, EXCEL_MASTER_DIR


def is_under_excel_masters(path: Path | str) -> bool:
    try:
        resolved = Path(path).resolve()
        masters = EXCEL_MASTER_DIR.resolve()
        return masters in resolved.parents or resolved == masters
    except (OSError, ValueError):
        return False


def is_under_excel_exports(path: Path | str) -> bool:
    try:
        resolved = Path(path).resolve()
        exports = EXCEL_EXPORTS_DIR.resolve()
        return exports in resolved.parents or resolved == exports
    except (OSError, ValueError):
        return False


def assert_not_excel_master_path(path: Path | str) -> None:
    """Impide operar sobre maestros (solo lectura)."""
    if is_under_excel_masters(path):
        raise ValueError(f"Ruta prohibida en maestro Excel: {path}")


def assert_writable_excel_path(path: Path | str) -> None:
    """Lanza ValueError si la ruta de escritura apunta a maestros."""
    p = Path(path)
    if is_under_excel_masters(p):
        raise ValueError(f"Escritura prohibida en maestro Excel: {p}")
    if not is_under_excel_exports(p):
        raise ValueError(f"Escritura Excel solo permitida bajo exports: {p}")
