from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime

import requests

from app.config import get_settings

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

INVALID_NAME_CHARS = r'[~"#%&*:<>?/\\{|}]'
SPACE_RE = re.compile(r"\s+")
_CACHE_LOCK = threading.Lock()
_CACHED_SITE_ID: str | None = None
_CACHED_DRIVE_ID: str | None = None
_FOLDER_CACHE: dict[str, str] = {}


class GraphUploadError(RuntimeError):
    """Error controlado para fallos de Microsoft Graph."""


@dataclass
class GraphContext:
    access_token: str
    site_id: str
    drive_id: str


def sanitize_graph_name(value: str) -> str:
    cleaned = value.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(INVALID_NAME_CHARS, " ", cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    return cleaned or "SIN_NOMBRE"


def normalize_cliente(value: str) -> str:
    return sanitize_graph_name(value).upper()


def normalize_vendedor(value: str) -> str:
    return sanitize_graph_name(value)


def normalize_folio_o_tmp(value: str) -> str:
    raw = sanitize_graph_name(value).upper()
    if raw.startswith("REVTMP-"):
        # REVTMP-2026-0002 -> TMP-2026-0002
        return "TMP-" + raw[len("REVTMP-") :]
    if raw.startswith("TMP-"):
        return raw
    if raw.isdigit():
        return raw
    if raw.startswith("PED-"):
        # PED-00001 -> 00001
        tail = raw.replace("PED-", "", 1).strip()
        return tail if tail else raw
    # Si no hay folio real, generar tmp estable por año.
    year = datetime.now().year
    return f"TMP-{year}-0001"


def _graph_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _raise_graph_error(response: requests.Response, endpoint: str, *, route: str | None = None, filename: str | None = None) -> None:
    body = response.text[:1500]
    log.error(
        "Graph request failed",
        extra={
            "endpoint": endpoint,
            "status_code": response.status_code,
            "response_body": body,
            "route": route,
            "filename": filename,
        },
    )
    raise GraphUploadError(f"Graph API error {response.status_code} on {endpoint}")


def _request_json(
    method: str,
    endpoint: str,
    *,
    token: str,
    json_payload: dict | None = None,
    data_payload: dict | None = None,
    expected_status: tuple[int, ...] = (200,),
    timeout: int = 30,
    route: str | None = None,
    filename: str | None = None,
) -> dict:
    headers = _graph_headers(token)
    response = requests.request(
        method,
        endpoint,
        headers=headers,
        json=json_payload,
        data=data_payload,
        timeout=timeout,
    )
    if response.status_code not in expected_status:
        _raise_graph_error(response, endpoint, route=route, filename=filename)
    if not response.text:
        return {}
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover - respuesta no JSON es error inesperado
        raise GraphUploadError(f"Invalid JSON response from Graph at {endpoint}") from exc


def get_access_token() -> str:
    settings = get_settings()
    if not settings.ms_tenant_id or not settings.ms_client_id or not settings.ms_client_secret:
        raise GraphUploadError("Faltan credenciales MS_TENANT_ID/MS_CLIENT_ID/MS_CLIENT_SECRET")
    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    log.info("Obteniendo token de Microsoft Graph")
    response = requests.post(token_url, data=payload, timeout=30)
    if response.status_code != 200:
        _raise_graph_error(response, token_url)
    data = response.json()
    token = data.get("access_token", "")
    if not token:
        raise GraphUploadError("No se recibió access_token de Graph")
    return token


def get_site_id() -> str:
    settings = get_settings()
    configured_site_id = settings.ms_site_id.strip()
    if configured_site_id:
        log.info("Using cached site_id")
        return configured_site_id
    global _CACHED_SITE_ID
    if _CACHED_SITE_ID:
        log.info("Using cached site_id")
        return _CACHED_SITE_ID
    if not settings.ms_site_hostname or not settings.ms_site_path:
        raise GraphUploadError("Faltan MS_SITE_HOSTNAME/MS_SITE_PATH")
    log.info("Fetching site_id from Graph")
    token = get_access_token()
    endpoint = f"{GRAPH_BASE}/sites/{settings.ms_site_hostname}:{settings.ms_site_path}"
    data = _request_json("GET", endpoint, token=token, expected_status=(200,))
    site_id = data.get("id", "")
    if not site_id:
        raise GraphUploadError("No se encontró site_id")
    with _CACHE_LOCK:
        _CACHED_SITE_ID = site_id
    log.info("Site ID encontrado")
    return site_id


def get_drive_id() -> str:
    settings = get_settings()
    configured_drive_id = settings.ms_drive_id.strip()
    if configured_drive_id:
        log.info("Using cached drive_id")
        return configured_drive_id
    global _CACHED_DRIVE_ID
    if _CACHED_DRIVE_ID:
        log.info("Using cached drive_id")
        return _CACHED_DRIVE_ID
    if not settings.ms_drive_name:
        raise GraphUploadError("Falta MS_DRIVE_NAME")
    log.info("Fetching drive_id from Graph")
    token = get_access_token()
    site_id = get_site_id()
    if not site_id:
        raise GraphUploadError("No se encontró site_id para buscar drives")
    drives_data = _request_json("GET", f"{GRAPH_BASE}/sites/{site_id}/drives", token=token, expected_status=(200,))
    drives = drives_data.get("value", [])
    for drive in drives:
        if drive.get("name") == settings.ms_drive_name:
            drive_id = drive.get("id", "")
            if drive_id:
                with _CACHE_LOCK:
                    _CACHED_DRIVE_ID = drive_id
                log.info("Drive ID encontrado")
                return drive_id
    for drive in drives:
        log.info(
            "Drive disponible",
            extra={
                "name": drive.get("name"),
                "id": drive.get("id"),
                "webUrl": drive.get("webUrl"),
            },
        )
    raise GraphUploadError(f"No se encontró drive con name={settings.ms_drive_name!r}")


def _ensure_child_folder(drive_id: str, parent_id: str, parent_path: str, folder_name: str, *, token: str) -> tuple[str, str]:
    children_endpoint = f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}/children"
    folder_name_clean = sanitize_graph_name(folder_name)
    children = _request_json("GET", children_endpoint, token=token, expected_status=(200,))
    for item in children.get("value", []):
        if item.get("name") == folder_name_clean and "folder" in item:
            full_path = f"{parent_path}/{folder_name_clean}"
            folder_id = item.get("id", "")
            with _CACHE_LOCK:
                _FOLDER_CACHE[full_path] = folder_id
            log.info("Folder already exists", extra={"folder_path": full_path})
            return full_path, folder_id
    payload = {
        "name": folder_name_clean,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "replace",
    }
    created = _request_json("POST", children_endpoint, token=token, json_payload=payload, expected_status=(201,))
    full_path = f"{parent_path}/{folder_name_clean}"
    folder_id = created.get("id", "")
    with _CACHE_LOCK:
        _FOLDER_CACHE[full_path] = folder_id
    log.info("Created folder", extra={"folder_path": full_path})
    return full_path, folder_id


