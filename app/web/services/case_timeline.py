"""Presentación de case_events como línea de tiempo legible (P15)."""

from __future__ import annotations

from typing import Any

from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case_event import CaseEvent
from app.services.case_event_service import (
    AUTH_GENERATED,
    AUTH_REGENERATED,
    CASE_CREATED,
    CHECKLIST_COMPLETE,
    CHECKLIST_INCOMPLETE,
    COMPULSA_APPROVED,
    COMPULSA_REJECTED,
    DOCUMENT_CREATED,
    DOCUMENT_RECEIVED,
    DOCUMENT_UPLOAD_FAILED,
    DOCUMENT_UPLOAD_QUEUED,
    DOCUMENT_UPLOADED,
    OCR_FAILED,
    OCR_NO_TEXT,
    OCR_PROCESSED,
    REFI_GENERATED,
    SNTE_EXCEL_GENERATED,
    SNTE_PDF_GENERATED,
    STATUS_CHANGED,
    TELEGRAM_NOTIFIED,
    SALE_CAPTURE_DRAFT,
    SALE_CAPTURE_EDITED,
    SALE_CAPTURE_REGISTERED,
    SALE_CAPTURE_VALIDATED,
    SALE_CAPTURE_REGISTER_BLOCKED,
    SALE_CAPTURE_EXPORT_FAILED,
    SALE_CAPTURE_DUPLICATE_DETECTED,
    SALE_CAPTURE_REGISTRATION_QUEUED,
    SALE_CAPTURE_PROCESSING,
    SALE_CAPTURE_REGISTRATION_FAILED,
    SALE_CAPTURE_RETRY_REQUESTED,
    SALE_CAPTURE_CONCILIATION_WARNING,
    COMMISSION_CREATED,
    COMMISSION_UPDATED,
    COMMISSION_PAID,
    COMMISSION_CANCELLED,
    WORKFLOW_TRANSITION_REQUESTED,
    WORKFLOW_TRANSITION_COMPLETED,
    WORKFLOW_TRANSITION_BLOCKED,
    WORKFLOW_DEPENDENCY_MISSING,
    WORKFLOW_STATE_RECALCULATED,
    SNTE_UNLOCKED_AFTER_APPROVAL,
    CASE_DOCUMENT_UPLOADED,
    CASE_DOCUMENT_REPLACED,
    CASE_DOCUMENT_VALIDATED,
    CASE_DOCUMENT_REJECTED,
    DOCUMENT_MISSING_BLOCKED,
    SHAREPOINT_UPLOAD_STARTED,
    SHAREPOINT_UPLOAD_OK,
    SHAREPOINT_UPLOAD_FAILED,
    SHAREPOINT_RETRY_REQUESTED,
    PAYMENT_REGISTERED,
    REFINANCE_CREATED,
    BALANCE_ADJUSTED,
    CONTRACT_CLOSED,
)

