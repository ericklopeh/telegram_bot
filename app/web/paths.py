"""Rutas absolutas del paquete web (independientes del cwd de uvicorn)."""

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = str(WEB_DIR / "templates")
STATIC_DIR = str(WEB_DIR / "static")
