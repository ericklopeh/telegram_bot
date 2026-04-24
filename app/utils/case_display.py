"""Formato legible para mostrar casos al vendedor: nombre — fecha/hora local."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models.case import Case


def _case_dt_to_local(dt: datetime | None, tz_name: str) -> datetime:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def format_case_primary_label(case: Case) -> str:
    """
    Ej.: Juan Pérez — 23/04/2026 14:35
    Usa created_at del caso (alta) en la zona configurada (DISPLAY_TIMEZONE).
    """
    settings = get_settings()
    local = _case_dt_to_local(case.created_at, settings.display_timezone)
    return f"{case.client_name} — {local.strftime('%d/%m/%Y %H:%M')}"


def format_case_ref_line(case: Case) -> str:
    """Línea corta con folio técnico para soporte o operación."""
    ref = case.official_folio or case.public_id
    return f"Ref: {ref}"


def format_vendor_case_summary(case: Case) -> str:
    """Texto simple para vendedores: nombre, cuándo y estatus visible (sin folios técnicos)."""
    settings = get_settings()
    local = _case_dt_to_local(case.created_at, settings.display_timezone)
    when = local.strftime("%d/%m/%Y a las %H:%M")
    return f"Cliente: {case.client_name}\nCuándo: {when}\nEstatus: {case.visible_status}"


def format_vendor_button_label(case: Case) -> str:
    """Etiqueta corta para botones (nombre en primer plano + fecha/hora)."""
    settings = get_settings()
    local = _case_dt_to_local(case.created_at, settings.display_timezone)
    return f"{case.client_name} · {local.strftime('%d/%m %H:%M')}"
