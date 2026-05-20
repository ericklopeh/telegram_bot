"""Reglas de porcentaje de comisión (P21-B) — extensible, sin lógica en el modelo."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

DEFAULT_COMMISSION_PERCENTAGE = Decimal("46")
JUAN_MANUEL_PERCENTAGE = Decimal("60")

_JUAN_MANUEL_KEYS = frozenset({"JUAN MANUEL", "JUAN MANUEL GARCIA", "JUAN MANUEL GARCIA "})


@dataclass(frozen=True)
class CommissionRuleContext:
    seller_name: str
    seccion: str | None = None
    tipo_venta: str | None = None
    producto: str | None = None
    qna: str | None = None


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().upper())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _rule_juan_manuel(ctx: CommissionRuleContext) -> Decimal | None:
    key = _normalize_name(ctx.seller_name)
    if key in _JUAN_MANUEL_KEYS or key.startswith("JUAN MANUEL"):
        return JUAN_MANUEL_PERCENTAGE
    return None


def _rule_default(_ctx: CommissionRuleContext) -> Decimal:
    return DEFAULT_COMMISSION_PERCENTAGE


# Orden: reglas específicas primero, default al final.
_COMMISSION_RULES: tuple[Callable[[CommissionRuleContext], Decimal | None], ...] = (
    _rule_juan_manuel,
)


def resolve_commission_percentage(ctx: CommissionRuleContext) -> Decimal:
    """Devuelve el porcentaje aplicable según reglas configuradas."""
    for rule in _COMMISSION_RULES:
        pct = rule(ctx)
        if pct is not None:
            return pct
    return _rule_default(ctx)
