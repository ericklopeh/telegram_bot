"""
Prueba rápida de conexión a PostgreSQL usando DATABASE_URL (misma config que la app).

Uso (desde la raíz del repo):
  python scripts/test_db_connection.py

Con Docker (bot ya levantado):
  docker compose exec bot python scripts/test_db_connection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Al ejecutar `python scripts/...py`, sys.path[0] es `scripts/`; hace falta la raíz para `import app`.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from app.config import get_settings

        url = get_settings().sqlalchemy_database_uri
        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            one = conn.execute(text("SELECT 1")).scalar_one()
        if one != 1:
            print(f"ERROR: SELECT 1 devolvió {one!r}, se esperaba 1.")
            return 1
    except Exception as exc:
        print("ERROR: fallo al probar PostgreSQL (config o conexión).")
        print(type(exc).__name__, str(exc))
        return 1

    print("OK: conexión a PostgreSQL correcta (SELECT 1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
