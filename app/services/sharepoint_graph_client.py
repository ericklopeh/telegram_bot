"""Cliente Microsoft Graph para SharePoint/OneDrive (P25 / P25.1)."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import Settings, get_settings
from app.services.sharepoint_graph_errors import (
    GraphApiError,
    GraphConfigError,
    GraphErrorKind,
    GraphUploadError,
    graph_request_id,
    parse_graph_response,
)
from app.services.sharepoint_graph_logging import log_graph_operation
from app.services.sharepoint_graph_retry import RetryPolicy

# Reexport compat P25
__all__ = [
    "GraphUploadError",
    "GraphConfigError",
    "GraphApiError",
    "GraphUploadResult",
    "SharePointGraphClient",
    "sanitize_graph_name",
]

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
INVALID_NAME_CHARS = r'[~"#%&*:<>?/\\{|}]'
SPACE_RE = re.compile(r"\s+")
_GRAPH_CHUNK_UNIT = 320 * 1024  # 320 KiB — requisito Graph upload session

_CACHE_LOCK = threading.Lock()
_CACHED_SITE_ID: str | None = None
_CACHED_DRIVE_ID: str | None = None
_FOLDER_CACHE: dict[str, str] = {}
_LAST_TOKEN_OK_AT: datetime | None = None


@dataclass(frozen=True)
class GraphUploadResult:
    web_url: str | None
    item_id: str | None
    drive_id: str
    site_id: str | None
    folder_path: str
    name: str | None
    size_bytes: int | None = None


@dataclass
class GraphLogContext:
    document_id: int | None = None
    case_id: int | None = None
    upload_attempt: int = 1


def sanitize_graph_name(value: str) -> str:
    cleaned = value.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(INVALID_NAME_CHARS, " ", cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    return cleaned or "SIN_NOMBRE"


def aligned_chunk_size(settings: Settings | None = None) -> int:
    s = settings or get_settings()
    raw = max(s.ms_graph_upload_chunk_bytes, _GRAPH_CHUNK_UNIT)
    units = max(1, raw // _GRAPH_CHUNK_UNIT)
    return units * _GRAPH_CHUNK_UNIT


class SharePointGraphClient:
    """Wrapper Graph: token, carpetas, upload simple/sesión, retries y errores tipados."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._retry = RetryPolicy.from_settings(self.settings)

    @property
    def last_token_ok_at(self) -> datetime | None:
        return _LAST_TOKEN_OK_AT

    def validate_config(self) -> None:
        s = self.settings
        missing = []
        if not s.ms_tenant_id:
            missing.append("MS_TENANT_ID")
        if not s.ms_client_id:
            missing.append("MS_CLIENT_ID")
        if not s.ms_client_secret:
            missing.append("MS_CLIENT_SECRET")
        if not s.ms_root_folder:
            missing.append("MS_ROOT_FOLDER")
        if not s.ms_drive_id and not s.ms_drive_name:
            missing.append("MS_DRIVE_ID o MS_DRIVE_NAME")
        if not s.ms_site_id and (not s.ms_site_hostname or not s.ms_site_path):
            missing.append("MS_SITE_ID o MS_SITE_HOSTNAME+MS_SITE_PATH")
        if missing:
            raise GraphConfigError(
                f"Faltan variables de entorno para Microsoft Graph: {', '.join(missing)}"
            )

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        global _LAST_TOKEN_OK_AT
        self.validate_config()
        if force_refresh:
            pass  # client credentials: cada llamada obtiene token nuevo
        token_url = (
            f"https://login.microsoftonline.com/{self.settings.ms_tenant_id}/oauth2/v2.0/token"
        )
        payload = {
            "client_id": self.settings.ms_client_id,
            "client_secret": self.settings.ms_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        data = self._request_json(
            "POST",
            token_url,
            token=None,
            data_payload=payload,
            expected_status=(200,),
            log_ctx=None,
            allow_token_retry=False,
        )
        token = data.get("access_token", "")
        if not token:
            raise GraphUploadError("No se recibió access_token de Graph")
        with _CACHE_LOCK:
            _LAST_TOKEN_OK_AT = datetime.now(timezone.utc)
        return token

    def get_site_id(self, *, token: str | None = None) -> str:
        configured = (self.settings.ms_site_id or "").strip()
        if configured:
            return configured
        global _CACHED_SITE_ID
        with _CACHE_LOCK:
            if _CACHED_SITE_ID:
                return _CACHED_SITE_ID
        if not self.settings.ms_site_hostname or not self.settings.ms_site_path:
            raise GraphConfigError("Faltan MS_SITE_HOSTNAME/MS_SITE_PATH")
        tok = token or self.get_access_token()
        endpoint = f"{GRAPH_BASE}/sites/{self.settings.ms_site_hostname}:{self.settings.ms_site_path}"
        data = self._request_json("GET", endpoint, token=tok, log_ctx=None)
        site_id = data.get("id", "")
        if not site_id:
            raise GraphUploadError("No se encontró site_id")
        with _CACHE_LOCK:
            _CACHED_SITE_ID = site_id
        return site_id

    def get_drive_id(self, *, token: str | None = None) -> str:
        configured = (self.settings.ms_drive_id or "").strip()
        if configured:
            return configured
        global _CACHED_DRIVE_ID
        with _CACHE_LOCK:
            if _CACHED_DRIVE_ID:
                return _CACHED_DRIVE_ID
        if not self.settings.ms_drive_name:
            raise GraphConfigError("Falta MS_DRIVE_NAME")
        tok = token or self.get_access_token()
        site_id = self.get_site_id(token=tok)
        drives_data = self._request_json(
            "GET", f"{GRAPH_BASE}/sites/{site_id}/drives", token=tok, log_ctx=None
        )
        for drive in drives_data.get("value", []):
            if drive.get("name") == self.settings.ms_drive_name:
                drive_id = drive.get("id", "")
                if drive_id:
                    with _CACHE_LOCK:
                        _CACHED_DRIVE_ID = drive_id
                    return drive_id
        raise GraphUploadError(
            f"No se encontró drive con name={self.settings.ms_drive_name!r}"
        )

    def build_remote_documents_folder(self, case_relative_path: str) -> str:
        root = "/".join(
            sanitize_graph_name(p)
            for p in (self.settings.ms_root_folder or "").split("/")
            if p.strip()
        )
        rel = "/".join(
            sanitize_graph_name(p) for p in case_relative_path.split("/") if p.strip()
        )
        if not root:
            raise GraphConfigError("Falta MS_ROOT_FOLDER")
        return f"{root}/{rel}" if rel else root

    def probe_root_folder_readable(self, drive_id: str, *, token: str | None = None) -> bool:
        """Comprueba que la primera parte de MS_ROOT_FOLDER existe o es creable."""
        tok = token or self.get_access_token()
        parts = [
            sanitize_graph_name(p)
            for p in (self.settings.ms_root_folder or "").split("/")
            if p.strip()
        ]
        if not parts:
            return False
        endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root:/{parts[0]}"
        try:
            self._request_json("GET", endpoint, token=tok, expected_status=(200,), log_ctx=None)
            return True
        except GraphApiError as exc:
            if exc.parsed.kind == GraphErrorKind.NOT_FOUND:
                return False
            raise

    def probe_write_permission(
        self, drive_id: str, folder_path: str, *, token: str | None = None
    ) -> bool:
        """Sube un archivo de prueba mínimo (.healthcheck) y lo elimina si es posible."""
        tok = token or self.get_access_token()
        probe_name = f".gaman_healthcheck_{int(time.time())}.txt"
        probe_bytes = b"healthcheck"
        try:
            self.ensure_folder_path(drive_id, folder_path, token=tok)
            result = self._upload_small(
                drive_id, folder_path, probe_name, probe_bytes, token=tok, log_ctx=None
            )
            item_id = result.get("id")
            if item_id:
                del_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}"
                try:
                    self._raw_http(
                        "DELETE", del_url, headers={"Authorization": f"Bearer {tok}"}, log_ctx=None
                    )
                except GraphUploadError:
                    pass
            return bool(result.get("id"))
        except GraphUploadError:
            return False

    def ensure_folder_path(
        self, drive_id: str, folder_path: str, *, token: str | None = None
    ) -> str:
        tok = token or self.get_access_token()
        sanitized_parts = [
            sanitize_graph_name(part) for part in folder_path.split("/") if part.strip()
        ]
        if not sanitized_parts:
            raise GraphUploadError("folder_path vacío")
        full_target = "/".join(sanitized_parts)
        with _CACHE_LOCK:
            if _FOLDER_CACHE.get(full_target):
                return full_target

        current_path = sanitized_parts[0]
        root_children_endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
        root_children = self._request_json(
            "GET", root_children_endpoint, token=tok, log_ctx=None
        )
        current_id = ""
        for item in root_children.get("value", []):
            if item.get("name") == current_path and "folder" in item:
                current_id = item.get("id", "")
                break
        if not current_id:
            payload = {
                "name": current_path,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "replace",
            }
            created = self._request_json(
                "POST",
                root_children_endpoint,
                token=tok,
                json_payload=payload,
                expected_status=(200, 201),
                log_ctx=None,
            )
            current_id = created.get("id", "")

        for part in sanitized_parts[1:]:
            current_path, current_id = self._ensure_child_folder(
                drive_id, current_id, current_path, part, token=tok
            )
        with _CACHE_LOCK:
            _FOLDER_CACHE[full_target] = current_id
        return full_target

    def upload_file(
        self,
        folder_path: str,
        filename: str,
        file_bytes: bytes,
        *,
        drive_id: str | None = None,
        token: str | None = None,
        log_ctx: GraphLogContext | None = None,
    ) -> GraphUploadResult:
        started = time.perf_counter()
        self.validate_config()
        size = len(file_bytes)
        tok = token or self.get_access_token()
        drive = drive_id or self.get_drive_id(token=tok)
        site_id = self.get_site_id(token=tok)
        self.ensure_folder_path(drive, folder_path, token=tok)
        clean_name = sanitize_graph_name(filename)
        raw_threshold = getattr(self.settings, "ms_graph_small_file_max_bytes", 4 * 1024 * 1024)
        try:
            threshold = int(raw_threshold)
        except (TypeError, ValueError):
            threshold = 4 * 1024 * 1024
        try:
            if size <= threshold:
                data = self._upload_small(
                    drive, folder_path, clean_name, file_bytes, token=tok, log_ctx=log_ctx
                )
            else:
                data = self._upload_large(
                    drive, folder_path, clean_name, file_bytes, token=tok, log_ctx=log_ctx
                )
            self._validate_upload_commit(data, expected_size=size)
        except GraphUploadError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            log_graph_operation(
                logging.ERROR,
                "graph_upload_failed",
                document_id=log_ctx.document_id if log_ctx else None,
                case_id=log_ctx.case_id if log_ctx else None,
                upload_attempt=log_ctx.upload_attempt if log_ctx else None,
                elapsed_ms=elapsed,
                error_code=getattr(exc, "error_code", None),
                endpoint=folder_path,
            )
            raise
        elapsed = int((time.perf_counter() - started) * 1000)
        log_graph_operation(
            logging.INFO,
            "graph_upload_ok",
            document_id=log_ctx.document_id if log_ctx else None,
            case_id=log_ctx.case_id if log_ctx else None,
            upload_attempt=log_ctx.upload_attempt if log_ctx else None,
            elapsed_ms=elapsed,
            extra={"size_bytes": size, "folder_path": folder_path},
        )
        clean_folder = "/".join(
            sanitize_graph_name(p) for p in folder_path.split("/") if p.strip()
        )
        return GraphUploadResult(
            web_url=data.get("webUrl"),
            item_id=data.get("id"),
            drive_id=drive,
            site_id=site_id,
            folder_path=f"{clean_folder}/{clean_name}",
            name=data.get("name"),
            size_bytes=data.get("size") or size,
        )

    @staticmethod
    def _validate_upload_commit(data: dict[str, Any], *, expected_size: int) -> None:
        if not data.get("id"):
            raise GraphUploadError("Upload incompleto: Graph no devolvió item id")
        remote_size = data.get("size")
        if remote_size is not None and int(remote_size) != expected_size:
            raise GraphUploadError(
                f"Upload incompleto: tamaño remoto {remote_size} != local {expected_size}"
            )

    def _upload_small(
        self,
        drive_id: str,
        folder_path: str,
        filename: str,
        file_bytes: bytes,
        *,
        token: str,
        log_ctx: GraphLogContext | None,
    ) -> dict[str, Any]:
        clean_folder = "/".join(
            sanitize_graph_name(p) for p in folder_path.split("/") if p.strip()
        )
        endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_folder}/{filename}:/content"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        response = self._raw_http(
            "PUT",
            endpoint,
            headers=headers,
            data=file_bytes,
            timeout=self.settings.ms_graph_upload_timeout,
            log_ctx=log_ctx,
        )
        if response.status_code not in (200, 201):
            self._raise_api_error(response, endpoint)
        return response.json()

    def _upload_large(
        self,
        drive_id: str,
        folder_path: str,
        filename: str,
        file_bytes: bytes,
        *,
        token: str,
        log_ctx: GraphLogContext | None,
    ) -> dict[str, Any]:
        clean_folder = "/".join(
            sanitize_graph_name(p) for p in folder_path.split("/") if p.strip()
        )
        session_endpoint = (
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_folder}/{filename}:/createUploadSession"
        )
        session = self._request_json(
            "POST",
            session_endpoint,
            token=token,
            json_payload={
                "item": {
                    "@microsoft.graph.conflictBehavior": "replace",
                    "name": filename,
                }
            },
            expected_status=(200, 201),
            log_ctx=log_ctx,
        )
        upload_url = session.get("uploadUrl")
        if not upload_url:
            raise GraphUploadError("createUploadSession sin uploadUrl")

        size = len(file_bytes)
        chunk_size = aligned_chunk_size(self.settings)
        start = 0
        result: dict[str, Any] = {}
        chunk_index = 0

        while start < size:
            end = min(start + chunk_size, size) - 1
            chunk_len = end - start + 1
            headers = {
                "Content-Length": str(chunk_len),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            response = self._upload_chunk_with_retry(
                upload_url, headers, file_bytes[start : end + 1], log_ctx=log_ctx, chunk_index=chunk_index
            )
            if response.status_code in (200, 201):
                result = response.json()
                break
            if response.status_code != 202:
                self._raise_api_error(response, upload_url)
            start = end + 1
            chunk_index += 1

        if not result.get("id") and start >= size:
            raise GraphUploadError("Sesión de upload finalizada sin respuesta de commit")
        return result

    def _upload_chunk_with_retry(
        self,
        upload_url: str,
        headers: dict[str, str],
        chunk: bytes,
        *,
        log_ctx: GraphLogContext | None,
        chunk_index: int,
    ) -> requests.Response:
        policy = self._retry
        last_response: requests.Response | None = None
        for attempt in range(policy.max_attempts):
            try:
                response = requests.put(
                    upload_url,
                    headers=headers,
                    data=chunk,
                    timeout=self.settings.ms_graph_upload_timeout,
                )
                last_response = response
                if response.status_code in (200, 201, 202):
                    return response
                parsed = parse_graph_response(response)
                if not parsed.retryable or attempt >= policy.max_attempts - 1:
                    raise GraphApiError(parsed, endpoint=upload_url)
                retry_after = None
                if parsed.status_code == 429:
                    ra = response.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        retry_after = float(ra)
                log_graph_operation(
                    logging.WARNING,
                    "graph_upload_chunk_retry",
                    document_id=log_ctx.document_id if log_ctx else None,
                    case_id=log_ctx.case_id if log_ctx else None,
                    upload_attempt=log_ctx.upload_attempt if log_ctx else None,
                    error_code=parsed.error_code,
                    http_status=parsed.status_code,
                    graph_request_id=parsed.request_id,
                    extra={"chunk_index": chunk_index, "attempt": attempt + 1},
                )
                policy.sleep_before_retry(attempt, retry_after=retry_after)
            except requests.Timeout as exc:
                if attempt >= policy.max_attempts - 1:
                    raise GraphUploadError(
                        f"Timeout subiendo fragmento {chunk_index}: {exc}"
                    ) from exc
                policy.sleep_before_retry(attempt)
            except requests.RequestException as exc:
                if attempt >= policy.max_attempts - 1:
                    raise GraphUploadError(f"Error de red en fragmento: {exc}") from exc
                policy.sleep_before_retry(attempt)
        if last_response is not None:
            self._raise_api_error(last_response, upload_url)
        raise GraphUploadError("Fallo de upload por sesión sin respuesta")

    def _ensure_child_folder(
        self,
        drive_id: str,
        parent_id: str,
        parent_path: str,
        folder_name: str,
        *,
        token: str,
    ) -> tuple[str, str]:
        children_endpoint = f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}/children"
        folder_name_clean = sanitize_graph_name(folder_name)
        children = self._request_json("GET", children_endpoint, token=token, log_ctx=None)
        for item in children.get("value", []):
            if item.get("name") == folder_name_clean and "folder" in item:
                return f"{parent_path}/{folder_name_clean}", item.get("id", "")
        payload = {
            "name": folder_name_clean,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace",
        }
        created = self._request_json(
            "POST",
            children_endpoint,
            token=token,
            json_payload=payload,
            expected_status=(200, 201),
            log_ctx=None,
        )
        return f"{parent_path}/{folder_name_clean}", created.get("id", "")

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        token: str | None,
        json_payload: dict | None = None,
        data_payload: dict | None = None,
        expected_status: tuple[int, ...] | None = None,
        log_ctx: GraphLogContext | None = None,
        allow_token_retry: bool = True,
    ) -> dict[str, Any]:
        expected = expected_status or (200,)
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self._raw_http(
            method,
            endpoint,
            headers=headers,
            json=json_payload,
            data=data_payload,
            timeout=self.settings.ms_graph_request_timeout,
            log_ctx=log_ctx,
            allow_token_retry=allow_token_retry,
            bearer_token=token,
        )
        if response.status_code not in expected:
            self._raise_api_error(response, endpoint)
        if not response.text:
            return {}
        return response.json()

    def _raw_http(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        data: dict | bytes | None = None,
        timeout: int | None = None,
        log_ctx: GraphLogContext | None = None,
        allow_token_retry: bool = True,
        bearer_token: str | None = None,
    ) -> requests.Response:
        policy = self._retry
        timeout = timeout or self.settings.ms_graph_request_timeout
        refreshed_token = False

        for attempt in range(policy.max_attempts):
            try:
                response = requests.request(
                    method, endpoint, headers=headers, json=json, data=data, timeout=timeout
                )
            except requests.Timeout as exc:
                log_graph_operation(
                    logging.WARNING,
                    "graph_timeout",
                    document_id=log_ctx.document_id if log_ctx else None,
                    case_id=log_ctx.case_id if log_ctx else None,
                    upload_attempt=log_ctx.upload_attempt if log_ctx else None,
                    error_code="timeout",
                    extra={"attempt": attempt + 1},
                )
                if attempt >= policy.max_attempts - 1:
                    raise GraphUploadError(f"Timeout Graph: {exc}") from exc
                policy.sleep_before_retry(attempt)
                continue
            except requests.RequestException as exc:
                log_graph_operation(
                    logging.WARNING,
                    "graph_network_error",
                    document_id=log_ctx.document_id if log_ctx else None,
                    case_id=log_ctx.case_id if log_ctx else None,
                    error_code="network",
                    extra={"attempt": attempt + 1},
                )
                if attempt >= policy.max_attempts - 1:
                    raise GraphUploadError(f"Error de red Graph: {exc}") from exc
                policy.sleep_before_retry(attempt)
                continue

            if response.status_code == 401 and allow_token_retry and bearer_token and not refreshed_token:
                refreshed_token = True
                new_token = self.get_access_token(force_refresh=True)
                if headers and "Authorization" in headers:
                    headers = dict(headers)
                    headers["Authorization"] = f"Bearer {new_token}"
                log_graph_operation(
                    logging.INFO,
                    "graph_token_refreshed",
                    document_id=log_ctx.document_id if log_ctx else None,
                    case_id=log_ctx.case_id if log_ctx else None,
                )
                continue

            parsed = parse_graph_response(response)
            if parsed.retryable and attempt < policy.max_attempts - 1:
                retry_after = None
                if parsed.status_code == 429:
                    ra = response.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        retry_after = float(ra)
                log_graph_operation(
                    logging.WARNING,
                    "graph_retry",
                    document_id=log_ctx.document_id if log_ctx else None,
                    case_id=log_ctx.case_id if log_ctx else None,
                    graph_request_id=parsed.request_id,
                    error_code=parsed.error_code,
                    http_status=parsed.status_code,
                    upload_attempt=log_ctx.upload_attempt if log_ctx else None,
                    extra={"attempt": attempt + 1},
                )
                policy.sleep_before_retry(attempt, retry_after=retry_after)
                continue
            return response

        raise GraphUploadError("Graph: agotados reintentos HTTP")

    @staticmethod
    def _raise_api_error(response: requests.Response, endpoint: str) -> None:
        parsed = parse_graph_response(response)
        log_graph_operation(
            logging.ERROR,
            "graph_api_error",
            graph_request_id=parsed.request_id,
            error_code=parsed.error_code,
            http_status=parsed.status_code,
            endpoint=endpoint[:200],
        )
        raise GraphApiError(parsed, endpoint=endpoint)
