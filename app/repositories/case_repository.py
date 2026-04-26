from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.case import Case


class CaseRepository:
    @staticmethod
    def next_revision_temp_folio(db: Session) -> str:
        year = datetime.now().year
        prefix = f"REVTMP-{year}-"
        last = db.scalar(
            select(Case.temp_folio)
            .where(Case.temp_folio.isnot(None), Case.temp_folio.startswith(prefix))
            .order_by(Case.id.desc())
            .limit(1)
        )
        if not last:
            n = 1
        else:
            try:
                n = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                n = 1
        return f"{prefix}{n:04d}"

    @staticmethod
    def next_pedido_official_folio(db: Session) -> str:
        rows = db.scalars(
            select(Case.official_folio)
            .where(
                Case.case_type == C.CASE_TYPE_PEDIDO,
                Case.official_folio.isnot(None),
            )
            .order_by(Case.id.desc())
            .limit(50)
        ).all()
        best = 0
        for r in rows:
            if r and r.isdigit():
                best = max(best, int(r))
        return f"{best + 1:05d}"

    @staticmethod
    def get_by_public_id(db: Session, public_id: str) -> Case | None:
        return db.scalar(select(Case).where(Case.public_id == public_id))

    @staticmethod
    def search_for_seller(
        db: Session,
        seller_chat_id: int,
        query: str,
        limit: int = 15,
    ) -> list[Case]:
        q = query.strip()
        if not q:
            return []
        stmt = select(Case).where(Case.seller_telegram_chat_id == seller_chat_id)
        if q.upper().startswith("REVTMP") or q.upper().startswith("PED-") or q.isdigit():
            stmt = stmt.where(
                or_(
                    Case.public_id.ilike(f"%{q}%"),
                    Case.temp_folio.ilike(f"%{q}%"),
                    Case.official_folio.ilike(f"%{q}%"),
                )
            )
        else:
            stmt = stmt.where(Case.client_name.ilike(f"%{q}%"))
        stmt = stmt.order_by(Case.updated_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def create(db: Session, case: Case) -> Case:
        db.add(case)
        db.flush()
        return case

    @staticmethod
    def save(db: Session, case: Case) -> None:
        db.add(case)

    @staticmethod
    def get_pendiente_compulsa(db: Session) -> list[Case]:
        stmt = (
            select(Case)
            .where(Case.current_status == C.ST_PED_PEND_COMPULSA)
            .order_by(Case.updated_at.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_seller_pedidos_of_day(
        db: Session,
        seller_chat_id: int,
        day: date,
        limit: int = 50,
    ) -> list[Case]:
        stmt = (
            select(Case)
            .where(
                Case.seller_telegram_chat_id == seller_chat_id,
                Case.case_type == C.CASE_TYPE_PEDIDO,
                func.date(Case.created_at) == day,
            )
            .order_by(Case.created_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_recent_revisions(db: Session, limit: int = 15) -> list[Case]:
        stmt = (
            select(Case)
            .where(Case.case_type == C.CASE_TYPE_REVISION)
            .order_by(Case.updated_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_pending_revisions(db: Session, limit: int = 20) -> list[Case]:
        pending = (C.ST_REV_RECIBIDO, C.ST_REV_EN_REVISION, C.ST_REV_CORRECCION)
        stmt = (
            select(Case)
            .where(
                Case.case_type == C.CASE_TYPE_REVISION,
                Case.current_status.in_(pending),
            )
            .order_by(Case.updated_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_recent_cases_global(db: Session, limit: int = 10) -> list[Case]:
        stmt = select(Case).order_by(Case.updated_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def search_global(db: Session, query: str, limit: int = 15) -> list[Case]:
        q = query.strip()
        if not q:
            return []
        stmt = select(Case)
        if q.upper().startswith("REVTMP") or q.upper().startswith("PED") or q.isdigit():
            stmt = stmt.where(
                or_(
                    Case.public_id.ilike(f"%{q}%"),
                    Case.temp_folio.ilike(f"%{q}%"),
                    Case.official_folio.ilike(f"%{q}%"),
                )
            )
        else:
            stmt = stmt.where(Case.client_name.ilike(f"%{q}%"))
        stmt = stmt.order_by(Case.updated_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_seller_cases_recent(
        db: Session,
        seller_chat_id: int,
        limit: int = 10,
    ) -> list[Case]:
        stmt = (
            select(Case)
            .where(Case.seller_telegram_chat_id == seller_chat_id)
            .order_by(Case.updated_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def seller_visible_status_summary(db: Session, seller_chat_id: int) -> dict[str, int]:
        stmt = (
            select(Case.visible_status, func.count(Case.id))
            .where(Case.seller_telegram_chat_id == seller_chat_id)
            .group_by(Case.visible_status)
        )
        rows = db.execute(stmt).all()
        return {status: count for status, count in rows}

    @staticmethod
    def list_cases_in_status_before(
        db: Session,
        statuses: tuple[str, ...] | list[str],
        cutoff: datetime,
    ) -> list[Case]:
        stmt = (
            select(Case)
            .where(Case.current_status.in_(tuple(statuses)), Case.updated_at <= cutoff)
            .order_by(Case.updated_at.asc())
        )
        return list(db.scalars(stmt).all())
