"""Búsqueda global ERP (P27)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.erp_customer import ErpCustomer
from app.models.erp_sale import ErpSale


@dataclass(frozen=True)
class SearchHit:
    kind: str
    id: int
    label: str
    detail: str
    url: str


class ErpSearchService:
    def search(self, db: Session, query: str, *, limit: int = 30) -> list[SearchHit]:
        q = (query or "").strip()
        if len(q) < 2:
            return []
        pattern = f"%{q}%"
        hits: list[SearchHit] = []

        for c in db.scalars(
            select(ErpCustomer)
            .where(
                or_(
                    ErpCustomer.name.ilike(pattern),
                    ErpCustomer.rfc.ilike(pattern),
                    ErpCustomer.curp.ilike(pattern),
                )
            )
            .limit(limit)
        ).all():
            hits.append(
                SearchHit(
                    kind="cliente",
                    id=c.id,
                    label=c.name,
                    detail=f"RFC: {c.rfc or '—'} · CURP: {c.curp or '—'}",
                    url=f"/clientes/{c.id}",
                )
            )

        for s in db.scalars(
            select(ErpSale)
            .where(
                or_(
                    ErpSale.folio.ilike(pattern),
                    ErpSale.contract_code.ilike(pattern),
                )
            )
            .limit(limit)
        ).all():
            hits.append(
                SearchHit(
                    kind="venta",
                    id=s.id,
                    label=s.folio or f"Venta {s.id}",
                    detail=f"Vendedor: {s.vendedor or '—'} · ${s.total_amount}",
                    url=f"/clientes/{s.customer_id}",
                )
            )

        for ct in db.scalars(
            select(Contract)
            .where(
                or_(
                    Contract.folio.ilike(pattern),
                    Contract.contract_code.ilike(pattern),
                )
            )
            .limit(limit)
        ).all():
            hits.append(
                SearchHit(
                    kind="contrato",
                    id=ct.id,
                    label=ct.contract_code or ct.folio or f"Contrato {ct.id}",
                    detail=f"Cliente #{ct.customer_id} · saldo ${ct.current_balance}",
                    url=f"/clientes/{ct.customer_id}",
                )
            )

        return hits[:limit]
