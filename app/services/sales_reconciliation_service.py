"""Conciliación entre capturas de venta en BD y archivos Excel exportados (P20-E)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.sale_capture import (
    REG_STATUS_REGISTRATION_FAILED,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_REGISTERED,
    SaleCapture,
    can_retry_registration,
    effective_registration_status,
    is_registration_complete,
)
from app.repositories.sale_capture_repository import SaleCaptureRepository

CONCILIATION_OK = "CONCILIATION_OK"
CONCILIATION_WARNING = "CONCILIATION_WARNING"
CONCILIATION_ERROR = "CONCILIATION_ERROR"


@dataclass
class ReconciliationIssue:
    sale_id: int
    folio: str
    cliente: str
    vendedor: str
    problem: str
    severity: str
    suggested_action: str
    can_retry: bool = False


def _sale_amount(sale: SaleCapture) -> Decimal | None:
    return sale.total_venta or sale.venta


def _path_exists(path_str: str | None) -> bool:
    if not path_str:
        return False
    return Path(path_str).is_file()


def _duplicate_folio_issues(sales: list[SaleCapture]) -> list[ReconciliationIssue]:
    by_folio: dict[str, list[SaleCapture]] = defaultdict(list)
    for s in sales:
        by_folio[str(s.folio).strip()].append(s)
    issues: list[ReconciliationIssue] = []
    for folio, group in by_folio.items():
        if len(group) < 2:
            continue
        for s in group:
            issues.append(
                ReconciliationIssue(
                    sale_id=s.id,
                    folio=s.folio,
                    cliente=s.cliente,
                    vendedor=s.vendedor,
                    problem=f"Folio duplicado en BD ({len(group)} capturas)",
                    severity=CONCILIATION_ERROR,
                    suggested_action="Revisar capturas y corregir folio antes de reintentar registro.",
                    can_retry=can_retry_registration(s),
                )
            )
    return issues


def _duplicate_business_key_issues(sales: list[SaleCapture]) -> list[ReconciliationIssue]:
    keys: dict[tuple[str, str, str], list[SaleCapture]] = defaultdict(list)
    for s in sales:
        amt = _sale_amount(s)
        if not s.rfc or not s.cliente or amt is None:
            continue
        key = (
            (s.rfc or "").strip().upper(),
            (s.cliente or "").strip().upper(),
            str(amt),
        )
        keys[key].append(s)
    issues: list[ReconciliationIssue] = []
    for _, group in keys.items():
        if len(group) < 2:
            continue
        for s in group:
            issues.append(
                ReconciliationIssue(
                    sale_id=s.id,
                    folio=s.folio,
                    cliente=s.cliente,
                    vendedor=s.vendedor,
                    problem="RFC + cliente + importe duplicado en BD",
                    severity=CONCILIATION_WARNING,
                    suggested_action="Verificar si es la misma operación o duplicado operativo.",
                    can_retry=can_retry_registration(s),
                )
            )
    return issues


def _per_sale_issues(sale: SaleCapture) -> list[ReconciliationIssue]:
    issues: list[ReconciliationIssue] = []
    reg_status = effective_registration_status(sale)
    ventas_ok = _path_exists(sale.ventas_export_path)
    contratos_ok = _path_exists(sale.contratos_export_path)
    can_retry = can_retry_registration(sale)

    if is_registration_complete(sale) or sale.status == SALE_STATUS_REGISTERED:
        if not ventas_ok:
            issues.append(
                ReconciliationIssue(
                    sale_id=sale.id,
                    folio=sale.folio,
                    cliente=sale.cliente,
                    vendedor=sale.vendedor,
                    problem="Registrada en BD sin archivo Excel de ventas",
                    severity=CONCILIATION_ERROR,
                    suggested_action="Reintentar registro o regenerar exportación.",
                    can_retry=can_retry,
                )
            )
        if not contratos_ok:
            issues.append(
                ReconciliationIssue(
                    sale_id=sale.id,
                    folio=sale.folio,
                    cliente=sale.cliente,
                    vendedor=sale.vendedor,
                    problem="Registrada en BD sin archivo Excel de contratos",
                    severity=CONCILIATION_ERROR,
                    suggested_action="Reintentar registro o regenerar exportación.",
                    can_retry=can_retry,
                )
            )
        if sale.ventas_export_path and not ventas_ok:
            issues.append(
                ReconciliationIssue(
                    sale_id=sale.id,
                    folio=sale.folio,
                    cliente=sale.cliente,
                    vendedor=sale.vendedor,
                    problem="Ruta de exportación ventas inexistente en disco",
                    severity=CONCILIATION_ERROR,
                    suggested_action="Verificar storage/excel_exports y reintentar.",
                    can_retry=can_retry,
                )
            )
        if sale.contratos_export_path and not contratos_ok:
            issues.append(
                ReconciliationIssue(
                    sale_id=sale.id,
                    folio=sale.folio,
                    cliente=sale.cliente,
                    vendedor=sale.vendedor,
                    problem="Ruta de exportación contratos inexistente en disco",
                    severity=CONCILIATION_ERROR,
                    suggested_action="Verificar storage/excel_exports y reintentar.",
                    can_retry=can_retry,
                )
            )

    if (ventas_ok or contratos_ok) and not is_registration_complete(sale):
        if sale.status != SALE_STATUS_REGISTERED:
            issues.append(
                ReconciliationIssue(
                    sale_id=sale.id,
                    folio=sale.folio,
                    cliente=sale.cliente,
                    vendedor=sale.vendedor,
                    problem="Hay archivos exportados pero la venta no está marcada como registrada",
                    severity=CONCILIATION_WARNING,
                    suggested_action="Completar registro o limpiar exportaciones huérfanas.",
                    can_retry=can_retry,
                )
            )

    if reg_status == REG_STATUS_REGISTRATION_FAILED or sale.status == SALE_STATUS_EXPORT_FAILED:
        err = sale.registration_error or sale.export_error or "Error de registro"
        issues.append(
            ReconciliationIssue(
                sale_id=sale.id,
                folio=sale.folio,
                cliente=sale.cliente,
                vendedor=sale.vendedor,
                problem=f"Registro fallido: {err}",
                severity=CONCILIATION_ERROR,
                suggested_action="Corregir causa (Excel abierto, permisos, plantilla) y reintentar.",
                can_retry=can_retry,
            )
        )
    elif sale.export_error and sale.status != SALE_STATUS_REGISTERED:
        issues.append(
            ReconciliationIssue(
                sale_id=sale.id,
                folio=sale.folio,
                cliente=sale.cliente,
                vendedor=sale.vendedor,
                problem=f"export_error activo: {sale.export_error}",
                severity=CONCILIATION_WARNING,
                suggested_action="Revisar error y reintentar registro.",
                can_retry=can_retry,
            )
        )

    return issues


def build_reconciliation_report(db: Session) -> dict[str, Any]:
    sales = SaleCaptureRepository.list_for_reconciliation(db)
    issues: list[ReconciliationIssue] = []
    seen: set[tuple[int, str]] = set()

    def _add(item: ReconciliationIssue) -> None:
        key = (item.sale_id, item.problem)
        if key in seen:
            return
        seen.add(key)
        issues.append(item)

    for sale in sales:
        for item in _per_sale_issues(sale):
            _add(item)
    for item in _duplicate_folio_issues(sales):
        _add(item)
    for item in _duplicate_business_key_issues(sales):
        _add(item)

    errors = sum(1 for i in issues if i.severity == CONCILIATION_ERROR)
    warnings = sum(1 for i in issues if i.severity == CONCILIATION_WARNING)
    ok_count = max(0, len(sales) - len({i.sale_id for i in issues}))

    severity_order = {
        CONCILIATION_ERROR: 0,
        CONCILIATION_WARNING: 1,
        CONCILIATION_OK: 2,
    }
    issues.sort(key=lambda x: (severity_order.get(x.severity, 9), x.folio))

    return {
        "total_sales": len(sales),
        "issue_count": len(issues),
        "error_count": errors,
        "warning_count": warnings,
        "ok_estimate": ok_count,
        "issues": issues,
        "has_issues": bool(issues),
    }
