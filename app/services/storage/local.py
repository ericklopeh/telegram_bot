from __future__ import annotations

import os
from pathlib import Path


class LocalStorageBackend:
    """
    Backend de almacenamiento local.

    - Si `base_path` se define, todas las rutas relativas se guardan bajo esa carpeta.
    - Si no se define, usa `STORAGE_BASE_PATH` del entorno.
    - Si tampoco existe en entorno, opera con rutas tal cual se reciben.
    """

    def __init__(self, base_path: str | Path | None = None) -> None:
        raw_base = base_path if base_path is not None else os.getenv("STORAGE_BASE_PATH")
        self.base_path = Path(raw_base).expanduser() if raw_base else None
        if self.base_path is not None:
            self.base_path.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute() or self.base_path is None:
            return candidate
        return self.base_path / candidate

    def ensure_dir(self, path: str | Path) -> Path:
        directory = self.resolve_path(path)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_bytes(self, relative_path: str | Path, content: bytes) -> Path:
        file_path = self.resolve_path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return file_path
