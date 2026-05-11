#!/usr/bin/env python3
"""
Smoke check: validar imports, plantillas y variables de entorno mínimas
sin levantar servidores ni imprimir secretos.

Uso (desde la raíz del repo):
    python scripts/smoke_check.py

Código de salida: 0 OK, 1 fallo crítico.
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Permite ejecutar `python scripts/smoke_check.py` desde cualquier cwd (Windows/Linux).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ok(msg: str) -> None:
    print(f"OK   {msg}")


def fail(msg: str) -> None:
    print(f"FAIL {msg}")


def warn(msg: str) -> None:
    print(f"WARN {msg}")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        warn("python-dotenv no disponible; solo variables de entorno del proceso")
        return
    path = ROOT / ".env"
    if path.is_file():
        load_dotenv(path)
        ok(f".env cargado ({path.relative_to(ROOT)})")
    else:
        warn(f"No existe {path.relative_to(ROOT)}; usando solo entorno del sistema")


def _env_nonempty(name: str) -> tuple[bool, int]:
    raw = os.environ.get(name, "")
    s = raw.strip().strip('"').strip("'")
    return (bool(s), len(s))


def check_env() -> bool:
    """Variables requeridas sin mostrar valores."""
    good = True
    for var in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN"):
        present, length = _env_nonempty(var)
        if present:
            ok(f"{var} definida (longitud={length})")
        else:
            fail(f"Falta o está vacía: {var}")
            good = False

    # Sesión web: la app usa WEB_SESSION_SECRET; se acepta SESSION_SECRET_KEY como alias de chequeo.
    session_keys = ("WEB_SESSION_SECRET", "SESSION_SECRET_KEY")
    session_ok = False
    used: str | None = None
    for key in session_keys:
        present, length = _env_nonempty(key)
        if present:
            session_ok = True
            used = key
            ok(f"Secreto de sesión presente vía {key} (longitud={length})")
            break
    if not session_ok:
        fail("Falta WEB_SESSION_SECRET o SESSION_SECRET_KEY (definir al menos uno, no vacío)")
        good = False
    elif used == "SESSION_SECRET_KEY":
        warn(
            "La app FastAPI usa WEB_SESSION_SECRET en runtime; "
            "SESSION_SECRET_KEY solo pasó el smoke — unifica en .env si la web no arranca."
        )
    return good


_MASTER_XLSX = Path("storage") / "templates" / "plantilla_master_autorizaciones.xlsx"

_MASTER_HINT = (
    "Copia plantilla_master_autorizaciones.xlsx desde el repo / paquete de autorización SNTE de "
    "referencia a storage/templates/ (mismo nombre de archivo). "
    "Documentación: docs/SNTE_MODULE.md (secciones 3–4). "
    "Si en tu equipo el maestro está en otra ruta (p. ej. E:\\dev\\autorizacion_snte u otro "
    "directorio interno), copia el .xlsx desde allí sin renombrarlo."
)


def check_templates() -> bool:
    rels = (
        Path("storage") / "templates" / "plantilla_orden_snte.pdf",
        Path("storage") / "templates" / "plantilla_refinanciamiento.xlsx",
        _MASTER_XLSX,
    )
    good = True
    for rel in rels:
        p = ROOT / rel
        if p.is_file():
            ok(f"Plantilla {rel.as_posix()}")
        else:
            fail(f"Plantilla ausente: {rel.as_posix()}")
            if rel == _MASTER_XLSX:
                warn(_MASTER_HINT)
            good = False
    return good


def check_imports() -> bool:
    modules = (
        "app.main",
        "app.web.main",
        "app.api.main",
        "app.services.authorization_service",
        "app.services.refinanciamiento_service",
        "app.services.document_service",
        "app.services.case_service",
        "app.services.notification_service",
    )
    good = True
    for name in modules:
        try:
            importlib.import_module(name)
            ok(f"import {name}")
        except Exception as exc:
            fail(f"import {name}: {type(exc).__name__}: {exc}")
            good = False
    return good


def _database_url_uses_docker_db_host(url: str) -> bool:
    """True si el host parece el servicio interno `db` de Compose (no resuelve fuera de Docker)."""
    u = url.strip().strip('"').strip("'")
    if re.search(r"[@/]db(?::|/)", u, re.IGNORECASE):
        return True
    if re.search(r"://db(?::|/)", u, re.IGNORECASE):
        return True
    return False


def _short_db_error(exc: Exception) -> str:
    raw = str(exc).strip().splitlines()
    return raw[0][:240] if raw else type(exc).__name__


def check_db() -> bool:
    present, _ = _env_nonempty("DATABASE_URL")
    if not present:
        warn("DATABASE_URL ausente; se omite SELECT 1")
        return True
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        fail("sqlalchemy no disponible para prueba DB")
        return False
    url = os.environ["DATABASE_URL"].strip().strip('"').strip("'")
    docker_db = _database_url_uses_docker_db_host(url)
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        ok("SELECT 1 en base de datos")
        return True
    except Exception as exc:
        fail(f"Conexión DB / SELECT 1 falló: {_short_db_error(exc)}")
        if docker_db:
            warn(
                'El host "db" solo resuelve dentro de la red de Docker Compose. '
                "Desde PowerShell en Windows (fuera del contenedor) usa localhost y el puerto "
                "mapeado (p. ej. :5433 según README) o ejecuta: docker compose up -d db "
                "y prueba de nuevo. No se modifica .env desde este script."
            )
        else:
            warn(
                "Revisa credenciales, firewall y que PostgreSQL esté escuchando en el host/puerto "
                "indicados en DATABASE_URL."
            )
        return False


def check_alembic(*, db_connected: bool) -> None:
    """Informativo: no falla el smoke. `current` requiere DB; `heads` no."""
    # alembic current → consulta DB; evita stderr largo si la DB no está
    if not db_connected:
        warn("alembic current no ejecutado: la base de datos no respondió al SELECT 1.")
    else:
        _run_alembic(("current",))

    _run_alembic(("heads",))


def _run_alembic(cmd: tuple[str, ...]) -> None:
    label = " ".join(cmd)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", *cmd],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except FileNotFoundError:
        warn("alembic: intérprete no encontrado")
        return
    except subprocess.TimeoutExpired:
        warn(f"alembic {label}: timeout")
        return
    if proc.returncode != 0:
        warn(f"alembic {label} falló (exit={proc.returncode}). Revisa entorno o versión de Alembic.")
        return
    ok(f"alembic {label}")
    out = (proc.stdout or "").strip()
    if out:
        for line in out.splitlines()[:8]:
            print(f"     {line}")


def main() -> int:
    print("=== smoke_check sistema_gaman ===\n")
    _load_dotenv()

    checks: list[tuple[str, bool]] = []

    checks.append(("env", check_env()))
    checks.append(("templates", check_templates()))

    # Imports dependen de env válido para Settings en app.web.main
    if checks[0][1]:
        checks.append(("imports", check_imports()))
    else:
        fail("Se omiten imports por fallo de variables de entorno")
        checks.append(("imports", False))

    db_ok = False
    if checks[0][1]:
        db_ok = check_db()
        checks.append(("database", db_ok))
    else:
        checks.append(("database", True))

    print()
    check_alembic(db_connected=db_ok)

    critical = [name for name, ok_flag in checks if not ok_flag]
    print()
    if critical:
        print(f"Resultado: FAIL (fallos en: {', '.join(critical)})")
        return 1
    print("Resultado: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