_ICON: dict[str, str] = {
    CASE_CREATED: "bi-folder-plus",
    DOCUMENT_RECEIVED: "bi-cloud-upload",
    DOCUMENT_CREATED: "bi-file-earmark-plus",
    DOCUMENT_UPLOAD_QUEUED: "bi-hourglass-split",
    DOCUMENT_UPLOADED: "bi-cloud-check",
    DOCUMENT_UPLOAD_FAILED: "bi-cloud-slash",
    OCR_PROCESSED: "bi-cpu",
    OCR_FAILED: "bi-exclamation-triangle",
    OCR_NO_TEXT: "bi-file-earmark-x",
    CHECKLIST_COMPLETE: "bi-check2-square",
    CHECKLIST_INCOMPLETE: "bi-ui-checks",
    AUTH_GENERATED: "bi-file-earmark-excel",
    AUTH_REGENERATED: "bi-arrow-repeat",
    SNTE_PDF_GENERATED: "bi-file-earmark-pdf",
    SNTE_EXCEL_GENERATED: "bi-file-earmark-spreadsheet",
    REFI_GENERATED: "bi-file-earmark-excel",
    STATUS_CHANGED: "bi-arrow-left-right",
    COMPULSA_APPROVED: "bi-hand-thumbs-up",
    COMPULSA_REJECTED: "bi-hand-thumbs-down",
    TELEGRAM_NOTIFIED: "bi-telegram",
    SALE_CAPTURE_DRAFT: "bi-receipt",
    SALE_CAPTURE_EDITED: "bi-pencil-square",
    SALE_CAPTURE_REGISTERED: "bi-table",
    SALE_CAPTURE_VALIDATED: "bi-patch-check",
    SALE_CAPTURE_REGISTER_BLOCKED: "bi-slash-circle",
    SALE_CAPTURE_EXPORT_FAILED: "bi-file-excel",
    SALE_CAPTURE_DUPLICATE_DETECTED: "bi-exclamation-diamond",
    SALE_CAPTURE_REGISTRATION_QUEUED: "bi-hourglass",
    SALE_CAPTURE_PROCESSING: "bi-arrow-repeat",
    SALE_CAPTURE_REGISTRATION_FAILED: "bi-x-octagon",
    SALE_CAPTURE_RETRY_REQUESTED: "bi-arrow-clockwise",
    SALE_CAPTURE_CONCILIATION_WARNING: "bi-shield-exclamation",
    COMMISSION_CREATED: "bi-cash-coin",
    COMMISSION_UPDATED: "bi-cash-stack",
    COMMISSION_PAID: "bi-check2-circle",
    COMMISSION_CANCELLED: "bi-x-circle",
    WORKFLOW_TRANSITION_REQUESTED: "bi-signpost",
    WORKFLOW_TRANSITION_COMPLETED: "bi-check2-all",
    WORKFLOW_TRANSITION_BLOCKED: "bi-slash-circle",
    WORKFLOW_DEPENDENCY_MISSING: "bi-exclamation-triangle",
    WORKFLOW_STATE_RECALCULATED: "bi-arrow-repeat",
    SNTE_UNLOCKED_AFTER_APPROVAL: "bi-unlock",
    CASE_DOCUMENT_UPLOADED: "bi-file-earmark-arrow-up",
    CASE_DOCUMENT_REPLACED: "bi-arrow-repeat",
    CASE_DOCUMENT_VALIDATED: "bi-patch-check",
    CASE_DOCUMENT_REJECTED: "bi-x-circle",
    DOCUMENT_MISSING_BLOCKED: "bi-folder-x",
    SHAREPOINT_UPLOAD_STARTED: "bi-cloud-upload",
    SHAREPOINT_UPLOAD_OK: "bi-cloud-check-fill",
    SHAREPOINT_UPLOAD_FAILED: "bi-cloud-slash",
    SHAREPOINT_RETRY_REQUESTED: "bi-arrow-clockwise",
    PAYMENT_REGISTERED: "bi-credit-card",
    REFINANCE_CREATED: "bi-arrow-repeat",
    BALANCE_ADJUSTED: "bi-sliders",
    CONTRACT_CLOSED: "bi-lock",
}

_BADGE: dict[str, str] = {
    CASE_CREATED: "bg-primary",
    DOCUMENT_RECEIVED: "bg-info text-dark",
    DOCUMENT_CREATED: "bg-success",
    DOCUMENT_UPLOAD_QUEUED: "bg-warning text-dark",
    DOCUMENT_UPLOADED: "bg-success",
    DOCUMENT_UPLOAD_FAILED: "bg-danger",
    OCR_PROCESSED: "bg-success",
    OCR_FAILED: "bg-danger",
    OCR_NO_TEXT: "bg-warning text-dark",
    CHECKLIST_COMPLETE: "bg-success",
    CHECKLIST_INCOMPLETE: "bg-warning text-dark",
    AUTH_GENERATED: "bg-success",
    AUTH_REGENERATED: "bg-primary",
    SNTE_PDF_GENERATED: "bg-danger",
    SNTE_EXCEL_GENERATED: "bg-success",
    REFI_GENERATED: "bg-success",
    STATUS_CHANGED: "bg-secondary",
    COMPULSA_APPROVED: "bg-success",
    COMPULSA_REJECTED: "bg-danger",
    TELEGRAM_NOTIFIED: "bg-info text-dark",
    SALE_CAPTURE_DRAFT: "bg-secondary",
    SALE_CAPTURE_EDITED: "bg-info text-dark",
    SALE_CAPTURE_REGISTERED: "bg-success",
    SALE_CAPTURE_VALIDATED: "bg-success",
    SALE_CAPTURE_REGISTER_BLOCKED: "bg-danger",
    SALE_CAPTURE_EXPORT_FAILED: "bg-danger",
    SALE_CAPTURE_DUPLICATE_DETECTED: "bg-warning text-dark",
    SALE_CAPTURE_REGISTRATION_QUEUED: "bg-warning text-dark",
    SALE_CAPTURE_PROCESSING: "bg-info text-dark",
    SALE_CAPTURE_REGISTRATION_FAILED: "bg-danger",
    SALE_CAPTURE_RETRY_REQUESTED: "bg-primary",
    SALE_CAPTURE_CONCILIATION_WARNING: "bg-warning text-dark",
    COMMISSION_CREATED: "bg-success",
    COMMISSION_UPDATED: "bg-info text-dark",
    COMMISSION_PAID: "bg-success",
    COMMISSION_CANCELLED: "bg-secondary",
    WORKFLOW_TRANSITION_REQUESTED: "bg-info text-dark",
    WORKFLOW_TRANSITION_COMPLETED: "bg-success",
    WORKFLOW_TRANSITION_BLOCKED: "bg-danger",
    WORKFLOW_DEPENDENCY_MISSING: "bg-warning text-dark",
    WORKFLOW_STATE_RECALCULATED: "bg-primary",
    SNTE_UNLOCKED_AFTER_APPROVAL: "bg-success",
    CASE_DOCUMENT_UPLOADED: "bg-info text-dark",
    CASE_DOCUMENT_REPLACED: "bg-primary",
    CASE_DOCUMENT_VALIDATED: "bg-success",
    CASE_DOCUMENT_REJECTED: "bg-danger",
    DOCUMENT_MISSING_BLOCKED: "bg-warning text-dark",
    SHAREPOINT_UPLOAD_STARTED: "bg-info text-dark",
    SHAREPOINT_UPLOAD_OK: "bg-success",
    SHAREPOINT_UPLOAD_FAILED: "bg-danger",
    SHAREPOINT_RETRY_REQUESTED: "bg-primary",
    PAYMENT_REGISTERED: "bg-success",
    REFINANCE_CREATED: "bg-warning text-dark",
    BALANCE_ADJUSTED: "bg-info text-dark",
    CONTRACT_CLOSED: "bg-secondary",
}

