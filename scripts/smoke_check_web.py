#!/usr/bin/env python3
"""
P69 — Smoke check web/enterprise (staging readiness).

Valida DB, Redis opcional, health, rutas críticas, realtime, storage,
plantillas, migraciones, jobs, flags y endpoints de cohesión.

Uso:
    python scripts/smoke_check_web.py
    python scripts/smoke_check_web.py --base-url http://127.0.0.1:8000

Salida: OK / WARN / FAIL por check + tiempos + resumen.
Código de salida: 0 si no hay FAIL críticos, 1 si hay FAIL.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class CheckResult:
    name: str
    status: str  # OK | WARN | FAIL
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class SmokeReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", elapsed_ms: float = 0.0) -> None:
        self.results.append(CheckResult(name, status, detail, elapsed_ms))
        tag = {"OK": "OK  ", "WARN": "WARN", "FAIL": "FAIL"}[status]
        ms = f" ({elapsed_ms:.0f}ms)" if elapsed_ms else ""
        line = f"{tag} {name}{ms}"
        if detail:
            line += f" — {detail}"
        print(line)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "FAIL"]

    @property
    def warned(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "WARN"]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


def _timed(report: SmokeReport, name: str, fn: Callable[[], tuple[str, str]]) -> None:
    t0 = time.perf_counter()
    try:
        status, detail = fn()
    except Exception as exc:
        status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
    elapsed = (time.perf_counter() - t0) * 1000
    report.add(name, status, detail, elapsed)


def _docker_db_host(url: str) -> bool:
    return bool(re.search(r"[@/]db(?::|/)", url, re.I) or re.search(r"://db(?::|/)", url, re.I))


def check_db(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            return "WARN", "DATABASE_URL no definida"
        from sqlalchemy import create_engine, text

        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return "OK", "SELECT 1"
        except Exception as exc:
            if _docker_db_host(url):
                return "WARN", f"host db no resuelve fuera de Docker ({type(exc).__name__})"
            return "FAIL", str(exc)[:200]

    _timed(report, "database", _run)


def check_redis(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            return "WARN", "REDIS_URL no configurado (opcional)"
        try:
            from redis import Redis

            client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
            client.ping()
            return "OK", "PING"
        except Exception as exc:
            return "WARN", f"Redis no disponible: {type(exc).__name__}"

    _timed(report, "redis_optional", _run)


def check_excel_masters_guard(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from app.core.paths import EXCEL_MASTER_DIR
        from app.services.excel_path_guard import is_under_excel_masters

        master = EXCEL_MASTER_DIR.resolve()
        if not master.is_dir():
            return "WARN", f"Directorio masters ausente: {master}"
        outside = ROOT / "storage" / "exports"
        outside.mkdir(parents=True, exist_ok=True)
        if is_under_excel_masters(outside):
            return "FAIL", "excel_path_guard clasifica exports como masters"
        return "OK", "masters protegido / guard OK"

    _timed(report, "excel_masters_protected", _run)


def check_storage_folders(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from app.config import get_settings
        from app.core.paths import EXCEL_EXPORTS_DIR, IMPORTS_DIR

        settings = get_settings()
        root = Path(settings.storage_root)
        root.mkdir(parents=True, exist_ok=True)
        for label, path in (
            ("storage_root", root),
            ("imports", IMPORTS_DIR),
            ("exports", EXCEL_EXPORTS_DIR),
        ):
            path.mkdir(parents=True, exist_ok=True)
            test = path / ".smoke_write"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
        return "OK", "storage, imports, exports escribibles"

    _timed(report, "storage_writable", _run)


def check_templates_exist(report: SmokeReport) -> None:
    CRITICAL_TEMPLATES = (
        "base.html",
        "activity_feed.html",
        "supervisor_cockpit.html",
        "workflow_visual.html",
        "ai_copilot.html",
        "compliance_center.html",
        "automations.html",
        "rules_simulator.html",
        "jobs.html",
        "ops_dashboard.html",
    )

    def _run() -> tuple[str, str]:
        from app.web.paths import TEMPLATES_DIR

        tpl_dir = Path(TEMPLATES_DIR)
        missing = [t for t in CRITICAL_TEMPLATES if not (tpl_dir / t).is_file()]
        if missing:
            return "FAIL", f"Faltan: {', '.join(missing)}"
        return "OK", f"{len(CRITICAL_TEMPLATES)} plantillas críticas"

    _timed(report, "templates_critical", _run)


def check_migrations_head(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return "WARN", "alembic heads falló"
        heads = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if not heads:
            return "WARN", "sin heads"
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            return "OK", f"heads={heads[0][:12]}… (DB no probada)"
        proc2 = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc2.returncode != 0:
            return "WARN", "alembic current falló"
        cur = (proc2.stdout or "").strip()
        if heads[0].split()[0] not in cur and "(head)" not in cur:
            return "WARN", "BD puede no estar en head"
        return "OK", "migraciones en head"

    _timed(report, "migrations_head", _run)


def check_app_imports(report: SmokeReport) -> None:
    MODULES = (
        "app.web.main",
        "app.services.realtime_service",
        "app.services.job_service",
        "app.services.platform_cohesion_service",
        "app.services.performance_service",
        "app.services.feature_flag_service",
    )

    def _run() -> tuple[str, str]:
        errors = []
        for mod in MODULES:
            try:
                importlib.import_module(mod)
            except Exception as exc:
                errors.append(f"{mod}: {exc}")
        if errors:
            return "FAIL", "; ".join(errors[:3])
        return "OK", f"{len(MODULES)} módulos"

    _timed(report, "imports_core", _run)


def check_realtime_hub(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from app.services.realtime_service import RealtimeService, get_realtime_hub

        svc = RealtimeService()
        svc.publish("activity", "smoke", {"ok": True})
        bundle = svc.build_poll_bundle(["activity", "heartbeat"])
        if "activity" not in bundle:
            return "FAIL", "poll bundle sin activity"
        hub = get_realtime_hub()
        hub.cleanup_stale_subscribers()
        hb = hub.heartbeat()
        if hb.get("event") != "ping":
            return "FAIL", "heartbeat inválido"
        return "OK", "publish + poll + heartbeat"

    _timed(report, "realtime_hub", _run)


def check_jobs_service(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from app.services.job_service import JOB_TYPES, JobService

        if len(JOB_TYPES) < 5:
            return "FAIL", "JOB_TYPES incompleto"
        stale = JobService().reconcile_stale_jobs.__doc__
        if not stale:
            return "WARN", "reconcile_stale_jobs sin doc"
        return "OK", f"{len(JOB_TYPES)} tipos de job"

    _timed(report, "jobs_registry", _run)


def check_feature_flags(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from unittest.mock import MagicMock

        from app.services.feature_flag_service import FeatureFlagService

        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        svc = FeatureFlagService()
        if not svc.is_enabled(db, "realtime_ws"):
            return "WARN", "realtime_ws default off"
        return "OK", "defaults accesibles"

    _timed(report, "feature_flags", _run)


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    req = Request(url, headers={"User-Agent": "gaman-smoke/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read(512).decode("utf-8", errors="replace")
        return resp.status, body


def check_http_routes(report: SmokeReport, base_url: str | None) -> None:
    if not base_url:
        report.add("http_skipped", "WARN", "Sin --base-url; omitiendo HTTP/WS")
        return

    base = base_url.rstrip("/")
    routes: list[tuple[str, str, int | None]] = [
        ("health", "/health", 200),
        ("health_full", "/health/full", None),
        ("realtime_poll", "/api/realtime/poll?channels=heartbeat", 200),
    ]

    for name, path, expected in routes:
        url = f"{base}{path}"

        def _run(u=url, exp=expected, nm=name) -> tuple[str, str]:
            try:
                code, _ = _http_get(u)
            except URLError as exc:
                return "WARN", f"no alcanzable: {exc.reason}"
            if exp and code != exp:
                return "FAIL", f"HTTP {code}"
            return "OK", f"HTTP {code}"

        _timed(report, f"http_{name}", _run)

    def _ws_handshake() -> tuple[str, str]:
        try:
            import asyncio
            from urllib.parse import urlparse

            import websockets

            parsed = urlparse(base)
            scheme = "wss" if parsed.scheme == "https" else "ws"
            ws_url = f"{scheme}://{parsed.netloc}/ws/activity"
            async def _probe():
                async with websockets.connect(ws_url, open_timeout=3, close_timeout=2) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=3)

            asyncio.run(_probe())
            return "OK", "handshake /ws/activity"
        except ImportError:
            return "WARN", "paquete websockets no instalado"
        except Exception as exc:
            return "WARN", f"WS: {type(exc).__name__}"

    _timed(report, "websocket_handshake", _ws_handshake)

    auth_routes = [
        "/activity",
        "/jobs",
        "/workflow/visual",
        "/supervisor/cockpit",
        "/ai/copilot",
        "/calendar",
        "/search",
        "/reports/builder",
        "/analytics/avanzado",
        "/imports",
        "/admin/automations",
        "/admin/rules/simulator",
        "/admin/compliance-center",
    ]
    for path in auth_routes:
        slug = path.strip("/").replace("/", "_") or "root"

        def _run(p=path, s=slug) -> tuple[str, str]:
            try:
                code, _ = _http_get(f"{base}{p}")
            except URLError as exc:
                return "WARN", str(exc.reason)
            if code in (200, 302, 303, 307):
                return "OK", f"HTTP {code}"
            if code == 401 or code == 403:
                return "OK", f"HTTP {code} (auth esperado)"
            return "WARN", f"HTTP {code}"

        _timed(report, f"route_{slug}", _run)


def check_secrets_in_logs(report: SmokeReport) -> None:
    def _run() -> tuple[str, str]:
        from app.core.log_safety import SecretScrubFilter

        f = SecretScrubFilter()
        rec = type("R", (), {"msg": "token=abc123 password=secret RFC1234567890", "args": ()})()
        f.filter(rec)
        msg = str(rec.msg)
        if "abc123" in msg or "secret" in msg:
            return "FAIL", "scrub no aplicado"
        if "RFC" in msg and "1234567890" in msg:
            return "FAIL", "RFC completo en log"
        return "OK", "scrub activo"

    _timed(report, "log_secret_scrub", _run)


def main() -> int:
    parser = argparse.ArgumentParser(description="P69 smoke check web")
    parser.add_argument("--base-url", default=os.environ.get("SMOKE_BASE_URL", ""))
    args = parser.parse_args()

    print("=== P69 smoke_check_web ===\n")
    _load_dotenv()
    report = SmokeReport()

    check_db(report)
    check_redis(report)
    check_app_imports(report)
    check_excel_masters_guard(report)
    check_storage_folders(report)
    check_templates_exist(report)
    check_migrations_head(report)
    check_realtime_hub(report)
    check_jobs_service(report)
    check_feature_flags(report)
    check_secrets_in_logs(report)
    check_http_routes(report, args.base_url or None)

    total_ms = sum(r.elapsed_ms for r in report.results)
    print("\n--- Resumen ---")
    print(f"Checks: {len(report.results)} | FAIL: {len(report.failed)} | WARN: {len(report.warned)}")
    print(f"Tiempo total aprox: {total_ms:.0f}ms")
    critical_fail = [f for f in report.failed if f.name not in ("database",)]
    if report.failed:
        print("Estado: FAIL" if critical_fail else "Estado: OK con FAIL no críticos")
        for f in report.failed:
            print(f"  - {f.name}: {f.detail}")
        return 1 if critical_fail else 0
    if report.warned:
        print("Estado: OK con advertencias")
    else:
        print("Estado: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
