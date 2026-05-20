"""Cola segura de registro Excel para capturas de venta (P20)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.sale_capture import (
    REG_STATUS_PENDING_REGISTRATION,
    REG_STATUS_PROCESSING_REGISTRATION,
    REG_STATUS_REGISTERED,
    REG_STATUS_REGISTRATION_FAILED,
    SaleCapture,
    sync_legacy_status_from_registration,
)
from app.models.user import UserRole
from app.repositories.case_repository import CaseRepository
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.case_event_service import (
    SALE_CAPTURE_EXPORT_FAILED,
    SALE_CAPTURE_PROCESSING,
    SALE_CAPTURE_REGISTERED,
    SALE_CAPTURE_REGISTRATION_FAILED,
    SALE_CAPTURE_REGISTRATION_QUEUED,
    SALE_CAPTURE_RETRY_REQUESTED,
    SALE_CAPTURE_VALIDATED,
    log_event,
)
from app.services.commission_service import CommissionService
from app.services.excel_registry_service import ExcelRegistryError, ExcelRegistryService

log = logging.getLogger(__name__)

_ROLES_REGISTER = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
        UserRole.AUTORIZACION.value,
    }
)


class RegistrationQueueError(Exception):
    pass


def _log_sale_event(
    db: Session,
    sale: SaleCapture,
    event_type: str,
    message: str,
    user: dict[str, Any],
    *,
    metadata: dict | None = None,
) -> None:
    if not sale.case_id:
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


def mark_processing(db: Session, sale: SaleCapture) -> None:
    sale.registration_status = REG_STATUS_PROCESSING_REGISTRATION
    sale.registration_attempts = (sale.registration_attempts or 0) + 1
    sale.last_registration_attempt_at = datetime.now(timezone.utc)
    sync_legacy_status_from_registration(sale)
    SaleCaptureRepository.save(db, sale)


def mark_registered(
    db: Session,
    sale: SaleCapture,
    result: dict[str, Any],
    user: dict[str, Any],
) -> None:
    sale.registration_status = REG_STATUS_REGISTERED
    sale.registration_error = None
    sale.export_error = None
    sale.registered_at = datetime.now(timezone.utc)
    sale.ventas_export_path = result.get("ventas_path")
    sale.contratos_export_path = result.get("contratos_path")
    sale.ventas_excel_row = result.get("ventas_row")
    sale.contratos_excel_row = result.get("contratos_row")
    sale.contratos_sheet = result.get("contratos_sheet")
    if user.get("rol") in _ROLES_REGISTER:
        sale.validated_by_user_id = user.get("id")
    sync_legacy_status_from_registration(sale)
    SaleCaptureRepository.save(db, sale)


def mark_failed(db: Session, sale: SaleCapture, error_message: str) -> None:
    sale.registration_status = REG_STATUS_REGISTRATION_FAILED
    sale.registration_error = error_message
    sale.export_error = error_message
    sale.registered_at = None
    sync_legacy_status_from_registration(sale)
    SaleCaptureRepository.save(db, sale)


class RegistrationQueueService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.excel = ExcelRegistryService()

    def enqueue_sale_capture(
        self,
        db: Session,
        sale_capture_id: int,
        user: dict[str, Any],
    ) -> SaleCapture:
        sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
        if not sale:
            raise RegistrationQueueError("Captura no encontrada.")
        if sale.registration_status == REG_STATUS_REGISTERED:
            raise RegistrationQueueError("La venta ya está registrada.")

        sale.registration_status = REG_STATUS_PENDING_REGISTRATION
        sale.registration_error = None
        sync_legacy_status_from_registration(sale)
        SaleCaptureRepository.save(db, sale)
        _log_sale_event(
            db,
            sale,
            SALE_CAPTURE_REGISTRATION_QUEUED,
            f"Venta {sale.folio} en cola de registro Excel",
            user,
        )
        return sale

    def process_sale_capture_registration(
        self,
        db: Session,
        sale_capture_id: int,
        user: dict[str, Any],
    ) -> tuple[SaleCapture, dict[str, Any] | None, str | None]:
        """
        Procesa registro Excel. Retorna (sale, result, error_message).
        """
        sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
        if not sale:
            raise RegistrationQueueError("Captura no encontrada.")

        if sale.registration_status == REG_STATUS_REGISTERED:
            return sale, None, None

        if sale.registration_status not in (
            REG_STATUS_PENDING_REGISTRATION,
            REG_STATUS_PROCESSING_REGISTRATION,
            REG_STATUS_REGISTRATION_FAILED,
        ):
            sale.registration_status = REG_STATUS_PENDING_REGISTRATION
            sync_legacy_status_from_registration(sale)

        mark_processing(db, sale)
        _log_sale_event(
            db,
            sale,
            SALE_CAPTURE_PROCESSING,
            f"Procesando registro Excel (intento {sale.registration_attempts})",
            user,
            metadata={"attempt": sale.registration_attempts},
        )

        semana = sale.semana or self.settings.effective_semana_activa
        try:
            op_v, op_c = self.excel.prepare_operation_workbooks(sale)
            result = self.excel.append_sale_to_workbooks(
                sale,
                ventas_path=op_v,
                contratos_path=op_c,
                semana=semana,
                use_daily_base=True,
            )
        except ExcelRegistryError as exc:
            msg = str(exc)
            mark_failed(db, sale, msg)
            _log_sale_event(
                db,
                sale,
                SALE_CAPTURE_REGISTRATION_FAILED,
                msg,
                user,
                metadata={"error": msg, "code": getattr(exc, "code", None)},
            )
            _log_sale_event(db, sale, SALE_CAPTURE_EXPORT_FAILED, msg, user)
            return sale, None, msg

        mark_registered(db, sale, result, user)
        _log_sale_event(
            db,
            sale,
            SALE_CAPTURE_REGISTERED,
            f"Venta {sale.folio} registrada en Excel (V:{sale.ventas_excel_row})",
            user,
            metadata=result,
        )
        if sale.validated_by_user_id:
            _log_sale_event(db, sale, SALE_CAPTURE_VALIDATED, "Venta validada", user)
        CommissionService().ensure_commission_for_registered_sale(db, sale, user)
        if sale.case_id:
            try:
                from app.services.workflow_transition_service import (
                    recalculate_case_workflow_state,
                )

                recalculate_case_workflow_state(db, sale.case_id, user, apply=True)
            except Exception:
                log.exception("Recálculo workflow post-registro falló case_id=%s", sale.case_id)
        return sale, result, None

    def retry_sale_capture_registration(
        self,
        db: Session,
        sale_capture_id: int,
        user: dict[str, Any],
    ) -> tuple[SaleCapture | None, str | None]:
        sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
        if not sale:
            raise RegistrationQueueError("Captura no encontrada.")
        from app.models.sale_capture import can_retry_registration

        if not can_retry_registration(sale):
            raise RegistrationQueueError(
                "Solo se puede reintentar ventas con error de registro o en cola fallida."
            )

        _log_sale_event(
            db,
            sale,
            SALE_CAPTURE_RETRY_REQUESTED,
            f"Reintento de registro solicitado (intento previo: {sale.registration_attempts})",
            user,
        )
        sale.registration_status = REG_STATUS_PENDING_REGISTRATION
        sale.registration_error = None
        sync_legacy_status_from_registration(sale)
        SaleCaptureRepository.save(db, sale)

        updated, _, err = self.process_sale_capture_registration(db, sale_capture_id, user)
        return updated, err
