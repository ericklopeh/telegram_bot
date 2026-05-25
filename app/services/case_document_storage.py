"""Rutas locales estructuradas para documentos de caso (P24)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.models.case import Case
from app.utils.naming import sanitize_name

_MAX_SEGMENT = 120


def _safe_segment(text: str, fallback: str = "sin_dato") -> str:
    cleaned = sanitize_name(text or fallback)
    cleaned = re.sub(r"[^\w\s\-\.]", "_", cleaned, flags=re.UNICODE)
    cleaned = cleaned.strip("._ ") or fallback
    return cleaned[:_MAX_SEGMENT]


def case_documents_base_dir(case: Case, *, project_root: Path | None = None) -> Path:
    """
    storage/cases/{year}/SEM_{week}/{seller}/FOLIO_{folio}_{cliente}/documents/
    """
    root = project_root or Path.cwd()
    created = case.created_at or datetime.now(timezone.utc)
    year = str(created.year)
    week_raw = (case.week_code or "SEM_00").strip()
    week_seg = week_raw if week_raw.upper().startswith("SEM_") else f"SEM_{week_raw}"
    seller = _safe_segment(case.seller_name or "sin_vendedor", "sin_vendedor")
    folio = case.official_folio or case.temp_folio or case.public_id or str(case.id)
    cliente = _safe_segment(case.client_name, "cliente")
    folio_seg = _safe_segment(f"FOLIO_{folio}_{cliente}", f"FOLIO_{case.id}")
    return root / "storage" / "cases" / year / week_seg / seller / folio_seg / "documents"


def case_documents_remote_relative_path(case: Case) -> str:
    """
    Ruta relativa bajo MS_ROOT_FOLDER (alineada con storage/cases/.../documents).
    {year}/SEM_{week}/{seller}/FOLIO_{folio}_{cliente}/documents
    """
    created = case.created_at or datetime.now(timezone.utc)
    year = str(created.year)
    week_raw = (case.week_code or "SEM_00").strip()
    week_seg = week_raw if week_raw.upper().startswith("SEM_") else f"SEM_{week_raw}"
    seller = _safe_segment(case.seller_name or "sin_vendedor", "sin_vendedor")
    folio = case.official_folio or case.temp_folio or case.public_id or str(case.id)
    cliente = _safe_segment(case.client_name, "cliente")
    folio_seg = _safe_segment(f"FOLIO_{folio}_{cliente}", f"FOLIO_{case.id}")
    return f"{year}/{week_seg}/{seller}/{folio_seg}/documents"


def build_stored_filename(
    document_type: str,
    original_filename: str | None,
    *,
    version: int = 1,
) -> str:
    ext = ""
    if original_filename and "." in original_filename:
        ext = original_filename[original_filename.rfind(".") :]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_type = re.sub(r"[^\w\-]", "_", document_type)[:40]
    return f"{safe_type}_v{version}_{ts}{ext}"
