"""Detección de duplicados en capturas de venta (P19.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.sale_capture import SALE_STATUS_REGISTERED, SaleCapture


@dataclass
class DuplicateCheckResult:
    blocked: bool = False
    block_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    strong_matches: list[int] = field(default_factory=list)
    probable_matches: list[int] = field(default_factory=list)


def _sale_amount(sale: SaleCapture | dict[str, Any]) -> Decimal | None:
    if isinstance(sale, dict):
        for key in ("total_venta", "venta"):
            val = sale.get(key)
            if val is not None and str(val).strip():
                try:
                    return Decimal(str(val).replace(",", "").replace("$", ""))
                except Exception:
                    pass
        return None
    for attr in ("total_venta", "venta"):
        val = getattr(sale, attr, None)
        if val is not None:
            return Decimal(val)
    return None


def _amounts_close(a: Decimal | None, b: Decimal | None, tol: Decimal = Decimal("0.01")) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def check_duplicates(
    db: Session,
    data: dict[str, Any],
    *,
    sale_id: int | None = None,
    case_id: int | None = None,
) -> DuplicateCheckResult:
    result = DuplicateCheckResult()
    folio = str(data.get("folio") or "").strip()
    rfc = (data.get("rfc") or "").strip().upper()
    cliente = (data.get("cliente") or "").strip().upper()
    amount = _sale_amount(data)
    sale_date = data.get("sale_date")

    if case_id:
        other = db.scalar(
            select(SaleCapture.id).where(
                SaleCapture.case_id == case_id,
                SaleCapture.status == SALE_STATUS_REGISTERED,
                SaleCapture.id != sale_id if sale_id else True,
            )
        )
        if other:
            result.blocked = True
            result.block_reason = (
                f"El caso #{case_id} ya tiene una venta registrada (captura #{other})."
            )
            result.strong_matches.append(int(other))
            return result

    if folio:
        stmt = select(SaleCapture).where(SaleCapture.folio == folio)
        if sale_id:
            stmt = stmt.where(SaleCapture.id != sale_id)
        existing = db.scalar(stmt)
        if existing:
            result.blocked = True
            result.block_reason = f"El folio {folio} ya está en captura #{existing.id}."
            result.strong_matches.append(existing.id)
            return result
        case_folio = db.scalar(select(Case.id).where(Case.official_folio == folio))
        if case_folio and (not case_id or case_folio != case_id):
            result.blocked = True
            result.block_reason = f"El folio {folio} ya está asignado al caso #{case_folio}."
            return result

    if not rfc or not cliente or amount is None:
        return result

    base = select(SaleCapture).where(
        SaleCapture.rfc.isnot(None),
        func.upper(SaleCapture.rfc) == rfc,
        func.upper(SaleCapture.cliente) == cliente,
    )
    if sale_id:
        base = base.where(SaleCapture.id != sale_id)

    for cand in db.scalars(base.limit(20)).all():
        cand_amt = _sale_amount(cand)
        if not _amounts_close(amount, cand_amt):
            continue
        if sale_date and cand.sale_date:
            delta = abs((sale_date - cand.sale_date).days)
            if delta <= 3:
                result.warnings.append(
                    f"Posible duplicado: captura #{cand.id} (folio {cand.folio}) "
                    f"mismo RFC, cliente e importe con fecha cercana ({delta} días)."
                )
                result.probable_matches.append(cand.id)
            else:
                result.warnings.append(
                    f"Posible duplicado por RFC+cliente+importe: captura #{cand.id} (folio {cand.folio})."
                )
                result.probable_matches.append(cand.id)
        else:
            result.warnings.append(
                f"Posible duplicado por RFC+cliente+importe: captura #{cand.id} (folio {cand.folio})."
            )
            result.probable_matches.append(cand.id)

    return result
