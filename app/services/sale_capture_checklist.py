"""Checklist operativo para captura de ventas (P19.1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.models.sale_capture import (
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_PENDING_VALIDATION,
    SALE_STATUS_REGISTERED,
    SaleCapture,
)
from app.services.case_service import CaseService
from app.services.sale_capture_validation import parse_sale_form

CheckStatus = Literal["ok", "pending", "error"]


@dataclass
class ChecklistItem:
    key: str
    label: str
    status: CheckStatus
    detail: str


@dataclass
class SaleChecklist:
    items: list[ChecklistItem]
    ready_to_register: bool
    register_block_reason: str | None = None

    @property
    def all_ok_for_register(self) -> bool:
        required_keys = {
            "capture_complete",
            "case_linked",
            "documents_minimum",
            "validation_ready",
        }
        for item in self.items:
            if item.key in required_keys and item.status != "ok":
                return False
        return True


def _form_dict_from_sale(sale: SaleCapture) -> dict[str, Any]:
    return {
        "folio": sale.folio,
        "fecha": sale.sale_date.isoformat() if sale.sale_date else "",
        "vendedor": sale.vendedor,
        "seccion": sale.seccion or "",
        "qna": sale.qna or "",
        "cliente": sale.cliente,
        "rfc": sale.rfc or "",
        "codigo": sale.codigo or "",
        "producto": sale.producto or "",
        "tipo_venta": sale.tipo_venta or "",
        "plazo": str(sale.plazo) if sale.plazo is not None else "",
        "costo": str(sale.costo) if sale.costo is not None else "",
        "venta": str(sale.venta) if sale.venta is not None else "",
        "venta_refinanciamiento": (
            str(sale.venta_refinanciamiento) if sale.venta_refinanciamiento is not None else ""
        ),
        "total_venta": str(sale.total_venta) if sale.total_venta is not None else "",
        "precio_comision": str(sale.precio_comision) if sale.precio_comision is not None else "",
        "venta_sin_agregado": (
            str(sale.venta_sin_agregado) if sale.venta_sin_agregado is not None else ""
        ),
        "recuperacion": str(sale.recuperacion) if sale.recuperacion is not None else "",
        "tipo_cotizacion": sale.tipo_cotizacion or "",
        "observaciones": sale.observaciones or "",
        "semana": sale.semana or "",
        "sale_date": sale.sale_date,
    }


def build_sale_checklist(db: Session, sale: SaleCapture | None) -> SaleChecklist:
    if not sale:
        return SaleChecklist(
            items=[
                ChecklistItem("capture_complete", "Captura completa", "pending", "Sin datos"),
            ],
            ready_to_register=False,
            register_block_reason="No hay captura guardada.",
        )

    form = _form_dict_from_sale(sale)
    _, val_errors = parse_sale_form(form)
    capture_ok = not val_errors
    capture_detail = "Datos obligatorios completos." if capture_ok else "; ".join(val_errors[:3])

    case_ok = sale.case_id is not None
    case_detail = f"Caso #{sale.case_id}" if case_ok else "Asocie caso (enviar a validación)."

    docs_ok = False
    docs_detail = "Sin caso vinculado."
    if sale.case_id:
        from app.repositories.case_repository import CaseRepository

        case = CaseRepository.get_by_id(db, sale.case_id)
        if case and case.case_type == C.CASE_TYPE_PEDIDO:
            svc = CaseService(get_settings())
            if svc.pedido_has_all_documents(db, case):
                docs_ok = True
                docs_detail = "Checklist documental del pedido completo."
            else:
                docs_detail = "Faltan documentos obligatorios en el caso."
        else:
            docs_detail = "Caso no encontrado o no es pedido."

    validation_ok = sale.status in (
        SALE_STATUS_PENDING_VALIDATION,
        SALE_STATUS_REGISTERED,
        SALE_STATUS_EXPORT_FAILED,
    )
    validation_detail = (
        "Lista para registro definitivo."
        if validation_ok
        else "Envíe a validación antes de registrar en Excel."
    )

    excel_ok = sale.status == SALE_STATUS_REGISTERED and bool(sale.ventas_export_path)
    excel_detail = "Registrada en copia Excel." if excel_ok else "Pendiente de registro Excel."
    if sale.status == SALE_STATUS_EXPORT_FAILED:
        excel_detail = sale.export_error or "Error al exportar a Excel."

    exports_ok = False
    exports_detail = "Sin archivos exportados."
    if sale.ventas_export_path and sale.contratos_export_path:
        v_ok = Path(sale.ventas_export_path).is_file()
        c_ok = Path(sale.contratos_export_path).is_file()
        exports_ok = v_ok and c_ok
        if exports_ok:
            exports_detail = "Ventas y contratos disponibles para descarga."
        else:
            exports_detail = "Rutas guardadas pero archivos no encontrados en disco."

    items = [
        ChecklistItem(
            "capture_complete",
            "Captura completa",
            "ok" if capture_ok else "error",
            capture_detail,
        ),
        ChecklistItem(
            "case_linked",
            "Caso asociado",
            "ok" if case_ok else "pending",
            case_detail,
        ),
        ChecklistItem(
            "documents_minimum",
            "Documentos mínimos",
            "ok" if docs_ok else ("pending" if not case_ok else "error"),
            docs_detail,
        ),
        ChecklistItem(
            "validation_ready",
            "Validación lista",
            "ok" if validation_ok else "pending",
            validation_detail,
        ),
        ChecklistItem(
            "excel_registered",
            "Registro Excel",
            "ok" if excel_ok else ("error" if sale.status == SALE_STATUS_EXPORT_FAILED else "pending"),
            excel_detail,
        ),
        ChecklistItem(
            "exports_available",
            "Exportaciones disponibles",
            "ok" if exports_ok else "pending",
            exports_detail,
        ),
    ]

    ready = (
        capture_ok
        and case_ok
        and docs_ok
        and validation_ok
        and sale.status not in (SALE_STATUS_REGISTERED,)
    )
    block = None
    if sale.status == SALE_STATUS_REGISTERED:
        block = "La venta ya está registrada."
    elif sale.status == SALE_STATUS_EXPORT_FAILED:
        block = sale.export_error or "Corrija el error de Excel y reintente el registro."
    elif not capture_ok:
        block = capture_detail
    elif not case_ok:
        block = "Asocie un caso antes de registrar."
    elif not docs_ok:
        block = docs_detail
    elif not validation_ok:
        block = validation_detail

    return SaleChecklist(
        items=items,
        ready_to_register=ready,
        register_block_reason=block,
    )
