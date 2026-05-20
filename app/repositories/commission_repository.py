"""Acceso a datos de comisiones (P21)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.commission import (
    PAYMENT_STATUS_CANCELLED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    Commission,
)
from app.models.sale_capture import SaleCapture


class CommissionRepository:
    @staticmethod
    def get_by_id(db: Session, commission_id: int) -> Commission | None:
        return db.scalar(
            select(Commission)
            .options(joinedload(Commission.sale_capture))
            .where(Commission.id == commission_id)
        )

    @staticmethod
    def get_by_sale_capture_id(db: Session, sale_capture_id: int) -> Commission | None:
        return db.scalar(
            select(Commission).where(Commission.sale_capture_id == sale_capture_id)
        )

    @staticmethod
    def create(db: Session, commission: Commission) -> Commission:
        db.add(commission)
        db.flush()
        return commission

    @staticmethod
    def save(db: Session, commission: Commission) -> None:
        db.add(commission)

    @staticmethod
    def list_commissions(
        db: Session,
        *,
        seller_name: str | None = None,
        qna: str | None = None,
        week: str | None = None,
        payment_status: str | None = None,
        limit: int = 500,
    ) -> list[Commission]:
        stmt = (
            select(Commission)
            .options(joinedload(Commission.sale_capture))
            .order_by(Commission.created_at.desc())
        )
        if seller_name and seller_name.strip():
            stmt = stmt.where(Commission.seller_name == seller_name.strip())
        if qna and qna.strip():
            stmt = stmt.where(Commission.qna.ilike(f"%{qna.strip()}%"))
        if week and week.strip():
            stmt = stmt.where(Commission.week == week.strip())
        if payment_status and payment_status.strip():
            stmt = stmt.where(Commission.payment_status == payment_status.strip())
        stmt = stmt.limit(limit)
        return list(db.scalars(stmt).unique().all())

    @staticmethod
    def list_sellers(db: Session, limit: int = 80) -> list[str]:
        rows = db.execute(
            select(Commission.seller_name)
            .distinct()
            .order_by(Commission.seller_name)
            .limit(limit)
        ).all()
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def list_weeks(db: Session, limit: int = 40) -> list[str]:
        rows = db.execute(
            select(Commission.week)
            .where(Commission.week.isnot(None), Commission.week != "")
            .distinct()
            .order_by(Commission.week.desc())
            .limit(limit)
        ).all()
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def summary_by_status(db: Session) -> dict[str, dict[str, Decimal | int]]:
        rows = db.execute(
            select(
                Commission.payment_status,
                func.count(Commission.id),
                func.coalesce(func.sum(Commission.commission_amount), 0),
            ).group_by(Commission.payment_status)
        ).all()
        out: dict[str, dict[str, Decimal | int]] = {}
        for status, count, total in rows:
            out[status] = {
                "count": int(count or 0),
                "total": Decimal(str(total or 0)),
            }
        return out

    @staticmethod
    def aggregate_by_seller(db: Session, limit: int = 15) -> list[tuple[str, Decimal]]:
        rows = db.execute(
            select(
                Commission.seller_name,
                func.coalesce(func.sum(Commission.commission_amount), 0),
            )
            .where(Commission.payment_status != PAYMENT_STATUS_CANCELLED)
            .group_by(Commission.seller_name)
            .order_by(func.sum(Commission.commission_amount).desc())
            .limit(limit)
        ).all()
        return [(r[0], Decimal(str(r[1] or 0))) for r in rows]

    @staticmethod
    def aggregate_by_week(db: Session, limit: int = 20) -> list[tuple[str, Decimal]]:
        rows = db.execute(
            select(
                Commission.week,
                func.coalesce(func.sum(Commission.commission_amount), 0),
            )
            .where(
                Commission.week.isnot(None),
                Commission.week != "",
                Commission.payment_status != PAYMENT_STATUS_CANCELLED,
            )
            .group_by(Commission.week)
            .order_by(Commission.week)
            .limit(limit)
        ).all()
        return [(r[0] or "—", Decimal(str(r[1] or 0))) for r in rows]

    @staticmethod
    def aggregate_by_qna(db: Session, limit: int = 20) -> list[tuple[str, Decimal]]:
        rows = db.execute(
            select(
                Commission.qna,
                func.coalesce(func.sum(Commission.commission_amount), 0),
            )
            .where(
                Commission.qna.isnot(None),
                Commission.qna != "",
                Commission.payment_status != PAYMENT_STATUS_CANCELLED,
            )
            .group_by(Commission.qna)
            .order_by(func.sum(Commission.commission_amount).desc())
            .limit(limit)
        ).all()
        return [(r[0] or "—", Decimal(str(r[1] or 0))) for r in rows]

    @staticmethod
    def supervisor_metrics(db: Session) -> dict[str, object]:
        summary = CommissionRepository.summary_by_status(db)
        pending = summary.get(PAYMENT_STATUS_PENDING, {"count": 0, "total": Decimal("0")})
        paid = summary.get(PAYMENT_STATUS_PAID, {"count": 0, "total": Decimal("0")})
        cancelled = summary.get(
            PAYMENT_STATUS_CANCELLED, {"count": 0, "total": Decimal("0")}
        )
        total_count = sum(int(v.get("count", 0)) for v in summary.values())
        total_amount = sum(
            Decimal(str(v.get("total", 0))) for v in summary.values()
        )
        avg = (
            total_amount / total_count if total_count else Decimal("0")
        )
        top = CommissionRepository.aggregate_by_seller(db, limit=10)
        return {
            "total_count": total_count,
            "total_amount": total_amount,
            "pending_count": int(pending.get("count", 0)),
            "pending_amount": Decimal(str(pending.get("total", 0))),
            "paid_count": int(paid.get("count", 0)),
            "paid_amount": Decimal(str(paid.get("total", 0))),
            "cancelled_count": int(cancelled.get("count", 0)),
            "average_commission": avg.quantize(Decimal("0.01")),
            "top_sellers": top,
        }
