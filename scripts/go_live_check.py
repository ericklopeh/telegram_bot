#!/usr/bin/env python3
"""P70 — validación go-live antes de producción."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ok(msg: str) -> None:
    print(f"OK   {msg}")


def warn(msg: str) -> None:
    print(f"WARN {msg}")


def fail(msg: str) -> None:
    print(f"FAIL {msg}")


def main() -> int:
    print("=== P70 go_live_check ===\n")
    fails = 0

    prod_compose = ROOT / "docker-compose.prod.yml"
    if prod_compose.is_file():
        ok("docker-compose.prod.yml")
    else:
        fail("docker-compose.prod.yml ausente")
        fails += 1

    for script in ("prod_backup.sh", "prod_restore.sh", "prod_verify_backup.sh", "smoke_check_web.py"):
        if (ROOT / "scripts" / script).is_file():
            ok(f"script {script}")
        else:
            fail(f"script {script}")
            fails += 1

    env_example = ROOT / ".env.example"
    if env_example.is_file():
        text = env_example.read_text(encoding="utf-8")
        for key in ("WEB_DEBUG=false", "SENTRY_DSN", "REDIS_URL", "SECURE_COOKIES"):
            if key.split("=")[0] in text:
                ok(f".env.example tiene {key.split('=')[0]}")
            else:
                warn(f".env.example sin {key.split('=')[0]}")
    else:
        fail(".env.example")
        fails += 1

    try:
        from app.config import Settings

        s = Settings(
            TELEGRAM_BOT_TOKEN="x",
            DATABASE_URL="postgresql+psycopg://u:p@localhost/db",
            ENVIRONMENT="production",
            WEB_DEBUG=False,
        )
        assert s.web_debug is False
        assert s.session_https_only is True
        ok("Settings production defaults")
    except Exception as exc:
        fail(f"Settings: {exc}")
        fails += 1

    try:
        from app.observability.metrics import build_prometheus_text

        body = build_prometheus_text()
        assert "gaman_up" in body
        ok("/metrics exposition")
    except Exception as exc:
        fail(f"metrics: {exc}")
        fails += 1

    try:
        from app.services.redis_client import get_redis_enterprise

        r = get_redis_enterprise()
        if r.ping():
            ok("Redis ping")
        else:
            warn("Redis no configurado o no responde (opcional)")
    except Exception as exc:
        warn(f"Redis: {exc}")

    nginx_prod = ROOT / "nginx" / "app.prod.conf"
    if nginx_prod.is_file() and "ws/" in nginx_prod.read_text(encoding="utf-8"):
        ok("nginx websocket prod")
    else:
        fail("nginx app.prod.conf websocket")
        fails += 1

    try:
        importlib.import_module("app.workers.worker_main")
        importlib.import_module("app.workers.scheduler_main")
        ok("workers importables")
    except Exception as exc:
        fail(f"workers: {exc}")
        fails += 1

    if (ROOT / "scripts" / "smoke_check_web.py").is_file():
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke_check_web.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            ok("smoke_check_web")
        else:
            warn("smoke_check_web con advertencias/fallos (revisar salida)")
            print(proc.stdout[-800:] if proc.stdout else proc.stderr[-800:])

    print()
    if fails:
        print(f"Go-live: NO LISTO ({fails} fallos críticos)")
        return 1
    print("Go-live: LISTO (revisar WARN)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
