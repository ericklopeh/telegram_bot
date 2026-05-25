"""Errores Microsoft Graph tipados y mensajes sanitizados (P25.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

_SECRET_PATTERNS = (
    re.compile(r"(access_token|refresh_token|client_secret)[\"']?\s*[:=]\s*[\"']?[\w\-\.]+", re.I),
    re.compile(r"Bearer\s+[\w\-\.]+", re.I),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
)


class GraphErrorKind(str, Enum):
    CONFIG = "config"
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    NETWORK = "network"
    CLIENT = "client"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedGraphError:
    status_code: int
    kind: GraphErrorKind
    error_code: str
    message: str
    request_id: str | None
    retryable: bool


def _redact_secrets(text: str) -> str:
    out = text or ""
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out[:500]


def graph_request_id(response: requests.Response) -> str | None:
    return (
        response.headers.get("request-id")
        or response.headers.get("client-request-id")
        or response.headers.get("x-ms-request-id")
    )


def parse_graph_response(response: requests.Response) -> ParsedGraphError:
    status = response.status_code
    request_id = graph_request_id(response)
    error_code = "unknown"
    raw_message = ""
    try:
        if response.text:
            payload = response.json()
            err = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(err, dict):
                error_code = str(err.get("code") or error_code)
                raw_message = str(err.get("message") or "")
    except (json.JSONDecodeError, TypeError):
        raw_message = (response.text or "")[:300]

    message = _redact_secrets(raw_message) or f"HTTP {status}"
    kind, retryable = _classify(status, error_code)
    return ParsedGraphError(
        status_code=status,
        kind=kind,
        error_code=error_code,
        message=message,
        request_id=request_id,
        retryable=retryable,
    )


def _classify(status: int, error_code: str) -> tuple[GraphErrorKind, bool]:
    code_lower = (error_code or "").lower()
    if status == 401 or "InvalidAuthenticationToken" in error_code:
        return GraphErrorKind.AUTH, False
    if status == 403 or "accessdenied" in code_lower:
        return GraphErrorKind.FORBIDDEN, False
    if status == 404 or "itemnotfound" in code_lower or "notfound" in code_lower:
        return GraphErrorKind.NOT_FOUND, False
    if status == 409 or "namealreadyexists" in code_lower or "conflict" in code_lower:
        return GraphErrorKind.CONFLICT, False
    if status == 429 or "activitylimitreached" in code_lower:
        return GraphErrorKind.RATE_LIMIT, True
    if status >= 500:
        return GraphErrorKind.TRANSIENT, True
    if 400 <= status < 500:
        return GraphErrorKind.CLIENT, False
    return GraphErrorKind.UNKNOWN, False


class GraphUploadError(RuntimeError):
    """Error controlado Graph (compatible P25)."""


class GraphConfigError(GraphUploadError):
    """Configuración incompleta."""


class GraphApiError(GraphUploadError):
    """Error HTTP Graph con metadatos para logs y UI."""

    def __init__(self, parsed: ParsedGraphError, *, endpoint: str = "") -> None:
        self.parsed = parsed
        self.endpoint = endpoint
        user_msg = self.user_message
        super().__init__(user_msg)

    @property
    def user_message(self) -> str:
        p = self.parsed
        hints = {
            GraphErrorKind.AUTH: "Token inválido o expirado (401). Revise credenciales Entra ID.",
            GraphErrorKind.FORBIDDEN: "Permisos insuficientes (403). Conceda Sites.ReadWrite.All o Files.ReadWrite.All.",
            GraphErrorKind.NOT_FOUND: "Recurso no encontrado (404). Verifique MS_ROOT_FOLDER, site y drive.",
            GraphErrorKind.CONFLICT: "Conflicto de nombre (409). El archivo o carpeta ya existe.",
            GraphErrorKind.RATE_LIMIT: "Límite de Graph (429). Reintente en unos segundos.",
            GraphErrorKind.TRANSIENT: f"Error temporal de Microsoft ({p.status_code}).",
            GraphErrorKind.NETWORK: "Timeout o error de red hacia Microsoft Graph.",
        }
        base = hints.get(p.kind, f"Error Graph {p.status_code}")
        detail = f" [{p.error_code}] {p.message}" if p.message else ""
        rid = f" (request-id: {p.request_id})" if p.request_id else ""
        return f"{base}{detail}{rid}"

    @property
    def retryable(self) -> bool:
        return self.parsed.retryable

    @property
    def error_code(self) -> str:
        return self.parsed.error_code

    @property
    def status_code(self) -> int:
        return self.parsed.status_code

    @property
    def request_id(self) -> str | None:
        return self.parsed.request_id
