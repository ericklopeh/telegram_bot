import logging
from dataclasses import dataclass
from pathlib import Path

from app.db.session import session_scope
from app.repositories.document_repository import DocumentRepository
from app.services.microsoft_graph import upload_document_to_sharepoint
from app.services.sharepoint_retry_queue import enqueue_failed_upload

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharePointUploadPayload:
    document_id: int
    file_path: str
    vendedor: str
    semana: str
    cliente: str
    folio: str
    tipo_documento: str
    filename: str


class SharePointDocumentService:
    def upload_document(self, payload: SharePointUploadPayload) -> dict:
        try:
            file_bytes = Path(payload.file_path).read_bytes()
            result = upload_document_to_sharepoint(
                vendedor=payload.vendedor,
                semana=payload.semana,
                cliente=payload.cliente,
                folio=payload.folio,
                tipo_documento=payload.tipo_documento,
                filename=payload.filename,
                file_bytes=file_bytes,
            )
            with session_scope() as db:
                DocumentRepository.set_upload_uploaded(
                    db,
                    payload.document_id,
                    result.get("webUrl"),
                    sharepoint_path=result.get("folder_path"),
                )
            log.info(
                "Documento subido a SharePoint",
                extra={
                    "document_id": payload.document_id,
                    "vendedor": payload.vendedor,
                    "folio": payload.folio,
                    "cliente": payload.cliente,
                    "tipo_documento": payload.tipo_documento,
                    "ruta_final": result.get("folder_path"),
                    "webUrl": result.get("webUrl"),
                },
            )
            return result
        except Exception as exc:
            with session_scope() as db:
                DocumentRepository.set_upload_failed(db, payload.document_id, str(exc))
            enqueue_failed_upload(
                file_path=payload.file_path,
                vendedor=payload.vendedor,
                semana=payload.semana,
                cliente=payload.cliente,
                folio=payload.folio,
                tipo_documento=payload.tipo_documento,
                filename=payload.filename,
                document_id=payload.document_id,
                error=str(exc),
            )
            log.exception(
                "Error subiendo documento a SharePoint en background",
                extra={
                    "document_id": payload.document_id,
                    "vendedor": payload.vendedor,
                    "folio": payload.folio,
                    "cliente": payload.cliente,
                    "tipo_documento": payload.tipo_documento,
                    "file_name_info": payload.filename,
                },
            )
            raise
