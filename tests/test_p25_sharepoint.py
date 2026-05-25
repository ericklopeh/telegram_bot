"""Pruebas P25 — SharePoint / Microsoft Graph (mocks, sin red)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain import constants as C
from app.domain.constants import is_sharepoint_synced
from app.models.case import Case
from app.models.document import Document
from app.services.sharepoint_graph_client import (
    GraphConfigError,
    GraphUploadResult,
    SharePointGraphClient,
)
from app.services.sharepoint_sync_service import SharePointSyncService
from app.services.workflow_dependency_service import WorkflowContext, _CRITICAL_SP_TYPES


def _case() -> Case:
    c = Case(
        id=1,
        public_id="PED-1",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Cliente SP",
        current_status=C.ST_PED_RECIBIDO,
        visible_status=C.VISIBLE_EN_PEDIDO,
        week_code="SEM_22",
        folder_path="/tmp",
        seller_name="Vendedor SP",
        official_folio="100",
    )
    c.created_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return c


def _doc(case_id: int = 1) -> Document:
    return Document(
        id=5,
        case_id=case_id,
        document_type=C.DOC_PEDIDO,
        stored_filename="pedido.pdf",
        file_path="/tmp/pedido.pdf",
        is_active=True,
        upload_status=C.UPLOAD_LOCAL,
        version=1,
    )


def test_validate_config_missing_vars():
    settings = MagicMock(
        ms_tenant_id="",
        ms_client_id="",
        ms_client_secret="",
        ms_root_folder="",
        ms_drive_id="",
        ms_drive_name="",
        ms_site_id="",
        ms_site_hostname="",
        ms_site_path="",
    )
    client = SharePointGraphClient(settings=settings)
    with pytest.raises(GraphConfigError, match="MS_TENANT_ID"):
        client.validate_config()


def test_remote_folder_matches_p24_layout():
    settings = MagicMock(ms_root_folder="Root/PEDIDOS")
    client = SharePointGraphClient(settings=settings)
    case = _case()
    rel = "2026/SEM_22/Vendedor_SP/FOLIO_100_Cliente_SP/documents"
    full = client.build_remote_documents_folder(rel)
    assert "2026" in full
    assert "SEM_22" in full
    assert "documents" in full
    assert "excel_masters" not in full


@patch("app.services.sharepoint_sync_service.SharePointGraphClient")
def test_sync_document_ok(mock_client_cls, tmp_path):
    pdf = tmp_path / "pedido.pdf"
    pdf.write_bytes(b"%PDF")

    mock_client = MagicMock()
    mock_client.validate_config.return_value = None
    mock_client.build_remote_documents_folder.return_value = "Root/2026/SEM_22/documents"
    mock_client.upload_file.return_value = GraphUploadResult(
        web_url="https://sp/item",
        item_id="item-1",
        drive_id="drive-1",
        site_id="site-1",
        folder_path="Root/2026/documents/pedido.pdf",
        name="pedido.pdf",
    )
    mock_client_cls.return_value = mock_client

    db = MagicMock()
    doc = _doc()
    doc.file_path = str(pdf)
    case = _case()
    db.get.side_effect = lambda model, pk: doc if pk == 5 else case

    svc = SharePointSyncService(graph=mock_client)
    with patch.object(svc, "_log_sp"):
        result = svc.sync_document(db, 5)

    assert result.ok
    assert result.upload_status == C.UPLOAD_SHAREPOINT_OK
    mock_client.ensure_folder_path.assert_not_called()  # ensure via upload_file path
    mock_client.upload_file.assert_called_once()


@patch("app.services.sharepoint_sync_service.SharePointGraphClient")
def test_sync_document_graph_fail(mock_client_cls, tmp_path):
    pdf = tmp_path / "pedido.pdf"
    pdf.write_bytes(b"x")
    mock_client = MagicMock()
    mock_client.validate_config.return_value = None
    mock_client.build_remote_documents_folder.return_value = "Root/documents"
    from app.services.sharepoint_graph_client import GraphUploadError

    mock_client.upload_file.side_effect = GraphUploadError("Graph 503")
    mock_client_cls.return_value = mock_client

    db = MagicMock()
    doc = _doc()
    doc.file_path = str(pdf)
    db.get.side_effect = lambda model, pk: doc if pk == 5 else _case()

    svc = SharePointSyncService(graph=mock_client)
    with patch.object(svc, "_log_sp"), patch.object(svc, "_enqueue_retry"):
        result = svc.sync_document(db, 5)

    assert not result.ok
    assert result.upload_status == C.UPLOAD_FAILED


@patch("app.services.sharepoint_sync_service.SharePointSyncService.sync_document")
def test_retry_sets_ok(mock_sync):
    mock_sync.return_value = MagicMock(
        ok=True, upload_status=C.UPLOAD_SHAREPOINT_OK, web_url="https://u"
    )
    db = MagicMock()
    doc = _doc()
    doc.upload_status = C.UPLOAD_FAILED
    db.scalars.return_value.all.return_value = [doc]
    results = SharePointSyncService().retry_failed_for_case(db, 1)
    assert results[0].ok
    mock_sync.assert_called_once()
    assert mock_sync.call_args.kwargs.get("is_retry") is True


def test_is_sharepoint_synced_accepts_legacy():
    assert is_sharepoint_synced(C.UPLOAD_SHAREPOINT_OK)
    assert is_sharepoint_synced(C.UPLOAD_LEGACY_OK)
    assert not is_sharepoint_synced(C.UPLOAD_FAILED)


def test_workflow_blocks_without_sharepoint():
    from app.models.document import Document as Doc

    docs = [
        Doc(
            id=1,
            case_id=1,
            document_type=C.DOC_PEDIDO,
            stored_filename="a",
            file_path="/a",
            upload_status=C.UPLOAD_LOCAL,
            is_active=True,
        )
    ]
    ctx = WorkflowContext(
        case=_case(),
        documents=docs,
        sharepoint_ok=False,
    )
    sp_statuses = [d.upload_status for d in ctx.documents if d.document_type in _CRITICAL_SP_TYPES]
    assert not all(is_sharepoint_synced(s) for s in sp_statuses)


@patch("app.services.sharepoint_sync_service.assert_not_excel_master_path")
def test_sync_does_not_read_excel_masters(mock_guard, tmp_path):
    mock_guard.side_effect = ValueError("Ruta prohibida en maestro Excel")
    pdf = tmp_path / "pedido.pdf"
    pdf.write_bytes(b"ok")
    doc = _doc()
    doc.file_path = str(pdf)
    db = MagicMock()
    db.get.side_effect = lambda model, pk: doc if pk == 5 else _case()

    mock_graph = MagicMock()
    mock_graph.validate_config.return_value = None
    svc = SharePointSyncService(graph=mock_graph)
    with patch.object(svc, "_log_sp"), patch.object(svc, "_enqueue_retry"):
        result = svc.sync_document(db, 5)
    assert not result.ok
    mock_graph.upload_file.assert_not_called()
    mock_guard.assert_called()
