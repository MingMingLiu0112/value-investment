"""D5 interface-only sleeve and shared-budget contracts.

No instance in this module authorizes a position or an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class PortfolioSleeve(str, Enum):
    CORE_VALUE = "CORE_VALUE"
    TACTICAL_HOTSPOT = "TACTICAL_HOTSPOT"
    CASH_RESERVE = "CASH_RESERVE"


def _fraction(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite fraction in [0, 1]")


@dataclass(frozen=True)
class SharedSleeveBudget:
    """Explicit portions of one portfolio; cash cannot be reserved twice."""

    core_value_budget: Decimal
    tactical_hotspot_budget: Decimal
    cash_floor: Decimal
    cross_sleeve_single_stock_cap: Decimal
    cross_sleeve_sector_cap: Decimal
    policy_scope: str
    action: str = "no_order"

    def __post_init__(self) -> None:
        for name in (
            "core_value_budget", "tactical_hotspot_budget", "cash_floor",
            "cross_sleeve_single_stock_cap", "cross_sleeve_sector_cap",
        ):
            _fraction(getattr(self, name), name)
        if self.core_value_budget + self.tactical_hotspot_budget + self.cash_floor > 1:
            raise ValueError("Sleeve reservations and cash floor exceed one portfolio")
        if self.policy_scope not in {"SYNTHETIC_POLICY_ONLY", "USER_CONFIRMED"}:
            raise ValueError("Sleeve budget requires an explicit policy provenance")
        if self.action != "no_order":
            raise ValueError("Sleeve budget cannot authorize orders")


__all__ = ["PortfolioSleeve", "SharedSleeveBudget"]
