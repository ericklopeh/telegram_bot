"""P75 — storage readiness y estructura de carpetas."""

from pathlib import Path

from app.services.case_document_storage import case_documents_base_dir
from app.services.storage.readiness import StorageReadinessChecklist


from datetime import datetime, timezone


class _FakeCase:
    created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    week_code = "SEM_12"
    seller_name = "Vendedor Test"
    official_folio = "F-001"
    client_name = "Cliente SA"
    temp_folio = None
    public_id = "pub-1"
    id = 1


def test_storage_readiness_checklist():
    cl = StorageReadinessChecklist.default_local()
    data = cl.to_dict()
    assert data["provider"] == "local"
    assert any(i["key"] == "folder_layout" and i["done"] for i in data["items"])


def test_case_documents_path_structure():
    path = case_documents_base_dir(_FakeCase(), project_root=Path("/tmp/gaman_test"))
    parts = path.parts
    assert "cases" in parts
    assert any("SEM" in p for p in parts)
    assert "documents" in parts


def test_p75_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P75_STORAGE_READINESS.md"
    assert doc.is_file()
    assert "SharePoint" in doc.read_text(encoding="utf-8")
