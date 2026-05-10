from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository


@dataclass(frozen=True)
class StoredIncomingFile:
    stored_filename: str
    file_path: str
    original_filename: str | None
    mime_type: str | None


class DocumentService:
    def revision_evidence_prefix(self, folio: str, client_name: str) -> str:
        return f"{folio} {client_name} - REVISION"

    def revision_dictamen_prefix(self, case: Case) -> str:
        return f"{case.public_id} {case.client_name} - DICTAMEN"

    def pedido_document_prefix(self, case: Case, client_name: str, document_type: str) -> str:
        tipo_limpio = "MUEBLE" if case.order_type == C.ORDER_TYPE_MUEBLE else "PRESTAMO"
        return f"{case.official_folio} {client_name} - {tipo_limpio} - {doc_type_label(document_type)}"

    def pedido_evidencias_dir(self, case: Case) -> Path:
        return Path(case.folder_path) / "EVIDENCIAS"

    def revision_dictamen_dir(self, case: Case) -> Path:
        return Path(case.folder_path) / "REVISION"

    def register_document_version(
        self,
        db: Session,
        case: Case,
        document_type: str,
        stored_file: StoredIncomingFile,
    ) -> Document:
        return DocumentRepository.add_version(
            db,
            case.id,
            document_type,
            stored_file.stored_filename,
            stored_file.file_path,
            stored_file.original_filename,
            stored_file.mime_type,
        )

    def mark_document_pending_upload(self, db: Session, document_id: int) -> None:
        DocumentRepository.set_upload_pending(db, document_id)

    def register_pedido_document_upload(
        self,
        db: Session,
        case: Case,
        document_type: str,
        stored_file: StoredIncomingFile,
    ) -> tuple[Document, set[str]]:
        document = self.register_document_version(db, case, document_type, stored_file)
        self.mark_document_pending_upload(db, document.id)
        present = DocumentRepository.get_active_types_for_case(db, case.id)
        return document, present

    def register_revision_dictamen_upload(
        self,
        db: Session,
        case: Case,
        stored_file: StoredIncomingFile,
    ) -> Document:
        return self.register_document_version(db, case, C.DOC_REVISION_DICTAMEN, stored_file)
