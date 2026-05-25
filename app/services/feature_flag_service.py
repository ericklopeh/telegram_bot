"""P59 — feature flags por entorno y tenant."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enterprise_advanced import FeatureFlag


DEFAULT_FLAGS = (
    ("realtime_ws", "WebSockets live", True),
    ("report_builder", "Constructor reportes", True),
    ("dynamic_rules", "Motor reglas", True),
    ("ai_ops_insights", "IA operacional", True),
    ("digital_signatures", "Firmas digitales", True),
    ("multi_tenant_saas", "Modo SaaS", False),
)


class FeatureFlagService:
    def is_enabled(
        self,
        db: Session,
        flag_key: str,
        *,
        company_id: int | None = None,
    ) -> bool:
        settings = get_settings()
        env = settings.environment
        stmt = select(FeatureFlag).where(FeatureFlag.flag_key == flag_key)
        flags = list(db.scalars(stmt).all())
        if not flags:
            for key, _, default in DEFAULT_FLAGS:
                if key == flag_key:
                    return default
            return False
        for f in flags:
            if f.company_id and company_id and f.company_id != company_id:
                continue
            if f.environment in ("all", env) and f.enabled:
                return True
        return False

    def seed_defaults(self, db: Session) -> None:
        settings = get_settings()
        for key, desc, enabled in DEFAULT_FLAGS:
            exists = db.scalar(
                select(FeatureFlag).where(
                    FeatureFlag.flag_key == key,
                    FeatureFlag.environment == "all",
                )
            )
            if exists:
                continue
            db.add(
                FeatureFlag(
                    flag_key=key,
                    description=desc,
                    enabled=enabled,
                    environment="all",
                )
            )
        db.flush()

    def list_flags(self, db: Session) -> list[dict[str, Any]]:
        return [
            {
                "id": f.id,
                "flag_key": f.flag_key,
                "description": f.description,
                "enabled": f.enabled,
                "environment": f.environment,
            }
            for f in db.scalars(select(FeatureFlag).order_by(FeatureFlag.flag_key)).all()
        ]

    def validate_defaults(self, db: Session) -> list[str]:
        """P69 — reporta flags críticos deshabilitados."""
        self.seed_defaults(db)
        warnings: list[str] = []
        for key, _, default in DEFAULT_FLAGS:
            if default and not self.is_enabled(db, flag_key=key):
                warnings.append(f"{key} deshabilitado (default on)")
        return warnings

    def set_flag(self, db: Session, flag_key: str, enabled: bool) -> FeatureFlag:
        flag = db.scalar(
            select(FeatureFlag).where(
                FeatureFlag.flag_key == flag_key,
                FeatureFlag.environment == "all",
            )
        )
        if not flag:
            flag = FeatureFlag(flag_key=flag_key, description=flag_key, environment="all")
            db.add(flag)
        flag.enabled = enabled
        db.flush()
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="feature_flag_toggled",
                title=f"Flag {flag_key}: {'on' if enabled else 'off'}",
                entity_type="feature_flag",
                entity_id=flag.id,
                source="admin",
                tone="info",
            )
        except Exception:
            pass
        return flag
