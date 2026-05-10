from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain import constants as C
from app.domain.constants import checklist_lines
from app.models.case import Case
from app.repositories.case_repository import CaseRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.history_repository import HistoryRepository
from app.services.storage.local import LocalStorageBackend


class CaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = LocalStorageBackend()

    def _revision_root(self, folio_tmp: str, client_name: str) -> Path:
        base = Path(self.settings.effective_revisiones_path)
        return base / self.settings.effective_semana_activa / f"{folio_tmp} {client_name}"

    def _pedido_root(self, official_folio: str, client_name: str) -> Path:
        base = Path(self.settings.effective_pedidos_path)
        return base / self.settings.effective_semana_activa / f"{official_folio} {client_name}"

    def ensure_revision_directories(self, folio: str, client_name: str) -> tuple[Path, Path]:
        root = self._revision_root(folio, client_name)
        self.storage.ensure_dir(root / "EVIDENCIAS")
        self.storage.ensure_dir(root / "REVISION")
        return root, root / "EVIDENCIAS"

    def get_case_by_public_id(self, db: Session, public_id: str) -> Case | None:
        return CaseRepository.get_by_public_id(db, public_id)

    def create_revision_case(
        self,
        db: Session,
        client_name: str,
        seller_chat_id: int,
        seller_name: str | None,
        stored_filename: str,
        file_abs_path: str,
        original_filename: str | None,
        mime_type: str | None,
        *,
        folio: str | None = None,
    ) -> Case:
        if folio is None:
            folio = CaseRepository.next_revision_temp_folio(db)
        root = self._revision_root(folio, client_name)
        self.storage.ensure_dir(root / "EVIDENCIAS")
        self.storage.ensure_dir(root / "REVISION")
        evidencias = root / "EVIDENCIAS"

        case = Case(
            public_id=folio,
            case_type=C.CASE_TYPE_REVISION,
            order_type=None,
            client_name=client_name,
            temp_folio=folio,
            official_folio=None,
            current_status=C.ST_REV_EN_REVISION,
            visible_status=C.visible_status_for_revision(C.ST_REV_EN_REVISION),
            seller_name=seller_name,
            seller_telegram_chat_id=seller_chat_id,
            week_code=self.settings.effective_semana_activa,
            folder_path=str(root),
        )
        CaseRepository.create(db, case)
        HistoryRepository.append(
            db,
            case.id,
            None,
            C.ST_REV_EN_REVISION,
            notes="Revisión registrada",
        )
        DocumentRepository.add_version(
            db,
            case.id,
            C.DOC_REVISION_EVIDENCIA,
            stored_filename,
            file_abs_path,
            original_filename,
            mime_type,
        )
        return case

    def create_pedido_case_skeleton(
        self,
        db: Session,
        client_name: str,
        order_type: str,
        seller_chat_id: int,
        seller_name: str | None,
    ) -> Case:
        folio = CaseRepository.next_pedido_official_folio(db)
        public_id = f"PED-{folio}"
        root = self._pedido_root(folio, client_name)
        self.storage.ensure_dir(root / "EVIDENCIAS")
        self.storage.ensure_dir(root / "AUTORIZACION")

        case = Case(
            public_id=public_id,
            case_type=C.CASE_TYPE_PEDIDO,
            order_type=order_type,
            client_name=client_name,
            temp_folio=None,
            official_folio=folio,
            current_status=C.ST_PED_RECIBIDO,
            visible_status=C.visible_status_for_pedido(C.ST_PED_RECIBIDO),
            seller_name=seller_name,
            seller_telegram_chat_id=seller_chat_id,
            week_code=self.settings.effective_semana_activa,
            folder_path=str(root),
        )
        CaseRepository.create(db, case)
        HistoryRepository.append(
            db,
            case.id,
            None,
            C.ST_PED_RECIBIDO,
            notes="Pedido iniciado",
        )
        return case

    def register_pedido_document(
        self,
        db: Session,
        case: Case,
        document_type: str,
        stored_filename: str,
        file_abs_path: str,
        original_filename: str | None,
        mime_type: str | None,
    ):
        return DocumentRepository.add_version(
            db,
            case.id,
            document_type,
            stored_filename,
            file_abs_path,
            original_filename,
            mime_type,
        )

    def pedido_has_all_documents(self, db: Session, case: Case) -> bool:
        if not case.order_type:
            return False
        present = DocumentRepository.get_active_types_for_case(db, case.id)
        required = set(C.required_doc_types_for_order(case.order_type))
        return required.issubset(present)

    def get_pedido_checklist(self, db: Session, case: Case) -> str:
        present = DocumentRepository.get_active_types_for_case(db, case.id)
        return checklist_lines(case.order_type or "", present)

    def finalize_pedido_if_complete(self, db: Session, case: Case) -> tuple[bool, Case, str | None]:
        if not self.pedido_has_all_documents(db, case):
            return False, case, self.get_pedido_checklist(db, case)
        return True, self.finalize_pedido(db, case), None

    def finalize_pedido(self, db: Session, case: Case) -> Case:
        old = case.current_status
        case.current_status = C.ST_PED_PREP_AUT
        case.visible_status = C.visible_status_for_pedido(case.current_status)
        HistoryRepository.append(
            db,
            case.id,
            old,
            C.ST_PED_PREP_AUT,
            notes="Pedido completo, enviado a autorización",
        )
        CaseRepository.save(db, case)
        return case

    def group_action_requires_reason(self, action: str) -> str | None:
        reason_required = {
            "ped_rechazar": C.ST_PED_RECHAZADO,
            "ped_corregir": C.ST_PED_CORRECCION,
            "com_noprocede": C.ST_PED_RECHAZADO,
        }
        return reason_required.get(action)

    def group_action_transition(self, action: str) -> tuple[str, str] | None:
        action_map = {
            "ped_aprobar": (C.ST_PED_EN_COMPULSA, "Aprobado en pedidos"),
            "com_ok": (C.ST_PED_COMPULSA_OK, "Compulsa OK"),
            "com_pendiente": (C.ST_PED_PEND_COMPULSA, "Pendiente de compulsa"),
            "com_compra": (C.ST_PED_COMPRA, "Compra realizada"),
            "com_editar": (C.ST_PED_EN_COMPULSA, "Compulsa reabierta para edición"),
        }
        return action_map.get(action)

    def transition_pedido_status(self, db: Session, case: Case, new_status: str, notes: str | None = None) -> Case:
        old = case.current_status
        case.current_status = new_status
        case.visible_status = C.visible_status_for_pedido(new_status)
        HistoryRepository.append(db, case.id, old, new_status, notes=notes)
        CaseRepository.save(db, case)
        return case

    def transition_case_status(
        self,
        db: Session,
        case: Case,
        new_status: str,
        notes: str | None = None,
        action_user: str | None = None,
    ) -> Case:
        old = case.current_status
        case.current_status = new_status
        if case.case_type == C.CASE_TYPE_PEDIDO:
            case.visible_status = C.visible_status_for_pedido(new_status)
        else:
            case.visible_status = C.visible_status_for_revision(new_status)
        HistoryRepository.append(
            db,
            case.id,
            old,
            new_status,
            action_user=action_user,
            notes=notes,
        )
        CaseRepository.save(db, case)
        return case
