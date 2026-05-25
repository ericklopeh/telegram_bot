import logging
from dataclasses import dataclass

from app.db.session import session_scope
from app.services.sharepoint_sync_service import SharePointSyncService
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
    """Fachada legacy: delega en SharePointSyncService (P25)."""

    def upload_document(self, payload: SharePointUploadPayload) -> dict:
        try:
            with session_scope() as db:
                sync = SharePointSyncService()
                result = sync.sync_document(db, payload.document_id, is_retry=False)
                db.commit()
            if not result.ok:
                raise RuntimeError(result.error or "SharePoint sync failed")
            doc = None
            with session_scope() as db:
                from app.models.document import Document

                doc = db.get(Document, payload.document_id)
            out = {
                "ok": True,
                "webUrl": result.web_url or (doc.sharepoint_web_url if doc else None),
                "folder_path": doc.sharepoint_folder_path if doc else None,
                "id": doc.sharepoint_item_id if doc else None,
            }
            log.info(
                "Documento subido a SharePoint",
                extra={"document_id": payload.document_id, "webUrl": out.get("webUrl")},
            )
            return out
        except Exception as exc:
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
                extra={"document_id": payload.document_id},
            )
            raise
