"""Fix/regression: upload foto pedido Telegram y workflow context."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.services.action_guard_service import build_case_action_state, can_upload_document
from app.services.document_service import DocumentService, StoredIncomingFile
from app.services.workflow_dependency_service import build_workflow_context


def _pedido_case(**kwargs) -> Case:
    c = Case(
        id=42,
        public_id="PED-00042",
        case_type=C.CASE_TYPE_PEDIDO,
        order_type=C.ORDER_TYPE_MUEBLE,
        client_name="Cliente Test",
        current_status=C.ST_PED_RECIBIDO,
        visible_status=C.visible_status_for_pedido(C.ST_PED_RECIBIDO),
        week_code="SEM 21-2026",
        folder_path="/tmp/pedido-test",
        seller_name="Vendedor Test",
        official_folio="00042",
    )
    c.created_at = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def _mock_db_for_workflow():
    db = MagicMock()
    docs_result = MagicMock()
    docs_result.unique.return_value.all.return_value = []
    events_result = MagicMock()
    events_result.all.return_value = []
    db.scalars.side_effect = [docs_result, events_result]
    db.scalar.return_value = None
    return db


@patch("app.services.case_document_service.CaseDocumentService")
@patch("app.services.workflow_dependency_service.CaseService")
@patch("app.services.workflow_dependency_service.get_settings")
def test_build_workflow_context_instantiates_case_service_with_settings(
    mock_get_settings,
    mock_case_service_cls,
    mock_doc_svc_cls,
):
    """Regression: CaseService() sin settings rompía can_upload_document en Telegram."""
    mock_get_settings.return_value = MagicMock()
    mock_case_service_cls.return_value.pedido_has_all_documents.return_value = False
    mock_doc_svc_cls.return_value.missing_required_types.return_value = [C.DOC_PEDIDO]

    ctx = build_workflow_context(_mock_db_for_workflow(), _pedido_case())

    mock_case_service_cls.assert_called_once_with(mock_get_settings.return_value)
    assert ctx.case.public_id == "PED-00042"


@patch("app.services.case_document_service.CaseDocumentService")
@patch("app.services.workflow_dependency_service.CaseService")
@patch("app.services.workflow_dependency_service.get_settings")
@patch("app.services.action_guard_service.get_settings")
def test_build_case_action_state_no_typeerror_on_generate_auth_eval(
    mock_guard_settings,
    mock_wf_settings,
    mock_case_service_cls,
    mock_doc_svc_cls,
):
    """build_case_action_state → _eval_generate_auth → build_workflow_context (ruta del bug)."""
    mock_guard_settings.return_value.web_rbac_relaxed = True
    mock_wf_settings.return_value = mock_guard_settings.return_value
    mock_case_service_cls.return_value.pedido_has_all_documents.return_value = False
    mock_doc_svc_cls.return_value.missing_required_types.return_value = [C.DOC_PEDIDO]

    db = _mock_db_for_workflow()
    db.query.return_value.filter.return_value.all.return_value = []

    case = _pedido_case()
    user = {"id": 1, "nombre": "Vendedor Test", "rol": "vendedor"}

    state = build_case_action_state(db, case, user)

    assert state.case_id == 42
    assert state.next_missing_doc_type == C.DOC_PEDIDO


@patch("app.services.case_document_service.CaseDocumentService")
@patch("app.services.workflow_dependency_service.CaseService")
@patch("app.services.workflow_dependency_service.get_settings")
@patch("app.services.action_guard_service.get_settings")
def test_can_upload_document_pedido_first_doc(
    mock_guard_settings,
    mock_wf_settings,
    mock_case_service_cls,
    mock_doc_svc_cls,
):
    mock_guard_settings.return_value.web_rbac_relaxed = True
    mock_wf_settings.return_value = mock_guard_settings.return_value
    mock_case_service_cls.return_value.pedido_has_all_documents.return_value = False
    mock_doc_svc_cls.return_value.missing_required_types.return_value = [C.DOC_PEDIDO]

    db = _mock_db_for_workflow()
    db.query.return_value.filter.return_value.all.return_value = []

    case = _pedido_case()
    user = {"id": 1, "nombre": "Vendedor Test", "rol": "vendedor"}

    ok, reason = can_upload_document(db, case, C.DOC_PEDIDO, user)

    assert ok is True
    assert reason is None


@patch("app.services.case_event_service.log_pedido_checklist_after_upload")
@patch("app.services.case_event_service.log_document_received")
@patch("app.repositories.document_repository.DocumentRepository.add_version")
def test_register_pedido_document_upload_creates_document(
    mock_add_version,
    _mock_log_doc,
    _mock_log_checklist,
):
    doc = Document(
        id=99,
        case_id=42,
        document_type=C.DOC_PEDIDO,
        stored_filename="foto.jpg",
        file_path="/tmp/foto.jpg",
        is_active=True,
    )
    mock_add_version.return_value = doc

    db = MagicMock()
    case = _pedido_case()
    stored = StoredIncomingFile("foto.jpg", "/tmp/foto.jpg", "pedido.jpg", "image/jpeg")

    out_doc, _present = DocumentService().register_pedido_document_upload(
        db,
        case,
        C.DOC_PEDIDO,
        stored,
        actor_role="Vendedor Test",
        source="telegram",
    )

    assert out_doc.id == 99
    mock_add_version.assert_called_once()


@patch("app.repositories.document_repository.DocumentRepository.add_version")
def test_register_pedido_upload_propagates_db_error(mock_add_version):
    mock_add_version.side_effect = RuntimeError("connection lost")
    db = MagicMock()
    case = _pedido_case()

    with pytest.raises(RuntimeError, match="connection lost"):
        DocumentService().register_pedido_document_upload(
            db,
            case,
            C.DOC_PEDIDO,
            StoredIncomingFile("x.jpg", "/tmp/x.jpg", None, "image/jpeg"),
        )


def test_user_facing_pedido_error_storage():
    from app.bot.handlers import _user_facing_pedido_error

    msg = _user_facing_pedido_error(OSError(13, "Permission denied"))
    assert "archivo" in msg.lower() or "almacenamiento" in msg.lower()
