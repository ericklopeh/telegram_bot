from dataclasses import dataclass
from pathlib import Path

from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case


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
