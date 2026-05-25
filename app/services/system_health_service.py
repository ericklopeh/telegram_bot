"""Health checks operativos del sistema (P30)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.paths import (
    EXCEL_EXPORTS_DIR,
    EXCEL_MASTER_DIR,
    PROJECT_ROOT,
    STORAGE_DIR,
    TEMPLATE_DIR,
)
from app.services.excel_path_guard import is_under_excel_masters
from app.services.sharepoint_graph_client import SharePointGraphClient
from app.services.sharepoint_graph_errors import GraphConfigError
from app.web.paths import TEMPLATES_DIR

_START_MONOTONIC = time.monotonic()
_APP_VERSION = "0.1.0"


@dataclass
class HealthCheckResult:
    name: str
    ok: bool
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealthReport:
    status: str
    checked_at: datetime
    uptime_seconds: float
    version: str
    environment: str
    checks: list[HealthCheckResult]

    def to_dict(self, *, full: bool = False) -> dict[str, Any]:
        failed = [c for c in self.checks if not c.ok]
        payload: dict[str, Any] = {
            "status": self.status,
            "checked_at": self.checked_at.isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "version": self.version,
            "environment": self.environment,
        }
        if full:
            payload["checks"] = [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "meta": c.meta} for c in self.checks
            ]
        else:
            payload["summary"] = {
                "total": len(self.checks),
                "failed": len(failed),
                "failed_names": [c.name for c in failed],
            }
        return payload


class SystemHealthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def version(self) -> str:
        return self.settings.app_version or _APP_VERSION

    def build_report(self, db: Session | None = None, *, full: bool = True) -> SystemHealthReport:
        checks: list[HealthCheckResult] = [
            self._check_database(db),
            self._check_storage_root(),
            self._check_excel_exports_writable(),
            self._check_excel_masters_present(),
            self._check_templates(),
            self._check_cases_storage(),
            self._check_sharepoint_config(),
            self._check_logs_dir(),
        ]
        failed = [c for c in checks if not c.ok]
        status = "ok" if not failed else ("degraded" if len(failed) < len(checks) else "unhealthy")
        return SystemHealthReport(
            status=status,
            checked_at=datetime.now(timezone.utc),
            uptime_seconds=time.monotonic() - _START_MONOTONIC,
            version=self.version,
            environment=self.settings.environment,
            checks=checks if full else checks,
        )

    def _check_database(self, db: Session | None) -> HealthCheckResult:
        if db is None:
            try:
                from app.db.session import session_scope

                with session_scope() as session:
                    session.execute(text("SELECT 1"))
                return HealthCheckResult("database", True, "Conexión OK")
            except Exception as exc:
                return HealthCheckResult("database", False, str(exc))
        try:
            db.execute(text("SELECT 1"))
            return HealthCheckResult("database", True, "Conexión OK")
        except Exception as exc:
            return HealthCheckResult("database", False, str(exc))

    def _check_storage_root(self) -> HealthCheckResult:
        root = Path(self.settings.base_storage_path)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".health_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return HealthCheckResult(
                "storage_root",
                True,
                str(root),
                {"writable": True, "exists": root.is_dir()},
            )
        except OSError as exc:
            return HealthCheckResult("storage_root", False, str(exc), {"path": str(root)})

    def _check_excel_exports_writable(self) -> HealthCheckResult:
        path = EXCEL_EXPORTS_DIR
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            if is_under_excel_masters(path):
                return HealthCheckResult(
                    "excel_exports",
                    False,
                    "Ruta de exports bajo excel_masters (inválido)",
                )
            return HealthCheckResult("excel_exports", True, str(path))
        except OSError as exc:
            return HealthCheckResult("excel_exports", False, str(exc))

    def _check_excel_masters_present(self) -> HealthCheckResult:
        masters = EXCEL_MASTER_DIR
        if not masters.is_dir():
            return HealthCheckResult(
                "excel_masters",
                False,
                f"No existe {masters} (montar volumen o copiar masters)",
            )
        xlsx = list(masters.rglob("*.xlsx"))
        return HealthCheckResult(
            "excel_masters",
            bool(xlsx),
            f"{len(xlsx)} archivo(s) xlsx" if xlsx else "Sin archivos .xlsx",
            {"path": str(masters), "read_only_ok": True},
        )

    def _check_templates(self) -> HealthCheckResult:
        web_tpl = TEMPLATES_DIR.is_dir()
        storage_tpl = TEMPLATE_DIR.is_dir()
        ok = web_tpl
        detail = f"web={TEMPLATES_DIR}" if web_tpl else f"Falta {TEMPLATES_DIR}"
        if storage_tpl:
            detail += f"; storage_templates={TEMPLATE_DIR}"
        return HealthCheckResult("templates", ok, detail)

    def _check_cases_storage(self) -> HealthCheckResult:
        cases_dir = STORAGE_DIR / "cases"
        try:
            cases_dir.mkdir(parents=True, exist_ok=True)
            return HealthCheckResult("storage_cases", True, str(cases_dir))
        except OSError as exc:
            return HealthCheckResult("storage_cases", False, str(exc))

    def _check_sharepoint_config(self) -> HealthCheckResult:
        try:
            SharePointGraphClient().validate_config()
            return HealthCheckResult(
                "sharepoint_config",
                True,
                "Variables Graph presentes",
                {
                    "tenant": bool(self.settings.ms_tenant_id),
                    "root_folder": self.settings.ms_root_folder or "",
                },
            )
        except GraphConfigError as exc:
            return HealthCheckResult(
                "sharepoint_config",
                False,
                str(exc),
                {"hint": "Opcional en staging sin SharePoint"},
            )

    def _check_logs_dir(self) -> HealthCheckResult:
        logs_root = PROJECT_ROOT / "logs"
        try:
            logs_root.mkdir(parents=True, exist_ok=True)
            probe = logs_root / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return HealthCheckResult("logs", True, str(logs_root))
        except OSError as exc:
            return HealthCheckResult("logs", False, str(exc))
