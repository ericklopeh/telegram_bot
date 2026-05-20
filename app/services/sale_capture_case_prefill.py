"""Autollenado de formulario de venta desde un caso existente (P19.1)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.models.sale_capture import SaleCapture
from app.repositories.case_repository import CaseRepository
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.ocr_service import OCRService


def build_form_prefill_from_case(
    db: Session,
    case_id: int,
    *,
    suggested_folio: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Retorna (form_dict, error). No crea captura; solo datos para el formulario."""
    case = CaseRepository.get_by_id(db, case_id)
    if not case:
        return None, "Caso no encontrado."
    if case.case_type != C.CASE_TYPE_PEDIDO:
        return None, "Solo se puede precargar desde casos de tipo pedido."

    linked = db.scalar(select(SaleCapture.id).where(SaleCapture.case_id == case_id))
    if linked:
        return None, f"El caso ya está vinculado a la captura #{linked}. Edite esa captura."

    ocr = OCRService.build_case_autorizacion_prefill(db, case_id)
    form_ocr = ocr.get("form") or {}

    folio = case.official_folio or suggested_folio or SaleCaptureRepository.next_suggested_folio(db)

    tipo_cot = "MATERIAL"
    if case.order_type == C.ORDER_TYPE_MUEBLE:
        tipo_cot = "MUEBLE"
    elif case.order_type == C.ORDER_TYPE_PRESTAMO:
        tipo_cot = "DINERO"

    monto = form_ocr.get("monto_total")
    plazo = form_ocr.get("plazo_qnas")

    return {
        "case_id": case_id,
        "folio": str(folio),
        "fecha": date.today().isoformat(),
        "vendedor": case.seller_name or "",
        "semana": case.week_code or get_settings().effective_semana_activa,
        "cliente": case.client_name,
        "rfc": str(form_ocr.get("rfc") or ""),
        "seccion": str(form_ocr.get("categoria") or form_ocr.get("seccion") or ""),
        "qna": str(form_ocr.get("qna_inicial") or ""),
        "codigo": "",
        "producto": "",
        "tipo_venta": "PARALELA",
        "tipo_cotizacion": tipo_cot,
        "plazo": str(plazo) if plazo not in (None, "") else "",
        "costo": "",
        "venta": str(monto) if monto not in (None, "") else "",
        "total_venta": str(monto) if monto not in (None, "") else "",
        "venta_refinanciamiento": "",
        "precio_comision": "",
        "venta_sin_agregado": "",
        "recuperacion": "",
        "observaciones": f"Precargado desde caso {case.public_id}",
    }, None
