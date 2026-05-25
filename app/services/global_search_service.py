"""P41 — búsqueda global con ranking y agrupación."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.commission import Commission
from app.models.document import Document
from app.models.import_batch import ImportBatch
from app.models.sale_capture import SaleCapture
class GlobalSearchService:
    MAX_PER_GROUP = 8

    def search(self, db: Session, query: str, *, limit: int = 30) -> dict[str, Any]:
        q = (query or "").strip()
        if len(q) < 2:
            return {"query": q, "groups": [], "total": 0}

        groups: list[dict[str, Any]] = []
        cases = self._search_cases(db, q)
        if cases:
            groups.append({"key": "cases", "label": "Casos", "entries": cases, "count": len(cases)})

        sales = self._search_sales(db, q)
        if sales:
            groups.append({"key": "sales", "label": "Ventas", "entries": sales, "count": len(sales)})

        docs = self._search_documents(db, q)
        if docs:
            groups.append({"key": "documents", "label": "Documentos", "entries": docs, "count": len(docs)})

        commissions = self._search_commissions(db, q)
        if commissions:
            groups.append(
                {"key": "commissions", "label": "Comisiones", "entries": commissions, "count": len(commissions)}
            )

        imports = self._search_imports(db, q)
        if imports:
            groups.append({"key": "imports", "label": "Importaciones", "entries": imports, "count": len(imports)})

        total = sum(g["count"] for g in groups)
        return {"query": q, "groups": groups, "total": min(total, limit)}

    def _rank_case(self, case: Case, q: str) -> int:
        qu = q.upper()
        score = 0
        if case.public_id.upper() == qu:
            score += 100
        elif qu in (case.public_id or "").upper():
            score += 60
        if case.client_name and qu in case.client_name.upper():
            score += 40
        if case.official_folio and q in case.official_folio:
            score += 50
        return score

    def _search_cases(self, db: Session, q: str) -> list[dict[str, Any]]:
        stmt = select(Case).where(
            or_(
                Case.public_id.ilike(f"%{q}%"),
                Case.client_name.ilike(f"%{q}%"),
                Case.official_folio.ilike(f"%{q}%"),
                Case.temp_folio.ilike(f"%{q}%"),
                Case.seller_name.ilike(f"%{q}%"),
            )
        ).limit(40)
        rows = list(db.scalars(stmt).all())
        rows.sort(key=lambda c: self._rank_case(c, q), reverse=True)
        out = []
        for c in rows[: self.MAX_PER_GROUP]:
            out.append(
                {
                    "title": c.public_id,
                    "subtitle": c.client_name,
                    "meta": c.current_status,
                    "href": f"/casos/{c.id}",
                    "score": self._rank_case(c, q),
                    "quick_action": "Ver caso",
                }
            )
        return out

    def _search_sales(self, db: Session, q: str) -> list[dict[str, Any]]:
        stmt = select(SaleCapture).where(
            or_(
                SaleCapture.cliente.ilike(f"%{q}%"),
                SaleCapture.vendedor.ilike(f"%{q}%"),
                SaleCapture.rfc.ilike(f"%{q}%"),
                SaleCapture.folio.ilike(f"%{q}%"),
            )
        ).limit(self.MAX_PER_GROUP)
        rows = list(db.scalars(stmt).all())
        return [
            {
                "title": r.cliente or "Venta",
                "subtitle": r.vendedor or "",
                "meta": r.registration_status or r.status,
                "href": f"/ventas/{r.id}",
                "score": 30,
                "quick_action": "Ver venta",
            }
            for r in rows
        ]

    def _search_documents(self, db: Session, q: str) -> list[dict[str, Any]]:
        stmt = select(Document).where(
            or_(
                Document.original_filename.ilike(f"%{q}%"),
                Document.stored_filename.ilike(f"%{q}%"),
                Document.document_type.ilike(f"%{q}%"),
            )
        ).limit(self.MAX_PER_GROUP)
        rows = list(db.scalars(stmt).all())
        return [
            {
                "title": d.original_filename or d.stored_filename,
                "subtitle": d.document_type,
                "meta": f"case #{d.case_id}",
                "href": f"/casos/{d.case_id}",
                "score": 20,
                "quick_action": "Ver documento",
            }
            for d in rows
        ]

    def _search_commissions(self, db: Session, q: str) -> list[dict[str, Any]]:
        stmt = select(Commission).limit(self.MAX_PER_GROUP)
        if q.isdigit():
            stmt = stmt.where(Commission.id == int(q))
        else:
            stmt = stmt.where(Commission.seller_name.ilike(f"%{q}%"))
        rows = list(db.scalars(stmt).all())
        return [
            {
                "title": f"Comisión #{c.id}",
                "subtitle": c.seller_name or "",
                "meta": getattr(c, "payment_status", None) or "pending",
                "href": "/comisiones",
                "score": 15,
                "quick_action": "Ver comisiones",
            }
            for c in rows
        ]

    def _search_imports(self, db: Session, q: str) -> list[dict[str, Any]]:
        stmt = select(ImportBatch).where(
            ImportBatch.original_filename.ilike(f"%{q}%"),
        ).limit(self.MAX_PER_GROUP)
        rows = list(db.scalars(stmt).all())
        return [
            {
                "title": r.original_filename,
                "subtitle": r.source_type,
                "meta": str(r.row_count or 0) + " filas",
                "href": "/imports",
                "score": 10,
                "quick_action": "Ver import",
            }
            for r in rows
        ]
