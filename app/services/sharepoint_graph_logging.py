"""Logging estructurado para operaciones Graph (P25.1)."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("app.sharepoint.graph")


def log_graph_operation(
    level: int,
    message: str,
    *,
    document_id: int | None = None,
    case_id: int | None = None,
    graph_request_id: str | None = None,
    upload_attempt: int | None = None,
    elapsed_ms: int | None = None,
    error_code: str | None = None,
    http_status: int | None = None,
    endpoint: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if document_id is not None:
        payload["document_id"] = document_id
    if case_id is not None:
        payload["case_id"] = case_id
    if graph_request_id:
        payload["graph_request_id"] = graph_request_id
    if upload_attempt is not None:
        payload["upload_attempt"] = upload_attempt
    if elapsed_ms is not None:
        payload["elapsed_ms"] = elapsed_ms
    if error_code:
        payload["error_code"] = error_code
    if http_status is not None:
        payload["http_status"] = http_status
    if endpoint:
        payload["endpoint"] = endpoint[:200]
    if extra:
        payload.update(extra)
    log.log(level, message, extra=payload or None)
