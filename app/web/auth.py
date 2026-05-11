import logging
from collections.abc import Iterable

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.models.user import UserRole
from app.repositories.user_repository import UserRepository

log = logging.getLogger(__name__)

# Roles reutilizados en rutas sensibles (valores persistidos en BD, ver UserRole).
ROLES_ADMIN_SISTEMAS: tuple[str, ...] = (UserRole.ADMIN.value, UserRole.SISTEMAS.value)
ROLES_AUTORIZACION_SNTE: tuple[str, ...] = (
    UserRole.ADMIN.value,
    UserRole.SISTEMAS.value,
    UserRole.AUTORIZACION.value,
)


def _session_user_payload(usuario) -> dict:
    role = getattr(usuario.role, "value", usuario.role)
    return {
        "id": usuario.id,
        "user_id": usuario.id,
        "username": usuario.username,
        "nombre": usuario.nombre,
        "rol": role,
    }


def get_current_user(request: Request, db: Session) -> dict | None:
    session_user = request.session.get("usuario")
    if not session_user:
        return None

    user_id = session_user.get("user_id") or session_user.get("id")
    if not user_id:
        request.session.clear()
        return None

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        request.session.clear()
        return None

    usuario = UserRepository.get_by_id(db, user_id_int)
    if not usuario or not usuario.is_active:
        request.session.clear()
        return None

    current_user = _session_user_payload(usuario)
    request.session["usuario"] = current_user
    return current_user


def require_login(request: Request, db: Session):
    usuario = get_current_user(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return None


def require_roles(request: Request, db: Session, roles: Iterable[str]):
    usuario = get_current_user(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    allowed_roles = set(roles)
    if usuario.get("rol") not in allowed_roles:
        log.warning(
            "Acceso web denegado: rol no autorizado para la ruta",
            extra={
                "path": str(request.url.path),
                "user_id": usuario.get("id"),
                "rol": usuario.get("rol"),
                "allowed_roles": sorted(allowed_roles),
            },
        )
        return RedirectResponse(url="/dashboard", status_code=302)

    return None
