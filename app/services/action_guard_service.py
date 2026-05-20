"""Reglas centralizadas de acciones permitidas por estado, checklist y SharePoint (P16/P17)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.domain.constants import doc_type_label, normalize_doc_type
from app.models.case import Case
from app.models.document import Document
from app.models.user import UserRole
from app.repositories.document_repository import DocumentRepository
from app.services.case_service import CaseService
from app.services.ocr_service import OCR_ELIGIBLE_DOCUMENT_TYPES

# Orden de captura en flujo pedido (Telegram)
_CHECKLIST_CAPTURE_ORDER: tuple[str, ...] = (
    C.DOC_PEDIDO,
    C.DOC_ORDEN_DESCUENTO,
    C.DOC_CARATULA_BANCARIA,
)

_PEDIDO_CAPTURE_STATUSES = frozenset(
    {
        C.ST_PED_RECIBIDO,
        C.ST_PED_CORRECCION,
    }
)

_SNTE_GENERATION_STATUSES = frozenset(
    {
        C.ST_PED_PREP_AUT,
        C.ST_PED_AUT_GENERADA,
    }
)

_COMPULSA_TARGET_STATUS = C.ST_PED_EN_COMPULSA

_CRITICAL_DOC_TYPES_FOR_SP = frozenset(
    {
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
        C.DOC_AUTORIZACION_SNTE,
        C.DOC_ORDEN_SNTE_PDF,
    }
)

_ACTION_UNAVAILABLE_MSG = "Esta acción ya no está disponible para este caso."

_ROLES_GENERATE_AUTH = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
        UserRole.AUTORIZACION.value,
    }
)

_ROLES_COMPULSA_STAFF = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
    }
)

_ROLES_RETRY_SP = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
        UserRole.AUTORIZACION.value,
        UserRole.VENDEDOR.value,
    }
)

_PD_BUTTON_MAP: dict[str, tuple[str, str]] = {
    "p": (C.DOC_PEDIDO, "📎 Pedido"),
    "o": (C.DOC_ORDEN_DESCUENTO, "📎 Orden descuento"),
    "c": (C.DOC_CARATULA_BANCARIA, "📎 Carátula bancaria"),
}


@dataclass
class DocUploadFlags:
    document_id: int
    document_type: str
    label: str
    upload_status: str


@dataclass
class CaseActionState:
    """Snapshot de reglas para un caso (una fila lógica por caso)."""

    case_id: int
    public_id: str
    order_type: str | None
    current_status: str
    checklist_ok: bool = False
    missing_doc_types: list[str] = field(default_factory=list)
    next_missing_doc_type: str | None = None
    present_doc_types: set[str] = field(default_factory=set)
    sharepoint_pending: list[DocUploadFlags] = field(default_factory=list)
    sharepoint_failed: list[DocUploadFlags] = field(default_factory=list)
    ocr_notice: str | None = None
    has_critical_sharepoint_failed: bool = False
    can_finalize_pedido: bool = False
    can_generate_authorization: bool = False
    can_send_to_compulsa: bool = False
    can_retry_sharepoint: bool = False
    allowed_pedido_doc_keys: list[str] = field(default_factory=list)
    finalize_block_reason: str | None = None
    generate_auth_block_reason: str | None = None
    compulsa_block_reason: str | None = None
    sharepoint_notice: str | None = None


def action_unavailable_message() -> str:
    return _ACTION_UNAVAILABLE_MSG


def _user_role(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    rol = user.get("rol", "")
    return str(getattr(rol, "value", rol)).strip().lower()


def _rbac_relaxed() -> bool:
    return bool(get_settings().web_rbac_relaxed)


def _user_owns_case(user: dict[str, Any] | None, case: Case) -> bool:
    if not user:
        return False
    nombre = user.get("nombre")
    if not nombre or not case.seller_name:
        return False
    return str(case.seller_name).strip() == str(nombre).strip()


def _required_types(order_type: str | None) -> list[str]:
    if not order_type:
        return []
    return list(C.required_doc_types_for_order(order_type))


def _present_normalized(db: Session, case_id: int) -> set[str]:
    raw = DocumentRepository.get_active_types_for_case(db, case_id)
    return {normalize_doc_type(dt) for dt in raw}


def _missing_types(order_type: str | None, present: set[str]) -> list[str]:
    return [dt for dt in _required_types(order_type) if dt not in present]


def _next_missing(order_type: str | None, present: set[str]) -> str | None:
    for dt in _CHECKLIST_CAPTURE_ORDER:
        if dt not in _required_types(order_type):
            continue
        if dt not in present:
            return dt
    return None


def _collect_upload_flags(documents: list[Document]) -> tuple[list[DocUploadFlags], list[DocUploadFlags]]:
    pending: list[DocUploadFlags] = []
    failed: list[DocUploadFlags] = []
    for doc in documents:
        if not doc.is_active:
            continue
        flags = DocUploadFlags(
            document_id=doc.id,
            document_type=doc.document_type,
            label=doc_type_label(doc.document_type),
            upload_status=doc.upload_status or "",
        )
        if doc.upload_status == "PENDING_UPLOAD":
            pending.append(flags)
        elif doc.upload_status == "UPLOAD_FAILED":
            failed.append(flags)
    return pending, failed


def _ocr_notice_for_case(documents: list[Document]) -> str | None:
    pending_labels: list[str] = []
    error_labels: list[str] = []
    for doc in documents:
        if not doc.is_active or doc.document_type not in OCR_ELIGIBLE_DOCUMENT_TYPES:
            continue
        if not doc.ocr_results:
            continue
        latest = max(doc.ocr_results, key=lambda r: r.created_at)
        if latest.review_status == "pending":
            pending_labels.append(doc_type_label(doc.document_type))
        elif latest.review_status == "error":
            error_labels.append(doc_type_label(doc.document_type))
    if pending_labels or error_labels:
        parts = ["OCR pendiente o con error en algunos documentos; puedes continuar o revisar manualmente."]
        if pending_labels:
            parts.append(f"Pendiente: {', '.join(pending_labels)}.")
        if error_labels:
            parts.append(f"Error OCR: {', '.join(error_labels)}.")
        return " ".join(parts)
    return None


def _critical_failed(failed: list[DocUploadFlags]) -> bool:
    return any(
        normalize_doc_type(f.document_type) in _CRITICAL_DOC_TYPES_FOR_SP for f in failed
    )


def build_case_action_state(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
    *,
    documents: list[Document] | None = None,
) -> CaseActionState:
    """Calcula permisos y mensajes para UI web/Telegram."""
    docs = documents
    if docs is None:
        docs = (
            db.query(Document)
            .filter(Document.case_id == case.id, Document.is_active.is_(True))
            .all()
        )

    present = {normalize_doc_type(d.document_type) for d in docs}
    missing = _missing_types(case.order_type, present)
    next_miss = _next_missing(case.order_type, present)
    checklist_ok = case.case_type == C.CASE_TYPE_PEDIDO and not missing

    pending, failed = _collect_upload_flags(docs)
    crit_failed = _critical_failed(failed)
    ocr_notice = _ocr_notice_for_case(docs)

    sp_notice: str | None = None
    if pending:
        sp_notice = (
            "Documento recibido; subida a SharePoint pendiente en: "
            + ", ".join(p.label for p in pending)
            + "."
        )
    elif failed and crit_failed:
        sp_notice = (
            "Hay documentos con error de subida a SharePoint. Reintenta antes de acciones críticas."
        )

    role = _user_role(user)
    relaxed = _rbac_relaxed()
    owns = _user_owns_case(user, case)
    case_svc = CaseService(get_settings())

    # Teclado Telegram: solo el siguiente doc obligatorio (o reemplazo del mismo tipo si ya está)
    allowed_keys: list[str] = []
    if case.case_type == C.CASE_TYPE_PEDIDO and case.current_status in _PEDIDO_CAPTURE_STATUSES:
        if next_miss:
            for key, (dtype, _) in _PD_BUTTON_MAP.items():
                if dtype == next_miss:
                    allowed_keys.append(key)
                    break
        else:
            for key, (dtype, _) in _PD_BUTTON_MAP.items():
                if dtype in present:
                    allowed_keys.append(key)

    state = CaseActionState(
        case_id=case.id,
        public_id=case.public_id,
        order_type=case.order_type,
        current_status=case.current_status,
        checklist_ok=checklist_ok,
        missing_doc_types=missing,
        next_missing_doc_type=next_miss,
        present_doc_types=present,
        sharepoint_pending=pending,
        sharepoint_failed=failed,
        ocr_notice=ocr_notice,
        has_critical_sharepoint_failed=crit_failed,
        allowed_pedido_doc_keys=allowed_keys,
        sharepoint_notice=sp_notice,
    )

    state.can_finalize_pedido, state.finalize_block_reason = _eval_finalize(
        case, state, case_svc, db
    )
    state.can_generate_authorization, state.generate_auth_block_reason = _eval_generate_auth(
        case, state, role, relaxed, case_svc, db
    )
    state.can_send_to_compulsa, state.compulsa_block_reason = _eval_compulsa(
        case, state, role, relaxed, case_svc, db
    )
    state.can_retry_sharepoint = _eval_retry_sp(case, state, role, relaxed, owns, docs)

    return state


def _eval_finalize(
    case: Case,
    state: CaseActionState,
    case_svc: CaseService,
    db: Session,
) -> tuple[bool, str | None]:
    if case.case_type != C.CASE_TYPE_PEDIDO:
        return False, "Solo aplica a pedidos."
    if case.current_status not in _PEDIDO_CAPTURE_STATUSES:
        return False, "El pedido ya fue enviado a autorización o está en otro estatus."
    if not state.checklist_ok:
        missing = ", ".join(doc_type_label(dt) for dt in state.missing_doc_types)
        return False, f"Falta documentación obligatoria: {missing}."
    if state.has_critical_sharepoint_failed:
        return (
            False,
            "Hay documentos con error de subida a SharePoint. Reintenta la subida antes de enviar el pedido.",
        )
    return True, None


def _eval_generate_auth(
    case: Case,
    state: CaseActionState,
    role: str,
    relaxed: bool,
    case_svc: CaseService,
    db: Session,
) -> tuple[bool, str | None]:
    if case.case_type != C.CASE_TYPE_PEDIDO:
        return False, "Solo aplica a pedidos."
    if relaxed or role in _ROLES_GENERATE_AUTH:
        pass
    else:
        return False, "Solo autorización, administración o sistemas puede generar SNTE."
    from app.services.workflow_dependency_service import (
        build_workflow_context,
        can_action_generate_snte,
    )

    ctx = build_workflow_context(db, case)
    wf_ok, wf_reason = can_action_generate_snte(ctx)
    if not wf_ok:
        return False, wf_reason
    if not case_svc.pedido_has_all_documents(db, case):
        return False, "Falta completar el checklist del pedido."
    if state.has_critical_sharepoint_failed:
        return False, "Documento pendiente de subir a SharePoint o con error de subida."
    return True, None


def _eval_compulsa(
    case: Case,
    state: CaseActionState,
    role: str,
    relaxed: bool,
    _case_svc: CaseService,
    db: Session,
) -> tuple[bool, str | None]:
    if case.case_type != C.CASE_TYPE_PEDIDO:
        return False, "Solo aplica a pedidos."
    if not (relaxed or role in _ROLES_COMPULSA_STAFF):
        return False, "Solo administración o sistemas puede aprobar a compulsa."
    if state.has_critical_sharepoint_failed and not (relaxed or role in _ROLES_COMPULSA_STAFF):
        return False, "Hay documentos con error de subida a SharePoint."
    if state.has_critical_sharepoint_failed:
        return (
            False,
            "No se puede enviar a compulsa: documentos con UPLOAD_FAILED. Reintenta SharePoint o contacta administración.",
        )
    try:
        from app.services.document_service import DocumentService

        DocumentService().validate_active_documents_for_compulsa(db, case)
    except ValueError as exc:
        return False, str(exc)
    except Exception:
        return False, "No se cumplen los requisitos documentales para compulsa."
    active = _present_normalized(db, case.id)
    if C.DOC_AUTORIZACION_REFI not in active and C.DOC_AUTORIZACION_SNTE not in active:
        return False, "Falta autorización SNTE activa (Excel)."
    return True, None


def _eval_retry_sp(
    case: Case,
    state: CaseActionState,
    role: str,
    relaxed: bool,
    owns: bool,
    documents: list[Document],
) -> bool:
    if not state.sharepoint_failed:
        return False
    if relaxed or role in _ROLES_RETRY_SP and (role != UserRole.VENDEDOR.value or owns):
        pass
    elif role == UserRole.VENDEDOR.value and owns:
        pass
    else:
        return False
    for doc in documents:
        if doc.upload_status == "UPLOAD_FAILED" and doc.file_path and os.path.isfile(doc.file_path):
            return True
    return False


def get_case_action_state(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
) -> CaseActionState:
    return build_case_action_state(db, case, user)


def can_upload_document(
    db: Session,
    case: Case,
    doc_type: str,
    user: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    state = build_case_action_state(db, case, user)
    norm = normalize_doc_type(doc_type)
    if case.case_type != C.CASE_TYPE_PEDIDO:
        return False, "Solo se pueden subir documentos de pedido en este flujo."
    if case.current_status not in _PEDIDO_CAPTURE_STATUSES:
        return False, action_unavailable_message()
    required = set(_required_types(case.order_type))
    if norm not in required:
        return False, f"Tipo de documento no válido para este pedido: {doc_type_label(norm)}."
    if state.next_missing_doc_type and norm != state.next_missing_doc_type:
        if norm not in state.present_doc_types:
            return (
                False,
                f"Primero debes cargar: {doc_type_label(state.next_missing_doc_type)}.",
            )
    if state.has_critical_sharepoint_failed and norm in state.present_doc_types:
        pass
    return True, None


def can_finalize_pedido(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    state = build_case_action_state(db, case, user)
    if state.can_finalize_pedido:
        return True, None
    return False, state.finalize_block_reason or action_unavailable_message()


def can_generate_authorization(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    state = build_case_action_state(db, case, user)
    if state.can_generate_authorization:
        return True, None
    return False, state.generate_auth_block_reason or action_unavailable_message()


def can_send_to_compulsa(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    state = build_case_action_state(db, case, user)
    if state.can_send_to_compulsa:
        return True, None
    return False, state.compulsa_block_reason or action_unavailable_message()


def can_retry_sharepoint(
    db: Session,
    case: Case,
    user: dict[str, Any] | None,
    *,
    document_id: int | None = None,
) -> tuple[bool, str | None]:
    state = build_case_action_state(db, case, user)
    if not state.can_retry_sharepoint:
        return False, "No hay documentos con error de subida que se puedan reintentar."
    if document_id is not None:
        doc = db.get(Document, document_id)
        if not doc or doc.case_id != case.id or doc.upload_status != "UPLOAD_FAILED":
            return False, action_unavailable_message()
        if not doc.file_path or not os.path.isfile(doc.file_path):
            return False, "El archivo local ya no está disponible para reintentar."
    return True, None


def explain_blocked_action(
    action: str,
    case: Case,
    user: dict[str, Any] | None,
    db: Session,
) -> str:
    """Mensaje humano para una acción bloqueada."""
    action = (action or "").strip().lower()
    if action in ("upload_document", "upload", "pd"):
        _, reason = can_upload_document(db, case, "", user)
        return reason or action_unavailable_message()
    if action in ("finalize_pedido", "finalize", "pd|f", "f"):
        _, reason = can_finalize_pedido(db, case, user)
        return reason or action_unavailable_message()
    if action in ("generate_authorization", "generate_auth", "snte"):
        _, reason = can_generate_authorization(db, case, user)
        return reason or action_unavailable_message()
    if action in ("send_to_compulsa", "compulsa", "ped_aprobar"):
        _, reason = can_send_to_compulsa(db, case, user)
        return reason or action_unavailable_message()
    if action in ("retry_sharepoint", "retry_sp"):
        _, reason = can_retry_sharepoint(db, case, user)
        return reason or action_unavailable_message()
    state = build_case_action_state(db, case, user)
    return state.finalize_block_reason or action_unavailable_message()


def keyboard_pedidos_filtered(case_public_id: str, state: CaseActionState) -> list[list[tuple[str, str]]]:
    """Filas de botones inline para grupo pedidos (Aprobar solo si compulsa permitida)."""
    rows: list[list[tuple[str, str]]] = []
    first_row: list[tuple[str, str]] = []
    if state.can_send_to_compulsa:
        first_row.append(("✅ Aprobar", f"ped_aprobar|{case_public_id}"))
    first_row.append(("❌ Rechazar", f"ped_rechazar|{case_public_id}"))
    rows.append(first_row)
    rows.append([("🟡 Pedir corrección", f"ped_corregir|{case_public_id}")])
    return rows
