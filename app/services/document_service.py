import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.domain import constants as C
from app.domain.constants import doc_type_label, normalize_doc_type
from app.models.case import Case
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository

log = logging.getLogger(__name__)


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

    def validate_active_documents_for_compulsa(self, db: Session, case: Case) -> None:
        """
        Comprueba documentos activos mínimos antes de pasar el pedido a compulsa.
        No genera archivos ni llama a servicios externos.
        """
        if case.case_type != C.CASE_TYPE_PEDIDO:
            raise ValueError(
                f"Solo los pedidos requieren validación documental para compulsa (caso id={case.id})."
            )

        active_raw = DocumentRepository.get_active_types_for_case(db, case.id)
        active: set[str] = {normalize_doc_type(dt) for dt in active_raw}

        if C.DOC_AUTORIZACION_REFI in active:
            required = (C.DOC_AUTORIZACION_REFI, C.DOC_ORDEN_SNTE_PDF)
            missing = [dt for dt in required if dt not in active]
            if missing:
                labels = ", ".join(doc_type_label(dt) for dt in missing)
                msg = (
                    "No se puede pasar a compulsa: faltan documentos de refinanciamiento activos "
                    f"({labels})."
                )
                log.warning(
                    "Validación compulsa (refinanciamiento) fallida",
                    extra={"case_id": case.id, "missing": missing, "active": sorted(active)},
                )
                raise ValueError(msg)
            log.info(
                "Validación compulsa (refinanciamiento) OK",
                extra={"case_id": case.id},
            )
            return

        if not case.order_type:
            log.warning(
                "Validación compulsa fallida: pedido sin order_type",
                extra={"case_id": case.id},
            )
            raise ValueError(
                "No se puede pasar a compulsa: el pedido no tiene tipo (mueble/préstamo) definido."
            )

        required_list: list[str] = [
            C.DOC_PEDIDO,
            C.DOC_ORDEN_DESCUENTO,
            C.DOC_AUTORIZACION_SNTE,
        ]
        if case.order_type == C.ORDER_TYPE_PRESTAMO:
            required_list.append(C.DOC_CARATULA_BANCARIA)
        elif case.order_type != C.ORDER_TYPE_MUEBLE:
            log.warning(
                "Validación compulsa: order_type no reconocido",
                extra={"case_id": case.id, "order_type": case.order_type},
            )
            raise ValueError(
                f"No se puede pasar a compulsa: tipo de pedido no reconocido ({case.order_type!r})."
            )

        missing = [dt for dt in required_list if dt not in active]
        if missing:
            labels = ", ".join(doc_type_label(dt) for dt in missing)
            msg = (
                "No se puede pasar a compulsa: faltan documentos activos obligatorios "
                f"({labels})."
            )
            log.warning(
                "Validación compulsa (mueble/préstamo) fallida",
                extra={
                    "case_id": case.id,
                    "order_type": case.order_type,
                    "missing": missing,
                    "active": sorted(active),
                },
            )
            raise ValueError(msg)
        log.info(
            "Validación compulsa (mueble/préstamo) OK",
            extra={"case_id": case.id, "order_type": case.order_type},
        )
