"""Pruebas unitarias ligeras para sale_action_guard (P19.1)."""

from app.models.user import UserRole
from app.services.sale_action_guard_service import get_sale_action_permissions


def test_vendor_cannot_register_without_sale():
    perms = get_sale_action_permissions(
        None,  # db not needed when sale is None and no checklist docs
        {"rol": UserRole.VENDEDOR.value, "id": 1},
        None,
    )
    assert perms.can_register_definitive is False
    assert "autorización" in (perms.register_reason or "").lower()


def test_admin_can_register_flag_when_no_sale():
    perms = get_sale_action_permissions(
        None,
        {"rol": UserRole.ADMIN.value, "id": 1},
        None,
    )
    assert perms.can_register_definitive is False
    assert perms.register_reason is not None
