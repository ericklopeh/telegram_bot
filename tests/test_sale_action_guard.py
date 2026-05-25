"""Pruebas unitarias ligeras para sale_action_guard (P19.1)."""

from unittest.mock import patch

from app.models.user import UserRole
from app.services.sale_action_guard_service import get_sale_action_permissions


@patch("app.services.sale_action_guard_service.get_settings")
def test_vendor_cannot_register_without_sale(mock_settings):
    mock_settings.return_value.web_rbac_relaxed = False
    perms = get_sale_action_permissions(
        None,  # db not needed when sale is None and no checklist docs
        {"rol": UserRole.VENDEDOR.value, "id": 1},
        None,
    )
    assert perms.can_register_definitive is False
    reason = (perms.register_reason or "").lower()
    assert "captura" in reason or "autorización" in reason


def test_admin_can_register_flag_when_no_sale():
    perms = get_sale_action_permissions(
        None,
        {"rol": UserRole.ADMIN.value, "id": 1},
        None,
    )
    assert perms.can_register_definitive is False
    assert perms.register_reason is not None
