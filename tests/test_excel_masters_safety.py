"""P23: maestros Excel no deben recibir escrituras de registro de ventas."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.paths import (
    CONTRATOS_MASTER_PATH,
    EXCEL_EXPORTS_DIR,
    EXCEL_MASTER_DIR,
    VENTAS_MASTER_PATH,
)
from app.services.excel_path_guard import (
    assert_writable_excel_path,
    is_under_excel_exports,
    is_under_excel_masters,
)
from app.services.excel_registry_service import ExcelRegistryError, ExcelRegistryService


def test_master_paths_live_under_excel_masters_dir():
    assert is_under_excel_masters(VENTAS_MASTER_PATH)
    assert is_under_excel_masters(CONTRATOS_MASTER_PATH)
    assert EXCEL_MASTER_DIR in VENTAS_MASTER_PATH.parents


def test_exports_path_not_master():
    export_example = EXCEL_EXPORTS_DIR / "operations" / "99" / "ventas.xlsx"
    assert is_under_excel_exports(export_example)
    assert not is_under_excel_masters(export_example)


def test_assert_writable_rejects_master_path():
    with pytest.raises(ValueError, match="maestro"):
        assert_writable_excel_path(VENTAS_MASTER_PATH)


def test_assert_writable_accepts_exports_path(tmp_path):
    dest = tmp_path / "excel_exports" / "operations" / "1" / "ventas.xlsx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Resolver contra proyecto: usar ruta bajo EXCEL_EXPORTS_DIR real
    under_exports = EXCEL_EXPORTS_DIR / "operations" / "test_safety" / "v.xlsx"
    under_exports.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_excel_path(under_exports)


def test_ensure_copy_blocks_dest_on_master():
    svc = ExcelRegistryService()
    with pytest.raises(ExcelRegistryError) as exc:
        svc.ensure_copy(VENTAS_MASTER_PATH, VENTAS_MASTER_PATH)
    assert exc.value.code == "master_write_forbidden"


@patch("app.services.excel_registry_service.shutil.copy2")
def test_ensure_copy_writes_only_to_exports_dest(mock_copy2, tmp_path):
    master = tmp_path / "masters" / "ventas.xlsx"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"x")
    dest = EXCEL_EXPORTS_DIR / "operations" / "42" / "ventas.xlsx"
    dest.parent.mkdir(parents=True, exist_ok=True)

    svc = ExcelRegistryService()
    result = svc.ensure_copy(master, dest)
    assert result == dest
    mock_copy2.assert_called_once()
    _src, dst = mock_copy2.call_args[0]
    assert dst == dest
    assert not is_under_excel_masters(dst)


@patch("app.services.excel_registry_service.load_workbook")
def test_append_ventas_save_target_not_master(mock_load_wb):
    from datetime import date

    from app.models.sale_capture import SaleCapture

    mock_wb = MagicMock()
    mock_ws = MagicMock()
    mock_ws.max_row = 6
    mock_wb.sheetnames = ["CAPTURA_2026"]
    mock_wb.__getitem__.return_value = mock_ws
    mock_load_wb.return_value = mock_wb

    sale = SaleCapture(
        id=1,
        status="draft",
        registration_status="draft",
        folio="00001",
        sale_date=date.today(),
        vendedor="TEST",
        cliente="CLIENTE",
    )
    export_path = EXCEL_EXPORTS_DIR / "operations" / "1" / "Ventas_2026_COMISION_FINAL_v15.xlsx"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_bytes(b"fake")

    svc = ExcelRegistryService()
    with patch(
        "app.services.excel_registry_service._next_empty_row_ventas",
        return_value=7,
    ):
        svc._append_ventas(export_path, sale, "S1")

    mock_wb.save.assert_called_once()
    saved_path = mock_wb.save.call_args[0][0]
    assert is_under_excel_exports(saved_path)
    assert not is_under_excel_masters(saved_path)
