"""Filtros globales del dashboard BI (P29)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select

from app.models.case import Case
from app.models.sale_capture import SaleCapture


@dataclass(frozen=True)
class BiFilters:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    semana: str | None = None
    qna: str | None = None
    vendedor: str | None = None
    seccion: str | None = None
    tipo_venta: str | None = None
    workflow_state: str | None = None

    @classmethod
    def from_query(
        cls,
        *,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
        semana: str | None = None,
        qna: str | None = None,
        vendedor: str | None = None,
        seccion: str | None = None,
        tipo_venta: str | None = None,
        workflow_state: str | None = None,
    ) -> BiFilters:
        def _parse_d(raw: str | None) -> date | None:
            if not raw or not raw.strip():
                return None
            try:
                return date.fromisoformat(raw.strip()[:10])
            except ValueError:
                return None

        return cls(
            fecha_desde=_parse_d(fecha_desde),
            fecha_hasta=_parse_d(fecha_hasta),
            semana=(semana or "").strip() or None,
            qna=(qna or "").strip() or None,
            vendedor=(vendedor or "").strip() or None,
            seccion=(seccion or "").strip() or None,
            tipo_venta=(tipo_venta or "").strip() or None,
            workflow_state=(workflow_state or "").strip() or None,
        )

    def cache_key(self) -> str:
        payload = {
            "fecha_desde": self.fecha_desde.isoformat() if self.fecha_desde else None,
            "fecha_hasta": self.fecha_hasta.isoformat() if self.fecha_hasta else None,
            "semana": self.semana,
            "qna": self.qna,
            "vendedor": self.vendedor,
            "seccion": self.seccion,
            "tipo_venta": self.tipo_venta,
            "workflow_state": self.workflow_state,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]

    def to_query_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.fecha_desde:
            out["fecha_desde"] = self.fecha_desde.isoformat()
        if self.fecha_hasta:
            out["fecha_hasta"] = self.fecha_hasta.isoformat()
        for key in ("semana", "qna", "vendedor", "seccion", "tipo_venta", "workflow_state"):
            val = getattr(self, key)
            if val:
                out[key] = val
        return out

    def _apply_sale(self, stmt: Select) -> Select:
        if self.fecha_desde:
            stmt = stmt.where(SaleCapture.sale_date >= self.fecha_desde)
        if self.fecha_hasta:
            stmt = stmt.where(SaleCapture.sale_date <= self.fecha_hasta)
        if self.semana:
            stmt = stmt.where(SaleCapture.semana == self.semana)
        if self.qna:
            stmt = stmt.where(SaleCapture.qna == self.qna)
        if self.vendedor:
            stmt = stmt.where(SaleCapture.vendedor == self.vendedor)
        if self.seccion:
            stmt = stmt.where(SaleCapture.seccion == self.seccion)
        if self.tipo_venta:
            stmt = stmt.where(SaleCapture.tipo_venta == self.tipo_venta)
        return stmt

    def apply_sale(self, stmt: Select) -> Select:
        return self._apply_sale(stmt)

    def apply_case(self, stmt: Select) -> Select:
        if self.workflow_state:
            stmt = stmt.where(Case.current_status == self.workflow_state)
        if self.vendedor:
            stmt = stmt.where(Case.seller_name == self.vendedor)
        if self.semana:
            stmt = stmt.where(Case.week_code == self.semana)
        if self.fecha_desde:
            stmt = stmt.where(Case.created_at >= _date_start_utc(self.fecha_desde))
        if self.fecha_hasta:
            stmt = stmt.where(Case.created_at <= _date_end_utc(self.fecha_hasta))
        return stmt


def _date_start_utc(d: date) -> Any:
    from datetime import datetime, timezone

    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _date_end_utc(d: date) -> Any:
    from datetime import datetime, timezone

    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def sale_amount_column():
    """Expresión SQL de monto de venta (total_venta o venta)."""
    from sqlalchemy import func

    return func.coalesce(SaleCapture.total_venta, SaleCapture.venta, 0)
