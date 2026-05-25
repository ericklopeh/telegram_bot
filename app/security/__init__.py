"""Seguridad centralizada (P81 RBAC)."""

from app.security.rbac import Permission, RbacRole, normalize_rbac_role

__all__ = ["Permission", "RbacRole", "normalize_rbac_role"]
