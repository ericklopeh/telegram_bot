from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


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

    @staticmethod
    def set_upload_uploaded(db: Session, document_id: int, web_url: str | None) -> None:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.upload_status = "UPLOADED"
        doc.sharepoint_web_url = web_url
        doc.upload_error = None

    @staticmethod
    def set_upload_failed(db: Session, document_id: int, error: str) -> None:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.upload_status = "UPLOAD_FAILED"
        doc.upload_error = error
        doc.upload_attempts = (doc.upload_attempts or 0) + 1
