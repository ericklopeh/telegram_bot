"""Dashboard ejecutivo BI (P29) — agrega KPIs reutilizando ERP P27."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session, joinedload

from app.domain import constants as C
from app.models.case import Case
from app.models.commission import Commission, PAYMENT_STATUS_PENDING
from app.models.contract import CONTRACT_ACTIVE, Contract
from app.models.document import Document
from app.models.sale_capture import REG_STATUS_REGISTERED, REG_STATUS_REGISTRATION_FAILED, SaleCapture
from app.services.bi_filters import BiFilters, sale_amount_column
from app.services.contract_financial_service import ContractFinancialService
from app.services.erp_reconciliation_service import ErpReconciliationService

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SEC = 45

_CERRADOS = (
    C.ST_PED_CERRADO,
    C.ST_PED_RECHAZADO,
    C.ST_PED_COMPRA,
    C.ST_REV_CERRADO,
    C.ST_REV_RECHAZADO,
    C.ST_REV_SIN_LIQUIDEZ,
)


@dataclass
class BiKpiCard:
    key: str
    label: str
    value: str
    hint: str
    drill_url: str


@dataclass
class BiRankingRow:
    label: str
    metric: float
    detail: str
    drill_url: str


@dataclass
class BiOperationalAlert:
    code: str
    severity: str
    title: str
    message: str
    count: int
    drill_url: str


@dataclass
class BiDashboardPayload:
    filters: BiFilters
    kpis: list[BiKpiCard]
    charts: dict[str, dict[str, list]]
    rankings: dict[str, list[BiRankingRow]]
    alerts: list[BiOperationalAlert]
    filter_options: dict[str, list[str]]
    erp_summary: dict[str, Any] = field(default_factory=dict)


class BiDashboardService:
    def __init__(self) -> None:
        self._financial = ContractFinancialService()
        self._reconciliation = ErpReconciliationService()

    def build_dashboard(self, db: Session, filters: BiFilters) -> BiDashboardPayload:
        key = f"bi:{filters.cache_key()}"
        cached = _CACHE.get(key)
        now = time.time()
        if cached and now - cached[0] < _CACHE_TTL_SEC:
            return cached[1]

        payload = self._build_dashboard_uncached(db, filters)
        _CACHE[key] = (now, payload)
        return payload

    def _build_dashboard_uncached(self, db: Session, filters: BiFilters) -> BiDashboardPayload:
        erp_kpis = self._financial.build_dashboard_kpis(db)
        amt = sale_amount_column()

        ventas_totales = self._sum_sales(db, filters)

        semana_ref = filters.semana or self._detect_current_semana(db)
        qna_ref = filters.qna or self._detect_current_qna(db)

        ventas_semana = self._sum_sales(
            db, filters, extra=lambda s: s.where(SaleCapture.semana == semana_ref) if semana_ref else s
        )
        ventas_qna = self._sum_sales(
            db, filters, extra=lambda s: s.where(SaleCapture.qna == qna_ref) if qna_ref else s
        )

        comm_q = select(func.coalesce(func.sum(Commission.commission_amount), 0))
        if filters.vendedor:
            comm_q = comm_q.where(Commission.seller_name == filters.vendedor)
        if filters.qna:
            comm_q = comm_q.where(Commission.qna == filters.qna)
        if filters.semana:
            comm_q = comm_q.where(Commission.week == filters.semana)
        comisiones_total = db.scalar(comm_q) or Decimal("0")

        docs_pending = self._count_documents(db, filters, pending=True)
        sp_failed = self._count_documents(db, filters, upload_failed=True)
        casos_atorados = self._count_stale_cases(db, filters)

        kpis = [
            BiKpiCard(
                "ventas_totales",
                "Ventas totales",
                f"${float(ventas_totales):,.2f}",
                "Ventas registradas (filtro aplicado)",
                self._drill_ventas(filters),
            ),
            BiKpiCard(
                "ventas_semana",
                "Ventas semana",
                f"${float(ventas_semana):,.2f}",
                semana_ref or "Sin semana detectada",
                self._drill_ventas(filters, semana=semana_ref),
            ),
            BiKpiCard(
                "ventas_qna",
                "Ventas QNA",
                f"${float(ventas_qna):,.2f}",
                qna_ref or "Sin QNA detectada",
                self._drill_ventas(filters, qna=qna_ref),
            ),
            BiKpiCard(
                "saldo_pendiente",
                "Saldo pendiente",
                f"${float(erp_kpis.total_balance):,.2f}",
                "Contratos activos (ERP P27)",
                "/erp/dashboard",
            ),
            BiKpiCard(
                "recovery",
                "Recovery",
                f"{erp_kpis.total_recovery_pct}%",
                "Recuperación global ERP",
                "/erp/dashboard",
            ),
            BiKpiCard(
                "refin",
                "Refinanciado",
                f"${float(erp_kpis.total_refinanced):,.2f}",
                "Total refinanciado",
                "/erp/conciliacion",
            ),
            BiKpiCard(
                "comisiones",
                "Comisiones",
                f"${float(comisiones_total):,.2f}",
                "Monto comisiones (filtros comisión)",
                self._drill_comisiones(filters),
            ),
            BiKpiCard(
                "docs_pending",
                "Docs pendientes",
                str(docs_pending),
                "Revisión o subida pendiente",
                "/casos",
            ),
            BiKpiCard(
                "sp_failed",
                "SharePoint fallidos",
                str(sp_failed),
                "Uploads con error",
                "/admin/sharepoint",
            ),
            BiKpiCard(
                "workflow_stale",
                "Casos atorados",
                str(casos_atorados),
                "Sin movimiento >24h",
                "/dashboard?filter=stale_24h",
            ),
        ]

        charts = {
            "ventas_vendedor": self._chart_group_sales(db, filters, SaleCapture.vendedor),
            "ventas_semana": self._chart_group_sales(db, filters, SaleCapture.semana),
            "ventas_seccion": self._chart_group_sales(db, filters, SaleCapture.seccion),
            "ventas_tipo": self._chart_group_sales(db, filters, SaleCapture.tipo_venta),
            "workflow_estado": self._chart_workflow(db, filters),
            "sharepoint": self._chart_sharepoint(db, filters),
            "recovery_vendedor": self._chart_recovery_vendedor(db, filters),
        }

        rankings = {
            "top_vendedores": self._ranking_top_vendedores(db, filters),
            "top_recovery": self._ranking_top_recovery(db, filters),
            "mas_pendientes": self._ranking_mas_pendientes(db, filters),
            "mas_refinanciado": self._ranking_mas_refin(db, filters),
            "mas_ventas": self._ranking_mas_ventas(db, filters),
        }

        alerts = self.build_operational_alerts(db, filters)
        options = self._filter_options(db)

        return BiDashboardPayload(
            filters=filters,
            kpis=kpis,
            charts=charts,
            rankings=rankings,
            alerts=alerts,
            filter_options=options,
            erp_summary={
                "active_contracts": erp_kpis.active_contracts,
                "overdue_amount": float(erp_kpis.overdue_amount),
            },
        )

    def build_operational_alerts(self, db: Session, filters: BiFilters) -> list[BiOperationalAlert]:
        alerts: list[BiOperationalAlert] = []

        sin_comision = db.scalar(
            select(func.count(SaleCapture.id))
            .outerjoin(Commission, Commission.sale_capture_id == SaleCapture.id)
            .where(
                SaleCapture.registration_status == REG_STATUS_REGISTERED,
                Commission.id.is_(None),
            )
        ) or 0
        if sin_comision:
            alerts.append(
                BiOperationalAlert(
                    "SALE_WITHOUT_COMMISSION",
                    "warning",
                    "Ventas sin comisión",
                    "Ventas registradas sin registro de comisión",
                    int(sin_comision),
                    self._drill_comisiones(filters),
                )
            )

        docs_missing = self._count_documents(db, filters, pending=True)
        if docs_missing:
            alerts.append(
                BiOperationalAlert(
                    "DOCS_PENDING",
                    "warning",
                    "Documentos pendientes",
                    "Documentos en revisión o subida pendiente",
                    docs_missing,
                    "/casos",
                )
            )

        sp_failed = self._count_documents(db, filters, upload_failed=True)
        if sp_failed:
            alerts.append(
                BiOperationalAlert(
                    "SHAREPOINT_FAILED",
                    "error",
                    "SharePoint fallidos",
                    "Documentos con upload_status UPLOAD_FAILED",
                    sp_failed,
                    "/admin/sharepoint",
                )
            )

        stale = self._count_stale_cases(db, filters)
        if stale:
            alerts.append(
                BiOperationalAlert(
                    "WORKFLOW_STALE",
                    "warning",
                    "Workflow atorado >24h",
                    "Casos abiertos sin actualización reciente",
                    stale,
                    "/dashboard?filter=stale_24h",
                )
            )

        compulsa = db.scalar(
            select(func.count(Case.id)).where(Case.current_status == C.ST_PED_PEND_COMPULSA)
        ) or 0
        if compulsa:
            alerts.append(
                BiOperationalAlert(
                    "COMPULSA_PENDING",
                    "info",
                    "Pendientes compulsa",
                    "Pedidos en espera de compulsa",
                    int(compulsa),
                    "/dashboard?filter=compulsa",
                )
            )

        excel_failed = db.scalar(
            select(func.count(SaleCapture.id)).where(
                SaleCapture.registration_status == REG_STATUS_REGISTRATION_FAILED
            )
        ) or 0
        if excel_failed:
            alerts.append(
                BiOperationalAlert(
                    "EXCEL_EXPORT_FAILED",
                    "error",
                    "Export Excel fallido",
                    "Capturas con registro Excel fallido",
                    int(excel_failed),
                    "/ventas/pendientes",
                )
            )

        report = self._reconciliation.build_report(db)
        for issue in report.issues:
            if issue.code == "NEGATIVE_BALANCE":
                alerts.append(
                    BiOperationalAlert(
                        issue.code,
                        issue.severity,
                        "Saldo negativo",
                        issue.message,
                        1,
                        "/erp/conciliacion",
                    )
                )
            elif issue.code == "DUPLICATE_REFI":
                alerts.append(
                    BiOperationalAlert(
                        issue.code,
                        issue.severity,
                        "Refin inconsistente",
                        issue.message,
                        1,
                        "/erp/conciliacion",
                    )
                )

        return alerts

    def _sum_sales(self, db: Session, filters: BiFilters, extra=None) -> Decimal:
        amt = sale_amount_column()
        stmt = select(func.coalesce(func.sum(amt), 0)).where(
            SaleCapture.registration_status == REG_STATUS_REGISTERED
        )
        stmt = filters.apply_sale(stmt)
        if extra:
            stmt = extra(stmt)
        return Decimal(str(db.scalar(stmt) or 0))

    def _chart_group_sales(
        self, db: Session, filters: BiFilters, column: Any, *, limit: int = 12
    ) -> dict[str, list]:
        amt = sale_amount_column()
        col = column
        stmt = (
            select(col, func.coalesce(func.sum(amt), 0))
            .where(
                SaleCapture.registration_status == REG_STATUS_REGISTERED,
                col.isnot(None),
                col != "",
            )
            .group_by(col)
            .order_by(func.sum(amt).desc())
            .limit(limit)
        )
        stmt = filters.apply_sale(stmt)
        rows = db.execute(stmt).all()
        labels = [str(r[0] or "—") for r in rows]
        values = [float(r[1] or 0) for r in rows]
        return {"labels": labels, "values": values}

    def _chart_workflow(self, db: Session, filters: BiFilters) -> dict[str, list]:
        stmt = select(Case.current_status, func.count(Case.id)).group_by(Case.current_status)
        stmt = filters.apply_case(stmt)
        rows = db.execute(stmt.order_by(func.count(Case.id).desc()).limit(15)).all()
        return {
            "labels": [str(r[0]) for r in rows],
            "values": [int(r[1]) for r in rows],
        }

    def _chart_sharepoint(self, db: Session, filters: BiFilters) -> dict[str, list]:
        stmt = (
            select(Document.upload_status, func.count(Document.id))
            .where(Document.is_active.is_(True))
            .group_by(Document.upload_status)
        )
        if filters.vendedor or filters.workflow_state:
            stmt = stmt.join(Case, Document.case_id == Case.id)
            stmt = filters.apply_case(stmt)
        rows = db.execute(stmt).all()
        ok = 0
        failed = 0
        other = 0
        for status, cnt in rows:
            n = int(cnt)
            s = (status or "").upper()
            if s in ("SHAREPOINT_OK", "UPLOADED"):
                ok += n
            elif s == "UPLOAD_FAILED":
                failed += n
            else:
                other += n
        return {"labels": ["OK", "Fallidos", "Otros"], "values": [ok, failed, other]}

    def _chart_recovery_vendedor(self, db: Session, filters: BiFilters) -> dict[str, list]:
        """Recovery % por vendedor vía contratos ERP (una pasada, sin N+1 por venta)."""
        contracts = list(
            db.scalars(
                select(Contract)
                .options(joinedload(Contract.erp_sale))
                .where(Contract.status == CONTRACT_ACTIVE)
            )
            .unique()
            .all()
        )
        by_vendor: dict[str, tuple[Decimal, Decimal]] = {}
        for c in contracts:
            v = (c.erp_sale.vendedor if c.erp_sale else None) or "Sin vendedor"
            if filters.vendedor and v != filters.vendedor:
                continue
            snap = self._financial.compute_snapshot(db, c)
            sale_sum, paid_sum = by_vendor.get(v, (Decimal("0"), Decimal("0")))
            by_vendor[v] = (sale_sum + snap.total_sale, paid_sum + snap.total_paid)

        rows: list[tuple[str, float]] = []
        for v, (sale, paid) in by_vendor.items():
            pct = float((paid / sale * 100) if sale > 0 else 0)
            rows.append((v, round(pct, 2)))
        rows.sort(key=lambda x: x[1], reverse=True)
        rows = rows[:12]
        return {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

    def _ranking_top_vendedores(self, db: Session, filters: BiFilters) -> list[BiRankingRow]:
        chart = self._chart_group_sales(db, filters, SaleCapture.vendedor, limit=8)
        return [
            BiRankingRow(
                label=chart["labels"][i],
                metric=chart["values"][i],
                detail="Monto ventas",
                drill_url=self._drill_ventas(filters, vendedor=chart["labels"][i]),
            )
            for i in range(len(chart["labels"]))
        ]

    def _ranking_mas_ventas(self, db: Session, filters: BiFilters) -> list[BiRankingRow]:
        return self._ranking_top_vendedores(db, filters)

    def _ranking_top_recovery(self, db: Session, filters: BiFilters) -> list[BiRankingRow]:
        chart = self._chart_recovery_vendedor(db, filters)
        return [
            BiRankingRow(
                label=chart["labels"][i],
                metric=chart["values"][i],
                detail="Recovery %",
                drill_url=self._drill_comisiones(filters, vendedor=chart["labels"][i]),
            )
            for i in range(len(chart["labels"]))
        ]

    def _ranking_mas_pendientes(self, db: Session, filters: BiFilters) -> list[BiRankingRow]:
        contracts = list(
            db.scalars(
                select(Contract)
                .options(joinedload(Contract.erp_sale))
                .where(Contract.status == CONTRACT_ACTIVE)
            )
            .unique()
            .all()
        )
        rows: list[tuple[str, float]] = []
        for c in contracts:
            snap = self._financial.compute_snapshot(db, c)
            if snap.saldo_final <= 0:
                continue
            v = (c.erp_sale.vendedor if c.erp_sale else None) or "Sin vendedor"
            rows.append((v, float(snap.saldo_final)))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [
            BiRankingRow(
                label=r[0],
                metric=r[1],
                detail="Saldo pendiente",
                drill_url="/erp/dashboard",
            )
            for r in rows[:8]
        ]

    def _ranking_mas_refin(self, db: Session, filters: BiFilters) -> list[BiRankingRow]:
        from app.models.contract import RefinanceOperation

        stmt = (
            select(Contract, func.coalesce(func.sum(RefinanceOperation.refinanced_amount), 0))
            .outerjoin(RefinanceOperation, RefinanceOperation.contract_id == Contract.id)
            .options(joinedload(Contract.erp_sale))
            .group_by(Contract.id)
            .order_by(func.sum(RefinanceOperation.refinanced_amount).desc())
            .limit(8)
        )
        rows = db.execute(stmt).all()
        result: list[BiRankingRow] = []
        for c, total in rows:
            if not total or float(total) <= 0:
                continue
            label = f"Contrato {c.id}"
            if c.erp_sale and c.erp_sale.vendedor:
                label = c.erp_sale.vendedor
            result.append(
                BiRankingRow(
                    label=label,
                    metric=float(total),
                    detail="Refinanciado",
                    drill_url=f"/clientes/{c.customer_id}",
                )
            )
        return result

    def _count_documents(
        self,
        db: Session,
        filters: BiFilters,
        *,
        pending: bool = False,
        upload_failed: bool = False,
    ) -> int:
        stmt = select(func.count(Document.id)).where(Document.is_active.is_(True))
        if pending:
            stmt = stmt.where(
                Document.review_status == "PENDING_REVIEW",
                Document.upload_status.in_(("PENDING_UPLOAD", "UPLOADING", "LOCAL")),
            )
        if upload_failed:
            stmt = stmt.where(Document.upload_status == "UPLOAD_FAILED")
        if filters.vendedor or filters.workflow_state:
            stmt = stmt.join(Case, Document.case_id == Case.id)
            stmt = filters.apply_case(stmt)
        return int(db.scalar(stmt) or 0)

    def _count_stale_cases(self, db: Session, filters: BiFilters) -> int:
        umbral = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = select(func.count(Case.id)).where(
            not_(Case.current_status.in_(_CERRADOS)),
            Case.updated_at < umbral,
        )
        stmt = filters.apply_case(stmt)
        return int(db.scalar(stmt) or 0)

    def _filter_options(self, db: Session) -> dict[str, list[str]]:
        def _distinct(col, model=SaleCapture, limit=40):
            rows = db.scalars(
                select(col)
                .where(col.isnot(None), col != "")
                .distinct()
                .order_by(col)
                .limit(limit)
            ).all()
            return [str(r) for r in rows]

        workflow = db.scalars(
            select(Case.current_status).distinct().order_by(Case.current_status).limit(50)
        ).all()
        semanas = list(
            dict.fromkeys(_distinct(SaleCapture.semana) + _distinct(Case.week_code, Case))
        )
        return {
            "vendedores": _distinct(SaleCapture.vendedor),
            "secciones": _distinct(SaleCapture.seccion),
            "semanas": semanas,
            "qnas": _distinct(SaleCapture.qna),
            "tipos_venta": _distinct(SaleCapture.tipo_venta),
            "workflow_states": [str(w) for w in workflow],
        }

    def _detect_current_semana(self, db: Session) -> str | None:
        row = db.scalar(
            select(SaleCapture.semana)
            .where(SaleCapture.semana.isnot(None), SaleCapture.semana != "")
            .order_by(SaleCapture.sale_date.desc())
            .limit(1)
        )
        if row:
            return str(row)
        iso = date.today().isocalendar()
        return f"SEM_{iso.week:02d}"

    def _detect_current_qna(self, db: Session) -> str | None:
        return db.scalar(
            select(SaleCapture.qna)
            .where(SaleCapture.qna.isnot(None), SaleCapture.qna != "")
            .order_by(SaleCapture.sale_date.desc())
            .limit(1)
        )

    def _drill_ventas(
        self,
        filters: BiFilters,
        *,
        vendedor: str | None = None,
        semana: str | None = None,
        qna: str | None = None,
    ) -> str:
        q = filters.to_query_dict()
        if vendedor:
            q["vendedor"] = vendedor
        if semana:
            q["semana"] = semana
        if qna:
            q["qna"] = qna
        if not q:
            return "/ventas"
        from urllib.parse import urlencode

        return f"/ventas?{urlencode(q)}"

    def _drill_comisiones(self, filters: BiFilters, vendedor: str | None = None) -> str:
        q: dict[str, str] = {}
        if filters.vendedor or vendedor:
            q["vendedor"] = vendedor or filters.vendedor or ""
        if filters.qna:
            q["qna"] = filters.qna
        if filters.semana:
            q["semana"] = filters.semana
        if not q:
            return "/comisiones"
        from urllib.parse import urlencode

        return f"/comisiones?{urlencode(q)}"

    def clear_cache(self) -> None:
        _CACHE.clear()
