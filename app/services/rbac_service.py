"""P81 — servicio RBAC + auditoría reutilizable."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.security.rbac import Permission, normalize_rbac_role, role_has_permission
from app.services.compliance_service import ComplianceService

log = logging.getLogger(__name__)


class RbacService:
    def __init__(self) -> None:
        self._compliance = ComplianceService()

    def is_relaxed(self) -> bool:
        return bool(get_settings().web_rbac_relaxed)

    def has_permission(
        self,
        user: dict[str, Any] | None,
        permission: Permission,
    ) -> bool:
        if self.is_relaxed():
            return True
        return role_has_permission((user or {}).get("rol"), permission)

    def actor_label(self, user: dict[str, Any] | None) -> str:
        if not user:
            return "anonymous"
        uid = user.get("id") or user.get("user_id")
        username = user.get("username") or user.get("nombre") or "?"
        role = user.get("rol") or "?"
        profile = normalize_rbac_role(role).value
        return f"user:{uid}:{username} ({role}/{profile})"

    def record_audit(
        self,
        db: Session,
        *,
        user: dict[str, Any] | None,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        allowed: bool,
        permission: Permission | None = None,
        detail: dict[str, Any] | None = None,
        company_id: int | None = None,
    ) -> None:
        """Registra en audit_entries (ComplianceService)."""
        try:
            payload = {
                "allowed": allowed,
                "permission": permission.value if permission else None,
                "detail": detail or {},
            }
            self._compliance.record_audit(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_label=self.actor_label(user),
                before=None,
                after=payload,
                company_id=company_id or (user or {}).get("company_id") or 1,
            )
        except Exception:
            log.exception("No se pudo registrar auditoría RBAC action=%s", action)

    def check_permission(
        self,
        db: Session | None,
        user: dict[str, Any] | None,
        permission: Permission,
        *,
        action: str = "rbac_check",
        entity_type: str = "system",
        entity_id: int | None = None,
        audit: bool = True,
    ) -> bool:
        ok = self.has_permission(user, permission)
        if audit and db is not None and not ok:
            self.record_audit(
                db,
                user=user,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                allowed=False,
                permission=permission,
            )
        return ok
