"""P57 — data warehouse / snapshots diarios (OLTP separado analítico)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.enterprise_advanced import DailyMetricsSnapshot
from app.models.sale_capture import SaleCapture
from app.services.analytics_service import AnalyticsService


class WarehouseService:
    def capture_daily(self, db: Session, *, domain: str, company_id: int = 1) -> DailyMetricsSnapshot:
        today = date.today()
        metrics = self._collect_domain_metrics(db, domain, company_id=company_id)
        existing = db.scalar(
            select(DailyMetricsSnapshot).where(
                DailyMetricsSnapshot.snapshot_date == today,
                DailyMetricsSnapshot.domain == domain,
                DailyMetricsSnapshot.company_id == company_id,
            )
        )
        if existing:
            existing.metrics_json = metrics
            db.flush()
            return existing
        snap = DailyMetricsSnapshot(
            snapshot_date=today,
            domain=domain,
            metrics_json=metrics,
            company_id=company_id,
        )
        db.add(snap)
        db.flush()
        return snap

    def capture_all_domains(self, db: Session, *, company_id: int = 1) -> list[str]:
        domains = ("bi", "erp", "ops", "workflow")
        for d in domains:
            self.capture_daily(db, domain=d, company_id=company_id)
        AnalyticsService().capture_snapshot(
            db, period_label=datetime.now(timezone.utc).strftime("%Y-%m"),
            company_id=company_id,
        )
        return list(domains)

    def _collect_domain_metrics(self, db: Session, domain: str, *, company_id: int) -> dict[str, Any]:
        if domain == "bi":
            return AnalyticsService().build_advanced_dashboard(db, company_id=company_id)
        if domain == "workflow":
            open_cases = db.scalar(
                select(func.count(Case.id)).where(Case.company_id == company_id)
            ) or 0
            return {"open_cases": open_cases}
        if domain == "erp":
            sales = db.scalar(select(func.count(SaleCapture.id))) or 0
            return {"registered_sales": sales}
        return {"captured_at": datetime.now(timezone.utc).isoformat(), "domain": domain}

    def list_snapshots(
        self, db: Session, *, domain: str | None = None, limit: int = 30
    ) -> list[dict[str, Any]]:
        stmt = select(DailyMetricsSnapshot).order_by(DailyMetricsSnapshot.snapshot_date.desc())
        if domain:
            stmt = stmt.where(DailyMetricsSnapshot.domain == domain)
        stmt = stmt.limit(limit)
        return [
            {
                "id": s.id,
                "date": s.snapshot_date.isoformat(),
                "domain": s.domain,
                "keys": list((s.metrics_json or {}).keys())[:8],
            }
            for s in db.scalars(stmt).all()
        ]