_CERRADOS_PEDIDO = {C.ST_PED_CERRADO, C.ST_PED_RECHAZADO, C.ST_PED_COMPRA}
_CERRADOS_REV = {C.ST_REV_CERRADO, C.ST_REV_RECHAZADO, C.ST_REV_SIN_LIQUIDEZ}

_LABEL: dict[str, str] = {
    CASE_CREATED: "Caso creado",
    DOCUMENT_RECEIVED: "Documento subido",
    DOCUMENT_CREATED: "Documento generado",
    DOCUMENT_UPLOAD_QUEUED: "SharePoint pendiente",
    DOCUMENT_UPLOADED: "SharePoint sincronizado",
    DOCUMENT_UPLOAD_FAILED: "SharePoint fallido",
    OCR_PROCESSED: "OCR procesado",
    OCR_FAILED: "OCR fallido",
    OCR_NO_TEXT: "OCR sin texto",
    CHECKLIST_COMPLETE: "Checklist completo",
    CHECKLIST_INCOMPLETE: "Checklist incompleto",
    AUTH_GENERATED: "Autorización SNTE generada",
    AUTH_REGENERATED: "Autorización SNTE regenerada",
    SNTE_PDF_GENERATED: "PDF sindicato generado",
    SNTE_EXCEL_GENERATED: "Excel autorización generado",
    REFI_GENERATED: "Refinanciamiento generado",
    STATUS_CHANGED: "Cambio de estado",
    COMPULSA_APPROVED: "Compulsa aprobada",
    COMPULSA_REJECTED: "Compulsa rechazada",
    TELEGRAM_NOTIFIED: "Notificación Telegram",
    SALE_CAPTURE_DRAFT: "Captura de venta (borrador/validación)",
    SALE_CAPTURE_EDITED: "Captura de venta editada",
    SALE_CAPTURE_REGISTERED: "Venta registrada en Excel",
    SALE_CAPTURE_VALIDATED: "Venta validada",
    SALE_CAPTURE_REGISTER_BLOCKED: "Registro de venta bloqueado",
    SALE_CAPTURE_EXPORT_FAILED: "Error exportación Excel venta",
    SALE_CAPTURE_DUPLICATE_DETECTED: "Posible venta duplicada",
    SALE_CAPTURE_REGISTRATION_QUEUED: "Venta en cola de registro",
    SALE_CAPTURE_PROCESSING: "Procesando registro Excel",
    SALE_CAPTURE_REGISTRATION_FAILED: "Registro Excel fallido",
    SALE_CAPTURE_RETRY_REQUESTED: "Reintento de registro solicitado",
    SALE_CAPTURE_CONCILIATION_WARNING: "Advertencia de conciliación",
    COMMISSION_CREATED: "Comisión generada",
    COMMISSION_UPDATED: "Comisión actualizada",
    COMMISSION_PAID: "Comisión pagada",
    COMMISSION_CANCELLED: "Comisión cancelada",
    WORKFLOW_TRANSITION_REQUESTED: "Transición de workflow solicitada",
    WORKFLOW_TRANSITION_COMPLETED: "Transición de workflow completada",
    WORKFLOW_TRANSITION_BLOCKED: "Transición de workflow bloqueada",
    WORKFLOW_DEPENDENCY_MISSING: "Dependencia de workflow faltante",
    WORKFLOW_STATE_RECALCULATED: "Estado de workflow recalculado",
    SNTE_UNLOCKED_AFTER_APPROVAL: "SNTE habilitado tras aprobación",
    CASE_DOCUMENT_UPLOADED: "Documento cargado (revisión)",
    CASE_DOCUMENT_REPLACED: "Documento reemplazado",
    CASE_DOCUMENT_VALIDATED: "Documento validado",
    CASE_DOCUMENT_REJECTED: "Documento rechazado",
    DOCUMENT_MISSING_BLOCKED: "Bloqueo por documentos faltantes",
    SHAREPOINT_UPLOAD_STARTED: "Subida SharePoint iniciada",
    SHAREPOINT_UPLOAD_OK: "SharePoint sincronizado",
    SHAREPOINT_UPLOAD_FAILED: "SharePoint fallido",
    SHAREPOINT_RETRY_REQUESTED: "Reintento SharePoint solicitado",
    PAYMENT_REGISTERED: "Pago registrado",
    REFINANCE_CREATED: "Refinanciamiento creado",
    BALANCE_ADJUSTED: "Saldo ajustado",
    CONTRACT_CLOSED: "Contrato cerrado",
}


