from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.case_event import CaseEvent

log = logging.getLogger(__name__)

EventSource = Literal["web", "telegram", "system", "sharepoint", "bot"]

CASE_CREATED = "CASE_CREATED"
STATUS_CHANGED = "STATUS_CHANGED"
AUTH_GENERATED = "AUTH_GENERATED"
REFI_GENERATED = "REFI_GENERATED"
DOCUMENT_CREATED = "DOCUMENT_CREATED"
DOCUMENT_UPLOAD_QUEUED = "DOCUMENT_UPLOAD_QUEUED"
DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
DOCUMENT_UPLOAD_FAILED = "DOCUMENT_UPLOAD_FAILED"
TELEGRAM_NOTIFIED = "TELEGRAM_NOTIFIED"
COMPULSA_APPROVED = "COMPULSA_APPROVED"
COMPULSA_REJECTED = "COMPULSA_REJECTED"
DOCUMENT_RECEIVED = "DOCUMENT_RECEIVED"
OCR_PROCESSED = "OCR_PROCESSED"
OCR_FAILED = "OCR_FAILED"
OCR_NO_TEXT = "OCR_NO_TEXT"
CHECKLIST_COMPLETE = "CHECKLIST_COMPLETE"
CHECKLIST_INCOMPLETE = "CHECKLIST_INCOMPLETE"
AUTH_REGENERATED = "AUTH_REGENERATED"
SNTE_PDF_GENERATED = "SNTE_PDF_GENERATED"
SNTE_EXCEL_GENERATED = "SNTE_EXCEL_GENERATED"
SALE_CAPTURE_DRAFT = "SALE_CAPTURE_DRAFT"
SALE_CAPTURE_REGISTERED = "SALE_CAPTURE_REGISTERED"
SALE_CAPTURE_VALIDATED = "SALE_CAPTURE_VALIDATED"
SALE_CAPTURE_EDITED = "SALE_CAPTURE_EDITED"
SALE_CAPTURE_REGISTER_BLOCKED = "SALE_CAPTURE_REGISTER_BLOCKED"
SALE_CAPTURE_EXPORT_FAILED = "SALE_CAPTURE_EXPORT_FAILED"
SALE_CAPTURE_DUPLICATE_DETECTED = "SALE_CAPTURE_DUPLICATE_DETECTED"
SALE_CAPTURE_REGISTRATION_QUEUED = "SALE_CAPTURE_REGISTRATION_QUEUED"
SALE_CAPTURE_PROCESSING = "SALE_CAPTURE_PROCESSING"
SALE_CAPTURE_REGISTRATION_FAILED = "SALE_CAPTURE_REGISTRATION_FAILED"
SALE_CAPTURE_RETRY_REQUESTED = "SALE_CAPTURE_RETRY_REQUESTED"
SALE_CAPTURE_CONCILIATION_WARNING = "SALE_CAPTURE_CONCILIATION_WARNING"
COMMISSION_CREATED = "COMMISSION_CREATED"
COMMISSION_UPDATED = "COMMISSION_UPDATED"
COMMISSION_PAID = "COMMISSION_PAID"
COMMISSION_CANCELLED = "COMMISSION_CANCELLED"
WORKFLOW_TRANSITION_REQUESTED = "WORKFLOW_TRANSITION_REQUESTED"
WORKFLOW_TRANSITION_COMPLETED = "WORKFLOW_TRANSITION_COMPLETED"
WORKFLOW_TRANSITION_BLOCKED = "WORKFLOW_TRANSITION_BLOCKED"
WORKFLOW_DEPENDENCY_MISSING = "WORKFLOW_DEPENDENCY_MISSING"
WORKFLOW_STATE_RECALCULATED = "WORKFLOW_STATE_RECALCULATED"
SNTE_UNLOCKED_AFTER_APPROVAL = "SNTE_UNLOCKED_AFTER_APPROVAL"
# P24 — revisión documental (distinto de DOCUMENT_UPLOADED = SharePoint)
CASE_DOCUMENT_UPLOADED = "CASE_DOCUMENT_UPLOADED"
CASE_DOCUMENT_REPLACED = "CASE_DOCUMENT_REPLACED"
CASE_DOCUMENT_VALIDATED = "CASE_DOCUMENT_VALIDATED"
CASE_DOCUMENT_REJECTED = "CASE_DOCUMENT_REJECTED"
DOCUMENT_MISSING_BLOCKED = "DOCUMENT_MISSING_BLOCKED"
SHAREPOINT_UPLOAD_STARTED = "SHAREPOINT_UPLOAD_STARTED"
SHAREPOINT_UPLOAD_OK = "SHAREPOINT_UPLOAD_OK"
SHAREPOINT_UPLOAD_FAILED = "SHAREPOINT_UPLOAD_FAILED"
SHAREPOINT_RETRY_REQUESTED = "SHAREPOINT_RETRY_REQUESTED"
PAYMENT_REGISTERED = "PAYMENT_REGISTERED"
REFINANCE_CREATED = "REFINANCE_CREATED"
BALANCE_ADJUSTED = "BALANCE_ADJUSTED"
CONTRACT_CLOSED = "CONTRACT_CLOSED"


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, set):
        return sorted(value, key=str)
    return str(value)


