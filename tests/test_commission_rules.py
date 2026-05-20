"""Pruebas reglas de comisión P21."""

from decimal import Decimal

from app.services.commission_rules import (
    DEFAULT_COMMISSION_PERCENTAGE,
    JUAN_MANUEL_PERCENTAGE,
    CommissionRuleContext,
    resolve_commission_percentage,
)


def test_default_percentage_46():
    ctx = CommissionRuleContext(seller_name="MARIA LOPEZ")
    assert resolve_commission_percentage(ctx) == DEFAULT_COMMISSION_PERCENTAGE
    assert resolve_commission_percentage(ctx) == Decimal("46")


def test_juan_manuel_percentage_60():
    for name in ("Juan Manuel", "JUAN MANUEL", "Juan Manuel García"):
        ctx = CommissionRuleContext(seller_name=name)
        assert resolve_commission_percentage(ctx) == JUAN_MANUEL_PERCENTAGE
        assert resolve_commission_percentage(ctx) == Decimal("60")
