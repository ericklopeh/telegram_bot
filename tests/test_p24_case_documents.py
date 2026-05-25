"""Pruebas P24 — gestión documental avanzada (sin BD real)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.services.case_document_service import CaseDocumentService
from app.services.case_document_storage import case_documents_base_dir
from app.services.case_event_service import (
    CASE_DOCUMENT_REJECTED,
    CASE_DOCUMENT_UPLOADED,
    CASE_DOCUMENT_VALIDATED,
    DOCUMENT_MISSING_BLOCKED,
)


def _case(**kwargs) -> Case:
    c = Case(
        id=42,
        public_id="PED-TEST",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Cliente Prueba",
        current_status=C.ST_PED_RECIBIDO,
        visible_status=C.VISIBLE_EN_PEDIDO,
        week_code="SEM_20",
        folder_path="/tmp/caso",
        seller_name="Vendedor Uno",
        official_folio="12345",
    )
    c.created_at = datetime(2026, 5, 19, tzinfo=timezone.utc)
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_storage_path_structure():
    case = _case()
    path = case_documents_base_dir(case, project_root=Path("/proj"))
    parts = path.parts
    assert "storage" in parts
    assert "cases" in parts
    assert "2026" in parts
    assert "SEM_20" in parts
    assert parts[-1] == "documents"


def test_required_mueble():
    db = MagicMock()
    case = _case(order_type=C.ORDER_TYPE_MUEBLE)
    with patch.object(
        CaseDocumentService,
        "has_refinanciamiento",
        return_value=False,
    ):
        required = CaseDocumentService().required_document_types(db, case)
    assert C.DOC_PEDIDO in required
    assert C.DOC_ORDEN_DESCUENTO in required
    assert C.DOC_AUTORIZACION_SNTE in required
    assert C.DOC_ORDEN_SNTE_PDF not in required


def test_required_prestamo():
    db = MagicMock()
    case = _case(order_type=C.ORDER_TYPE_PRESTAMO)
    with patch.object(
        CaseDocumentService,
        "has_refinanciamiento",
        return_value=False,
    ):
        required = CaseDocumentService().required_document_types(db, case)
    assert C.DOC_ORDEN_SNTE_PDF in required
    assert C.DOC_AUTORIZACION_SNTE not in required


def test_required_refinanciamiento():
    db = MagicMock()
    case = _case(order_type=C.ORDER_TYPE_PRESTAMO)
    with patch.object(
        CaseDocumentService,
        "has_refinanciamiento",
        return_value=True,
    ):
        required = CaseDocumentService().required_document_types(db, case)
    assert C.DOC_AUTORIZACION_REFI in required


@patch("app.repositories.document_repository.DocumentRepository.get_active_document", return_value=None)
@patch("app.services.case_document_service.log_document_event")
@patch("app.repositories.document_repository.DocumentRepository.add_version")
@patch("app.services.case_document_service.case_documents_base_dir")
def test_upload_document(mock_dir, mock_add, mock_log_event, _mock_active, tmp_path):
    mock_dir.return_value = tmp_path / "docs"
    mock_dir.return_value.mkdir(parents=True)

    doc = Document(
        id=1,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="pedido_v1.pdf",
        file_path=str(tmp_path / "pedido_v1.pdf"),
        review_status=C.REVIEW_PENDING,
        version=1,
        is_active=True,
    )
    mock_add.return_value = doc

    db = MagicMock()
    case = _case()
    svc = CaseDocumentService()
    result = svc.upload_document(
        db,
        case,
        C.DOC_PEDIDO,
        b"%PDF-1.4 test",
        original_filename="pedido.pdf",
        mime_type="application/pdf",
        uploaded_by="admin",
    )
    assert result.id == 1
    mock_log_event.assert_called()
    assert mock_log_event.call_args.kwargs["event_type"] == CASE_DOCUMENT_UPLOADED


@patch("app.services.case_document_service.log_document_event")
def test_validate_document(mock_log):
    db = MagicMock()
    case = _case()
    doc = Document(
        id=5,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="f.pdf",
        file_path="/tmp/f.pdf",
        is_active=True,
        review_status=C.REVIEW_PENDING,
    )
    svc = CaseDocumentService()
    with patch.object(svc, "get_document", return_value=doc):
        out = svc.validate_document(db, case, 5, validated_by="compulsa")
    assert out.review_status == C.REVIEW_VALID
    assert mock_log.call_args.kwargs["event_type"] == CASE_DOCUMENT_VALIDATED


@patch("app.services.case_document_service.log_document_event")
def test_reject_document_requires_reason(mock_log):
    db = MagicMock()
    case = _case()
    doc = Document(
        id=5,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="f.pdf",
        file_path="/tmp/f.pdf",
        is_active=True,
        review_status=C.REVIEW_PENDING,
    )
    svc = CaseDocumentService()
    with patch.object(svc, "get_document", return_value=doc):
        with pytest.raises(ValueError, match="motivo"):
            svc.reject_document(db, case, 5, "  ")
    with patch.object(svc, "get_document", return_value=doc):
        out = svc.reject_document(db, case, 5, "ilegible")
    assert out.review_status == C.REVIEW_INVALID
    assert out.rejection_reason == "ilegible"


@patch("app.services.case_document_service.CaseDocumentService.list_active_documents")
@patch("app.repositories.document_repository.DocumentRepository.get_active_types_for_case")
def test_missing_required_types(mock_types, mock_list):
    mock_types.return_value = {C.DOC_PEDIDO}
    mock_list.return_value = []
    db = MagicMock()
    case = _case()
    with patch.object(CaseDocumentService, "has_refinanciamiento", return_value=False):
        missing = CaseDocumentService().missing_required_types(db, case)
    assert C.DOC_ORDEN_DESCUENTO in missing
    assert C.DOC_AUTORIZACION_SNTE in missing


@patch("app.services.case_document_service.log_event")
@patch("app.services.case_document_service.CaseDocumentService.missing_for_workflow_target")
def test_assert_workflow_documents_blocked(mock_missing, mock_log_event):
    mock_missing.return_value = [C.DOC_PEDIDO]
    db = MagicMock()
    case = _case()
    from app.services.workflow_state_service import WF_EN_COMPULSA

    svc = CaseDocumentService()
    with pytest.raises(ValueError, match="faltan documentos"):
        svc.assert_workflow_documents(db, case, WF_EN_COMPULSA)
    mock_log_event.assert_called()
    assert mock_log_event.call_args.kwargs["event_type"] == DOCUMENT_MISSING_BLOCKED


def test_list_active_documents():
    db = MagicMock()
    doc = Document(
        id=1,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="a.pdf",
        file_path="/a.pdf",
        is_active=True,
    )
    db.scalars.return_value.all.return_value = [doc]
    listed = CaseDocumentService().list_active_documents(db, 42)
    assert len(listed) == 1


@patch("app.services.case_document_service.log_document_event")
@patch("app.services.case_document_service.CaseDocumentService.upload_document")
def test_replace_document(mock_upload, mock_log):
    db = MagicMock()
    case = _case()
    old = Document(
        id=1,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="old.pdf",
        file_path="/old.pdf",
        is_active=True,
        version=1,
    )
    new = Document(
        id=2,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="new.pdf",
        file_path="/new.pdf",
        is_active=True,
        version=2,
    )
    mock_upload.return_value = new
    svc = CaseDocumentService()
    with patch.object(svc, "get_document", return_value=old):
        result = svc.replace_document(db, case, 1, b"data", original_filename="new.pdf")
    assert result.version == 2
    assert old.review_status == C.REVIEW_REPLACED
    from app.services.case_event_service import CASE_DOCUMENT_REPLACED

    assert any(
        c.kwargs.get("event_type") == CASE_DOCUMENT_REPLACED for c in mock_log.call_args_list
    )


def test_upload_writes_under_storage_cases_not_excel_masters(tmp_path):
    """Confirmar que el árbol P24 no apunta a excel_masters."""
    case = _case()
    base = case_documents_base_dir(case, project_root=tmp_path)
    assert "excel_masters" not in str(base)
    assert "excel_exports" not in str(base)
    assert base.parts[-2] != "excel_masters"
