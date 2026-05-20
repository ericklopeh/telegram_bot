"""Orquestación de captura de ventas, casos y exportación Excel (P19 / P19.1)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.models.sale_capture import (
    REG_STATUS_PENDING_VALIDATION,
    SALE_STATUS_DRAFT,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_PENDING_VALIDATION,
    SALE_STATUS_REGISTERED,
    SaleCapture,
    is_registration_complete,
    sync_legacy_status_from_registration,
)
from app.models.user import UserRole
from app.repositories.case_repository import CaseRepository
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.case_event_service import (
    SALE_CAPTURE_DRAFT,
    SALE_CAPTURE_DUPLICATE_DETECTED,
    SALE_CAPTURE_EDITED,
    SALE_CAPTURE_REGISTER_BLOCKED,
    log_event,
)
from app.services.case_service import CaseService
from app.services.excel_registry_service import ExcelRegistryService
from app.services.registration_queue_service import RegistrationQueueService
from app.services.sale_action_guard_service import (
    assert_action,
    get_sale_action_permissions,
)
from app.services.sale_capture_checklist import build_sale_checklist
from app.services.sale_capture_duplicate import check_duplicates
from app.services.sale_capture_validation import parse_sale_form

log = logging.getLogger(__name__)

_ROLES_VALIDATE = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
        UserRole.AUTORIZACION.value,
    }
)


class SaleCaptureService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.excel = ExcelRegistryService()
        self.case_svc = CaseService(self.settings)

    def permissions(
        self,
        db: Session,
        user: dict[str, Any],
        sale: SaleCapture | None,
        *,
        form: dict[str, Any] | None = None,
    ):
        return get_sale_action_permissions(db, user, sale, form=form)

    def checklist(self, db: Session, sale: SaleCapture | None):
        return build_sale_checklist(db, sale)

    def can_edit_sale(self, db: Session, sale: SaleCapture, user: dict[str, Any]) -> bool:
        ok, _ = assert_action(db, user, sale, "edit")
        return ok

    def can_validate(self, user: dict[str, Any]) -> bool:
        return user.get("rol") in _ROLES_VALIDATE or bool(self.settings.web_rbac_relaxed)

    def can_register(self, db: Session, sale: SaleCapture | None, user: dict[str, Any]) -> bool:
        perms = get_sale_action_permissions(db, user, sale)
        return perms.can_register_definitive

    def suggest_folio(self, db: Session) -> str:
        daily_v, _ = self.excel.prepare_daily_workbooks()
        from_excel = self.excel.suggest_next_folio_from_copy(daily_v)
        from_db = int(SaleCaptureRepository.next_suggested_folio(db))
        return f"{max(from_excel, from_db):05d}"

    def apply_form_to_model(self, sale: SaleCapture, data: dict[str, Any]) -> None:
        for key, value in data.items():
            if key == "sale_date" and value is not None:
                sale.sale_date = value
            elif hasattr(sale, key):
                setattr(sale, key, value)

    def _ensure_case_id_on_form(self, form: dict[str, Any], sale: SaleCapture) -> None:
        cid = form.get("case_id") or form.get("linked_case_id")
        if cid and str(cid).strip().isdigit():
            sale.case_id = int(cid)

    def save_draft(
        self,
        db: Session,
        user: dict[str, Any],
        form: dict[str, Any],
        *,
        sale_id: int | None = None,
        linked_case_id: int | None = None,
    ) -> tuple[SaleCapture | None, list[str]]:
        sale_for_perm = (
            SaleCaptureRepository.get_by_id(db, sale_id) if sale_id else None
        )
        ok, reason = assert_action(db, user, sale_for_perm, "save_draft", form=form)
        if not ok:
            return None, [reason or "Acción no permitida."]

        data, errors = parse_sale_form(form)
        if errors:
            return None, errors

        dup = check_duplicates(
            db,
            data,
            sale_id=sale_id,
            case_id=linked_case_id or (int(form["case_id"]) if str(form.get("case_id", "")).isdigit() else None),
        )
        if dup.blocked:
            self._log_blocked(db, user, sale_id, dup.block_reason, data, dup)
            return None, [dup.block_reason or "Duplicado detectado."]

        warnings = dup.warnings

        if sale_id:
            sale = SaleCaptureRepository.get_by_id(db, sale_id)
            if not sale:
                return None, ["Captura no encontrada."]
            ok, reason = assert_action(db, user, sale, "save_draft", form=form)
            if not ok:
                return None, [reason or "No puedes editar esta captura."]
            was_registered = sale.status == SALE_STATUS_REGISTERED
            self.apply_form_to_model(sale, data)
            if was_registered and user.get("rol") in (UserRole.ADMIN.value, UserRole.SISTEMAS.value):
                pass
            else:
                sale.status = SALE_STATUS_DRAFT
                sale.export_error = None
            self._ensure_case_id_on_form(form, sale)
            if linked_case_id:
                sale.case_id = linked_case_id
            self._log_sale_event(db, sale, SALE_CAPTURE_EDITED, "Captura de venta editada", user)
        else:
            semana = data.get("semana") or self.settings.effective_semana_activa
            sale = SaleCapture(
                status=SALE_STATUS_DRAFT,
                folio=data["folio"],
                sale_date=data["sale_date"],
                vendedor=data["vendedor"],
                seccion=data.get("seccion"),
                qna=data.get("qna"),
                cliente=data["cliente"],
                rfc=data.get("rfc"),
                codigo=data.get("codigo"),
                producto=data.get("producto"),
                tipo_venta=data.get("tipo_venta"),
                plazo=data.get("plazo"),
                costo=data.get("costo"),
                venta=data.get("venta"),
                venta_refinanciamiento=data.get("venta_refinanciamiento"),
                total_venta=data.get("total_venta"),
                precio_comision=data.get("precio_comision"),
                venta_sin_agregado=data.get("venta_sin_agregado"),
                recuperacion=data.get("recuperacion"),
                tipo_cotizacion=data.get("tipo_cotizacion"),
                observaciones=data.get("observaciones"),
                semana=semana,
                created_by_user_id=user.get("id"),
                case_id=linked_case_id,
            )
            if str(form.get("case_id", "")).isdigit():
                sale.case_id = int(form["case_id"])
            SaleCaptureRepository.create(db, sale)

        if sale.case_id:
            self._log_sale_event(db, sale, SALE_CAPTURE_DRAFT, "Borrador de venta guardado", user)

        if warnings:
            self._log_sale_event(
                db,
                sale,
                SALE_CAPTURE_DUPLICATE_DETECTED,
                "; ".join(warnings),
                user,
                metadata={"probable": dup.probable_matches},
            )
            return sale, warnings
        return sale, []

    def submit_for_validation(
        self,
        db: Session,
        user: dict[str, Any],
        form: dict[str, Any],
        *,
        sale_id: int | None = None,
        linked_case_id: int | None = None,
    ) -> tuple[SaleCapture | None, list[str]]:
        sale, errors = self.save_draft(
            db, user, form, sale_id=sale_id, linked_case_id=linked_case_id
        )
        if errors and not sale:
            return sale, errors
        if not sale:
            return None, ["No se pudo guardar la captura."]

        ok, reason = assert_action(db, user, sale, "submit_validation", form=form)
        if not ok:
            return None, [reason or "No puedes enviar a validación."]

        sale.status = SALE_STATUS_PENDING_VALIDATION
        sale.export_error = None
        if linked_case_id:
            sale.case_id = linked_case_id
        elif str(form.get("case_id", "")).isdigit():
            sale.case_id = int(form["case_id"])
        case = self._ensure_case(db, sale, user)
        sale.case_id = case.id
        self._log_sale_event(db, sale, SALE_CAPTURE_DRAFT, "Venta enviada a validación", user)
        return sale, errors

    def register_definitive(
        self,
        db: Session,
        user: dict[str, Any],
        form: dict[str, Any],
        *,
        sale_id: int | None = None,
        linked_case_id: int | None = None,
        confirm_probable_duplicate: bool = False,
    ) -> tuple[SaleCapture | None, list[str]]:
        existing = SaleCaptureRepository.get_by_id(db, sale_id) if sale_id else None
        ok, reason = assert_action(db, user, existing, "register", form=form)
        if not ok:
            if existing and existing.case_id:
                self._log_sale_event(
                    db,
                    existing,
                    SALE_CAPTURE_REGISTER_BLOCKED,
                    reason or "Registro bloqueado",
                    user,
                )
            return None, [reason or "No puedes registrar definitivo."]

        data, errors = parse_sale_form(form)
        if errors:
            return None, errors

        case_id_hint = linked_case_id
        if str(form.get("case_id", "")).isdigit():
            case_id_hint = int(form["case_id"])
        elif existing and existing.case_id:
            case_id_hint = existing.case_id

        dup = check_duplicates(db, data, sale_id=sale_id, case_id=case_id_hint)
        if dup.blocked:
            self._log_blocked(db, user, sale_id, dup.block_reason, data, dup, existing)
            return None, [dup.block_reason or "Duplicado bloqueado."]
        if dup.warnings and not confirm_probable_duplicate:
            if existing and existing.case_id:
                self._log_sale_event(
                    db,
                    existing,
                    SALE_CAPTURE_DUPLICATE_DETECTED,
                    "; ".join(dup.warnings),
                    user,
                    metadata={"probable": dup.probable_matches, "requires_confirm": True},
                )
            return None, dup.warnings + [
                "Marque la confirmación de duplicado probable para continuar."
            ]

        if SaleCaptureRepository.folio_taken(db, data["folio"], exclude_id=sale_id):
            msg = f"El folio {data['folio']} ya existe."
            self._log_blocked(db, user, sale_id, msg, data, dup, existing)
            return None, [msg]

        daily_v, _ = self.excel.prepare_daily_workbooks()
        if self.excel.folio_exists_in_ventas_copy(daily_v, data["folio"]):
            msg = f"El folio {data['folio']} ya existe en el Excel de ventas (copia diaria)."
            self._log_blocked(db, user, sale_id, msg, data, dup, existing)
            return None, [msg]

        if sale_id:
            sale = existing
            if not sale:
                return None, ["Captura no encontrada."]
            if is_registration_complete(sale):
                return None, ["La venta ya fue registrada."]
            self.apply_form_to_model(sale, data)
            self._ensure_case_id_on_form(form, sale)
        else:
            semana = data.get("semana") or self.settings.effective_semana_activa
            sale = SaleCapture(
                status=SALE_STATUS_PENDING_VALIDATION,
                registration_status=REG_STATUS_PENDING_VALIDATION,
                folio=data["folio"],
                sale_date=data["sale_date"],
                vendedor=data["vendedor"],
                seccion=data.get("seccion"),
                qna=data.get("qna"),
                cliente=data["cliente"],
                rfc=data.get("rfc"),
                codigo=data.get("codigo"),
                producto=data.get("producto"),
                tipo_venta=data.get("tipo_venta"),
                plazo=data.get("plazo"),
                costo=data.get("costo"),
                venta=data.get("venta"),
                venta_refinanciamiento=data.get("venta_refinanciamiento"),
                total_venta=data.get("total_venta"),
                precio_comision=data.get("precio_comision"),
                venta_sin_agregado=data.get("venta_sin_agregado"),
                recuperacion=data.get("recuperacion"),
                tipo_cotizacion=data.get("tipo_cotizacion"),
                observaciones=data.get("observaciones"),
                semana=semana,
                created_by_user_id=user.get("id"),
                case_id=case_id_hint,
            )
            SaleCaptureRepository.create(db, sale)
            db.flush()

        case = self._ensure_case(db, sale, user)
        sale.case_id = case.id
        if case.official_folio != sale.folio:
            case.official_folio = sale.folio
            CaseRepository.save(db, case)

        sync_legacy_status_from_registration(sale)
        SaleCaptureRepository.save(db, sale)

        queue = RegistrationQueueService()
        queue.enqueue_sale_capture(db, sale.id, user)
        sale, _result, err = queue.process_sale_capture_registration(db, sale.id, user)
        if err:
            return None, [err]
        return sale, dup.warnings

    def retry_registration(
        self,
        db: Session,
        user: dict[str, Any],
        sale_id: int,
    ) -> tuple[SaleCapture | None, list[str]]:
        sale = SaleCaptureRepository.get_by_id(db, sale_id)
        if not sale:
            return None, ["Captura no encontrada."]
        role = user.get("rol")
        if role not in _ROLES_VALIDATE and not self.settings.web_rbac_relaxed:
            return None, ["Solo autorización, admin o sistemas puede reintentar el registro."]
        from app.models.sale_capture import can_retry_registration

        if not can_retry_registration(sale):
            return None, [
                "Solo se puede reintentar ventas con error de registro o exportación fallida."
            ]
        queue = RegistrationQueueService()
        try:
            updated, err = queue.retry_sale_capture_registration(db, sale_id, user)
        except Exception as exc:
            return None, [str(exc)]
        if err:
            return updated, [err]
        return updated, []

    def _log_blocked(
        self,
        db: Session,
        user: dict[str, Any],
        sale_id: int | None,
        reason: str | None,
        data: dict,
        dup,
        existing: SaleCapture | None = None,
    ) -> None:
        sale = existing or (SaleCaptureRepository.get_by_id(db, sale_id) if sale_id else None)
        if sale and sale.case_id:
            self._log_sale_event(
                db,
                sale,
                SALE_CAPTURE_REGISTER_BLOCKED,
                reason or "Registro bloqueado",
                user,
                metadata={"duplicate": dup.strong_matches},
            )
        if dup.probable_matches or dup.strong_matches:
            if sale and sale.case_id:
                self._log_sale_event(
                    db,
                    sale,
                    SALE_CAPTURE_DUPLICATE_DETECTED,
                    reason or "Duplicado",
                    user,
                    metadata={"strong": dup.strong_matches, "probable": dup.probable_matches},
                )

    def _ensure_case(self, db: Session, sale: SaleCapture, user: dict[str, Any]) -> Any:
        from app.models.case import Case

        if sale.case_id:
            case = CaseRepository.get_by_id(db, sale.case_id)
            if case:
                return case

        order_type = C.ORDER_TYPE_MUEBLE
        tc = (sale.tipo_cotizacion or "").upper()
        if tc == "DINERO":
            order_type = C.ORDER_TYPE_PRESTAMO
        elif "PRESTAMO" in (sale.tipo_venta or "").upper():
            order_type = C.ORDER_TYPE_PRESTAMO

        folio = sale.folio
        public_id = f"PED-{folio}"
        existing = CaseRepository.get_by_public_id(db, public_id)
        if existing:
            return existing

        root = self.case_svc._pedido_root(folio, sale.cliente)
        self.case_svc.storage.ensure_dir(root / "EVIDENCIAS")
        self.case_svc.storage.ensure_dir(root / "AUTORIZACION")

        case = Case(
            public_id=public_id,
            case_type=C.CASE_TYPE_PEDIDO,
            order_type=order_type,
            client_name=sale.cliente,
            temp_folio=None,
            official_folio=folio,
            current_status=C.ST_PED_RECIBIDO,
            workflow_state="PEDIDO_RECIBIDO",
            visible_status=C.visible_status_for_pedido(C.ST_PED_RECIBIDO),
            seller_name=sale.vendedor,
            seller_telegram_chat_id=None,
            week_code=sale.semana or self.settings.effective_semana_activa,
            folder_path=str(root),
        )
        CaseRepository.create(db, case)
        from app.services.case_event_service import log_case_created

        log_case_created(
            db,
            case_id=case.id,
            case_type=C.CASE_TYPE_PEDIDO,
            client_name=sale.cliente,
            actor_role=user.get("rol"),
            source="web",
            metadata={"official_folio": folio, "sale_capture_id": sale.id},
        )
        return case

    def _log_sale_event(
        self,
        db: Session,
        sale: SaleCapture | None,
        event_type: str,
        message: str,
        user: dict[str, Any],
        *,
        metadata: dict | None = None,
    ) -> None:
        if not sale or not sale.case_id:
            return
        log_event(
            db,
            case_id=sale.case_id,
            event_type=event_type,
            message=message,
            actor_user_id=user.get("id"),
            actor_role=user.get("rol"),
            source="web",
            metadata=metadata,
        )
