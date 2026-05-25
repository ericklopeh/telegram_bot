"""Cliente Microsoft Graph para SharePoint/OneDrive (P25)."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
INVALID_NAME_CHARS = r'[~"#%&*:<>?/\\{|}]'
SPACE_RE = re.compile(r"\s+")
_SMALL_FILE_MAX_BYTES = 4 * 1024 * 1024
_DEFAULT_TIMEOUT = 30
_UPLOAD_TIMEOUT = 120
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3

_CACHE_LOCK = threading.Lock()
_CACHED_SITE_ID: str | None = None
_CACHED_DRIVE_ID: str | None = None
_FOLDER_CACHE: dict[str, str] = {}


class GraphUploadError(RuntimeError):
    """Error controlado para fallos de Microsoft Graph."""


class GraphConfigError(GraphUploadError):
    """Configuración Graph incompleta o inválida."""


@dataclass(frozen=True)
class GraphUploadResult:
    web_url: str | None
    item_id: str | None
    drive_id: str
    site_id: str | None
    folder_path: str
    name: str | None


def sanitize_graph_name(value: str) -> str:
    cleaned = value.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(INVALID_NAME_CHARS, " ", cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    return cleaned or "SIN_NOMBRE"


class SharePointGraphClient:
    """Wrapper Graph con token, carpetas y subida (simple o por sesión)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

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

    def get_access_token(self) -> str:
        self.validate_config()
        token_url = (
            f"https://login.microsoftonline.com/{self.settings.ms_tenant_id}/oauth2/v2.0/token"
        )
        payload = {
            "client_id": self.settings.ms_client_id,
            "client_secret": self.settings.ms_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        data = self._request(
            "POST",
            token_url,
            token=None,
            data_payload=payload,
            expected_status=(200,),
            timeout=_DEFAULT_TIMEOUT,
        )
        token = data.get("access_token", "")
        if not token:
            raise GraphUploadError("No se recibió access_token de Graph")
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
        data = self._request("GET", endpoint, token=tok, expected_status=(200,))
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
        drives_data = self._request(
            "GET", f"{GRAPH_BASE}/sites/{site_id}/drives", token=tok, expected_status=(200,)
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
        """MS_ROOT_FOLDER + ruta relativa P24 (year/SEM_.../documents)."""
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

    def ensure_folder_path(self, drive_id: str, folder_path: str, *, token: str | None = None) -> str:
        tok = token or self.get_access_token()
        sanitized_parts = [
            sanitize_graph_name(part) for part in folder_path.split("/") if part.strip()
        ]
        if not sanitized_parts:
            raise GraphUploadError("folder_path vacío")
        full_target = "/".join(sanitized_parts)
        with _CACHE_LOCK:
            cached = _FOLDER_CACHE.get(full_target)
        if cached:
            return full_target

        current_path = sanitized_parts[0]
        root_children_endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
        root_children = self._request("GET", root_children_endpoint, token=tok, expected_status=(200,))
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
            created = self._request(
                "POST", root_children_endpoint, token=tok, json_payload=payload, expected_status=(201,)
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
    ) -> GraphUploadResult:
        self.validate_config()
        tok = token or self.get_access_token()
        drive = drive_id or self.get_drive_id(token=tok)
        site_id = self.get_site_id(token=tok)
        self.ensure_folder_path(drive, folder_path, token=tok)
        clean_name = sanitize_graph_name(filename)
        if len(file_bytes) <= _SMALL_FILE_MAX_BYTES:
            data = self._upload_small(drive, folder_path, clean_name, file_bytes, token=tok)
        else:
            data = self._upload_large(drive, folder_path, clean_name, file_bytes, token=tok)
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
        )

    def _upload_small(
        self, drive_id: str, folder_path: str, filename: str, file_bytes: bytes, *, token: str
    ) -> dict[str, Any]:
        clean_folder = "/".join(
            sanitize_graph_name(p) for p in folder_path.split("/") if p.strip()
        )
        endpoint = (
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_folder}/{filename}:/content"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        response = self._raw_request(
            "PUT", endpoint, headers=headers, data=file_bytes, timeout=_UPLOAD_TIMEOUT
        )
        if response.status_code not in (200, 201):
            self._raise_from_response(response, endpoint)
        return response.json()

    def _upload_large(
        self, drive_id: str, folder_path: str, filename: str, file_bytes: bytes, *, token: str
    ) -> dict[str, Any]:
        clean_folder = "/".join(
            sanitize_graph_name(p) for p in folder_path.split("/") if p.strip()
        )
        session_endpoint = (
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_folder}/{filename}:/createUploadSession"
        )
        session = self._request(
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
        )
        upload_url = session.get("uploadUrl")
        if not upload_url:
            raise GraphUploadError("createUploadSession sin uploadUrl")
        size = len(file_bytes)
        chunk = 320 * 1024 * 10  # 3.2 MB
        start = 0
        result: dict[str, Any] = {}
        while start < size:
            end = min(start + chunk, size) - 1
            headers = {
                "Content-Length": str(end - start + 1),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            response = requests.put(
                upload_url,
                headers=headers,
                data=file_bytes[start : end + 1],
                timeout=_UPLOAD_TIMEOUT,
            )
            if response.status_code in (200, 201):
                result = response.json()
                break
            if response.status_code not in (202,):
                self._raise_from_response(response, upload_url)
            start = end + 1
        return result

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
        children = self._request("GET", children_endpoint, token=token, expected_status=(200,))
        for item in children.get("value", []):
            if item.get("name") == folder_name_clean and "folder" in item:
                full_path = f"{parent_path}/{folder_name_clean}"
                return full_path, item.get("id", "")
        payload = {
            "name": folder_name_clean,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace",
        }
        created = self._request(
            "POST", children_endpoint, token=token, json_payload=payload, expected_status=(201,)
        )
        return f"{parent_path}/{folder_name_clean}", created.get("id", "")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        token: str | None,
        json_payload: dict | None = None,
        data_payload: dict | None = None,
        expected_status: tuple[int, ...] = (200,),
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self._raw_request(
            method,
            endpoint,
            headers=headers,
            json=json_payload,
            data=data_payload,
            timeout=timeout,
        )
        if response.status_code not in expected_status:
            self._raise_from_response(response, endpoint)
        if not response.text:
            return {}
        return response.json()

    def _raw_request(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        data: dict | bytes | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = requests.request(
                    method, endpoint, headers=headers, json=json, data=data, timeout=timeout
                )
                if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return response
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise GraphUploadError(f"Error de red Graph: {exc}") from exc
        raise GraphUploadError(f"Error de red Graph: {last_exc}")

    @staticmethod
    def _raise_from_response(response: requests.Response, endpoint: str) -> None:
        body = (response.text or "")[:1500]
        log.error(
            "Graph request failed",
            extra={"endpoint": endpoint, "status_code": response.status_code, "body": body},
        )
        raise GraphUploadError(f"Graph API error {response.status_code} on {endpoint}")
