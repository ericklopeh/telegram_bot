"""Monitoreo operativo y sincronización de incidencias (P33)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session

from app.core.paths import EXCEL_EXPORTS_DIR, IMPORTS_DIR, STORAGE_DIR
from app.domain import constants as C
from app.models.case import Case
from app.models.case_event import CaseEvent
from app.models.commission import Commission
from app.models.document import Document
from app.models.import_batch import ImportBatch, STATUS_FAILED
from app.models.ops_incident import (
    ACTIVE_STATUSES,
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_OPEN,
    STATUS_RESOLVED,
    OpsIncident,
)
from app.models.sale_capture import (
    REG_STATUS_REGISTERED,
    REG_STATUS_REGISTRATION_FAILED,
    SaleCapture,
)
from app.services.case_event_service import (
    DOCUMENT_UPLOAD_FAILED,
    OCR_FAILED,
    SALE_CAPTURE_EXPORT_FAILED,
    SALE_CAPTURE_REGISTRATION_FAILED,
    SHAREPOINT_UPLOAD_FAILED,
    WORKFLOW_TRANSITION_BLOCKED,
)
from app.services.erp_reconciliation_service import ErpReconciliationService
from app.services.storage_layout_service import _REQUIRED_UNDER_STORAGE
from app.services.system_health_service import SystemHealthService
from app.services.workflow_dependency_service import build_workflow_context
from app.services.workflow_state_service import WF_CERRADO, normalize_workflow_state
from app.web.services.operational_review_service import OperationalReviewService, ReviewItem

log = logging.getLogger(__name__)

_RECENT_FAILURE_EVENTS = frozenset(
    {
        SHAREPOINT_UPLOAD_FAILED,
        DOCUMENT_UPLOAD_FAILED,
        SALE_CAPTURE_EXPORT_FAILED,
        SALE_CAPTURE_REGISTRATION_FAILED,
        OCR_FAILED,
        WORKFLOW_TRANSITION_BLOCKED,
    }
)

_CERRADOS = (
    C.ST_PED_CERRADO,
    C.ST_PED_RECHAZADO,
    C.ST_PED_COMPRA,
    C.ST_REV_CERRADO,
    C.ST_REV_RECHAZADO,
    C.ST_REV_SIN_LIQUIDEZ,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def incident_key(source: str, entity_type: str, entity_id: int | None, code: str) -> str:
    return f"{source}:{entity_type}:{entity_id or 0}:{code}"


@dataclass(frozen=True)
class OpsFinding:
    source: str
    code: str
    severity: str
    entity_type: str
    entity_id: int | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    url: str | None = None
    recommended_action: str | None = None

    @property
    def key(self) -> str:
        return incident_key(self.source, self.entity_type, self.entity_id, self.code)


@dataclass
class OpsDashboard:
    generated_at: datetime
    health_status: str
    health_checks_failed: list[str]
    counts: dict[str, int]
    critical_items: list[OpsFinding]
    warning_items: list[OpsFinding]
    pending_items: list[OpsFinding]
    recent_failures: list[dict[str, Any]]
    recommended_actions: list[str]
    open_incidents: int
    sla_cases: list[OpsFinding]


class OpsMonitorService:
    def collect_findings(self, db: Session) -> list[OpsFinding]:
        findings: list[OpsFinding] = []
        findings.extend(self._findings_from_review(db))
        findings.extend(self._findings_imports_failed(db))
        findings.extend(self._findings_sales_without_export(db))
        findings.extend(self._findings_workflow_blocked(db))
        findings.extend(self._findings_documents_invalid(db))
        findings.extend(self._findings_storage_paths())
        findings.extend(self._findings_recent_errors(db))
        return findings

    def _findings_from_review(self, db: Session) -> list[OpsFinding]:
        report = OperationalReviewService().build_report(db)
        section_map = {
            "sharepoint_fallidos": ("sharepoint", "sharepoint.failed", SEVERITY_ERROR, "document"),
            "export_excel_fallido": ("sales", "sale.export_failed", SEVERITY_ERROR, "sale_capture"),
            "casos_atorados": ("cases", "case.stale_24h", SEVERITY_WARNING, "case"),
            "comisiones_pendientes": ("commissions", "sale.no_commission", SEVERITY_WARNING, "sale_capture"),
            "ventas_pendientes": ("sales", "sale.pending_registration", SEVERITY_INFO, "sale_capture"),
            "documentos_pendientes": ("documents", "document.pending_review", SEVERITY_WARNING, "document"),
            "conciliacion_critica": ("reconciliation", "reconciliation.critical", SEVERITY_ERROR, "system"),
        }
        out: list[OpsFinding] = []
        for section, items in report.sections.items():
            meta = section_map.get(section)
            if not meta:
                continue
            source, code, default_sev, entity_type = meta
            for item in items:
                sev = item.severity.upper()
                if sev == "ERROR":
                    severity = SEVERITY_ERROR
                elif sev == "WARNING":
                    severity = SEVERITY_WARNING
                else:
                    severity = default_sev
                if section == "conciliacion_critica" and item.severity == "error":
                    severity = SEVERITY_CRITICAL
                out.append(
                    OpsFinding(
                        source=source,
                        code=code,
                        severity=severity,
                        entity_type=entity_type,
                        entity_id=item.entity_id,
                        message=f"{item.title}: {item.detail}",
                        details={"section": section, "url": item.url},
                        url=item.url,
                        recommended_action=self._action_for_code(code),
                    )
                )
        return out

    def _findings_imports_failed(self, db: Session) -> list[OpsFinding]:
        batches = db.scalars(
            select(ImportBatch)
            .where(ImportBatch.status == STATUS_FAILED)
            .order_by(ImportBatch.created_at.desc())
            .limit(30)
        ).all()
        return [
            OpsFinding(
                source="imports",
                code="import.failed",
                severity=SEVERITY_ERROR,
                entity_type="import_batch",
                entity_id=b.id,
                message=f"Importación fallida: {b.original_filename}",
                details={"error": b.error_message},
                url=f"/imports/{b.id}/preview",
                recommended_action="Revisar archivo y reintentar preview",
            )
            for b in batches
        ]

    def _findings_sales_without_export(self, db: Session) -> list[OpsFinding]:
        sales = db.scalars(
            select(SaleCapture)
            .where(
                SaleCapture.registration_status == REG_STATUS_REGISTERED,
                SaleCapture.ventas_export_path.is_(None),
            )
            .limit(25)
        ).all()
        findings = []
        for s in sales:
            findings.append(
                OpsFinding(
                    source="sales",
                    code="sale.no_excel_export",
                    severity=SEVERITY_WARNING,
                    entity_type="sale_capture",
                    entity_id=s.id,
                    message=f"Venta {s.folio} registrada sin ruta de export Excel",
                    url="/ventas/pendientes",
                    recommended_action="Regenerar export Excel",
                )
            )
        reg_failed = db.scalars(
            select(SaleCapture)
            .where(SaleCapture.registration_status == REG_STATUS_REGISTRATION_FAILED)
            .limit(25)
        ).all()
        for s in reg_failed:
            if not any(f.entity_id == s.id and f.code == "sale.export_failed" for f in findings):
                findings.append(
                    OpsFinding(
                        source="sales",
                        code="sale.export_failed",
                        severity=SEVERITY_ERROR,
                        entity_type="sale_capture",
                        entity_id=s.id,
                        message=f"Export/registro fallido: {s.folio}",
                        details={"error": s.export_error or s.registration_error},
                        url="/ventas/pendientes",
                        recommended_action="Regenerar export o reintentar registro",
                    )
                )
        return findings

    def _findings_workflow_blocked(self, db: Session) -> list[OpsFinding]:
        cases = db.scalars(
            select(Case)
            .where(not_(Case.current_status.in_(_CERRADOS)))
            .order_by(Case.updated_at.desc())
            .limit(60)
        ).all()
        findings: list[OpsFinding] = []
        for case in cases:
            ctx = build_workflow_context(db, case)
            if ctx.p24_missing_docs:
                findings.append(
                    OpsFinding(
                        source="workflow",
                        code="document.missing",
                        severity=SEVERITY_WARNING,
                        entity_type="case",
                        entity_id=case.id,
                        message=f"Caso {case.public_id}: faltan {', '.join(ctx.p24_missing_docs[:3])}",
                        details={"missing": ctx.p24_missing_docs},
                        url=f"/casos/{case.id}/documentos",
                        recommended_action="Revalidar checklist documental",
                    )
                )
            if ctx.sharepoint_failed:
                findings.append(
                    OpsFinding(
                        source="workflow",
                        code="workflow.blocked",
                        severity=SEVERITY_ERROR,
                        entity_type="case",
                        entity_id=case.id,
                        message=f"Caso {case.public_id}: workflow bloqueado por SharePoint",
                        url=f"/casos/{case.id}",
                        recommended_action="Reintentar SharePoint",
                    )
                )
            elif ctx.has_critical_timeline_error:
                findings.append(
                    OpsFinding(
                        source="workflow",
                        code="workflow.blocked",
                        severity=SEVERITY_ERROR,
                        entity_type="case",
                        entity_id=case.id,
                        message=f"Caso {case.public_id}: error crítico en timeline",
                        url=f"/casos/{case.id}",
                        recommended_action="Revisar timeline y recovery",
                    )
                )
            wf = normalize_workflow_state(case.workflow_state, legacy_status=case.current_status)
            if wf != WF_CERRADO and ctx.sharepoint_pending and not ctx.sharepoint_ok:
                key_exists = any(
                    f.entity_id == case.id and f.code == "workflow.blocked" for f in findings
                )
                if not key_exists:
                    findings.append(
                        OpsFinding(
                            source="workflow",
                            code="workflow.blocked",
                            severity=SEVERITY_WARNING,
                            entity_type="case",
                            entity_id=case.id,
                            message=f"Caso {case.public_id}: pendiente SharePoint",
                            url=f"/casos/{case.id}",
                            recommended_action="Sincronizar documentos a SharePoint",
                        )
                    )
        return findings[:40]

    def _findings_documents_invalid(self, db: Session) -> list[OpsFinding]:
        docs = db.scalars(
            select(Document)
            .where(
                Document.is_active.is_(True),
                Document.review_status == C.REVIEW_INVALID,
            )
            .order_by(Document.updated_at.desc())
            .limit(25)
        ).all()
        return [
            OpsFinding(
                source="documents",
                code="document.invalid",
                severity=SEVERITY_WARNING,
                entity_type="document",
                entity_id=d.id,
                message=f"Documento inválido #{d.id} caso {d.case_id}",
                details={"reason": d.rejection_reason},
                url=f"/casos/{d.case_id}/documentos",
                recommended_action="Reemplazar o revalidar documento",
            )
            for d in docs
        ]

    def _findings_storage_paths(self) -> list[OpsFinding]:
        missing: list[str] = []
        for sub in _REQUIRED_UNDER_STORAGE:
            if not (STORAGE_DIR / sub).is_dir():
                missing.append(sub)
        if not IMPORTS_DIR.is_dir():
            missing.append("imports")
        if not EXCEL_EXPORTS_DIR.is_dir():
            missing.append("excel_exports")
        if not missing:
            return []
        return [
            OpsFinding(
                source="storage",
                code="storage.path_missing",
                severity=SEVERITY_CRITICAL,
                entity_type="system",
                entity_id=None,
                message=f"Rutas storage faltantes: {', '.join(missing)}",
                details={"paths": missing},
                recommended_action="Ejecutar arranque web o crear directorios",
            )
        ]

    def _findings_recent_errors(self, db: Session) -> list[OpsFinding]:
        since = _utcnow() - timedelta(hours=48)
        events = db.scalars(
            select(CaseEvent)
            .where(
                CaseEvent.event_type.in_(_RECENT_FAILURE_EVENTS),
                CaseEvent.created_at >= since,
            )
            .order_by(CaseEvent.created_at.desc())
            .limit(30)
        ).all()
        return [
            OpsFinding(
                source="timeline",
                code="recent.failure",
                severity=SEVERITY_INFO,
                entity_type="case",
                entity_id=e.case_id,
                message=f"{e.event_type}: {e.message[:200]}",
                details={"event_type": e.event_type, "at": e.created_at.isoformat()},
                url=f"/casos/{e.case_id}",
            )
            for e in events
        ]

    @staticmethod
    def _action_for_code(code: str) -> str | None:
        return {
            "sharepoint.failed": "POST /ops/retry/sharepoint",
            "sale.export_failed": "POST /ops/regenerate/export/{id}",
            "sale.no_commission": "POST /ops/recalculate/commissions",
            "reconciliation.critical": "POST /ops/rebuild/conciliation",
            "import.failed": "Re-preview en /imports/{id}/preview",
        }.get(code)

    def sync_incidents(self, db: Session, findings: list[OpsFinding]) -> tuple[int, int]:
        """Crea/actualiza incidencias; auto-resuelve las que ya no aplican."""
        now = _utcnow()
        active_keys = {f.key for f in findings}
        created = updated = 0

        for f in findings:
            inc = db.scalar(select(OpsIncident).where(OpsIncident.incident_key == f.key))
            details = dict(f.details or {})
            if f.url:
                details["url"] = f.url
            if f.recommended_action:
                details["recommended_action"] = f.recommended_action

            if inc:
                inc.severity = f.severity
                inc.message = f.message
                inc.details_json = details
                inc.last_seen_at = now
                if inc.status in (STATUS_RESOLVED, "IGNORED"):
                    inc.status = STATUS_OPEN
                    inc.resolved_at = None
                    inc.resolved_by = None
                updated += 1
            else:
                db.add(
                    OpsIncident(
                        incident_key=f.key,
                        source=f.source,
                        severity=f.severity,
                        status=STATUS_OPEN,
                        entity_type=f.entity_type,
                        entity_id=f.entity_id,
                        message=f.message,
                        details_json=details,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                created += 1

        stale = db.scalars(
            select(OpsIncident).where(OpsIncident.status.in_(ACTIVE_STATUSES))
        ).all()
        resolved_auto = 0
        for inc in stale:
            if inc.incident_key not in active_keys:
                inc.status = STATUS_RESOLVED
                inc.resolved_at = now
                inc.resolved_by = "system:auto_clear"
                trail = list((inc.details_json or {}).get("audit") or [])
                trail.append({"at": now.isoformat(), "action": "auto_resolved", "reason": "finding_cleared"})
                inc.details_json = {**(inc.details_json or {}), "audit": trail}
                resolved_auto += 1

        db.flush()
        return created + updated, resolved_auto

    def build_dashboard(self, db: Session, *, sync: bool = True) -> OpsDashboard:
        findings = self.collect_findings(db)
        if sync:
            self.sync_incidents(db, findings)

        health = SystemHealthService().build_report(db, full=False)
        failed_checks = [
            c.name for c in health.checks if not c.ok
        ] if hasattr(health, "checks") else []

        critical = [f for f in findings if f.severity in (SEVERITY_CRITICAL, SEVERITY_ERROR)]
        warning = [f for f in findings if f.severity == SEVERITY_WARNING]
        pending = [f for f in findings if f.severity == SEVERITY_INFO]

        open_count = db.scalar(
            select(func.count(OpsIncident.id)).where(OpsIncident.status.in_(ACTIVE_STATUSES))
        ) or 0

        sla = [f for f in findings if f.code == "case.stale_24h"][:20]
        recent = [
            {
                "message": f.message,
                "severity": f.severity,
                "url": f.url,
                "source": f.source,
            }
            for f in findings
            if f.code == "recent.failure"
        ][:15]

        actions: list[str] = []
        seen: set[str] = set()
        for f in findings:
            if f.recommended_action and f.recommended_action not in seen:
                seen.add(f.recommended_action)
                actions.append(f.recommended_action)
            if len(actions) >= 12:
                break

        counts = {
            "critical": len(critical),
            "warning": len(warning),
            "pending": len(pending),
            "total_findings": len(findings),
            "open_incidents": int(open_count),
            "sharepoint_failed": sum(1 for f in findings if f.code == "sharepoint.failed"),
            "imports_failed": sum(1 for f in findings if f.code == "import.failed"),
            "exports_failed": sum(1 for f in findings if f.code == "sale.export_failed"),
            "sales_pending": sum(1 for f in findings if f.code == "sale.pending_registration"),
            "docs_pending": sum(1 for f in findings if f.code == "document.pending_review"),
        }

        return OpsDashboard(
            generated_at=_utcnow(),
            health_status=health.status,
            health_checks_failed=failed_checks,
            counts=counts,
            critical_items=critical[:30],
            warning_items=warning[:30],
            pending_items=pending[:20],
            recent_failures=recent,
            recommended_actions=actions,
            open_incidents=int(open_count),
            sla_cases=sla,
        )

    def list_incidents(
        self,
        db: Session,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[OpsIncident]:
        q = select(OpsIncident).order_by(OpsIncident.last_seen_at.desc())
        if status:
            q = q.where(OpsIncident.status == status)
        return list(db.scalars(q.limit(limit)).all())

    def get_incident(self, db: Session, incident_id: int) -> OpsIncident | None:
        return db.get(OpsIncident, incident_id)
