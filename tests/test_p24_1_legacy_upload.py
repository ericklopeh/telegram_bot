"""Pruebas P24.1 — upload legacy alineado con case_document_service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.services.case_document_service import CaseDocumentService
from app.services.case_event_service import (
    CASE_DOCUMENT_REPLACED,
    CASE_DOCUMENT_UPLOADED,
)


def _case(**kwargs) -> Case:
    c = Case(
        id=7,
        public_id="PED-LEG",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Cliente Legacy",
        current_status=C.ST_PED_RECIBIDO,
        visible_status=C.VISIBLE_EN_PEDIDO,
        week_code="SEM_21",
        folder_path="/tmp/legacy",
        seller_name="Vendedor Test",
        official_folio="99999",
    )
    c.created_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


@patch("app.services.case_event_service.log_pedido_checklist_after_upload")
@patch("app.services.case_document_service.log_document_event")
@patch("app.repositories.document_repository.DocumentRepository.add_version")
@patch("app.repositories.document_repository.DocumentRepository.get_active_document")
@patch("app.services.case_document_service.case_documents_base_dir")
def test_legacy_web_upload_uses_storage_cases(
    mock_base_dir,
    mock_get_active,
    mock_add_version,
    mock_log_event,
    _mock_checklist,
    tmp_path,
):
    mock_base_dir.return_value = tmp_path / "storage" / "cases" / "docs"
    mock_get_active.return_value = None

    doc = Document(
        id=10,
        case_id=7,
        document_type=C.DOC_PEDIDO,
        stored_filename="pedido_v1.pdf",
        file_path=str(mock_base_dir.return_value / "pedido_v1.pdf"),
        review_status=C.REVIEW_PENDING,
        version=1,
        is_active=True,
        upload_status="LOCAL",
    )
    mock_add_version.return_value = doc

    case = _case()
    db = MagicMock()
    svc = CaseDocumentService()
    result = svc.upload_document_legacy_web(
        db,
        case,
        C.DOC_PEDIDO,
        b"%PDF test",
        original_filename="pedido.pdf",
        mime_type="application/pdf",
        uploaded_by="web",
    )

    assert result.id == 10
    mock_add_version.assert_called_once()
    file_path = mock_add_version.call_args[0][4]
    assert "excel_masters" not in file_path.replace("\\", "/")
    assert mock_base_dir.called
    assert "excel_masters" not in file_path
    events = [c.kwargs.get("event_type") for c in mock_log_event.call_args_list]
    assert CASE_DOCUMENT_UPLOADED in events


@patch("app.services.case_event_service.log_pedido_checklist_after_upload")
@patch("app.services.case_document_service.log_document_event")
@patch("app.repositories.document_repository.DocumentRepository.add_version")
@patch("app.repositories.document_repository.DocumentRepository.get_active_document")
@patch("app.services.case_document_service.case_documents_base_dir")
def test_legacy_web_versioning_emits_replaced(
    mock_base_dir,
    mock_get_active,
    mock_add_version,
    mock_log_event,
    _mock_checklist,
    tmp_path,
):
    mock_base_dir.return_value = tmp_path / "docs"
    prev = Document(
        id=1,
        case_id=7,
        document_type=C.DOC_PEDIDO,
        stored_filename="old.pdf",
        file_path="/old.pdf",
        version=1,
        is_active=True,
    )
    mock_get_active.return_value = prev

    new_doc = Document(
        id=2,
        case_id=7,
        document_type=C.DOC_PEDIDO,
        stored_filename="new.pdf",
        file_path=str(tmp_path / "new.pdf"),
        version=2,
        is_active=True,
    )
    mock_add_version.return_value = new_doc

    svc = CaseDocumentService()
    svc.upload_document_legacy_web(
        MagicMock(),
        _case(),
        C.DOC_PEDIDO,
        b"data",
        original_filename="new.pdf",
    )

    events = [c.kwargs.get("event_type") for c in mock_log_event.call_args_list]
    assert CASE_DOCUMENT_UPLOADED in events
    assert CASE_DOCUMENT_REPLACED in events
    assert mock_add_version.call_args.kwargs.get("version") == 2


def test_store_bytes_without_case_uses_uploads_not_cases():
    stored, path = CaseDocumentService.store_bytes_without_case(
        b"orphan",
        original_filename="tmp.pdf",
        storage_key="no_case",
    )
    assert stored.endswith(".pdf")
    assert "uploads" in path.replace("\\", "/")
    assert "no_case" in path.replace("\\", "/")
    assert "excel_masters" not in path
    Path(path).unlink(missing_ok=True)


def test_store_bytes_without_case_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stored, path = CaseDocumentService.store_bytes_without_case(b"x", storage_key="orphan")
    assert Path(path).is_file()
    assert Path(path).read_bytes() == b"x"


@patch("app.services.case_document_service.CaseDocumentService.upload_document")
def test_legacy_web_delegates_to_upload_document(mock_upload):
    doc = Document(
        id=3,
        case_id=7,
        document_type="talon",
        stored_filename="t.pdf",
        file_path="/t.pdf",
        is_active=True,
    )
    mock_upload.return_value = doc
    db = MagicMock()
    case = _case()
    with patch("app.services.case_event_service.log_pedido_checklist_after_upload"):
        out = CaseDocumentService().upload_document_legacy_web(
            db, case, "talon", b"tal", original_filename="talon.jpg"
        )
    assert out is doc
    mock_upload.assert_called_once()
    assert mock_upload.call_args[0][2] == "talon"