def ensure_folder_path(drive_id: str, folder_path: str) -> str:
    token = get_access_token()
    sanitized_parts = [sanitize_graph_name(part) for part in folder_path.split("/") if part.strip()]
    if not sanitized_parts:
        raise GraphUploadError("folder_path vacío para ensure_folder_path")
    full_target = "/".join(sanitized_parts)
    cached_folder_id = _FOLDER_CACHE.get(full_target)
    if cached_folder_id:
        log.info("Folder cache hit", extra={"folder_path": full_target, "folder_id": cached_folder_id})
        return full_target
    log.info("Folder cache miss", extra={"folder_path": full_target})

    current_path = sanitized_parts[0]
    root_children_endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
    root_children = _request_json("GET", root_children_endpoint, token=token, expected_status=(200,))
    current_id = ""
    for item in root_children.get("value", []):
        if item.get("name") == current_path and "folder" in item:
            current_id = item.get("id", "")
            with _CACHE_LOCK:
                _FOLDER_CACHE[current_path] = current_id
            log.info("Folder already exists", extra={"folder_path": current_path})
            break
    if not current_id:
        payload = {"name": current_path, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"}
        created = _request_json("POST", root_children_endpoint, token=token, json_payload=payload, expected_status=(201,))
        current_id = created.get("id", "")
        with _CACHE_LOCK:
            _FOLDER_CACHE[current_path] = current_id
        log.info("Created folder", extra={"folder_path": current_path})

    for part in sanitized_parts[1:]:
        current_path, current_id = _ensure_child_folder(drive_id, current_id, current_path, part, token=token)
    if current_id:
        with _CACHE_LOCK:
            _FOLDER_CACHE[current_path] = current_id
    return current_path


def upload_small_file(drive_id: str, folder_path: str, filename: str, file_bytes: bytes) -> dict:
    token = get_access_token()
    clean_filename = sanitize_graph_name(filename)
    clean_folder = "/".join(sanitize_graph_name(p) for p in folder_path.split("/") if p.strip())
    endpoint = f"{GRAPH_BASE}/drives/{drive_id}/root:/{clean_folder}/{clean_filename}:/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }
    response = requests.put(endpoint, headers=headers, data=file_bytes, timeout=60)
    if response.status_code not in (200, 201):
        _raise_graph_error(response, endpoint, route=clean_folder, filename=clean_filename)
    data = response.json()
    return {
        "ok": True,
        "webUrl": data.get("webUrl"),
        "id": data.get("id"),
        "name": data.get("name"),
        "path": f"{clean_folder}/{clean_filename}",
    }


def _map_tipo_documento(tipo_documento: str) -> str:
    raw = (tipo_documento or "").strip().upper()
    if raw.startswith("REVISION"):
        return "01_REVISIONES"
    if raw.startswith("PEDIDO"):
        return "02_PEDIDOS"
    if raw.startswith("AUTORIZACION"):
        return "03_AUTORIZACIONES"
    if raw.startswith("COMPULSA"):
        return "04_COMPULSA"
    raise GraphUploadError(f"tipo_documento no válido: {tipo_documento!r}")


STANDARD_CASE_SUBFOLDERS = (
    "01_REVISIONES",
    "02_PEDIDOS",
    "03_AUTORIZACIONES",
    "04_COMPULSA",
)


def ensure_case_subfolders(drive_id: str, case_root_folder: str) -> None:
    for subfolder in STANDARD_CASE_SUBFOLDERS:
        ensure_folder_path(drive_id, f"{case_root_folder}/{subfolder}")


def build_sharepoint_case_folder_name(folio: str, cliente: str) -> str:
    # Carpeta estable por cliente (dentro de semana + vendedor), para evitar
    # crear una carpeta nueva por cada folio temporal/oficial.
    _ = folio  # Mantener firma por compatibilidad con llamadas existentes.
    cliente_norm = normalize_cliente(cliente)
    return sanitize_graph_name(cliente_norm)


def build_sharepoint_final_folder(
    root_folder: str,
    semana: str,
    vendedor: str,
    folio: str,
    cliente: str,
    tipo_documento: str,
) -> tuple[str, str]:
    subcarpeta_tipo = _map_tipo_documento(tipo_documento)
    root = "/".join(sanitize_graph_name(part) for part in root_folder.split("/") if part.strip())
    semana_norm = sanitize_graph_name(semana)
    vendedor_norm = normalize_vendedor(vendedor)
    case_folder = build_sharepoint_case_folder_name(folio, cliente)
    case_root_folder = f"{root}/{semana_norm}/{vendedor_norm}/{case_folder}"
    final_folder = f"{case_root_folder}/{subcarpeta_tipo}"
    return case_root_folder, final_folder


def prepare_case_folder_migration(old_case_folder: str, new_case_folder: str) -> None:
    """
    TODO: Implementar migración/renombrado de carpeta temporal a folio real.
    Ejemplo: TMP-2026-0002 - PABLO -> 00001 - PABLO.
    """
    log.info(
        "TODO pendiente: migrar carpeta de caso temporal a folio real",
        extra={"old_case_folder": old_case_folder, "new_case_folder": new_case_folder},
    )


def upload_document_to_sharepoint(
    vendedor: str,
    semana: str,
    cliente: str,
    folio: str,
    tipo_documento: str,
    filename: str,
    file_bytes: bytes,
) -> dict:
    settings = get_settings()
    if not settings.ms_root_folder:
        raise GraphUploadError("Falta MS_ROOT_FOLDER")
    case_root_folder, final_folder = build_sharepoint_final_folder(
        settings.ms_root_folder,
        semana,
        vendedor,
        folio,
        cliente,
        tipo_documento,
    )
    log.info("Ruta final SharePoint", extra={"folder_path": final_folder})

    site_id = get_site_id()
    drive_id = get_drive_id()

    ensure_case_subfolders(drive_id, case_root_folder)
    result = upload_small_file(drive_id, final_folder, filename, file_bytes)
    log.info("Archivo subido correctamente", extra={"webUrl": result.get("webUrl"), "path": result.get("path")})
    result["site_id"] = site_id
    result["drive_id"] = drive_id
    result["case_folder"] = case_root_folder.split("/")[-1]
    result["folder_path"] = final_folder
    # TODO: Implementar upload session para archivos grandes.
    return result
