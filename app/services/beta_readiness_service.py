"""Evaluación de preparación para beta interna (P34)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.paths import EXCEL_EXPORTS_DIR, EXCEL_MASTER_DIR, IMPORTS_DIR, PROJECT_ROOT, STORAGE_DIR
from app.domain import constants as C
from app.models.document import Document
from app.models.import_batch import ImportBatch, STATUS_FAILED, STATUS_PREVIEWED, STATUS_UPLOADED
from app.models.ops_incident import ACTIVE_STATUSES, SEVERITY_CRITICAL, SEVERITY_ERROR, OpsIncident
from app.models.sale_capture import REG_STATUS_REGISTRATION_FAILED, SaleCapture
from app.services.beta_ops_log import log_beta_warning
from app.services.beta_safe_mode_service import BetaSafeModeService
from app.services.excel_path_guard import is_under_excel_masters
from app.services.ops_monitor_service import OpsMonitorService
from app.services.storage_layout_service import _REQUIRED_UNDER_STORAGE
from app.services.system_health_service import SystemHealthService

log = logging.getLogger(__name__)

_BACKUP_MAX_AGE_HOURS_WARN = 48
_BACKUP_MAX_AGE_HOURS_FAIL = 168


@dataclass
class ReadinessCheck:
    key: str
    label: str
    ok: bool
    severity: str
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class BetaReadinessReport:
    generated_at: datetime
    overall_status: str
    readiness_score: int
    safe_mode: bool
    checks: list[ReadinessCheck]
    warnings: list[str]
    critical_errors: list[str]
    recent_errors: list[dict[str, Any]]
    recent_backups: list[dict[str, Any]]
    open_incidents: list[OpsIncident]
    pending_ops: dict[str, int]

    @property
    def ready_for_beta(self) -> bool:
        return self.overall_status in ("ready", "degraded") and self.readiness_score >= 70


class BetaReadinessService:
    def build_report(self, db: Session) -> BetaReadinessReport:
        checks: list[ReadinessCheck] = []
        checks.append(self._check_migrations(db))
        checks.extend(self._checks_from_health(db))
        checks.append(self._check_critical_paths())
        checks.append(self._check_logs_active())
        checks.extend(self._check_backups())
        checks.extend(self._check_operational_pending(db))
        checks.append(self._check_health_routes())
        checks.append(self._check_excel_masters_readonly())

        warnings: list[str] = []
        critical: list[str] = []
        for c in checks:
            if c.ok:
                continue
            if c.severity == "error":
                critical.append(f"{c.label}: {c.detail}")
                log_beta_warning(c.key, c.detail)
            elif c.severity == "warning":
                warnings.append(f"{c.label}: {c.detail}")

        score = self._compute_score(checks)
        failed_errors = sum(1 for c in checks if not c.ok and c.severity == "error")
        if failed_errors == 0 and score >= 85:
            status = "ready"
        elif failed_errors == 0:
            status = "degraded"
        else:
            status = "not_ready"

        open_inc = list(
            db.scalars(
                select(OpsIncident)
                .where(OpsIncident.status.in_(ACTIVE_STATUSES))
                .order_by(OpsIncident.severity.desc(), OpsIncident.last_seen_at.desc())
                .limit(30)
            ).all()
        )

        findings = OpsMonitorService().collect_findings(db)
        pending = {
            "imports_failed": sum(1 for f in findings if f.code == "import.failed"),
            "exports_failed": sum(1 for f in findings if f.code == "sale.export_failed"),
            "sharepoint_failed": sum(1 for f in findings if f.code == "sharepoint.failed"),
            "critical_incidents": sum(
                1 for i in open_inc if i.severity in (SEVERITY_CRITICAL, SEVERITY_ERROR)
            ),
            "total_findings": len(findings),
        }

        return BetaReadinessReport(
            generated_at=datetime.now(timezone.utc),
            overall_status=status,
            readiness_score=score,
            safe_mode=BetaSafeModeService().is_enabled(),
            checks=checks,
            warnings=warnings,
            critical_errors=critical,
            recent_errors=self._recent_timeline_errors(db),
            recent_backups=self._list_recent_backups(),
            open_incidents=open_inc,
            pending_ops=pending,
        )

    def quick_banner_alerts(self, db: Session) -> dict[str, Any]:
        """Consultas mínimas para badges en navbar."""
        critical_count = db.scalar(
            select(func.count(OpsIncident.id)).where(
                OpsIncident.status.in_(ACTIVE_STATUSES),
                OpsIncident.severity.in_((SEVERITY_CRITICAL, SEVERITY_ERROR)),
            )
        ) or 0
        imports_pending = db.scalar(
            select(func.count(ImportBatch.id)).where(
                ImportBatch.status.in_((STATUS_FAILED, STATUS_UPLOADED, STATUS_PREVIEWED))
            )
        ) or 0
        sp_failed = db.scalar(
            select(func.count(Document.id)).where(
                Document.is_active.is_(True),
                Document.upload_status == C.UPLOAD_FAILED,
            )
        ) or 0
        backups = self._list_recent_backups()
        backup_stale = True
        if backups:
            latest = backups[0].get("age_hours", 9999)
            backup_stale = latest > _BACKUP_MAX_AGE_HOURS_WARN

        sp_degraded = False
        try:
            from app.services.sharepoint_graph_client import SharePointGraphClient
            from app.services.sharepoint_graph_errors import GraphConfigError

            SharePointGraphClient().validate_config()
        except GraphConfigError:
            sp_degraded = True

        if critical_count or backup_stale or sp_degraded:
            log_beta_warning(
                "banner",
                f"critical={critical_count} backup_stale={backup_stale} sp={sp_degraded}",
            )

        return {
            "critical_incidents": int(critical_count),
            "imports_pending": int(imports_pending),
            "sharepoint_failed": int(sp_failed),
            "sharepoint_degraded": sp_degraded,
            "backup_stale": backup_stale,
            "safe_mode": BetaSafeModeService().is_enabled(),
        }

    def _compute_score(self, checks: list[ReadinessCheck]) -> int:
        if not checks:
            return 0
        weight = {"error": 3, "warning": 2, "ok": 1}
        total_w = sum(weight.get(c.severity if not c.ok else "ok", 1) for c in checks)
        ok_w = sum(
            weight.get(c.severity if not c.ok else "ok", 1)
            for c in checks
            if c.ok
        )
        return min(100, int(100 * ok_w / total_w)) if total_w else 0

    def _check_migrations(self, db: Session) -> ReadinessCheck:
        try:
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
            script = ScriptDirectory.from_config(cfg)
            conn = db.connection()
            context = MigrationContext.configure(conn)
            current = context.get_current_revision()
            heads = script.get_heads()
            head = heads[0] if len(heads) == 1 else ",".join(heads)
            ok = current in heads if heads else True
            return ReadinessCheck(
                "migrations",
                "Migraciones Alembic",
                ok,
                "ok" if ok else "error",
                f"actual={current or '—'} head={head}",
                {"current": current, "head": head},
            )
        except Exception as exc:
            return ReadinessCheck(
                "migrations",
                "Migraciones Alembic",
                False,
                "warning",
                str(exc)[:200],
            )

    def _checks_from_health(self, db: Session) -> list[ReadinessCheck]:
        report = SystemHealthService().build_report(db, full=True)
        out: list[ReadinessCheck] = []
        for c in report.checks:
            sev = "ok" if c.ok else ("error" if c.name in ("database", "storage_root", "excel_exports") else "warning")
            out.append(
                ReadinessCheck(
                    f"health_{c.name}",
                    c.name.replace("_", " ").title(),
                    c.ok,
                    sev,
                    c.detail,
                    c.meta,
                )
            )
        return out

    def _check_critical_paths(self) -> ReadinessCheck:
        missing = [s for s in _REQUIRED_UNDER_STORAGE if not (STORAGE_DIR / s).is_dir()]
        if not IMPORTS_DIR.is_dir():
            missing.append("imports")
        ok = not missing
        return ReadinessCheck(
            "storage_paths",
            "Rutas storage críticas",
            ok,
            "ok" if ok else "error",
            "OK" if ok else f"Faltan: {', '.join(missing)}",
            {"missing": missing},
        )

    def _check_logs_active(self) -> ReadinessCheck:
        logs_dir = PROJECT_ROOT / "logs"
        app_log = logs_dir / "app.log"
        ok = logs_dir.is_dir()
        detail = str(logs_dir)
        if app_log.is_file():
            age_h = (datetime.now(timezone.utc) - datetime.fromtimestamp(app_log.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
            detail += f"; app.log hace {age_h:.1f}h"
            ok = ok and age_h < 72
        else:
            detail += "; app.log aún no creado"
        return ReadinessCheck("logs", "Logs activos", ok, "ok" if ok else "warning", detail)

    def _check_backups(self) -> list[ReadinessCheck]:
        backups = self._list_recent_backups()
        if not backups:
            return [
                ReadinessCheck(
                    "backups",
                    "Backups recientes",
                    False,
                    "warning",
                    "Sin archivos .sql.gz en backups/",
                )
            ]
        age = backups[0]["age_hours"]
        if age > _BACKUP_MAX_AGE_HOURS_FAIL:
            sev = "error"
            ok = False
        elif age > _BACKUP_MAX_AGE_HOURS_WARN:
            sev = "warning"
            ok = False
        else:
            sev = "ok"
            ok = True
        return [
            ReadinessCheck(
                "backups",
                "Backups recientes",
                ok,
                sev,
                f"Último backup hace {age:.0f}h ({backups[0]['name']})",
                {"latest": backups[0]},
            )
        ]

    def _list_recent_backups(self) -> list[dict[str, Any]]:
        backup_dir = PROJECT_ROOT / "backups"
        if not backup_dir.is_dir():
            return []
        files = sorted(backup_dir.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        now = datetime.now(timezone.utc)
        out: list[dict[str, Any]] = []
        for p in files[:8]:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            age_h = (now - mtime).total_seconds() / 3600
            out.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "mtime": mtime.isoformat(),
                    "age_hours": round(age_h, 1),
                }
            )
        return out

    def _check_operational_pending(self, db: Session) -> list[ReadinessCheck]:
        critical_inc = db.scalar(
            select(func.count(OpsIncident.id)).where(
                OpsIncident.status.in_(ACTIVE_STATUSES),
                OpsIncident.severity.in_((SEVERITY_CRITICAL, SEVERITY_ERROR)),
            )
        ) or 0
        imports_fail = db.scalar(
            select(func.count(ImportBatch.id)).where(ImportBatch.status == STATUS_FAILED)
        ) or 0
        exports_fail = db.scalar(
            select(func.count(SaleCapture.id)).where(
                SaleCapture.registration_status == REG_STATUS_REGISTRATION_FAILED
            )
        ) or 0
        sp_fail = db.scalar(
            select(func.count(Document.id)).where(
                Document.is_active.is_(True),
                Document.upload_status == C.UPLOAD_FAILED,
            )
        ) or 0

        checks = [
            ReadinessCheck(
                "incidents_critical",
                "Incidencias críticas abiertas",
                critical_inc == 0,
                "ok" if critical_inc == 0 else "error",
                f"{critical_inc} abiertas",
            ),
            ReadinessCheck(
                "imports_failed",
                "Imports fallidos",
                imports_fail == 0,
                "ok" if imports_fail == 0 else "warning",
                f"{imports_fail} lotes",
            ),
            ReadinessCheck(
                "exports_failed",
                "Exports / registro fallido",
                exports_fail == 0,
                "ok" if exports_fail == 0 else "error",
                f"{exports_fail} ventas",
            ),
            ReadinessCheck(
                "sharepoint_failed",
                "SharePoint fallidos",
                sp_fail == 0,
                "ok" if sp_fail == 0 else "warning",
                f"{sp_fail} documentos",
            ),
        ]
        return checks

    def _check_health_routes(self) -> ReadinessCheck:
        try:
            from app.web.main import web_app

            paths = {getattr(r, "path", "") for r in web_app.routes}
            need = {"/health", "/ping"}
            missing = need - paths
            ok = not missing
            return ReadinessCheck(
                "health_endpoints",
                "Health endpoints",
                ok,
                "ok" if ok else "error",
                "OK" if ok else f"Faltan rutas: {missing}",
            )
        except Exception as exc:
            return ReadinessCheck("health_endpoints", "Health endpoints", False, "warning", str(exc))

    def _check_excel_masters_readonly(self) -> ReadinessCheck:
        from app.services.excel_path_guard import assert_writable_excel_path, is_under_excel_masters

        sample = EXCEL_MASTER_DIR / "ventas" / "_beta_probe.xlsx"
        blocked = False
        try:
            assert_writable_excel_path(sample)
        except ValueError:
            blocked = True
        ok = is_under_excel_masters(sample) and blocked
        return ReadinessCheck(
            "excel_masters_guard",
            "Excel masters solo lectura",
            ok,
            "ok" if ok else "error",
            "Guard de escritura activo" if ok else "Riesgo de escritura en masters",
        )

    def _recent_timeline_errors(self, db: Session) -> list[dict[str, Any]]:
        from app.models.case_event import CaseEvent
        from app.services.case_event_service import (
            SALE_CAPTURE_EXPORT_FAILED,
            SALE_CAPTURE_REGISTRATION_FAILED,
            SHAREPOINT_UPLOAD_FAILED,
        )

        since = datetime.now(timezone.utc) - timedelta(hours=72)
        events = db.scalars(
            select(CaseEvent)
            .where(
                CaseEvent.event_type.in_(
                    (
                        SHAREPOINT_UPLOAD_FAILED,
                        SALE_CAPTURE_EXPORT_FAILED,
                        SALE_CAPTURE_REGISTRATION_FAILED,
                    )
                ),
                CaseEvent.created_at >= since,
            )
            .order_by(CaseEvent.created_at.desc())
            .limit(20)
        ).all()
        return [
            {
                "case_id": e.case_id,
                "type": e.event_type,
                "message": (e.message or "")[:180],
                "at": e.created_at.isoformat() if e.created_at else "",
            }
            for e in events
        ]