def _json_safe(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return json.loads(json.dumps(metadata, default=_json_default, ensure_ascii=False))


def log_event(
    db: Session,
    *,
    case_id: int,
    event_type: str,
    message: str | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
    metadata: dict[str, Any] | None = None,
) -> CaseEvent | None:
    """Add a timeline/audit event to the current session.

    This function does not commit. Callers keep ownership of transaction
    boundaries. If event preparation fails, the error is logged and the caller's
    main flow can continue.
    """
    try:
        event = CaseEvent(
            case_id=case_id,
            event_type=event_type,
            message=message,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source=source,
            metadata_json=_json_safe(metadata),
        )
        db.add(event)
        return event
    except Exception:
        log.exception(
            "No se pudo preparar evento de auditoria",
            extra={"case_id": case_id, "event_type": event_type, "source": source},
        )
        return None


def log_status_change(
    db: Session,
    *,
    case_id: int,
    old_status: str | None,
    new_status: str,
    message: str | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
    metadata: dict[str, Any] | None = None,
) -> CaseEvent | None:
    event_metadata = {
        "old_status": old_status,
        "new_status": new_status,
        **(metadata or {}),
    }
    return log_event(
        db,
        case_id=case_id,
        event_type=STATUS_CHANGED,
        message=message or f"Estado actualizado: {old_status or 'N/A'} -> {new_status}",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source=source,
        metadata=event_metadata,
    )


def log_document_event(
    db: Session,
    *,
    case_id: int,
    event_type: str,
    document_id: int | None = None,
    document_type: str | None = None,
    filename: str | None = None,
    message: str | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
    metadata: dict[str, Any] | None = None,
) -> CaseEvent | None:
    event_metadata = {
        "document_id": document_id,
        "document_type": document_type,
        "filename": filename,
        **(metadata or {}),
    }
    return log_event(
        db,
        case_id=case_id,
        event_type=event_type,
        message=message,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source=source,
        metadata=event_metadata,
    )


def log_document_received(
    db: Session,
    *,
    case_id: int,
    document_type: str,
    document_id: int | None = None,
    filename: str | None = None,
    message: str | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
    metadata: dict[str, Any] | None = None,
) -> CaseEvent | None:
    from app.domain.constants import doc_type_label

    label = doc_type_label(document_type)
    default_msg = message or f"Documento recibido: {label}"
    return log_document_event(
        db,
        case_id=case_id,
        event_type=DOCUMENT_RECEIVED,
        document_id=document_id,
        document_type=document_type,
        filename=filename,
        message=default_msg,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source=source,
        metadata=metadata,
    )


def log_ocr_event(
    db: Session,
    *,
    case_id: int,
    document_id: int,
    document_type: str,
    review_status: str,
    confidence: float | None = None,
    action_user: str | None = None,
    source: EventSource | str | None = "system",
) -> CaseEvent | None:
    from app.domain.constants import doc_type_label

    label = doc_type_label(document_type)
    if review_status == "processed":
        event_type = OCR_PROCESSED
        msg = f"OCR procesado en {label}"
        if confidence is not None:
            msg += f" ({int(confidence * 100)}% confianza)"
    elif review_status == "error":
        event_type = OCR_NO_TEXT
        msg = f"OCR sin texto legible en {label}"
    else:
        event_type = OCR_FAILED
        msg = f"OCR fallido en {label}"

    return log_document_event(
        db,
        case_id=case_id,
        event_type=event_type,
        document_id=document_id,
        document_type=document_type,
        message=msg,
        actor_role=action_user,
        source=source,
        metadata={
            "review_status": review_status,
            "confidence_score": confidence,
        },
    )


def log_checklist_event(
    db: Session,
    *,
    case_id: int,
    complete: bool,
    checklist_text: str,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
) -> CaseEvent | None:
    event_type = CHECKLIST_COMPLETE if complete else CHECKLIST_INCOMPLETE
    if complete:
        message = "Checklist del pedido completo — listo para enviar a autorización"
    else:
        message = "Checklist del pedido incompleto"
    return log_event(
        db,
        case_id=case_id,
        event_type=event_type,
        message=message,
        actor_role=actor_role,
        source=source,
        metadata={"checklist": checklist_text, "complete": complete},
    )


def log_pedido_checklist_after_upload(
    db: Session,
    case,
    *,
    source: EventSource | str,
    actor_role: str | None = None,
) -> None:
    """Registra estado del checklist tras subir un documento de pedido."""
    from app.config import get_settings
    from app.domain import constants as C
    from app.services.case_service import CaseService

    if case.case_type != C.CASE_TYPE_PEDIDO or not case.order_type:
        return
    svc = CaseService(get_settings())
    complete = svc.pedido_has_all_documents(db, case)
    checklist = svc.get_pedido_checklist(db, case)
    log_checklist_event(
        db,
        case_id=case.id,
        complete=complete,
        checklist_text=checklist,
        actor_role=actor_role,
        source=source,
    )


def log_case_created(
    db: Session,
    *,
    case_id: int,
    case_type: str,
    client_name: str,
    actor_role: str | None = None,
    source: EventSource | str | None = "system",
    metadata: dict[str, Any] | None = None,
) -> CaseEvent | None:
    tipo = "revisión" if case_type == "revision" else "pedido"
    return log_event(
        db,
        case_id=case_id,
        event_type=CASE_CREATED,
        message=f"Caso de {tipo} creado — {client_name}",
        actor_role=actor_role,
        source=source,
        metadata={"case_type": case_type, **(metadata or {})},
    )
