"""Mensajes de error legibles para operadores (P31)."""

from __future__ import annotations

import re

# Patrones → mensaje amigable (orden: más específico primero)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"graph|sharepoint|401|403|404|429", re.I), "SharePoint/Microsoft Graph: revise credenciales en .env y el health en Admin → SharePoint."),
    (re.compile(r"upload.*fail|UPLOAD_FAILED|sharepoint.*error", re.I), "La subida a SharePoint falló. Reintente desde documentos del caso o Admin SharePoint."),
    (re.compile(r"excel|export.*fail|registration_failed|REGISTRATION", re.I), "Error al registrar en Excel. Revise ventas pendientes y reintente el registro."),
    (re.compile(r"workflow|transición|blocked|dependenc", re.I), "El workflow bloqueó la acción. Revise documentos, SharePoint y el estado del caso."),
    (re.compile(r"document|checklist|faltan|missing.*doc", re.I), "Faltan documentos o están pendientes de validación. Abra la gestión documental del caso."),
    (re.compile(r"comisi[oó]n|commission", re.I), "Problema con la comisión vinculada a la venta. Revise /comisiones."),
    (re.compile(r"storage|permission|read.?only|excel_masters", re.I), "Error de almacenamiento. No modifique excel_masters; use solo exports."),
    (re.compile(r"database|sqlalchemy|connection|psycopg", re.I), "Error de base de datos. Verifique que PostgreSQL esté activo y DATABASE_URL."),
    (re.compile(r"timeout|timed out", re.I), "La operación tardó demasiado (timeout). Reintente o revise red/SharePoint."),
]


def friendly_error_message(raw: str | None, *, category: str | None = None) -> str:
    """Convierte mensajes técnicos en texto útil para el operador."""
    if not raw or not str(raw).strip():
        return ""
    text = str(raw).strip()
    if len(text) > 500 and "Traceback" in text:
        return "Ocurrió un error interno. Si persiste, contacte a sistemas (sin detalles técnicos en pantalla)."

    if category == "graph":
        return _PATTERNS[0][1]
    if category == "excel":
        return _PATTERNS[2][1]
    if category == "workflow":
        return _PATTERNS[3][1]
    if category == "document":
        return _PATTERNS[4][1]
    if category == "commission":
        return _PATTERNS[5][1]
    if category == "storage":
        return _PATTERNS[6][1]
    if category == "database":
        return _PATTERNS[7][1]

    for pattern, msg in _PATTERNS:
        if pattern.search(text):
            return msg
    if len(text) > 220:
        return text[:220] + "…"
    return text


def friendly_block_reason(reason: str | None) -> str:
    """Razones de bloqueo del action guard."""
    return friendly_error_message(reason, category="workflow") if reason else ""
