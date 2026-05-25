"""P81 — roles, permisos y matriz centralizada."""

from __future__ import annotations

from enum import Enum


class RbacRole(str, Enum):
    """Perfiles RBAC de negocio (P81)."""

    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    VENDEDOR = "vendedor"
    READONLY = "readonly"


class Permission(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    APPROVE = "approve"
    COMPULSA = "compulsa"
    EXPORT = "export"
    DELETE = "delete"
    DOWNLOAD = "download"
    VIEW_AUDIT = "view_audit"


# Matriz por perfil RBAC normalizado
_ROLE_PERMISSIONS: dict[RbacRole, frozenset[Permission]] = {
    RbacRole.ADMIN: frozenset(Permission),
    RbacRole.SUPERVISOR: frozenset(
        {
            Permission.CREATE,
            Permission.EDIT,
            Permission.APPROVE,
            Permission.COMPULSA,
            Permission.EXPORT,
            Permission.DOWNLOAD,
        }
    ),
    RbacRole.VENDEDOR: frozenset(
        {
            Permission.CREATE,
            Permission.EDIT,
            Permission.DOWNLOAD,
        }
    ),
    RbacRole.READONLY: frozenset({Permission.DOWNLOAD}),
}

# Roles persistidos en BD → perfil RBAC
_LEGACY_ROLE_MAP: dict[str, RbacRole] = {
    "admin": RbacRole.ADMIN,
    "sistemas": RbacRole.ADMIN,
    "supervisor": RbacRole.SUPERVISOR,
    "autorizacion": RbacRole.SUPERVISOR,
    "autorizaciones": RbacRole.SUPERVISOR,
    "compras": RbacRole.SUPERVISOR,
    "compulsa": RbacRole.SUPERVISOR,
    "vendedor": RbacRole.VENDEDOR,
    "consulta": RbacRole.READONLY,
    "readonly": RbacRole.READONLY,
}


def normalize_rbac_role(role: str | None) -> RbacRole:
    """Mapea rol de sesión/BD al perfil RBAC sin migrar usuarios."""
    key = (role or "").strip().lower()
    return _LEGACY_ROLE_MAP.get(key, RbacRole.READONLY)


def role_has_permission(role: str | None, permission: Permission) -> bool:
    profile = normalize_rbac_role(role)
    return permission in _ROLE_PERMISSIONS.get(profile, frozenset())


def permissions_for_role(role: str | None) -> dict[str, bool]:
    """Flags para plantillas Jinja (bloqueo visual)."""
    profile = normalize_rbac_role(role)
    allowed = _ROLE_PERMISSIONS.get(profile, frozenset())
    return {p.value: (p in allowed) for p in Permission}
