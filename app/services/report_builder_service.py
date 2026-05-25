"""P51 — constructor de reportes guardados."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.enterprise_advanced import SavedReport
from app.models.sale_capture import SaleCapture


class ReportBuilderService:
    AVAILABLE_SOURCES = {
        "cases": {
            "columns": ["public_id", "client_name", "current_status", "seller_name", "updated_at"],
        },
        "sales": {
            "columns": ["folio", "cliente", "vendedor", "registration_status", "total_venta"],
        },
    }

    def list_saved(self, db: Session, *, company_id: int = 1) -> list[SavedReport]:
        return list(
            db.scalars(
                select(SavedReport)
                .where(SavedReport.company_id == company_id)
                .order_by(SavedReport.id.desc())
            ).all()
        )

    def save_report(
        self,
        db: Session,
        *,
        name: str,
        definition: dict[str, Any],
        created_by: str | None,
        shared: bool = False,
        company_id: int = 1,
    ) -> SavedReport:
        report = SavedReport(
            name=name,
            definition_json=definition,
            created_by=created_by,
            shared=shared,
            company_id=company_id,
        )
        db.add(report)
        db.flush()
        return report

    def run_report(self, db: Session, definition: dict[str, Any], *, limit: int = 500) -> list[dict[str, Any]]:
        source = definition.get("source", "cases")
        columns = definition.get("columns") or self.AVAILABLE_SOURCES.get(source, {}).get("columns", [])
        filters = definition.get("filters") or {}

        if source == "sales":
            stmt = select(SaleCapture).limit(limit)
            if filters.get("vendedor"):
                stmt = stmt.where(SaleCapture.vendedor.ilike(f"%{filters['vendedor']}%"))
            rows = list(db.scalars(stmt).all())
            return [{col: getattr(r, col, None) for col in columns} for r in rows]

        stmt = select(Case).limit(limit)
        if filters.get("status"):
            stmt = stmt.where(Case.current_status == filters["status"])
        rows = list(db.scalars(stmt).all())
        out = []
        for r in rows:
            row = {}
            for col in columns:
                val = getattr(r, col, None)
                row[col] = val.isoformat() if hasattr(val, "isoformat") else val
            out.append(row)
        return out

    def export_csv(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()
