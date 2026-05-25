"""Gestión documental avanzada por caso/pedido (P24)."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.domain.constants import (
    doc_type_label,
    normalize_doc_type,
    p24_required_doc_types_for_pedido,
)
from app.models.case import Case
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.services.case_document_storage import (
    build_stored_filename,
    case_documents_base_dir,
)
from app.services.case_event_service import (
    CASE_DOCUMENT_REJECTED,
    CASE_DOCUMENT_REPLACED,
    CASE_DOCUMENT_UPLOADED,
    CASE_DOCUMENT_VALIDATED,
    DOCUMENT_MISSING_BLOCKED,
    log_document_event,
    log_event,
)
from app.services.workflow_state_service import (
    WF_APROBADO,
    WF_EN_COMPULSA,
    WF_PREP_AUTORIZACION,
    WF_REGISTRADO,
    WF_REGISTRO_PENDIENTE,
    WF_SHAREPOINT_OK,
)

log = logging.getLogger(__name__)

# Estados workflow que exigen checklist P24 completo y validado
_WORKFLOW_REQUIRES_P24_DOCS = frozenset(
    {
        WF_PREP_AUTORIZACION,
        WF_EN_COMPULSA,
        WF_APROBADO,
        WF_SHAREPOINT_OK,
        WF_REGISTRO_PENDIENTE,
        WF_REGISTRADO,
    }
)

_ALL_UPLOAD_TYPES = frozenset(
    {
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
        C.DOC_AUTORIZACION_SNTE,
        C.DOC_ORDEN_SNTE_PDF,
        C.DOC_AUTORIZACION_REFI,
        C.DOC_INE,
        C.DOC_ESTADO_CUENTA,
        C.DOC_OTRO,
        C.DOC_REVISION_EVIDENCIA,
        C.DOC_REVISION_DICTAMEN,
    }
)


@dataclass(frozen=True)
class ChecklistItem:
    document_type: str
    label: str
    required: bool
    present: bool
    valid: bool
    document_id: int | None
    review_status: str | None


@dataclass(frozen=True)
class DocumentSummary:
    complete: int
    pending: int
    invalid: int
    missing: int


class CaseDocumentService:
    def has_refinanciamiento(self, db: Session, case: Case) -> bool:
        present = DocumentRepository.get_active_types_for_case(db, case.id)
        return C.DOC_AUTORIZACION_REFI in {normalize_doc_type(t) for t in present}

    def required_document_types(self, db: Session, case: Case) -> list[str]:
        if case.case_type != C.CASE_TYPE_PEDIDO:
            return []
        return p24_required_doc_types_for_pedido(
            case.order_type or C.ORDER_TYPE_MUEBLE,
            has_refinanciamiento=self.has_refinanciamiento(db, case),
        )

    def list_active_documents(self, db: Session, case_id: int) -> list[Document]:
        return list(
            db.scalars(
                select(Document)
                .where(Document.case_id == case_id, Document.is_active.is_(True))
                .order_by(Document.document_type, Document.version.desc())
            ).all()
        )

    def list_all_documents(self, db: Session, case_id: int) -> list[Document]:
        return list(
            db.scalars(
                select(Document)
                .where(Document.case_id == case_id)
                .order_by(Document.created_at.desc())
            ).all()
        )

    def get_document(self, db: Session, case_id: int, document_id: int) -> Document | None:
        doc = db.get(Document, document_id)
        if not doc or doc.case_id != case_id:
            return None
        return doc

    def build_checklist(self, db: Session, case: Case) -> list[ChecklistItem]:
        required = set(self.required_document_types(db, case))
        active = {
            normalize_doc_type(d.document_type): d
            for d in self.list_active_documents(db, case.id)
        }
        items: list[ChecklistItem] = []
        for dt in sorted(required, key=doc_type_label):
            doc = active.get(dt)
            items.append(
                ChecklistItem(
                    document_type=dt,
                    label=doc_type_label(dt),
                    required=True,
                    present=doc is not None,
                    valid=doc is not None and doc.review_status == C.REVIEW_VALID,
                    document_id=doc.id if doc else None,
                    review_status=doc.review_status if doc else None,
                )
            )
        return items

    def missing_required_types(self, db: Session, case: Case) -> list[str]:
        required = self.required_document_types(db, case)
        present = {
            normalize_doc_type(t)
            for t in DocumentRepository.get_active_types_for_case(db, case.id)
        }
        return [dt for dt in required if dt not in present]

    def missing_valid_types(self, db: Session, case: Case) -> list[str]:
        """Tipos requeridos sin documento activo en estado VALID."""
        required = set(self.required_document_types(db, case))
        missing: list[str] = []
        for doc in self.list_active_documents(db, case.id):
            dt = normalize_doc_type(doc.document_type)
            if dt in required and doc.review_status != C.REVIEW_VALID:
                if dt not in missing:
                    missing.append(dt)
        present = {normalize_doc_type(d.document_type) for d in self.list_active_documents(db, case.id)}
        for dt in required:
            if dt not in present and dt not in missing:
                missing.append(dt)
        return missing

    def summarize(self, db: Session, case: Case) -> DocumentSummary:
        checklist = self.build_checklist(db, case)
        complete = sum(1 for i in checklist if i.valid)
        pending = sum(1 for i in checklist if i.present and not i.valid and i.review_status != C.REVIEW_INVALID)
        invalid = sum(1 for i in checklist if i.review_status == C.REVIEW_INVALID)
        missing = sum(1 for i in checklist if not i.present)
        return DocumentSummary(
            complete=complete,
            pending=pending,
            invalid=invalid,
            missing=missing,
        )

    def missing_for_workflow_target(self, db: Session, case: Case, target_state: str) -> list[str]:
        if target_state not in _WORKFLOW_REQUIRES_P24_DOCS:
            return []
        if case.case_type != C.CASE_TYPE_PEDIDO:
            return []
        missing_present = self.missing_required_types(db, case)
        if missing_present:
            return missing_present
        return self.missing_valid_types(db, case)

    def assert_workflow_documents(self, db: Session, case: Case, target_state: str) -> None:
        missing = self.missing_for_workflow_target(db, case, target_state)
        if not missing:
            return
        labels = ", ".join(doc_type_label(dt) for dt in missing)
        msg = (
            f"No se puede avanzar a {target_state}: faltan documentos obligatorios o sin validar "
            f"({labels})."
        )
        self._log_missing_blocked(db, case, target_state, missing, msg)
        raise ValueError(msg)

    def _log_missing_blocked(
        self,
        db: Session,
        case: Case,
        target_state: str,
        missing: list[str],
        message: str,
        *,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> None:
        log_event(
            db,
            case_id=case.id,
            event_type=DOCUMENT_MISSING_BLOCKED,
            message=message,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
            metadata={"target_state": target_state, "missing_types": missing},
        )

    def _save_bytes(
        self,
        case: Case,
        document_type: str,
        content: bytes,
        original_filename: str | None,
        mime_type: str | None,
        version: int,
    ) -> tuple[str, str, Path]:
        dest_dir = case_documents_base_dir(case)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = build_stored_filename(
            document_type, original_filename, version=version
        )
        dest = dest_dir / stored_filename
        if dest.exists():
            dest = dest_dir / build_stored_filename(
                document_type, original_filename, version=version + 1
            )
        dest.write_bytes(content)
        return stored_filename, str(dest.resolve()), dest

    def upload_document(
        self,
        db: Session,
        case: Case,
        document_type: str,
        file_bytes: bytes,
        *,
        original_filename: str | None = None,
        mime_type: str | None = None,
        uploaded_by: str | None = None,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
        source: str = "web",
    ) -> Document:
        document_type = normalize_doc_type(document_type)
        if document_type not in _ALL_UPLOAD_TYPES:
            raise ValueError(f"Tipo de documento no permitido: {document_type}")

        prev = DocumentRepository.get_active_document(db, case.id, document_type)
        version = (prev.version + 1) if prev else 1

        stored_filename, file_path, _ = self._save_bytes(
            case,
            document_type,
            file_bytes,
            original_filename,
            mime_type,
            version,
        )

        doc = DocumentRepository.add_version(
            db,
            case.id,
            document_type,
            stored_filename,
            file_path,
            original_filename,
            mime_type,
            size_bytes=len(file_bytes),
            version=version,
            uploaded_by=uploaded_by,
            review_status=C.REVIEW_PENDING,
            ocr_status=C.OCR_STATUS_PENDING,
        )
        log_document_event(
            db,
            case_id=case.id,
            event_type=CASE_DOCUMENT_UPLOADED,
            document_id=doc.id,
            document_type=document_type,
            filename=original_filename or stored_filename,
            message=f"Documento cargado: {doc_type_label(document_type)} (v{version})",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source=source,
            metadata={"version": version, "review_status": doc.review_status},
        )
        db.flush()
        return doc

    def replace_document(
        self,
        db: Session,
        case: Case,
        document_id: int,
        file_bytes: bytes,
        *,
        original_filename: str | None = None,
        mime_type: str | None = None,
        uploaded_by: str | None = None,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> Document:
        old = self.get_document(db, case.id, document_id)
        if not old:
            raise ValueError("Documento no encontrado.")
        document_type = normalize_doc_type(old.document_type)
        new_doc = self.upload_document(
            db,
            case,
            document_type,
            file_bytes,
            original_filename=original_filename,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        if old.is_active:
            old.is_active = False
            old.review_status = C.REVIEW_REPLACED
        log_document_event(
            db,
            case_id=case.id,
            event_type=CASE_DOCUMENT_REPLACED,
            document_id=new_doc.id,
            document_type=document_type,
            filename=original_filename or new_doc.stored_filename,
            message=f"Documento reemplazado: {doc_type_label(document_type)}",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
            metadata={"replaced_document_id": old.id, "new_document_id": new_doc.id},
        )
        db.flush()
        return new_doc

    def validate_document(
        self,
        db: Session,
        case: Case,
        document_id: int,
        *,
        validated_by: str | None = None,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> Document:
        doc = self.get_document(db, case.id, document_id)
        if not doc or not doc.is_active:
            raise ValueError("Documento activo no encontrado.")
        from datetime import datetime, timezone

        doc.review_status = C.REVIEW_VALID
        doc.validated_by = validated_by
        doc.validated_at = datetime.now(timezone.utc)
        doc.rejection_reason = None
        db.flush()
        log_document_event(
            db,
            case_id=case.id,
            event_type=CASE_DOCUMENT_VALIDATED,
            document_id=doc.id,
            document_type=doc.document_type,
            filename=doc.original_filename or doc.stored_filename,
            message=f"Documento validado: {doc_type_label(doc.document_type)}",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
        )
        return doc

    def reject_document(
        self,
        db: Session,
        case: Case,
        document_id: int,
        reason: str,
        *,
        validated_by: str | None = None,
        actor_user_id: int | None = None,
        actor_role: str | None = None,
    ) -> Document:
        doc = self.get_document(db, case.id, document_id)
        if not doc or not doc.is_active:
            raise ValueError("Documento activo no encontrado.")
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Indique el motivo de rechazo.")
        from datetime import datetime, timezone

        doc.review_status = C.REVIEW_INVALID
        doc.validated_by = validated_by
        doc.validated_at = datetime.now(timezone.utc)
        doc.rejection_reason = reason
        db.flush()
        log_document_event(
            db,
            case_id=case.id,
            event_type=CASE_DOCUMENT_REJECTED,
            document_id=doc.id,
            document_type=doc.document_type,
            filename=doc.original_filename or doc.stored_filename,
            message=f"Documento rechazado: {doc_type_label(doc.document_type)} — {reason}",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
            metadata={"rejection_reason": reason},
        )
        return doc

    def copy_upload_to_path(
        self,
        src_path: Path,
        case: Case,
        document_type: str,
        *,
        version: int = 1,
    ) -> tuple[str, str]:
        """Copia archivo existente al árbol P24 (p. ej. migración desde upload legacy)."""
        content = src_path.read_bytes()
        stored_filename, file_path, _ = self._save_bytes(
            case,
            document_type,
            content,
            src_path.name,
            None,
            version,
        )
        return stored_filename, file_path
