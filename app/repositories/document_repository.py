import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.case_event_service import (
    DOCUMENT_UPLOAD_FAILED,
    DOCUMENT_UPLOAD_QUEUED,
    DOCUMENT_UPLOADED,
    log_document_event,
)

log = logging.getLogger(__name__)


def _log_upload_event(
    db: Session,
    doc: Document,
    event_type: str,
    upload_status: str,
    *,
    sharepoint_path: str | None = None,
    error_message: str | None = None,
) -> None:
    try:
        with db.begin_nested():
            log_document_event(
                db,
                case_id=doc.case_id,
                event_type=event_type,
                document_id=doc.id,
                document_type=doc.document_type,
                filename=doc.stored_filename,
                source="sharepoint",
                metadata={
                    "case_id": doc.case_id,
                    "document_id": doc.id,
                    "upload_status": upload_status,
                    "sharepoint_path": sharepoint_path,
                    "error_message": error_message,
                },
            )
            db.flush()
    except Exception:
        log.exception(
            "No se pudo registrar evento de auditoria de upload",
            extra={"document_id": doc.id, "case_id": doc.case_id, "event_type": event_type},
        )


class DocumentRepository:
    @staticmethod
    def get_active_types_for_case(db: Session, case_id: int) -> set[str]:
        rows = db.scalars(
            select(Document.document_type).where(
                Document.case_id == case_id,
                Document.is_active.is_(True),
            )
        ).all()
        return set(rows)

    @staticmethod
    def deactivate_active(db: Session, case_id: int, document_type: str) -> int | None:
        existing = db.scalar(
            select(Document).where(
                Document.case_id == case_id,
                Document.document_type == document_type,
                Document.is_active.is_(True),
            )
        )
        if not existing:
            return None
        existing.is_active = False
        db.flush()
        return existing.id

    @staticmethod
    def add_version(
        db: Session,
        case_id: int,
        document_type: str,
        stored_filename: str,
        file_path: str,
        original_filename: str | None,
        mime_type: str | None,
    ) -> Document:
        replaced_id = DocumentRepository.deactivate_active(db, case_id, document_type)
        doc = Document(
            case_id=case_id,
            document_type=document_type,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            mime_type=mime_type,
            is_active=True,
            replaced_document_id=replaced_id,
        )
        db.add(doc)
        db.flush()
        return doc

    @staticmethod
    def get_active_document(db: Session, case_id: int, document_type: str) -> Document | None:
        return db.scalar(
            select(Document).where(
                Document.case_id == case_id,
                Document.document_type == document_type,
                Document.is_active.is_(True),
            )
        )

    @staticmethod
    def set_upload_pending(db: Session, document_id: int) -> None:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.upload_status = "PENDING_UPLOAD"
        doc.upload_error = None
        _log_upload_event(db, doc, DOCUMENT_UPLOAD_QUEUED, doc.upload_status)

    @staticmethod
    def set_upload_uploaded(
        db: Session,
        document_id: int,
        web_url: str | None,
        sharepoint_path: str | None = None,
    ) -> None:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.upload_status = "UPLOADED"
        doc.sharepoint_web_url = web_url
        doc.upload_error = None
        _log_upload_event(
            db,
            doc,
            DOCUMENT_UPLOADED,
            doc.upload_status,
            sharepoint_path=sharepoint_path,
        )

    @staticmethod
    def set_upload_failed(db: Session, document_id: int, error: str) -> None:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.upload_status = "UPLOAD_FAILED"
        doc.upload_error = error
        doc.upload_attempts = (doc.upload_attempts or 0) + 1
        _log_upload_event(
            db,
            doc,
            DOCUMENT_UPLOAD_FAILED,
            doc.upload_status,
            error_message=error,
        )
