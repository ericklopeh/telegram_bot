"""Flujo operativo guiado por caso (P31)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case
from app.models.commission import Commission, PAYMENT_STATUS_PENDING
from app.models.sale_capture import REG_STATUS_REGISTERED, REG_STATUS_REGISTRATION_FAILED, SaleCapture
from app.services.action_guard_service import CaseActionState
from app.services.case_document_service import DocumentSummary
from app.services.workflow_state_service import WORKFLOW_STATE_LABELS, normalize_workflow_state
from app.web.services.operational_tracking import (
    ACCION_AUT_GENERADA,
    ACCION_CERRADO,
    ACCION_ERROR_SP,
    ACCION_FALTA_CARATULA,
    ACCION_FALTA_ORDEN,
    ACCION_FALTA_PEDIDO,
    ACCION_LISTO_AUT,
    ACCION_PENDIENTE_COMPULSA,
    ACCION_PENDIENTE_OCR,
    ACCION_SEGUIMIENTO,
    CaseTrackingContext,
    badge_class_for_action,
    build_tracking_contexts,
    suggest_next_action,
)
from app.web.services.user_friendly_errors import friendly_block_reason

_GUIDANCE: dict[str, tuple[str, str, str]] = {
    ACCION_FALTA_PEDIDO: (
        "Subir documento de pedido",
        "Cargue y valide el pedido en la revisión documental.",
        "documentos",
    ),
    ACCION_FALTA_ORDEN: (
        "Subir orden de descuento",
        "Falta la orden de descuento en el expediente.",
        "documentos",
    ),
    ACCION_FALTA_CARATULA: (
        "Subir carátula bancaria",
        "Complete la carátula según el tipo de venta.",
        "documentos",
    ),
    ACCION_PENDIENTE_OCR: (
        "Procesar OCR",
        "Ejecute OCR en talón/pedido antes de autorización.",
        "documentos",
    ),
    ACCION_LISTO_AUT: (
        "Generar autorización SNTE",
        "Checklist completo: puede generar la autorización.",
        "autorizacion",
    ),
    ACCION_AUT_GENERADA: (
        "Seguimiento post-autorización",
        "Autorización lista; revise compulsa o cierre según proceso.",
        "caso",
    ),
    ACCION_PENDIENTE_COMPULSA: (
        "Compulsa",
        "Caso en flujo de compulsa; revise estado y documentos.",
        "caso",
    ),
    ACCION_ERROR_SP: (
        "Corregir SharePoint",
        "Hay fallos de subida; reintente sync o subida por documento.",
        "sharepoint",
    ),
    ACCION_CERRADO: (
        "Caso cerrado",
        "No hay acciones pendientes en este expediente.",
        "caso",
    ),
    ACCION_SEGUIMIENTO: (
        "Seguimiento general",
        "Revise timeline, documentos y venta vinculada.",
        "caso",
    ),
}


@dataclass
class QuickLink:
    label: str
    url: str
    style: str = "outline-secondary"


@dataclass
class CaseGuidedFlow:
    workflow_label: str
    status_badge: str
    next_action: str
    next_action_hint: str
    action_badge_class: str
    cta_label: str
    cta_url: str
    sharepoint_summary: str
    sharepoint_alert: bool
    missing_docs_labels: list[str]
    sale_summary: str | None
    sale_url: str | None
    commission_summary: str | None
    commission_url: str | None
    block_hints: list[str] = field(default_factory=list)
    quick_links: list[QuickLink] = field(default_factory=list)


def _cta_url(case_id: int, target: str) -> str:
    if target == "documentos":
        return f"/casos/{case_id}/documentos"
    if target == "sharepoint":
        return f"/casos/{case_id}/sharepoint/sync"
    if target == "autorizacion":
        return f"/casos/{case_id}#autorizaciones"
    return f"/casos/{case_id}"


def build_case_guided_flow(
    db: Session,
    case: Case,
    action_guard: CaseActionState,
    *,
    doc_summary: DocumentSummary | None = None,
    case_svc=None,
) -> CaseGuidedFlow:
    from app.config import get_settings
    from app.services.case_service import CaseService

    case_svc = case_svc or CaseService(get_settings())
    ctx_map = build_tracking_contexts(db, [case], case_svc)
    ctx: CaseTrackingContext = ctx_map.get(case.id, CaseTrackingContext())
    action_key = suggest_next_action(case, ctx)
    title, hint, target = _GUIDANCE.get(action_key, _GUIDANCE[ACCION_SEGUIMIENTO])

    wf = normalize_workflow_state(getattr(case, "workflow_state", None), legacy_status=case.current_status)
    wf_label = WORKFLOW_STATE_LABELS.get(wf, wf)

    missing_labels = [doc_type_label(dt) for dt in action_guard.missing_doc_types]
    if doc_summary and doc_summary.missing:
        missing_labels.append(f"{doc_summary.missing} tipo(s) sin archivo")

    sp_summary = ctx.sharepoint_estado
    if action_guard.sharepoint_failed:
        sp_summary = f"fallido ({len(action_guard.sharepoint_failed)} doc(s))"
    elif action_guard.sharepoint_pending:
        sp_summary = f"pendiente ({len(action_guard.sharepoint_pending)} doc(s))"

    sale = db.scalar(select(SaleCapture).where(SaleCapture.case_id == case.id).limit(1))
    sale_summary = None
    sale_url = None
    if sale:
        rs = sale.registration_status or sale.status
        sale_summary = f"Folio {sale.folio} · {rs}"
        if rs == REG_STATUS_REGISTRATION_FAILED:
            sale_summary += " · Excel fallido"
        sale_url = f"/ventas/{sale.id}"

    comm = None
    if sale:
        comm = db.scalar(select(Commission).where(Commission.sale_capture_id == sale.id))
    comm_summary = None
    comm_url = None
    if comm:
        comm_summary = f"${comm.commission_amount} · {comm.payment_status}"
        comm_url = "/comisiones"
    elif sale and sale.registration_status == REG_STATUS_REGISTERED:
        comm_summary = "Venta registrada sin comisión generada"
        comm_url = "/comisiones"

    blocks: list[str] = []
    for reason in (
        action_guard.finalize_block_reason,
        action_guard.generate_auth_block_reason,
        action_guard.compulsa_block_reason,
        action_guard.sharepoint_notice,
        action_guard.ocr_notice,
    ):
        if reason:
            friendly = friendly_block_reason(reason)
            if friendly and friendly not in blocks:
                blocks.append(friendly)

    links = [
        QuickLink("Documentos", f"/casos/{case.id}/documentos", "primary"),
        QuickLink("Timeline", f"/casos/{case.id}#timeline", "outline-secondary"),
        QuickLink("Ventas", "/ventas", "outline-secondary"),
        QuickLink("ERP", "/erp/dashboard", "outline-secondary"),
    ]
    if ctx.sp_failed or action_guard.can_retry_sharepoint:
        links.insert(1, QuickLink("SharePoint", f"/casos/{case.id}/sharepoint/sync", "warning"))

    return CaseGuidedFlow(
        workflow_label=wf_label,
        status_badge=case.visible_status or case.current_status,
        next_action=title,
        next_action_hint=hint,
        action_badge_class=badge_class_for_action(action_key),
        cta_label=title,
        cta_url=_cta_url(case.id, target),
        sharepoint_summary=sp_summary,
        sharepoint_alert=ctx.sp_failed or action_guard.has_critical_sharepoint_failed,
        missing_docs_labels=missing_labels,
        sale_summary=sale_summary,
        sale_url=sale_url,
        commission_summary=comm_summary,
        commission_url=comm_url,
        block_hints=blocks,
        quick_links=links,
    )
