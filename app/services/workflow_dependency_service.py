"""Dependencias reales por etapa del workflow (P22-C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import constants as C
from app.domain.constants import normalize_doc_type
from app.models.case import Case
from app.models.case_event import CaseEvent
from app.models.commission import PAYMENT_STATUS_CANCELLED, Commission
from app.models.document import Document
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture, is_registration_complete
from app.repositories.commission_repository import CommissionRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.case_event_service import (
    COMPULSA_APPROVED,
    OCR_FAILED,
    OCR_PROCESSED,
    SALE_CAPTURE_EXPORT_FAILED,
    SALE_CAPTURE_REGISTRATION_FAILED,
)
from app.services.case_service import CaseService
from app.services.workflow_state_service import (
    WORKFLOW_STATE_LABELS,
    WF_APROBADO,
    WF_PEDIDO_RECIBIDO,
    WF_CERRADO,
    WF_COMISION_OK,
    WF_COMISION_PENDIENTE,
    WF_CONTRATOS_OK,
    WF_CONTRATOS_PENDIENTE,
    WF_EN_COMPULSA,
    WF_OCR_PROCESADO,
    WF_PREP_AUTORIZACION,
    WF_REGISTRADO,
    WF_REGISTRO_PENDIENTE,
    WF_SHAREPOINT_PENDIENTE,
    WF_SHAREPOINT_OK,
    WF_SNTE_GENERADO,
    WF_SNTE_PENDIENTE,
    WORKFLOW_LINEAR_ORDER,
    normalize_workflow_state,
)

_CRITICAL_SP_TYPES = frozenset(
    {
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
        C.DOC_AUTORIZACION_SNTE,
        C.DOC_ORDEN_SNTE_PDF,
    }
)


@dataclass
class WorkflowContext:
    case: Case
    documents: list[Document] = field(default_factory=list)
    sale: SaleCapture | None = None
    commission: Commission | None = None
    events: list[CaseEvent] = field(default_factory=list)
    checklist_ok: bool = False
    has_snte_excel: bool = False
    has_snte_pdf: bool = False
    has_ocr: bool = False
    sharepoint_ok: bool = False
    sharepoint_pending: bool = False
    sharepoint_failed: bool = False
    has_critical_timeline_error: bool = False


def build_workflow_context(db: Session, case: Case) -> WorkflowContext:
    docs = list(
        db.scalars(
            select(Document)
            .options(joinedload(Document.ocr_results))
            .where(Document.case_id == case.id, Document.is_active.is_(True))
        )
        .unique()
        .all()
    )
    events = list(
        db.scalars(
            select(CaseEvent)
            .where(CaseEvent.case_id == case.id)
            .order_by(CaseEvent.created_at.desc())
            .limit(200)
        ).all()
    )
    sale = None
    if case.official_folio:
        sale = SaleCaptureRepository.get_by_folio(db, case.official_folio)
    if not sale:
        sale = db.scalar(
            select(SaleCapture).where(SaleCapture.case_id == case.id).limit(1)
        )
    commission = None
    if sale:
        commission = CommissionRepository.get_by_sale_capture_id(db, sale.id)

    present = {normalize_doc_type(d.document_type) for d in docs}
    has_snte_excel = C.DOC_AUTORIZACION_SNTE in present or C.DOC_AUTORIZACION_REFI in present
    has_snte_pdf = C.DOC_ORDEN_SNTE_PDF in present

    sp_statuses = [d.upload_status or "" for d in docs if d.document_type in _CRITICAL_SP_TYPES]
    sharepoint_ok = bool(sp_statuses) and all(s == "UPLOADED" for s in sp_statuses)
    sharepoint_pending = any(s == "PENDING_UPLOAD" for s in sp_statuses)
    sharepoint_failed = any(s == "UPLOAD_FAILED" for s in sp_statuses)

    event_types = {e.event_type for e in events}
    has_ocr = OCR_PROCESSED in event_types or any(
        len(getattr(d, "ocr_results", None) or []) > 0 for d in docs
    )

    critical_errors = {
        OCR_FAILED,
        SALE_CAPTURE_EXPORT_FAILED,
        SALE_CAPTURE_REGISTRATION_FAILED,
    }
    has_critical_timeline_error = bool(event_types & critical_errors)

    case_svc = CaseService()
    checklist_ok = (
        case.case_type == C.CASE_TYPE_PEDIDO and case_svc.pedido_has_all_documents(db, case)
    )

    return WorkflowContext(
        case=case,
        documents=docs,
        sale=sale,
        commission=commission,
        events=events,
        checklist_ok=checklist_ok,
        has_snte_excel=has_snte_excel,
        has_snte_pdf=has_snte_pdf,
        has_ocr=has_ocr,
        sharepoint_ok=sharepoint_ok,
        sharepoint_pending=sharepoint_pending,
        sharepoint_failed=sharepoint_failed,
        has_critical_timeline_error=has_critical_timeline_error,
    )


def _missing_pedido_docs(ctx: WorkflowContext) -> list[str]:
    if ctx.checklist_ok:
        return []
    required = C.required_doc_types_for_order(ctx.case.order_type or C.ORDER_TYPE_MUEBLE)
    present = {normalize_doc_type(d.document_type) for d in ctx.documents}
    return [dt for dt in required if dt not in present]


def check_dependencies_for_state(ctx: WorkflowContext, target_state: str) -> list[str]:
    """Lista dependencias faltantes para alcanzar o validar un estado."""
    missing: list[str] = []
    case = ctx.case

    if target_state == WF_PEDIDO_RECIBIDO:
        return []

    if target_state == WF_OCR_PROCESADO:
        if not _missing_pedido_docs(ctx):
            pass
        else:
            missing.append("Documentos mínimos del pedido")
        if not ctx.has_ocr:
            missing.append("OCR procesado en documentos del pedido")

    elif target_state == WF_PREP_AUTORIZACION:
        missing.extend(_missing_pedido_docs(ctx) and ["Documentos mínimos del pedido"] or [])
        if not ctx.checklist_ok:
            missing.append("Checklist de pedido incompleto")

    elif target_state == WF_EN_COMPULSA:
        if _missing_pedido_docs(ctx):
            missing.append("Pedido y documentos mínimos cargados")
        if not ctx.checklist_ok:
            missing.append("Autorización preparada (checklist completo)")
        if not (ctx.has_snte_excel or case.current_status == C.ST_PED_PREP_AUT):
            missing.append("Pedido listo para compulsa (preparación completada)")

    elif target_state == WF_APROBADO:
        if case.current_status not in (
            C.ST_PED_COMPULSA_OK,
            C.ST_PED_EN_COMPULSA,
            C.ST_PED_PEND_COMPULSA,
        ) and COMPULSA_APPROVED not in {e.event_type for e in ctx.events}:
            missing.append("Compulsa completa o aprobada")
        if case.current_status == C.ST_PED_CORRECCION:
            missing.append("Correcciones pendientes")

    elif target_state == WF_SNTE_PENDIENTE:
        wf = getattr(case, "workflow_state", None) or ""
        if wf not in (WF_APROBADO, WF_SNTE_PENDIENTE, WF_SNTE_GENERADO) and case.current_status not in (
            C.ST_PED_COMPULSA_OK,
            C.ST_PED_APROBADO,
        ):
            missing.append("Caso aprobado tras compulsa (APROBADO)")

    elif target_state == WF_SNTE_GENERADO:
        missing.extend(check_dependencies_for_state(ctx, WF_SNTE_PENDIENTE))
        if not ctx.has_snte_excel:
            missing.append("Excel autorización SNTE generado")
        if not ctx.has_snte_pdf:
            missing.append("PDF orden SNTE generado")

    elif target_state == WF_SHAREPOINT_PENDIENTE:
        missing.extend(check_dependencies_for_state(ctx, WF_SNTE_GENERADO))

    elif target_state == WF_SHAREPOINT_OK:
        if not ctx.has_snte_excel:
            missing.append("SNTE generado antes de SharePoint")
        if ctx.sharepoint_failed:
            missing.append("Sin errores de subida SharePoint")
        if not ctx.sharepoint_ok:
            missing.append("Documentos críticos subidos a SharePoint (UPLOADED)")

    elif target_state in (WF_REGISTRO_PENDIENTE, WF_REGISTRADO):
        if not ctx.sharepoint_ok:
            missing.append("SHAREPOINT_OK (documentos sincronizados)")
        if target_state == WF_REGISTRADO:
            if not ctx.sale:
                missing.append("Captura de venta vinculada al caso")
            elif not is_registration_complete(ctx.sale):
                missing.append("registration_status == registered")

    elif target_state in (WF_CONTRATOS_PENDIENTE, WF_CONTRATOS_OK):
        if not ctx.sale or not is_registration_complete(ctx.sale):
            missing.append("Venta registrada en Excel")
        if target_state == WF_CONTRATOS_OK:
            path = ctx.sale.contratos_export_path if ctx.sale else None
            if not path or not Path(path).is_file():
                missing.append("Archivo de contratos exportado")

    elif target_state in (WF_COMISION_PENDIENTE, WF_COMISION_OK):
        if not ctx.commission:
            missing.append("Comisión generada para la venta")
        elif target_state == WF_COMISION_OK:
            if ctx.commission.payment_status == PAYMENT_STATUS_CANCELLED:
                missing.append("Comisión no cancelada")

    elif target_state == WF_CERRADO:
        for st in (
            WF_REGISTRADO,
            WF_CONTRATOS_OK,
            WF_COMISION_OK,
            WF_SHAREPOINT_OK,
        ):
            missing.extend(check_dependencies_for_state(ctx, st))
        if ctx.has_critical_timeline_error:
            missing.append("Timeline sin errores críticos (OCR/registro fallido)")

    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def highest_achievable_state(ctx: WorkflowContext) -> str:
    """Estado más avanzado cuyas dependencias se cumplen (recálculo)."""
    if ctx.case.current_status == C.ST_PED_RECHAZADO:
        return WF_RECHAZADO
    if ctx.case.current_status == C.ST_PED_CORRECCION:
        return WF_CORRECCION

    best = WF_PEDIDO_RECIBIDO
    for state in WORKFLOW_LINEAR_ORDER:
        if not check_dependencies_for_state(ctx, state):
            best = state
    return best


def can_action_generate_snte(ctx: WorkflowContext) -> tuple[bool, str | None]:
    wf = normalize_workflow_state(
        getattr(ctx.case, "workflow_state", None), legacy_status=ctx.case.current_status
    )
    if wf not in (WF_APROBADO, WF_SNTE_PENDIENTE):
        return (
            False,
            "No se puede generar SNTE: el caso debe estar APROBADO tras compulsa. "
            f"Estado actual: {WORKFLOW_STATE_LABELS.get(wf, wf)}.",
        )
    missing = check_dependencies_for_state(ctx, WF_SNTE_PENDIENTE)
    if missing:
        return False, f"No se puede generar SNTE: falta {missing[0]}."
    return True, None


def can_action_register_sale(ctx: WorkflowContext) -> tuple[bool, str | None]:
    wf = normalize_workflow_state(
        getattr(ctx.case, "workflow_state", None), legacy_status=ctx.case.current_status
    )
    if wf not in (WF_SHAREPOINT_OK, WF_REGISTRO_PENDIENTE):
        return (
            False,
            f"No se puede registrar la venta: requiere SHAREPOINT_OK. "
            f"Estado workflow: {WORKFLOW_STATE_LABELS.get(wf, wf)}.",
        )
    if not ctx.sharepoint_ok:
        return False, "No se puede pasar a REGISTRADO porque falta SHAREPOINT_OK."
    if ctx.sale and is_registration_complete(ctx.sale):
        return False, "La venta ya está registrada."
    return True, None


def can_action_close_case(ctx: WorkflowContext) -> tuple[bool, str | None]:
    missing = check_dependencies_for_state(ctx, WF_CERRADO)
    if missing:
        return False, f"No se puede cerrar el caso: falta {missing[0]}."
    return True, None
