"""P81 — helpers web: guards, redirects y contexto UI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.security.rbac import Permission, permissions_for_role
from app.services.rbac_service import RbacService
from app.web.auth import get_current_user

log = logging.getLogger(__name__)
_rbac = RbacService()


def rbac_flags_for_user(user: dict[str, Any] | None) -> dict[str, bool]:
    if _rbac.is_relaxed():
        return {p.value: True for p in Permission}
    return permissions_for_role((user or {}).get("rol"))


def require_permission(
    request: Request,
    db: Session,
    permission: Permission,
    *,
    roles_fallback: tuple[str, ...] | None = None,
    action: str = "access_denied",
    entity_type: str = "route",
    entity_id: int | None = None,
):
    """
    Guard centralizado. Retorna RedirectResponse si falla (HTML)
    o None si OK. Respeta web_rbac_relaxed.
    """
    usuario = get_current_user(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    if _rbac.has_permission(usuario, permission):
        return None

    if roles_fallback and usuario.get("rol") in roles_fallback:
        return None

    _rbac.record_audit(
        db,
        user=usuario,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        allowed=False,
        permission=permission,
        detail={"path": str(request.url.path), "method": request.method},
    )
    log.warning(
        "RBAC denegado path=%s perm=%s user=%s",
        request.url.path,
        permission.value,
        usuario.get("id"),
    )
    return RedirectResponse(url="/dashboard?rbac=denied", status_code=302)


def require_permission_api(
    request: Request,
    db: Session,
    permission: Permission,
    *,
    action: str = "api_denied",
    entity_type: str = "api",
    entity_id: int | None = None,
) -> dict[str, Any]:
    """Para endpoints JSON: lanza HTTPException 403."""
    usuario = get_current_user(request, db)
    if not usuario:
        raise HTTPException(status_code=401, detail="No autenticado")
    if _rbac.check_permission(
        db, usuario, permission, action=action, entity_type=entity_type, entity_id=entity_id
    ):
        return usuario
    raise HTTPException(status_code=403, detail=f"Permiso requerido: {permission.value}")


def check_case_ownership_vendedor(usuario: dict, caso) -> bool:
    """Vendedor solo actúa sobre sus casos."""
    from app.models.user import UserRole

    if usuario.get("rol") != UserRole.VENDEDOR.value:
        return True
    return caso.seller_name == usuario.get("nombre")
