"""Pruebas P32 — importación histórica Excel segura."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from app.core.paths import EXCEL_MASTER_DIR
from app.models.import_batch import (
    SOURCE_VENTAS,
    STATUS_CONFIRMED,
    STATUS_PREVIEWED,
    STATUS_UPLOADED,
    ImportBatch,
)
from app.services.commercial_report_service import read_ventas_rows_raw
from app.services.excel_import_service import (
    EVENT_CONFIRMED,
    EVENT_PREVIEWED,
    EVENT_UPLOADED,
    ERR_DUPLICATE,
    ERR_MISSING_COLUMNS,
    ExcelImportService,
)
from app.services.excel_path_guard import assert_not_excel_master_path, is_under_excel_masters


def _ventas_workbook(path: Path, rows: list[tuple] | None = None) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "CAPTURA_2026"
    ws.append(
        ["FECHA", "FOLIO", "VENDEDOR", "SECCION", "QNA", "CLIENTE", "RFC", "VENTA REAL"]
    )
    for r in rows or [
        (date(2026, 1, 15), "IMP-001", "JUAN PEREZ", "SEC-A", "2026Q1", "CLIENTE ALPHA", "RFCX", 2500),
        (date(2026, 1, 16), "IMP-002", "MARIA LOPEZ", "SEC-B", "2026Q1", "CLIENTE BETA", "RFCY", 1800),
    ]:
        ws.append(list(r))
    wb.save(path)


def _bad_headers_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "CAPTURA_2026"
    ws.append(["COL_A", "COL_B", "COL_C"])
    ws.append([1, 2, 3])
    wb.save(path)


@pytest.fixture
def import_dirs(tmp_path):
    imports = tmp_path / "imports"
    exports_root = tmp_path / "excel_exports"
    exports = exports_root / "imports"
    imports.mkdir(parents=True)
    exports.mkdir(parents=True)
    with (
        patch("app.services.excel_import_service.IMPORTS_DIR", imports),
        patch("app.services.excel_import_service.EXCEL_EXPORTS_IMPORTS_DIR", exports),
        patch("app.services.excel_path_guard.EXCEL_EXPORTS_DIR", exports_root),
    ):
        yield imports, exports


def test_read_ventas_rows_raw_from_non_master(tmp_path):
    xlsx = tmp_path / "ventas.xlsx"
    _ventas_workbook(xlsx)
    assert_not_excel_master_path(xlsx)
    rows, meta = read_ventas_rows_raw(xlsx)
    assert not meta.error
    assert len(rows) == 2
    assert rows[0]["folio"] == "IMP-001"
    assert rows[0]["total_amount"] == Decimal("2500")


def test_detect_missing_columns(import_dirs, tmp_path):
    xlsx = tmp_path / "bad.xlsx"
    _bad_headers_workbook(xlsx)
    db = MagicMock()
    batch = ImportBatch(
        id=1,
        source_type=SOURCE_VENTAS,
        original_filename="bad.xlsx",
        stored_path=str(xlsx),
        status=STATUS_UPLOADED,
        audit_trail=[],
    )
    db.get.return_value = batch

    svc = ExcelImportService()
    result = svc.preview_batch(db, 1)
    assert result.status == "failed"
    assert result.error_count >= 1
    db.add.assert_called()


def test_detect_duplicates_in_preview(import_dirs, tmp_path):
    xlsx = tmp_path / "dup.xlsx"
    _ventas_workbook(
        xlsx,
        [
            (date(2026, 1, 1), "DUP-1", "V1", "S", "Q", "C1", None, 100),
            (date(2026, 1, 2), "DUP-1", "V2", "S", "Q", "C2", None, 200),
        ],
    )
    db = MagicMock()
    batch = ImportBatch(
        id=2,
        source_type=SOURCE_VENTAS,
        original_filename="dup.xlsx",
        stored_path=str(xlsx),
        status=STATUS_UPLOADED,
        audit_trail=[],
    )
    db.get.return_value = batch
    db.scalars.return_value.all.return_value = []

    svc = ExcelImportService()
    result = svc.preview_batch(db, 2)
    assert result.duplicate_count >= 1
    assert result.ready_count == 1


def test_preview_dry_run_does_not_confirm(import_dirs, tmp_path):
    xlsx = tmp_path / "ok.xlsx"
    _ventas_workbook(xlsx)
    db = MagicMock()
    batch = ImportBatch(
        id=3,
        source_type=SOURCE_VENTAS,
        original_filename="ok.xlsx",
        stored_path=str(xlsx),
        status=STATUS_UPLOADED,
        audit_trail=[],
    )
    db.get.return_value = batch
    db.scalars.return_value.all.return_value = []

    svc = ExcelImportService()
    result = svc.preview_batch(db, 3)
    assert result.status == STATUS_PREVIEWED
    assert result.preview_json.get("dry_run") is True
    assert (result.imported_count or 0) == 0
    trail = result.audit_trail or []
    assert any(e["type"] == EVENT_PREVIEWED for e in trail)
    assert not any(e["type"] == EVENT_CONFIRMED for e in trail)


@patch("app.services.excel_import_service.BiDashboardService")
@patch("app.services.excel_import_service.ErpConsolidationService")
def test_confirm_writes_erp(mock_consolidation, mock_bi, import_dirs, tmp_path):
    xlsx = tmp_path / "confirm.xlsx"
    _ventas_workbook(xlsx, [(date(2026, 2, 1), "IMP-C1", "VEND", "S", "Q", "CLI", None, 5000)])

    contract = MagicMock(id=99)
    mock_consolidation.return_value.ensure_contract_for_sale.return_value = contract

    db = MagicMock()
    batch = ImportBatch(
        id=4,
        source_type=SOURCE_VENTAS,
        original_filename="confirm.xlsx",
        stored_path=str(xlsx),
        status=STATUS_PREVIEWED,
        ready_count=1,
        audit_trail=[{"type": EVENT_UPLOADED}],
    )
    db.get.return_value = batch
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None

    svc = ExcelImportService()
    result = svc.confirm_batch(db, 4)
    assert result.status == STATUS_CONFIRMED
    assert result.imported_count == 1
    mock_bi.return_value.clear_cache.assert_called_once()
    assert any(e["type"] == EVENT_CONFIRMED for e in (result.audit_trail or []))


def test_export_errors_not_in_masters(import_dirs, tmp_path):
    xlsx = tmp_path / "err.xlsx"
    _bad_headers_workbook(xlsx)
    db = MagicMock()
    batch = ImportBatch(id=5, source_type=SOURCE_VENTAS, original_filename="err.xlsx", stored_path=str(xlsx))
    db.get.return_value = batch
    err = MagicMock(
        row_number=0,
        sheet_name=None,
        error_code=ERR_MISSING_COLUMNS,
        message="Encabezados",
        raw_data=None,
    )
    db.scalars.return_value.all.return_value = [err]

    _, exports = import_dirs
    svc = ExcelImportService()
    path = svc.export_errors_xlsx(db, 5)
    assert path.exists()
    assert "excel_exports" in str(path).replace("\\", "/")
    assert not is_under_excel_masters(path)
    assert path.parent == exports


def test_upload_stored_under_imports_not_masters(import_dirs, tmp_path):
    imports, _ = import_dirs
    content = tmp_path / "sample.xlsx"
    _ventas_workbook(content)
    data = content.read_bytes()

    db = MagicMock()
    db.flush = MagicMock()

    def _add(obj):
        if isinstance(obj, ImportBatch) and not getattr(obj, "id", None):
            obj.id = 10

    db.add.side_effect = _add

    svc = ExcelImportService()
    batch = svc.create_batch_from_upload(
        db,
        content=data,
        filename="sample.xlsx",
        source_type=SOURCE_VENTAS,
        user_id=1,
        username="admin",
    )
    stored = Path(batch.stored_path)
    assert imports in stored.parents or stored.parent == imports
    assert EXCEL_MASTER_DIR not in stored.parents
    assert not is_under_excel_masters(stored)
    assert any(e["type"] == EVENT_UPLOADED for e in (batch.audit_trail or []))


def test_master_path_guard_blocks_import_read():
    master = EXCEL_MASTER_DIR / "ventas" / "fake.xlsx"
    with pytest.raises(ValueError, match="prohibida"):
        read_ventas_rows_raw(master)
