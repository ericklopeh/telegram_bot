"""P60 — multi-tenant SaaS enterprise."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enterprise_advanced import TenantSettings, TenantStoragePath
from app.models.platform import Company


class SaasTenantService:
    def get_by_slug(self, db: Session, slug: str) -> TenantSettings | None:
        return db.scalar(select(TenantSettings).where(TenantSettings.slug == slug))

    def get_by_company(self, db: Session, company_id: int) -> TenantSettings | None:
        return db.scalar(select(TenantSettings).where(TenantSettings.company_id == company_id))

    def list_tenants(self, db: Session) -> list[dict[str, Any]]:
        rows = list(db.scalars(select(TenantSettings).order_by(TenantSettings.id)).all())
        return [
            {
                "id": t.id,
                "slug": t.slug,
                "display_name": t.display_name,
                "company_id": t.company_id,
                "is_active": t.is_active,
                "limits": t.limits_json or {},
            }
            for t in rows
        ]

    def resolve_storage_path(self, db: Session, company_id: int, path_key: str) -> str:
        custom = db.scalar(
            select(TenantStoragePath).where(
                TenantStoragePath.company_id == company_id,
                TenantStoragePath.path_key == path_key,
            )
        )
        settings = get_settings()
        base = Path(settings.storage_root) / "tenants" / str(company_id)
        if custom:
            return str(base / custom.relative_path)
        return str(base / path_key)

    def ensure_tenant_storage(self, db: Session, company_id: int) -> None:
        for key in ("attachments", "exports", "signed_docs"):
            path = self.resolve_storage_path(db, company_id, key)
            Path(path).mkdir(parents=True, exist_ok=True)

    def branding_for_request(self, db: Session, company_id: int) -> dict[str, Any]:
        tenant = self.get_by_company(db, company_id)
        if tenant and tenant.branding_json:
            return tenant.branding_json
        co = db.get(Company, company_id)
        return (co.branding_json if co else None) or {"name": co.name if co else "Gaman"}

    def check_limits(self, db: Session, company_id: int, metric: str, current: int) -> bool:
        tenant = self.get_by_company(db, company_id)
        limits = (tenant.limits_json if tenant else None) or {}
        cap = limits.get(metric)
        if cap is None:
            return True
        return current < int(cap)
