"""Herramientas de recuperación operativa seguras (P33)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging_setup import log_ops_action, set_ops_log_context
from app.models.import_batch import STATUS_FAILED, STATUS_PREVIEWED, STATUS_UPLOADED
from app.models.ops_incident import STATUS_ACKNOWLEDGED, STATUS_RESOLVED, OpsIncident
from app.models.sale_capture import SaleCapture
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.bi_dashboard_service import BiDashboardService
from app.services.case_document_service import CaseDocumentService
from app.services.case_event_service import CHECKLIST_COMPLETE, CHECKLIST_INCOMPLETE, log_event
from app.services.commission_service import CommissionService, CommissionServiceError
from app.services.erp_reconciliation_service import ErpReconciliationService
from app.services.excel_import_service import ExcelImportService
from app.services.excel_path_guard import assert_not_excel_master_path, is_under_excel_masters
from app.services.registration_queue_service import RegistrationQueueService
from app.services.sales_reconciliation_service import build_reconciliation_report
from app.services.sharepoint_sync_service import SharePointSyncService
from app.services.workflow_transition_service import recalculate_case_workflow_state

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryResult:
    ok: bool
    message: str
    details: dict[str, Any]

    @property
    def user_message(self) -> str:
        return self.message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _audit_incident(inc: OpsIncident, entry: dict[str, Any]) -> None:
    trail = list((inc.details_json or {}).get("audit") or [])
    trail.append(entry)
    inc.details_json = {**(inc.details_json or {}), "audit": trail}


class OpsRecoveryService:
    def retry_sharepoint(
        self,
        db: Session,
        *,
        case_id: int | None = None,
        document_id: int | None = None,
        username: str | None = None,
        user_id: int | None = None,
        limit: int = 25,
    ) -> RecoveryResult:
        set_ops_log_context(entity_type="sharepoint", entity_id=case_id or document_id, action="retry_sharepoint")
        t0 = time.perf_counter()
        sync = SharePointSyncService()
        try:
            if document_id:
                result = sync.sync_document(
                    db,
                    document_id,
                    actor_user_id=user_id,
                    actor_role=None,
                    is_retry=True,
                )
                results = [result]
            elif case_id:
                results = sync.retry_failed_for_case(
                    db,
                    case_id,
                    actor_user_id=user_id,
                )
            else:
                results = sync.retry_all_failed(
                    db,
                    limit=limit,
                    actor_user_id=user_id,
                )
            ok_n = sum(1 for r in results if r.ok)
            msg = f"SharePoint: {ok_n}/{len(results)} sincronizaciones OK"
            log_ops_action(
                log,
                logging.INFO,
                msg,
                action="retry_sharepoint",
                entity_type="case" if case_id else "document",
                entity_id=case_id or document_id,
                result="ok" if ok_n else "partial",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                ok_count=ok_n,
                total=len(results),
            )
            result = RecoveryResult(
                ok=ok_n > 0,
                message=msg,
                details={"results": [{"id": r.document_id, "ok": r.ok, "error": r.error} for r in results]},
            )
            try:
                from app.services.platform_cohesion_service import safe_cohesion_emit

                safe_cohesion_emit(
                    db,
                    action="recovery_sharepoint_retry",
                    title=msg,
                    entity_type="case" if case_id else "document",
                    entity_id=case_id or document_id,
                    actor_label=username,
                    source="recovery",
                    tone="warn" if not result.ok else "info",
                    href="/ops/recovery",
                )
            except Exception:
                pass
            return result
        except Exception as exc:
            log_ops_action(
                log,
                logging.ERROR,
                str(exc),
                action="retry_sharepoint",
                result="error",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
            return RecoveryResult(ok=False, message=str(exc), details={})

    def rebuild_conciliation(self, db: Session, *, username: str | None = None) -> RecoveryResult:
        set_ops_log_context(action="rebuild_conciliation")
        t0 = time.perf_counter()
        try:
            sales_report = build_reconciliation_report(db)
            erp_report = ErpReconciliationService().build_report(db)
            BiDashboardService().clear_cache()
            msg = (
                f"Conciliación recalculada: ventas {sales_report['issue_count']} incidencias, "
                f"ERP {len(erp_report.issues)} incidencias"
            )
            log_ops_action(
                log,
                logging.INFO,
                msg,
                action="rebuild_conciliation",
                result="ok",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
            return RecoveryResult(
                ok=True,
                message=msg,
                details={
                    "sales": {
                        "total": sales_report["total_sales"],
                        "issues": sales_report["issue_count"],
                    },
                    "erp_issues": len(erp_report.issues),
                    "username": username,
                },
            )
        except Exception as exc:
            log_ops_action(log, logging.ERROR, str(exc), action="rebuild_conciliation", result="error")
            return RecoveryResult(ok=False, message=str(exc), details={})

    def recalculate_commissions(
        self,
        db: Session,
        *,
        sale_capture_id: int | None = None,
        username: str | None = None,
        user: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> RecoveryResult:
        set_ops_log_context(entity_type="sale_capture", entity_id=sale_capture_id, action="recalculate_commissions")
        t0 = time.perf_counter()
        svc = CommissionService()
        user_payload = user or {"username": username, "rol": "sistemas"}
        ok = err = 0
        errors: list[str] = []

        if sale_capture_id:
            sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
            if not sale:
                return RecoveryResult(ok=False, message="Venta no encontrada", details={})
            sales = [sale]
        else:
            from sqlalchemy import select

            from app.models.commission import Commission
            from app.models.sale_capture import REG_STATUS_REGISTERED

            sales = list(
                db.scalars(
                    select(SaleCapture)
                    .outerjoin(Commission, Commission.sale_capture_id == SaleCapture.id)
                    .where(
                        SaleCapture.registration_status == REG_STATUS_REGISTERED,
                        Commission.id.is_(None),
                    )
                    .limit(limit)
                ).all()
            )

        for sale in sales:
            try:
                svc.generate_commission(db, sale, user_payload, force_update_pending=True)
                ok += 1
            except CommissionServiceError as exc:
                err += 1
                errors.append(f"{sale.folio}: {exc}")
            except Exception as exc:
                err += 1
                errors.append(f"{sale.folio}: {exc}")

        msg = f"Comisiones: {ok} generadas/actualizadas, {err} errores"
        log_ops_action(
            log,
            logging.INFO,
            msg,
            action="recalculate_commissions",
            result="ok" if ok else "partial",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
        return RecoveryResult(
            ok=ok > 0,
            message=msg,
            details={"ok": ok, "errors": errors[:10]},
        )

    def regenerate_sale_export(
        self,
        db: Session,
        sale_capture_id: int,
        *,
        user: dict[str, Any],
    ) -> RecoveryResult:
        set_ops_log_context(entity_type="sale_capture", entity_id=sale_capture_id, action="regenerate_export")
        t0 = time.perf_counter()
        sale = SaleCaptureRepository.get_by_id(db, sale_capture_id)
        if not sale:
            return RecoveryResult(ok=False, message="Captura no encontrada", details={})

        if sale.ventas_export_path:
            try:
                assert_not_excel_master_path(sale.ventas_export_path)
            except ValueError as exc:
                return RecoveryResult(ok=False, message=str(exc), details={})
            if is_under_excel_masters(sale.ventas_export_path):
                return RecoveryResult(
                    ok=False,
                    message="Ruta de export apunta a maestro; operación abortada",
                    details={},
                )

        try:
            updated, err = RegistrationQueueService().retry_sale_capture_registration(
                db, sale_capture_id, user
            )
            if err:
                return RecoveryResult(ok=False, message=err, details={"sale_id": sale_capture_id})
            path = updated.ventas_export_path if updated else None
            if path:
                assert_not_excel_master_path(path)
            msg = f"Export regenerado para {sale.folio}"
            log_ops_action(
                log,
                logging.INFO,
                msg,
                action="regenerate_export",
                entity_type="sale_capture",
                entity_id=sale_capture_id,
                result="ok",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                ventas_path=path,
            )
            return RecoveryResult(
                ok=True,
                message=msg,
                details={
                    "ventas_export_path": path,
                    "contratos_export_path": updated.contratos_export_path if updated else None,
                },
            )
        except Exception as exc:
            log_ops_action(
                log,
                logging.ERROR,
                str(exc),
                action="regenerate_export",
                entity_type="sale_capture",
                entity_id=sale_capture_id,
                result="error",
            )
            return RecoveryResult(ok=False, message=str(exc), details={})

    def revalidate_document_checklist(
        self,
        db: Session,
        case_id: int,
        *,
        user: dict[str, Any],
    ) -> RecoveryResult:
        set_ops_log_context(entity_type="case", entity_id=case_id, action="revalidate_checklist")
        t0 = time.perf_counter()
        from app.models.case import Case

        case = db.get(Case, case_id)
        if not case:
            return RecoveryResult(ok=False, message="Caso no encontrado", details={})

        doc_svc = CaseDocumentService()
        checklist = doc_svc.build_checklist(db, case)
        summary = doc_svc.summarize(db, case)
        complete = all(i.valid for i in checklist if i.required) and summary.missing == 0
        event_type = CHECKLIST_COMPLETE if complete else CHECKLIST_INCOMPLETE
        log_event(
            db,
            case_id=case.id,
            event_type=event_type,
            message="Checklist revalidado desde panel ops",
            actor_user_id=user.get("id"),
            actor_role=user.get("rol"),
            source="ops",
            metadata={"missing": summary.missing, "invalid": summary.invalid},
        )
        try:
            recalculate_case_workflow_state(db, case.id, user, apply=True)
        except Exception:
            log.exception("Workflow recalc tras checklist case_id=%s", case_id)

        msg = f"Checklist: {summary.complete} válidos, {summary.missing} faltantes, {summary.invalid} inválidos"
        log_ops_action(
            log,
            logging.INFO,
            msg,
            action="revalidate_checklist",
            entity_type="case",
            entity_id=case_id,
            result="ok",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
        return RecoveryResult(ok=True, message=msg, details={"complete": complete, "summary": summary.__dict__})

    def retry_failed_import(
        self,
        db: Session,
        batch_id: int,
        *,
        username: str | None = None,
    ) -> RecoveryResult:
        set_ops_log_context(entity_type="import_batch", entity_id=batch_id, action="retry_import")
        t0 = time.perf_counter()
        from app.models.import_batch import ImportBatch

        batch = db.get(ImportBatch, batch_id)
        if not batch:
            return RecoveryResult(ok=False, message="Lote no encontrado", details={})
        if batch.status not in (STATUS_FAILED, STATUS_UPLOADED, STATUS_PREVIEWED):
            return RecoveryResult(
                ok=False,
                message=f"Estado {batch.status} no admite reintento automático",
                details={},
            )
        try:
            updated = ExcelImportService().preview_batch(db, batch_id, username=username)
            ok = updated.status != STATUS_FAILED
            msg = f"Import preview: estado {updated.status}"
            log_ops_action(
                log,
                logging.INFO,
                msg,
                action="retry_import",
                entity_type="import_batch",
                entity_id=batch_id,
                result="ok" if ok else "failed",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
            return RecoveryResult(
                ok=ok,
                message=msg,
                details={"status": updated.status, "ready_count": updated.ready_count},
            )
        except Exception as exc:
            return RecoveryResult(ok=False, message=str(exc), details={})

    def acknowledge_incident(
        self,
        db: Session,
        incident_id: int,
        *,
        username: str | None = None,
    ) -> OpsIncident | None:
        inc = db.get(OpsIncident, incident_id)
        if not inc:
            return None
        inc.status = STATUS_ACKNOWLEDGED
        _audit_incident(
            inc,
            {"at": _utcnow().isoformat(), "action": "ack", "by": username},
        )
        db.flush()
        return inc

    def resolve_incident(
        self,
        db: Session,
        incident_id: int,
        *,
        username: str | None = None,
    ) -> OpsIncident | None:
        inc = db.get(OpsIncident, incident_id)
        if not inc:
            return None
        inc.status = STATUS_RESOLVED
        inc.resolved_at = _utcnow()
        inc.resolved_by = username
        _audit_incident(
            inc,
            {"at": inc.resolved_at.isoformat(), "action": "resolve", "by": username},
        )
        db.flush()
        return inc
