"""Rutas de plantillas y masters Excel bajo storage/."""

from pathlib import Path

# Raíz del repositorio (app/core/paths.py → app → repo)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

STORAGE_DIR = PROJECT_ROOT / "storage"
TEMPLATE_DIR = STORAGE_DIR / "templates"
EXCEL_MASTER_DIR = STORAGE_DIR / "excel_masters"

VENTAS_MASTER_PATH = EXCEL_MASTER_DIR / "ventas" / "Ventas_2026_COMISION_FINAL_v15.xlsx"
CONTRATOS_MASTER_PATH = EXCEL_MASTER_DIR / "contratos" / "PLANTILLA_RELACION_DE_CONTRATOS.xlsx"

# Copias de exportación (no modificar masters originales)
EXCEL_EXPORTS_DIR = STORAGE_DIR / "excel_exports"
EXCEL_EXPORTS_DAILY_DIR = EXCEL_EXPORTS_DIR / "daily"
EXCEL_EXPORTS_OPS_DIR = EXCEL_EXPORTS_DIR / "operations"
COMMISSION_EXPORTS_DIR = STORAGE_DIR / "commission_exports"

VENTAS_MASTER_FILENAME = VENTAS_MASTER_PATH.name
CONTRATOS_MASTER_FILENAME = CONTRATOS_MASTER_PATH.name

# Plantillas SNTE / refinanciamiento (nombres de archivo estables)
MASTER_AUTORIZACIONES_PATH = TEMPLATE_DIR / "plantilla_master_autorizaciones.xlsx"
ORDEN_SNTE_PDF_PATH = TEMPLATE_DIR / "plantilla_orden_snte.pdf"
REFINANCIAMIENTO_TEMPLATE_PATH = TEMPLATE_DIR / "plantilla_refinanciamiento.xlsx"
