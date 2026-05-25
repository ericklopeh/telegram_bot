"""Pruebas P25.1 — endurecimiento Graph y health check."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.sharepoint_graph_client import SharePointGraphClient, aligned_chunk_size
from app.services.sharepoint_graph_errors import (
    GraphApiError,
    GraphConfigError,
    GraphErrorKind,
    parse_graph_response,
)
from app.services.sharepoint_graph_retry import RetryPolicy
from app.services.sharepoint_health_service import SharePointHealthService


def _response(status: int, body: dict | None = None, headers: dict | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body or {}).encode()
    r.headers = headers or {}
    if body is None and status >= 400:
        r._content = b'{"error":{"code":"generalException","message":"fail"}}'
    return r


def test_parse_401_not_retryable():
    parsed = parse_graph_response(_response(401, {"error": {"code": "InvalidAuthenticationToken", "message": "expired"}}))
    assert parsed.kind == GraphErrorKind.AUTH
    assert not parsed.retryable


def test_parse_429_retryable():
    parsed = parse_graph_response(
        _response(429, {"error": {"code": "activityLimitReached", "message": "throttled"}}, {"Retry-After": "2"})
    )
    assert parsed.kind == GraphErrorKind.RATE_LIMIT
    assert parsed.retryable


def test_parse_403_forbidden():
    parsed = parse_graph_response(_response(403, {"error": {"code": "accessDenied", "message": "denied"}}))
    assert parsed.kind == GraphErrorKind.FORBIDDEN
    assert not parsed.retryable


def test_parse_404_not_found():
    parsed = parse_graph_response(_response(404, {"error": {"code": "itemNotFound", "message": "missing"}}))
    assert parsed.kind == GraphErrorKind.NOT_FOUND


def test_graph_api_error_sanitizes_bearer():
    parsed = parse_graph_response(
        _response(401, {"error": {"code": "InvalidAuthenticationToken", "message": "Bearer eyJabc.def.ghi"}})
    )
    err = GraphApiError(parsed)
    assert "eyJ" not in err.user_message
    assert "[REDACTED]" in err.user_message or "Token" in err.user_message


def test_retry_policy_exponential():
    policy = RetryPolicy(max_attempts=3, base_seconds=0.01)
    assert policy.max_attempts == 3


@patch("app.services.sharepoint_graph_client.requests.request")
def test_raw_http_retries_429_then_success(mock_req):
    settings = MagicMock(
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_root_folder="Root",
        ms_drive_id="drive-1",
        ms_site_id="site-1",
        ms_drive_name="",
        ms_site_hostname="",
        ms_site_path="",
        ms_graph_max_retries=3,
        ms_graph_retry_base_seconds=0.01,
        ms_graph_request_timeout=5,
        ms_graph_upload_timeout=5,
        ms_graph_upload_chunk_bytes=3276800,
        ms_graph_small_file_max_bytes=99999999,
    )
    fail = _response(429, {"error": {"code": "activityLimitReached", "message": "wait"}}, {"Retry-After": "0"})
    ok = _response(200, {"id": "1"})
    mock_req.side_effect = [fail, ok]
    client = SharePointGraphClient(settings=settings)
    resp = client._raw_http("GET", "https://graph.microsoft.com/v1.0/test", headers={}, log_ctx=None)
    assert resp.status_code == 200
    assert mock_req.call_count == 2


@patch("app.services.sharepoint_graph_client.requests.request")
def test_timeout_raises_graph_error(mock_req):
    settings = MagicMock(
        ms_graph_max_retries=2,
        ms_graph_retry_base_seconds=0.01,
        ms_graph_request_timeout=1,
        ms_graph_upload_timeout=1,
        ms_graph_upload_chunk_bytes=3276800,
        ms_graph_small_file_max_bytes=4 * 1024 * 1024,
    )
    mock_req.side_effect = requests.Timeout("timed out")
    client = SharePointGraphClient(settings=settings)
    from app.services.sharepoint_graph_errors import GraphUploadError

    with pytest.raises(GraphUploadError, match="Timeout"):
        client._raw_http("GET", "https://graph.example/x", headers={}, log_ctx=None)


@patch("app.services.sharepoint_graph_client.SharePointGraphClient._upload_large")
@patch("app.services.sharepoint_graph_client.SharePointGraphClient.ensure_folder_path")
@patch("app.services.sharepoint_graph_client.SharePointGraphClient.get_drive_id", return_value="d1")
@patch("app.services.sharepoint_graph_client.SharePointGraphClient.get_site_id", return_value="s1")
@patch("app.services.sharepoint_graph_client.SharePointGraphClient.get_access_token", return_value="tok")
@patch("app.services.sharepoint_graph_client.SharePointGraphClient.validate_config")
def test_upload_large_file_uses_session(
    _v, _tok, _site, _drive, _folder, mock_large
):
    settings = MagicMock(ms_graph_small_file_max_bytes=100)
    mock_large.return_value = {"id": "item-99", "webUrl": "https://u", "size": 5000}
    client = SharePointGraphClient(settings=settings)
    data = b"x" * 5000
    result = client.upload_file("Root/folder", "big.pdf", data)
    mock_large.assert_called_once()
    assert result.item_id == "item-99"


def test_aligned_chunk_multiple_of_320k():
    settings = MagicMock(ms_graph_upload_chunk_bytes=10 * 320 * 1024)
    size = aligned_chunk_size(settings)
    assert size % (320 * 1024) == 0


@patch("app.services.sharepoint_health_service.SharePointGraphClient")
def test_health_check_config_failure(mock_client_cls):
    mock_client = MagicMock()
    mock_client.validate_config.side_effect = GraphConfigError("Falta MS_TENANT_ID")
    mock_client.last_token_ok_at = None
    mock_client_cls.return_value = mock_client

    report = SharePointHealthService(graph=mock_client).run_check(db=None)
    assert not report.ok
    assert not report.config_ok
    assert "MS_TENANT_ID" in report.errors[0]


@patch("app.services.sharepoint_health_service.get_settings")
@patch("app.services.sharepoint_health_service.SharePointGraphClient")
def test_health_check_success(mock_client_cls, mock_get_settings):
    settings = MagicMock(
        ms_root_folder="Root/PEDIDOS",
        ms_drive_name="drive",
        ms_site_hostname="host",
        ms_site_path="/sites/x",
    )
    mock_get_settings.return_value = settings
    mock_client = MagicMock()
    mock_client.validate_config.return_value = None
    mock_client.get_access_token.return_value = "token"
    mock_client.last_token_ok_at = None
    mock_client.get_site_id.return_value = "site-1"
    mock_client.get_drive_id.return_value = "drive-1"
    mock_client.probe_root_folder_readable.return_value = True
    mock_client.probe_write_permission.return_value = True
    mock_client.settings = settings
    mock_client_cls.return_value = mock_client

    report = SharePointHealthService(graph=mock_client).run_check(db=None)
    assert report.ok
    assert report.token_ok
    assert report.write_probe_ok
