"""Sincronización de documentos y exports con SharePoint vía Microsoft Graph (P25)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.domain.constants import is_sharepoint_synced
from app.models.case import Case
from app.models.document import Document
from app.models.sale_capture import SaleCapture
from app.repositories.document_repository import DocumentRepository
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.case_document_storage import case_documents_remote_relative_path
from app.services.case_event_service import (
    SHAREPOINT_RETRY_REQUESTED,
    SHAREPOINT_UPLOAD_FAILED,
    SHAREPOINT_UPLOAD_OK,
    SHAREPOINT_UPLOAD_STARTED,
    log_event,
)
from app.services.excel_path_guard import assert_not_excel_master_path
from app.services.sharepoint_graph_client import (
    GraphConfigError,
    GraphUploadError,
    SharePointGraphClient,
)
from app.services.sharepoint_retry_queue import enqueue_failed_upload

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    document_id: int
    ok: bool
    upload_status: str
    web_url: str | None = None
    error: str | None = None


class SharePointSyncService:
    def __init__(self, graph: SharePointGraphClient | None = None) -> None:
        self.graph = graph or SharePointGraphClient()

    def _load_document(self, db: Session, document_id: int) -> tuple[Document, Case]:
        doc = db.get(Document, document_id)
        if not doc:
            raise ValueError(f"Documento {document_id} no encontrado.")
        case = db.get(Case, doc.case_id)
        if not case:
            raise ValueError(f"Caso {doc.case_id} no encontrado.")
        return doc, case

    def _local_file_bytes(self, doc: Document) -> bytes:
        path = Path(doc.file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Archivo local no encontrado: {doc.file_path}")
        assert_not_excel_master_path(str(path))
        return path.read_bytes()

    def _remote_folder_for_case(self, case: Case) -> str:
        rel = case_documents_remote_relative_path(case)
        return self.graph.build_remote_documents_folder(rel)

    def sync_document(
        self,
        db: Session,
        document_id: int,
        *,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
        is_retry: bool = False,
    ) -> SyncResult:
        doc, case = self._load_document(db, document_id)
        if is_retry:
            self._log_sp(
                db,
                case.id,
                SHAREPOINT_RETRY_REQUESTED,
                f"Reintento SharePoint: {doc.stored_filename}",
                document_id=doc.id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )
        try:
            self.graph.validate_config()
        except GraphConfigError as exc:
            DocumentRepository.set_upload_failed(db, document_id, str(exc))
            return SyncResult(document_id, False, C.UPLOAD_FAILED, error=str(exc))

        DocumentRepository.set_upload_uploading(db, document_id)
        self._log_sp(
            db,
            case.id,
            SHAREPOINT_UPLOAD_STARTED,
            f"Subida SharePoint iniciada: {doc.stored_filename}",
            document_id=doc.id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        db.flush()

        try:
            file_bytes = self._local_file_bytes(doc)
            folder_path = self._remote_folder_for_case(case)
            result = self.graph.upload_file(
                folder_path,
                doc.stored_filename,
                file_bytes,
            )
            DocumentRepository.set_sharepoint_ok(
                db,
                document_id,
                web_url=result.web_url,
                sharepoint_folder_path=result.folder_path,
                sharepoint_drive_id=result.drive_id,
                sharepoint_item_id=result.item_id,
            )
            self._log_sp(
                db,
                case.id,
                SHAREPOINT_UPLOAD_OK,
                f"SharePoint OK: {doc.stored_filename}",
                document_id=doc.id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                metadata={"web_url": result.web_url, "folder_path": result.folder_path},
            )
            db.flush()
            return SyncResult(
                document_id,
                True,
                C.UPLOAD_SHAREPOINT_OK,
                web_url=result.web_url,
            )
        except (GraphUploadError, GraphConfigError, FileNotFoundError, OSError, ValueError) as exc:
            err = str(exc)
            DocumentRepository.set_upload_failed(db, document_id, err)
            self._enqueue_retry(doc, case, err)
            self._log_sp(
                db,
                case.id,
                SHAREPOINT_UPLOAD_FAILED,
                f"SharePoint fallido: {err}",
                document_id=doc.id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                metadata={"error": err},
            )
            db.flush()
            return SyncResult(document_id, False, C.UPLOAD_FAILED, error=err)

    def sync_case_documents(
        self,
        db: Session,
        case_id: int,
        *,
        only_pending_or_failed: bool = True,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> list[SyncResult]:
        q = select(Document).where(Document.case_id == case_id, Document.is_active.is_(True))
        if only_pending_or_failed:
            q = q.where(
                Document.upload_status.in_(
                    (C.UPLOAD_LOCAL, C.UPLOAD_PENDING, C.UPLOAD_FAILED)
                )
            )
        docs = list(db.scalars(q).all())
        results: list[SyncResult] = []
        for doc in docs:
            if is_sharepoint_synced(doc.upload_status):
                continue
            results.append(
                self.sync_document(
                    db,
                    doc.id,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                )
            )
        return results

    def retry_failed_for_case(
        self,
        db: Session,
        case_id: int,
        *,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> list[SyncResult]:
        docs = list(
            db.scalars(
                select(Document).where(
                    Document.case_id == case_id,
                    Document.is_active.is_(True),
                    Document.upload_status == C.UPLOAD_FAILED,
                )
            ).all()
        )
        return [
            self.sync_document(
                db,
                d.id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                is_retry=True,
            )
            for d in docs
        ]

    def retry_all_failed(
        self,
        db: Session,
        *,
        limit: int = 50,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> list[SyncResult]:
        docs = list(
            db.scalars(
                select(Document)
                .where(Document.upload_status == C.UPLOAD_FAILED, Document.is_active.is_(True))
                .order_by(Document.updated_at.desc())
                .limit(limit)
            ).all()
        )
        return [
            self.sync_document(
                db,
                d.id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                is_retry=True,
            )
            for d in docs
        ]

    def sync_sale_exports(
        self,
        db: Session,
        sale_capture_id: int,
        *,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> list[SyncResult]:
        """Sube copias de export Excel (solo storage/excel_exports/)."""
        sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
        if not sale or not sale.case_id:
            return []
        case = db.get(Case, sale.case_id)
        if not case:
            return []
        results: list[SyncResult] = []
        export_paths = [
            ("ventas", sale.ventas_export_path),
            ("contratos", sale.contratos_export_path),
        ]
        folder_base = self._remote_folder_for_case(case)
        exports_folder = f"{folder_base}/excel_exports"
        for label, path_str in export_paths:
            if not path_str:
                continue
            path = Path(path_str)
            if not path.is_file():
                continue
            assert_not_excel_master_path(str(path))
            if "excel_exports" not in str(path).replace("\\", "/"):
                log.warning("Omitiendo export fuera de excel_exports: %s", path)
                continue
            try:
                self.graph.validate_config()
                file_bytes = path.read_bytes()
                result = self.graph.upload_file(
                    exports_folder,
                    path.name,
                    file_bytes,
                )
                log.info(
                    "Export %s subido a SharePoint",
                    extra={"sale_id": sale_capture_id, "path": result.folder_path},
                )
            except (GraphUploadError, GraphConfigError, OSError) as exc:
                log.warning("Export %s no subido: %s", label, exc)
        return results

    def list_admin_buckets(self, db: Session, *, limit: int = 100) -> dict[str, list[Document]]:
        pending = list(
            db.scalars(
                select(Document)
                .where(
                    Document.is_active.is_(True),
                    Document.upload_status.in_(
                        (C.UPLOAD_LOCAL, C.UPLOAD_PENDING, C.UPLOAD_UPLOADING)
                    ),
                )
                .order_by(Document.updated_at.desc())
                .limit(limit)
            ).all()
        )
        failed = list(
            db.scalars(
                select(Document)
                .where(
                    Document.is_active.is_(True),
                    Document.upload_status == C.UPLOAD_FAILED,
                )
                .order_by(Document.updated_at.desc())
                .limit(limit)
            ).all()
        )
        ok = list(
            db.scalars(
                select(Document)
                .where(
                    Document.is_active.is_(True),
                    Document.upload_status.in_((C.UPLOAD_SHAREPOINT_OK, C.UPLOAD_LEGACY_OK)),
                )
                .order_by(Document.updated_at.desc())
                .limit(limit)
            ).all()
        )
        return {"pending": pending, "failed": failed, "ok": ok}

    @staticmethod
    def _enqueue_retry(doc: Document, case: Case, error: str) -> None:
        try:
            enqueue_failed_upload(
                file_path=doc.file_path,
                vendedor=case.seller_name or "SIN VENDEDOR",
                semana=case.week_code,
                cliente=case.client_name,
                folio=case.official_folio or case.temp_folio or case.public_id,
                tipo_documento=doc.document_type,
                filename=doc.stored_filename,
                document_id=doc.id,
                error=error,
            )
        except Exception:
            log.exception("No se pudo encolar retry SharePoint", extra={"document_id": doc.id})

    @staticmethod
    def _log_sp(
        db: Session,
        case_id: int,
        event_type: str,
        message: str,
        *,
        document_id: int | None = None,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        meta = dict(metadata or {})
        if document_id:
            meta["document_id"] = document_id
        log_event(
            db,
            case_id=case_id,
            event_type=event_type,
            message=message,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="sharepoint",
            metadata=meta,
        )
