"""P39 — dashboards por rol (vendedor / supervisor)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.case import Case
from app.models.commission import Commission
from app.models.sale_capture import SaleCapture
from app.services.performance_service import PerformanceService, paginate


class RoleDashboardService:
    def build_vendor_dashboard(
        self,
        db: Session,
        *,
        seller_name: str | None,
        seller_chat_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        perf = PerformanceService()
        cache_key = f"vendor_dash:{seller_name}:{user_id}"
        return perf.cached(
            cache_key,
            lambda: self._vendor_payload(db, seller_name=seller_name, seller_chat_id=seller_chat_id),
            ttl=45,
        )

    def _vendor_payload(
        self,
        db: Session,
        *,
        seller_name: str | None,
        seller_chat_id: int | None,
    ) -> dict[str, Any]:
        cases_stmt = select(Case).order_by(Case.updated_at.desc())
        if seller_chat_id:
            cases_stmt = cases_stmt.where(Case.seller_telegram_chat_id == seller_chat_id)
        elif seller_name:
            cases_stmt = cases_stmt.where(Case.seller_name.ilike(seller_name))
        cases = list(db.scalars(cases_stmt.limit(50)).all())

        open_cases = [c for c in cases if c.current_status not in (C.ST_PED_CERRADO,)]
        pending = [c for c in cases if "PEND" in (c.current_status or "").upper()]

        sales_stmt = select(SaleCapture).order_by(SaleCapture.id.desc())
        if seller_name:
            sales_stmt = sales_stmt.where(SaleCapture.vendedor.ilike(f"%{seller_name}%"))
        sales = list(db.scalars(sales_stmt.limit(20)).all())

        comm_stmt = select(Commission)
        if seller_name:
            comm_stmt = comm_stmt.where(Commission.seller_name.ilike(f"%{seller_name}%"))
        commissions = list(db.scalars(comm_stmt.limit(15)).all())

        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        sla_risk = [c for c in open_cases if c.updated_at and c.updated_at < stale_cutoff]

        return {
            "role": "vendedor",
            "kpis": {
                "mis_casos": len(open_cases),
                "pendientes": len(pending),
                "ventas_recientes": len(sales),
                "comisiones": len(commissions),
                "sla_riesgo": len(sla_risk),
            },
            "cases": [
                {
                    "public_id": c.public_id,
                    "client_name": c.client_name,
                    "status": c.current_status,
                    "href": f"/casos/{c.id}",
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in open_cases[:12]
            ],
            "sales": [
                {
                    "folio": s.folio,
                    "cliente": s.cliente,
                    "status": s.registration_status,
                    "href": f"/ventas/{s.id}",
                }
                for s in sales[:8]
            ],
            "commissions": [
                {
                    "id": cm.id,
                    "amount": str(cm.commission_amount),
                    "status": cm.payment_status,
                }
                for cm in commissions[:8]
            ],
            "sla_alerts": [
                {"public_id": c.public_id, "href": f"/casos/{c.id}"} for c in sla_risk[:6]
            ],
        }

    def build_supervisor_dashboard(self, db: Session) -> dict[str, Any]:
        perf = PerformanceService()
        return perf.cached(
            "supervisor_dash",
            lambda: self._supervisor_payload(db),
            ttl=60,
        )

    def _supervisor_payload(self, db: Session) -> dict[str, Any]:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        by_seller = db.execute(
            select(Case.seller_name, func.count(Case.id))
            .where(Case.seller_name.isnot(None))
            .group_by(Case.seller_name)
            .order_by(func.count(Case.id).desc())
            .limit(12)
        ).all()

        stuck = list(
            db.scalars(
                select(Case)
                .where(Case.updated_at < stale_cutoff)
                .order_by(Case.updated_at.asc())
                .limit(15)
            ).all()
        )

        critical_sellers = []
        for name, count in by_seller:
            risk = db.scalar(
                select(func.count(Case.id)).where(
                    Case.seller_name == name,
                    Case.updated_at < stale_cutoff,
                )
            )
            if risk and risk > 0:
                critical_sellers.append({"seller": name, "open": count, "stale": risk})

        return {
            "role": "supervisor",
            "team_size": len(by_seller),
            "kpis": {
                "casos_atorados": len(stuck),
                "vendedores_criticos": len(critical_sellers),
                "casos_equipo": sum(c for _, c in by_seller),
            },
            "seller_ranking": [
                {"seller": name, "cases": count} for name, count in by_seller
            ],
            "stuck_cases": [
                {
                    "public_id": c.public_id,
                    "seller": c.seller_name,
                    "status": c.current_status,
                    "href": f"/casos/{c.id}",
                }
                for c in stuck
            ],
            "critical_sellers": critical_sellers[:8],
            "productivity_note": "Comparativa semanal disponible en Analytics avanzados.",
        }
