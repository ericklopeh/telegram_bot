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