def _status_category_label(status: str | None) -> str | None:
    if not status:
        return None
    if status in _CERRADOS_PEDIDO | _CERRADOS_REV:
        return "Cierre / rechazo"
    if status in (C.ST_PED_CORRECCION, C.ST_REV_CORRECCION):
        return "Corrección"
    if status in (C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA, C.ST_PED_COMPULSA_OK):
        return "Compulsa"
    return None


def _human_description(event: CaseEvent, meta: dict[str, Any]) -> str:
    if event.message:
        return event.message

    et = event.event_type
    if et == STATUS_CHANGED:
        old_s = meta.get("old_status") or "—"
        new_s = meta.get("new_status") or "—"
        return f"Estado: {old_s} → {new_s}"

    doc_type = meta.get("document_type")
    if doc_type:
        label = doc_type_label(str(doc_type))
        if et == DOCUMENT_RECEIVED:
            return f"Se recibió {label}"
        if et in (DOCUMENT_UPLOAD_QUEUED, DOCUMENT_UPLOADED, DOCUMENT_UPLOAD_FAILED):
            return f"{label}: subida SharePoint"
        if et == OCR_PROCESSED:
            return f"OCR aplicado a {label}"
    return _LABEL.get(et, et.replace("_", " ").title())


def _related_detail(event: CaseEvent, meta: dict[str, Any]) -> str | None:
    parts: list[str] = []
    doc_type = meta.get("document_type")
    if doc_type:
        parts.append(doc_type_label(str(doc_type)))
    new_status = meta.get("new_status")
    if new_status and event.event_type == STATUS_CHANGED:
        parts.append(str(new_status))
    elif new_status:
        parts.append(str(new_status))
    filename = meta.get("filename")
    if filename:
        parts.append(str(filename))
    upload_status = meta.get("upload_status")
    if upload_status and event.event_type.startswith("DOCUMENT_UPLOAD"):
        parts.append(str(upload_status))
    if meta.get("checklist") and event.event_type in (CHECKLIST_COMPLETE, CHECKLIST_INCOMPLETE):
        return str(meta.get("checklist")).replace("\n", " · ")
    return " · ".join(parts) if parts else None


def present_timeline_event(event: CaseEvent) -> dict[str, Any]:
    meta = event.metadata_json or {}
    et = event.event_type
    new_status = meta.get("new_status")
    category = _status_category_label(new_status) if et == STATUS_CHANGED else None

    actor_label = "Sistema"
    if event.actor_role:
        actor_label = event.actor_role
    elif event.actor:
        actor_label = event.actor.nombre or event.actor.username or "Usuario"

    source_label = (event.source or "system").capitalize()

    return {
        "id": event.id,
        "created_at": event.created_at,
        "event_type": et,
        "type_label": _LABEL.get(et, et),
        "icon": _ICON.get(et, "bi-circle"),
        "badge_class": _BADGE.get(et, "bg-secondary"),
        "description": _human_description(event, meta),
        "actor_label": actor_label,
        "actor_role": event.actor_role,
        "source_label": source_label,
        "related": _related_detail(event, meta),
        "category": category,
        "metadata": meta,
    }


def build_case_timeline(events: list[CaseEvent]) -> list[dict[str, Any]]:
    """Orden cronológico ascendente (más antiguo arriba)."""
    items = [present_timeline_event(e) for e in events]
    items.sort(key=lambda x: x["created_at"])
    return items
