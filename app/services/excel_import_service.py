"""Importación histórica segura desde Excel (P32)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.paths import EXCEL_EXPORTS_IMPORTS_DIR, IMPORTS_DIR
from app.models.contract import Contract
from app.models.erp_customer import ErpCustomer
from app.models.erp_payment import ErpPayment
from app.models.erp_sale import ErpSale
from app.models.import_batch import (
    SOURCE_CONTRATOS,
    SOURCE_VENTAS,
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PREVIEWED,
    STATUS_ROLLED_BACK,
    STATUS_UPLOADED,
    ImportBatch,
    ImportRowError,
    ImportedSaleReference,
)
from app.models.sale_capture import SaleCapture
from app.services.bi_dashboard_service import BiDashboardService
from app.services.commercial_report_service import (
    read_contratos_rows_raw,
    read_ventas_rows_raw,
)
from app.services.erp_consolidation_service import ErpConsolidationService
from app.services.excel_path_guard import assert_not_excel_master_path, assert_writable_excel_path

log = logging.getLogger(__name__)

EVENT_UPLOADED = "IMPORT_UPLOADED"
EVENT_PREVIEWED = "IMPORT_PREVIEWED"
EVENT_CONFIRMED = "IMPORT_CONFIRMED"
EVENT_FAILED = "IMPORT_FAILED"
EVENT_ROLLED_BACK = "IMPORT_ROLLED_BACK"

ERR_MISSING_COLUMNS = "MISSING_COLUMNS"
ERR_ROW_VALIDATION = "ROW_VALIDATION"
ERR_DUPLICATE = "DUPLICATE"
ERR_EMPTY_FOLIO = "EMPTY_FOLIO"
ERR_EMPTY_CLIENT = "EMPTY_CLIENT"
ERR_READ_FAILED = "READ_FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_vendedor(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    return text.upper() if text else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _row_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


class ExcelImportService:
    def __init__(self) -> None:
        self._consolidation = ErpConsolidationService()

    def ensure_directories(self) -> None:
        IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
        EXCEL_EXPORTS_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _append_audit(
        self,
        batch: ImportBatch,
        event_type: str,
        *,
        username: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        trail = list(batch.audit_trail or [])
        trail.append(
            {
                "type": event_type,
                "at": _utcnow().isoformat(),
                "username": username,
                "detail": detail or {},
            }
        )
        batch.audit_trail = trail

    def _safe_filename(self, name: str) -> str:
        base = Path(name).name
        return re.sub(r"[^\w.\-]+", "_", base)[:200] or "upload.xlsx"

    def create_batch_from_upload(
        self,
        db: Session,
        *,
        content: bytes,
        filename: str,
        source_type: str,
        user_id: int | None,
        username: str | None,
    ) -> ImportBatch:
        self.ensure_directories()
        if source_type not in (SOURCE_VENTAS, SOURCE_CONTRATOS):
            raise ValueError("source_type debe ser 'ventas' o 'contratos'.")

        batch = ImportBatch(
            source_type=source_type,
            original_filename=filename,
            stored_path="",
            status=STATUS_UPLOADED,
            created_by_user_id=user_id,
            created_by_username=username,
            audit_trail=[],
        )
        db.add(batch)
        db.flush()

        safe = self._safe_filename(filename)
        dest = IMPORTS_DIR / f"{batch.id}_{safe}"
        assert_not_excel_master_path(dest)
        dest.write_bytes(content)
        batch.stored_path = str(dest)
        self._append_audit(batch, EVENT_UPLOADED, username=username, detail={"filename": safe})
        db.flush()
        return batch

    def list_batches(self, db: Session, *, limit: int = 50) -> list[ImportBatch]:
        return list(
            db.scalars(
                select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit)
            ).all()
        )

    def get_batch(self, db: Session, batch_id: int) -> ImportBatch | None:
        return db.get(ImportBatch, batch_id)

    def _clear_row_errors(self, db: Session, batch_id: int) -> None:
        db.execute(delete(ImportRowError).where(ImportRowError.batch_id == batch_id))

    def _add_row_error(
        self,
        db: Session,
        batch_id: int,
        *,
        row_number: int,
        sheet_name: str | None,
        error_code: str,
        message: str,
        raw_data: dict[str, Any] | None,
    ) -> None:
        db.add(
            ImportRowError(
                batch_id=batch_id,
                row_number=row_number,
                sheet_name=sheet_name,
                error_code=error_code,
                message=message,
                raw_data=raw_data,
            )
        )

    def _existing_folios(self, db: Session) -> set[str]:
        folios: set[str] = set()
        for f in db.scalars(select(ErpSale.folio).where(ErpSale.folio.isnot(None))).all():
            if f:
                folios.add(str(f).strip().upper())
        for f in db.scalars(select(SaleCapture.folio)).all():
            if f:
                folios.add(str(f).strip().upper())
        return folios

    def _is_duplicate_folio(
        self,
        db: Session,
        folio: str,
        *,
        seen_in_file: set[str],
        existing: set[str],
    ) -> bool:
        key = folio.strip().upper()
        if not key:
            return False
        if key in seen_in_file or key in existing:
            return True
        seen_in_file.add(key)
        return False

    def preview_batch(
        self,
        db: Session,
        batch_id: int,
        *,
        username: str | None = None,
        limit: int = 5000,
    ) -> ImportBatch:
        batch = db.get(ImportBatch, batch_id)
        if not batch:
            raise ValueError("Lote no encontrado.")
        if batch.status == STATUS_ROLLED_BACK:
            raise ValueError("Lote revertido; no se puede previsualizar.")

        path = Path(batch.stored_path)
        assert_not_excel_master_path(path)
        self._clear_row_errors(db, batch.id)

        if batch.source_type == SOURCE_VENTAS:
            rows, meta = read_ventas_rows_raw(path, limit=limit)
        else:
            rows, meta = read_contratos_rows_raw(path, limit=limit)

        if meta.error:
            batch.status = STATUS_FAILED
            batch.error_message = meta.error
            self._add_row_error(
                db,
                batch.id,
                row_number=0,
                sheet_name=None,
                error_code=ERR_MISSING_COLUMNS if "Encabezado" in meta.error else ERR_READ_FAILED,
                message=meta.error,
                raw_data=None,
            )
            batch.error_count = 1
            self._append_audit(batch, EVENT_FAILED, username=username, detail={"error": meta.error})
            db.flush()
            return batch

        existing_folios = self._existing_folios(db)
        seen_file: set[str] = set()
        ready = 0
        dupes = 0
        errors = 0
        sample_ready: list[dict[str, Any]] = []
        sample_errors: list[dict[str, Any]] = []

        for row in rows:
            row_num = int(row.get("row_number") or 0)
            sheet = row.get("sheet_name")
            snap = _row_snapshot(row)
            folio = str(row.get("folio") or "").strip()
            cliente = str(row.get("cliente") or "").strip()

            if batch.source_type == SOURCE_VENTAS:
                if not folio:
                    errors += 1
                    self._add_row_error(
                        db,
                        batch.id,
                        row_number=row_num,
                        sheet_name=sheet,
                        error_code=ERR_EMPTY_FOLIO,
                        message="Folio vacío.",
                        raw_data=snap,
                    )
                    if len(sample_errors) < 20:
                        sample_errors.append({"row": row_num, "code": ERR_EMPTY_FOLIO})
                    continue
                if not cliente:
                    errors += 1
                    self._add_row_error(
                        db,
                        batch.id,
                        row_number=row_num,
                        sheet_name=sheet,
                        error_code=ERR_EMPTY_CLIENT,
                        message="Cliente vacío.",
                        raw_data=snap,
                    )
                    continue
                if self._is_duplicate_folio(db, folio, seen_in_file=seen_file, existing=existing_folios):
                    dupes += 1
                    self._add_row_error(
                        db,
                        batch.id,
                        row_number=row_num,
                        sheet_name=sheet,
                        error_code=ERR_DUPLICATE,
                        message=f"Folio duplicado: {folio}",
                        raw_data=snap,
                    )
                    if len(sample_errors) < 20:
                        sample_errors.append({"row": row_num, "code": ERR_DUPLICATE, "folio": folio})
                    continue
                ready += 1
                if len(sample_ready) < 25:
                    sample_ready.append(
                        {
                            "row": row_num,
                            "folio": folio,
                            "cliente": cliente,
                            "vendedor": _normalize_vendedor(row.get("vendedor")),
                            "total_amount": str(row.get("total_amount")),
                        }
                    )
            else:
                code = str(row.get("contract_code") or folio or "").strip()
                if not cliente and not code:
                    errors += 1
                    self._add_row_error(
                        db,
                        batch.id,
                        row_number=row_num,
                        sheet_name=sheet,
                        error_code=ERR_ROW_VALIDATION,
                        message="Cliente y código de contrato vacíos.",
                        raw_data=snap,
                    )
                    continue
                import_key = f"contratos:{code or folio}:{sheet}"
                if folio and self._is_duplicate_folio(
                    db, folio, seen_in_file=seen_file, existing=existing_folios
                ):
                    dupes += 1
                    self._add_row_error(
                        db,
                        batch.id,
                        row_number=row_num,
                        sheet_name=sheet,
                        error_code=ERR_DUPLICATE,
                        message=f"Folio duplicado: {folio}",
                        raw_data=snap,
                    )
                    continue
                ready += 1
                if len(sample_ready) < 25:
                    sample_ready.append(
                        {
                            "row": row_num,
                            "folio": folio,
                            "contract_code": code,
                            "cliente": cliente,
                            "vendedor": _normalize_vendedor(row.get("vendedor")),
                        }
                    )

        batch.row_count = len(rows)
        batch.ready_count = ready
        batch.duplicate_count = dupes
        batch.error_count = errors
        batch.preview_json = {
            "dry_run": True,
            "source_type": batch.source_type,
            "sheets": [d.sheet_name for d in meta.diagnostics],
            "sample_ready": sample_ready,
            "sample_errors": sample_errors,
        }
        batch.status = STATUS_PREVIEWED
        batch.previewed_at = _utcnow()
        self._append_audit(
            batch,
            EVENT_PREVIEWED,
            username=username,
            detail={
                "row_count": batch.row_count,
                "ready_count": ready,
                "duplicate_count": dupes,
                "error_count": errors,
            },
        )
        db.flush()
        return batch

    def _get_or_create_customer(self, db: Session, row: dict[str, Any]) -> ErpCustomer:
        name = str(row.get("cliente") or "").strip()
        customer = db.scalar(select(ErpCustomer).where(ErpCustomer.name == name).limit(1))
        if customer:
            if row.get("seccion") and not customer.seccion:
                customer.seccion = row.get("seccion")
            if row.get("rfc") and not customer.rfc:
                customer.rfc = row.get("rfc")
            return customer
        customer = ErpCustomer(
            name=name,
            seccion=row.get("seccion"),
            rfc=row.get("rfc"),
        )
        db.add(customer)
        db.flush()
        return customer

    def confirm_batch(
        self,
        db: Session,
        batch_id: int,
        *,
        username: str | None = None,
        limit: int = 5000,
    ) -> ImportBatch:
        batch = db.get(ImportBatch, batch_id)
        if not batch:
            raise ValueError("Lote no encontrado.")
        if batch.status != STATUS_PREVIEWED:
            raise ValueError("Debe ejecutar vista previa antes de confirmar.")
        if batch.ready_count <= 0:
            raise ValueError("No hay filas listas para importar.")

        path = Path(batch.stored_path)
        assert_not_excel_master_path(path)

        if batch.source_type == SOURCE_VENTAS:
            rows, meta = read_ventas_rows_raw(path, limit=limit)
        else:
            rows, meta = read_contratos_rows_raw(path, limit=limit)

        if meta.error:
            batch.status = STATUS_FAILED
            batch.error_message = meta.error
            self._append_audit(batch, EVENT_FAILED, username=username, detail={"error": meta.error})
            db.flush()
            raise ValueError(meta.error)

        existing_folios = self._existing_folios(db)
        seen_file: set[str] = set()
        imported = 0

        for row in rows:
            folio = str(row.get("folio") or "").strip()
            cliente = str(row.get("cliente") or "").strip()
            row_num = int(row.get("row_number") or 0)
            sheet = row.get("sheet_name")

            if batch.source_type == SOURCE_VENTAS:
                if not folio or not cliente:
                    continue
                if self._is_duplicate_folio(db, folio, seen_in_file=seen_file, existing=existing_folios):
                    continue

                customer = self._get_or_create_customer(db, row)
                sale = ErpSale(
                    customer_id=customer.id,
                    folio=folio,
                    vendedor=_normalize_vendedor(row.get("vendedor")),
                    seccion=row.get("seccion"),
                    sale_date=row.get("sale_date"),
                    total_amount=row.get("total_amount") or Decimal("0"),
                    status="active",
                )
                db.add(sale)
                db.flush()
                contract = self._consolidation.ensure_contract_for_sale(db, sale.id)
                import_key = f"ventas:{folio}"
                db.add(
                    ImportedSaleReference(
                        batch_id=batch.id,
                        erp_sale_id=sale.id,
                        erp_customer_id=customer.id,
                        contract_id=contract.id,
                        folio=folio,
                        import_key=import_key,
                        row_number=row_num,
                        is_active=True,
                    )
                )
                existing_folios.add(folio.strip().upper())
                imported += 1
            else:
                code = str(row.get("contract_code") or folio or "").strip()
                if not cliente and not code:
                    continue
                if folio and self._is_duplicate_folio(
                    db, folio, seen_in_file=seen_file, existing=existing_folios
                ):
                    continue

                customer = self._get_or_create_customer(db, row)
                sale = None
                if folio:
                    sale = db.scalar(select(ErpSale).where(ErpSale.folio == folio).limit(1))
                if not sale:
                    sale = ErpSale(
                        customer_id=customer.id,
                        folio=folio or None,
                        contract_code=code or None,
                        vendedor=_normalize_vendedor(row.get("vendedor")),
                        sale_date=None,
                        total_amount=row.get("total_amount") or Decimal("0"),
                        status="active",
                    )
                    db.add(sale)
                    db.flush()
                    if folio:
                        existing_folios.add(folio.strip().upper())

                if code and not sale.contract_code:
                    sale.contract_code = code
                contract = self._consolidation.ensure_contract_for_sale(db, sale.id)
                import_key = f"contratos:{code or folio}:{sheet}"
                db.add(
                    ImportedSaleReference(
                        batch_id=batch.id,
                        erp_sale_id=sale.id,
                        erp_customer_id=customer.id,
                        contract_id=contract.id,
                        folio=folio or None,
                        contract_code=code or None,
                        import_key=import_key,
                        row_number=row_num,
                        is_active=True,
                    )
                )
                imported += 1

        batch.imported_count = imported
        batch.status = STATUS_CONFIRMED
        batch.confirmed_at = _utcnow()
        self._append_audit(
            batch,
            EVENT_CONFIRMED,
            username=username,
            detail={"imported_count": imported},
        )
        BiDashboardService().clear_cache()
        db.flush()
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="import_completed",
                title=f"Import confirmado: lote {batch_id}",
                entity_type="import_batch",
                entity_id=batch_id,
                actor_label=username,
                source="imports",
                href="/imports",
                automation_trigger="import_completed",
                automation_context={"batch_id": batch_id, "imported": imported},
            )
        except Exception:
            pass
        return batch

    def rollback_batch(
        self,
        db: Session,
        batch_id: int,
        *,
        username: str | None = None,
    ) -> ImportBatch:
        batch = db.get(ImportBatch, batch_id)
        if not batch:
            raise ValueError("Lote no encontrado.")
        if batch.status != STATUS_CONFIRMED:
            raise ValueError("Solo se puede revertir un lote confirmado.")

        refs = list(
            db.scalars(
                select(ImportedSaleReference).where(
                    ImportedSaleReference.batch_id == batch.id,
                    ImportedSaleReference.is_active.is_(True),
                )
            ).all()
        )

        for ref in refs:
            if ref.contract_id:
                contract = db.get(Contract, ref.contract_id)
                if contract and contract.sales_sale_id == ref.erp_sale_id:
                    db.delete(contract)
            if ref.erp_sale_id:
                has_payments = db.scalar(
                    select(ErpPayment.id).where(ErpPayment.sale_id == ref.erp_sale_id).limit(1)
                )
                if not has_payments:
                    sale = db.get(ErpSale, ref.erp_sale_id)
                    if sale:
                        db.delete(sale)
            ref.is_active = False

        batch.status = STATUS_ROLLED_BACK
        batch.rolled_back_at = _utcnow()
        self._append_audit(batch, EVENT_ROLLED_BACK, username=username, detail={"refs": len(refs)})
        BiDashboardService().clear_cache()
        db.flush()
        return batch

    def list_row_errors(self, db: Session, batch_id: int) -> list[ImportRowError]:
        return list(
            db.scalars(
                select(ImportRowError)
                .where(ImportRowError.batch_id == batch_id)
                .order_by(ImportRowError.row_number)
            ).all()
        )

    def export_errors_xlsx(self, db: Session, batch_id: int) -> Path:
        batch = db.get(ImportBatch, batch_id)
        if not batch:
            raise ValueError("Lote no encontrado.")

        errors = self.list_row_errors(db, batch_id)
        out = EXCEL_EXPORTS_IMPORTS_DIR / f"import_errors_{batch_id}.xlsx"
        assert_writable_excel_path(out)

        wb = Workbook()
        ws = wb.active
        ws.title = "Errores"
        ws.append(["Fila", "Hoja", "Código", "Mensaje", "Datos"])
        for err in errors:
            raw = json.dumps(err.raw_data, ensure_ascii=False, default=str) if err.raw_data else ""
            ws.append([err.row_number, err.sheet_name or "", err.error_code, err.message, raw])
        wb.save(out)
        return out
