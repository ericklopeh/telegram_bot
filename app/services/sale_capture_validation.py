"""Validaciones de formulario de captura de ventas (P19)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

_RFC_RE = re.compile(
    r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$",
    re.IGNORECASE,
)
_QNA_RE = re.compile(r"^\d{1,2}-\d{4}$")


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip().replace(",", "").replace("$", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico inválido: {raw}") from exc


def _parse_int(raw: str | None) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"Entero inválido: {raw}") from exc


def parse_sale_form(form: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Convierte y valida campos del POST. Retorna (data, errors)."""
    errors: list[str] = []

    vendedor = (form.get("vendedor") or "").strip()
    cliente = (form.get("cliente") or "").strip()
    if not vendedor:
        errors.append("El vendedor es obligatorio.")
    if not cliente:
        errors.append("El cliente es obligatorio.")

    fecha_raw = (form.get("fecha") or "").strip()
    sale_date: date | None = None
    if not fecha_raw:
        errors.append("La fecha es obligatoria.")
    else:
        try:
            sale_date = date.fromisoformat(fecha_raw[:10])
        except ValueError:
            errors.append("Fecha inválida (use AAAA-MM-DD).")

    rfc = (form.get("rfc") or "").strip().upper()
    if rfc and not _RFC_RE.match(rfc):
        errors.append("RFC con formato inválido (12 o 13 caracteres).")

    qna = (form.get("qna") or "").strip()
    if qna and not _QNA_RE.match(qna):
        errors.append("QNA debe tener formato QQ-AAAA (ej. 24-2026).")

    folio = (form.get("folio") or "").strip()
    if not folio:
        errors.append("El folio es obligatorio.")
    elif not folio.isdigit():
        errors.append("El folio debe ser numérico.")

    plazo: int | None = None
    try:
        plazo = _parse_int(form.get("plazo"))
    except ValueError as exc:
        errors.append(str(exc))
    if plazo is None and "plazo" in form and str(form.get("plazo") or "").strip():
        errors.append("El plazo debe ser numérico.")
    elif plazo is not None and plazo <= 0:
        errors.append("El plazo debe ser mayor a cero.")

    numeric_fields = {
        "costo": form.get("costo"),
        "venta": form.get("venta"),
        "venta_refinanciamiento": form.get("venta_refinanciamiento"),
        "total_venta": form.get("total_venta"),
        "precio_comision": form.get("precio_comision"),
        "venta_sin_agregado": form.get("venta_sin_agregado"),
        "recuperacion": form.get("recuperacion"),
    }
    parsed_nums: dict[str, Decimal | None] = {}
    for key, raw in numeric_fields.items():
        try:
            parsed_nums[key] = _parse_decimal(raw)
        except ValueError as exc:
            errors.append(str(exc))

    if parsed_nums.get("costo") is None and str(form.get("costo") or "").strip():
        errors.append("El costo es obligatorio o inválido.")
    if parsed_nums.get("venta") is None and parsed_nums.get("total_venta") is None:
        if str(form.get("venta") or "").strip() or str(form.get("total_venta") or "").strip():
            errors.append("Indique venta o total de venta válido.")

    data = {
        "folio": folio,
        "sale_date": sale_date,
        "vendedor": vendedor,
        "seccion": (form.get("seccion") or "").strip() or None,
        "qna": qna or None,
        "cliente": cliente,
        "rfc": rfc or None,
        "codigo": (form.get("codigo") or "").strip() or None,
        "producto": (form.get("producto") or "").strip() or None,
        "tipo_venta": (form.get("tipo_venta") or "").strip() or None,
        "plazo": plazo,
        "costo": parsed_nums.get("costo"),
        "venta": parsed_nums.get("venta"),
        "venta_refinanciamiento": parsed_nums.get("venta_refinanciamiento"),
        "total_venta": parsed_nums.get("total_venta"),
        "precio_comision": parsed_nums.get("precio_comision"),
        "venta_sin_agregado": parsed_nums.get("venta_sin_agregado"),
        "recuperacion": parsed_nums.get("recuperacion"),
        "tipo_cotizacion": (form.get("tipo_cotizacion") or "").strip() or None,
        "observaciones": (form.get("observaciones") or "").strip() or None,
        "semana": (form.get("semana") or "").strip() or None,
    }
    return data, errors
