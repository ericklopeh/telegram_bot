"""Acceso a datos de capturas de venta."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.sale_capture import (
    REG_STATUS_PENDING_REGISTRATION,
    REG_STATUS_PROCESSING_REGISTRATION,
    REG_STATUS_REGISTRATION_FAILED,
    SALE_STATUS_DRAFT,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_REGISTERED,
    SaleCapture,
)


class SaleCaptureRepository:
    @staticmethod
    def get_by_id(db: Session, sale_id: int) -> SaleCapture | None:
        return db.get(SaleCapture, sale_id)

    @staticmethod
    def get_by_folio(db: Session, folio: str) -> SaleCapture | None:
        return db.scalar(select(SaleCapture).where(SaleCapture.folio == str(folio).strip()))

    @staticmethod
    def folio_taken(db: Session, folio: str, exclude_id: int | None = None) -> bool:
        stmt = select(SaleCapture.id).where(SaleCapture.folio == str(folio).strip())
        if exclude_id:
            stmt = stmt.where(SaleCapture.id != exclude_id)
        if db.scalar(stmt):
            return True
        case = db.scalar(
            select(Case.id).where(Case.official_folio == str(folio).strip()).limit(1)
        )
        return case is not None

    @staticmethod
    def next_suggested_folio(db: Session) -> str:
        max_sale = db.scalar(select(func.max(SaleCapture.folio)))
        best = 0
        if max_sale and str(max_sale).isdigit():
            best = int(max_sale)
        rows = db.scalars(
            select(Case.official_folio)
            .where(Case.official_folio.isnot(None))
            .order_by(Case.id.desc())
            .limit(100)
        ).all()
        for r in rows:
            if r and str(r).isdigit():
                best = max(best, int(r))
        return f"{best + 1:05d}"

    @staticmethod
    def create(db: Session, sale: SaleCapture) -> SaleCapture:
        db.add(sale)
        db.flush()
        return sale

    @staticmethod
    def save(db: Session, sale: SaleCapture) -> None:
        db.add(sale)

    @staticmethod
    def list_recent(
        db: Session,
        *,
        vendedor: str | None = None,
        status: str | None = None,
        q: str | None = None,
        folio: str | None = None,
        cliente: str | None = None,
        rfc: str | None = None,
        registered: str | None = None,
        limit: int = 100,
    ) -> list[SaleCapture]:
        stmt = select(SaleCapture).order_by(SaleCapture.updated_at.desc())
        if vendedor and vendedor.strip():
            stmt = stmt.where(SaleCapture.vendedor == vendedor.strip())
        if status and status.strip():
            stmt = stmt.where(SaleCapture.status == status.strip())
        if folio and folio.strip():
            stmt = stmt.where(SaleCapture.folio.ilike(f"%{folio.strip()}%"))
        if cliente and cliente.strip():
            stmt = stmt.where(SaleCapture.cliente.ilike(f"%{cliente.strip()}%"))
        if rfc and rfc.strip():
            stmt = stmt.where(SaleCapture.rfc.ilike(f"%{rfc.strip()}%"))
        if registered == "yes":
            stmt = stmt.where(SaleCapture.status == SALE_STATUS_REGISTERED)
        elif registered == "no":
            stmt = stmt.where(SaleCapture.status != SALE_STATUS_REGISTERED)
        if q and q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    SaleCapture.cliente.ilike(needle),
                    SaleCapture.folio.ilike(needle),
                    SaleCapture.rfc.ilike(needle),
                )
            )
        stmt = stmt.limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_vendedores(db: Session, limit: int = 50) -> list[str]:
        rows = db.execute(
            select(SaleCapture.vendedor)
            .where(SaleCapture.vendedor.isnot(None), SaleCapture.vendedor != "")
            .distinct()
            .order_by(SaleCapture.vendedor)
            .limit(limit)
        ).all()
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def list_pending_registration(
        db: Session,
        *,
        registration_status: str | None = None,
        vendedor: str | None = None,
        q: str | None = None,
        desde: str | None = None,
        hasta: str | None = None,
        limit: int = 200,
    ) -> list[SaleCapture]:
        pending_statuses = (
            REG_STATUS_PENDING_REGISTRATION,
            REG_STATUS_PROCESSING_REGISTRATION,
            REG_STATUS_REGISTRATION_FAILED,
            SALE_STATUS_EXPORT_FAILED,
        )
        stmt = select(SaleCapture).where(
            SaleCapture.registration_status.in_(pending_statuses)
            | (SaleCapture.status == SALE_STATUS_EXPORT_FAILED)
        )
        if registration_status and registration_status.strip():
            stmt = select(SaleCapture).where(
                SaleCapture.registration_status == registration_status.strip()
            )
        if vendedor and vendedor.strip():
            stmt = stmt.where(SaleCapture.vendedor == vendedor.strip())
        if q and q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    SaleCapture.cliente.ilike(needle),
                    SaleCapture.folio.ilike(needle),
                    SaleCapture.rfc.ilike(needle),
                )
            )
        stmt = stmt.order_by(
            SaleCapture.last_registration_attempt_at.desc().nullslast(),
            SaleCapture.updated_at.desc(),
        ).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_for_reconciliation(db: Session, limit: int = 500) -> list[SaleCapture]:
        stmt = (
            select(SaleCapture)
            .where(
                SaleCapture.status != SALE_STATUS_DRAFT,
            )
            .order_by(SaleCapture.updated_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def count_by_status(db: Session) -> dict[str, int]:
        rows = db.execute(
            select(SaleCapture.status, func.count(SaleCapture.id)).group_by(
                SaleCapture.status
            )
        ).all()
        return {status: count for status, count in rows}
