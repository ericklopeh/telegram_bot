"""P44 — contexto multiempresa / sucursal (compatible single-tenant)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.platform import Branch, Company


@dataclass
class TenantContext:
    company_id: int = 1
    branch_id: int = 1
    company_name: str = "Empresa principal"
    branch_name: str = "Sucursal principal"
    branding: dict[str, Any] | None = None


class TenantService:
    def default_context(self) -> TenantContext:
        settings = get_settings()
        return TenantContext(
            company_id=settings.default_company_id,
            branch_id=settings.default_branch_id,
        )

    def resolve_from_session(self, session_user: dict[str, Any] | None) -> TenantContext:
        if not session_user:
            return self.default_context()
        return TenantContext(
            company_id=int(session_user.get("company_id") or get_settings().default_company_id),
            branch_id=int(session_user.get("branch_id") or get_settings().default_branch_id),
            company_name=session_user.get("company_name") or "Empresa principal",
            branch_name=session_user.get("branch_name") or "Sucursal principal",
        )

    def list_companies(self, db: Session) -> list[Company]:
        return list(db.scalars(select(Company).order_by(Company.id)).all())

    def list_branches(self, db: Session, company_id: int) -> list[Branch]:
        stmt = select(Branch).where(Branch.company_id == company_id).order_by(Branch.id)
        return list(db.scalars(stmt).all())

    def apply_case_filter(self, stmt, ctx: TenantContext):
        """Filtro opcional por tenant — no excluye legacy si company_id=1."""
        from app.models.case import Case

        return stmt.where(
            Case.company_id == ctx.company_id,
        )

    def enrich_login_user(self, db: Session, user_dict: dict[str, Any]) -> dict[str, Any]:
        ctx = self.default_context()
        try:
            companies = self.list_companies(db)
            if companies:
                co = next((c for c in companies if c.id == ctx.company_id), companies[0])
                ctx.company_name = co.name
                ctx.branding = co.branding_json
            branches = self.list_branches(db, ctx.company_id)
            if branches:
                br = next((b for b in branches if b.id == ctx.branch_id), branches[0])
                ctx.branch_name = br.name
        except Exception:
            pass
        user_dict["company_id"] = ctx.company_id
        user_dict["branch_id"] = ctx.branch_id
        user_dict["company_name"] = ctx.company_name
        user_dict["branch_name"] = ctx.branch_name
        return user_dict
