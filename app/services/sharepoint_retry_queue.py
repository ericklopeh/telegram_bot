from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

_LOCK = threading.Lock()


@dataclass
class RetryItem:
    id: str
    file_path: str
    vendedor: str
    semana: str
    cliente: str
    folio: str
    tipo_documento: str
    filename: str
    attempts: int
    last_error: str | None
    created_at: str
    updated_at: str


def _queue_file_path() -> Path:
    settings = get_settings()
    queue_dir = Path(settings.base_storage_path)
    queue_dir.mkdir(parents=True, exist_ok=True)
    return queue_dir / "sharepoint_retry_queue.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_raw() -> list[dict[str, Any]]:
    path = _queue_file_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_raw(items: list[dict[str, Any]]) -> None:
    path = _queue_file_path()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue_failed_upload(
    *,
    file_path: str,
    vendedor: str,
    semana: str,
    cliente: str,
    folio: str,
    tipo_documento: str,
    filename: str,
    error: str | None = None,
) -> str:
    with _LOCK:
        items = _load_raw()
        now = _now_iso()
        item_id = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}-{len(items)+1}"
        items.append(
            {
                "id": item_id,
                "file_path": file_path,
                "vendedor": vendedor,
                "semana": semana,
                "cliente": cliente,
                "folio": folio,
                "tipo_documento": tipo_documento,
                "filename": filename,
                "attempts": 0,
                "last_error": error,
                "created_at": now,
                "updated_at": now,
            }
        )
        _save_raw(items)
        return item_id


def list_retry_items() -> list[RetryItem]:
    with _LOCK:
        items = _load_raw()
    parsed: list[RetryItem] = []
    for item in items:
        try:
            parsed.append(
                RetryItem(
                    id=str(item["id"]),
                    file_path=str(item["file_path"]),
                    vendedor=str(item["vendedor"]),
                    semana=str(item["semana"]),
                    cliente=str(item["cliente"]),
                    folio=str(item["folio"]),
                    tipo_documento=str(item["tipo_documento"]),
                    filename=str(item["filename"]),
                    attempts=int(item.get("attempts", 0)),
                    last_error=item.get("last_error"),
                    created_at=str(item.get("created_at", "")),
                    updated_at=str(item.get("updated_at", "")),
                )
            )
        except Exception:
            continue
    return parsed


def update_retry_item(item_id: str, *, attempts: int, last_error: str | None) -> None:
    with _LOCK:
        items = _load_raw()
        for item in items:
            if str(item.get("id")) == item_id:
                item["attempts"] = attempts
                item["last_error"] = last_error
                item["updated_at"] = _now_iso()
                break
        _save_raw(items)


def remove_retry_item(item_id: str) -> None:
    with _LOCK:
        items = _load_raw()
        items = [item for item in items if str(item.get("id")) != item_id]
        _save_raw(items)
