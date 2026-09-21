"""Frozen, research-only sizing for the first paper-account experiment."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .virtual_account import board_lot_quantity


@dataclass(frozen=True)
class PaperSizingPolicy:
    """P2 experiment defaults; this is not a real-account allocation policy."""

    max_position_weight: Decimal = Decimal("0.08")
    tranche_weights: tuple[Decimal, Decimal, Decimal] = (
        Decimal("0.50"), Decimal("0.30"), Decimal("0.20"),
    )
    fee_rate: Decimal = Decimal("0.0003")


def _validate(policy: PaperSizingPolicy, nav: Decimal, cash: Decimal, price: Decimal) -> None:
    if nav <= 0 or cash < 0 or price <= 0:
        raise ValueError("Finite positive NAV/price and nonnegative cash are required")
    if not (Decimal(0) < policy.max_position_weight <= Decimal(1)):
        raise ValueError("Position cap must be within (0, 1]")
    if len(policy.tranche_weights) != 3 or sum(policy.tranche_weights) != Decimal(1):
        raise ValueError("The frozen entry/add/add tranches must total one")
    if any(weight <= 0 for weight in policy.tranche_weights) or policy.fee_rate < 0:
        raise ValueError("Tranches and fee rate must be nonnegative")


def size_entry_or_add(*, nav: Decimal, cash: Decimal, current_shares: int, price: Decimal,
                      tranche_index: int, policy: PaperSizingPolicy = PaperSizingPolicy()) -> dict:
    """Size one registered entry/add tranche without creating an order."""
    _validate(policy, nav, cash, price)
    if type(current_shares) is not int or current_shares < 0:
        raise ValueError("Current shares must be a nonnegative integer")
    if tranche_index not in range(len(policy.tranche_weights)):
        raise ValueError("Tranche index must identify entry, first add, or second add")
    cap_cny = nav * policy.max_position_weight
    current_exposure_cny = Decimal(current_shares) * price
    tranche_budget_cny = cap_cny * policy.tranche_weights[tranche_index]
    remaining_cap_cny = max(Decimal(0), cap_cny - current_exposure_cny)
    permitted_budget_cny = min(cash, tranche_budget_cny, remaining_cap_cny)
    quantity = board_lot_quantity(permitted_budget_cny, price, policy.fee_rate)
    reasons = []
    if remaining_cap_cny <= 0:
        reasons.append("position_cap_reached")
    if cash < min(tranche_budget_cny, remaining_cap_cny):
        reasons.append("cash_limits_registered_tranche")
    if quantity == 0:
        reasons.append("insufficient_cash_or_board_lot")
    return {
        "tranche_index": tranche_index,
        "cap_cny": str(cap_cny),
        "current_exposure_cny": str(current_exposure_cny),
        "registered_tranche_budget_cny": str(tranche_budget_cny),
        "permitted_budget_cny": str(permitted_budget_cny),
        "quantity": quantity,
        "reasons": reasons,
        "policy_scope": "research_only_p2_position_sizing_experiment",
    }


def size_one_third_reduce(*, sellable_shares: int) -> dict:
    """Return an explicit board-lot partial reduction, never an implicit exit."""
    if type(sellable_shares) is not int or sellable_shares < 0:
        raise ValueError("Sellable shares must be a nonnegative integer")
    quantity = (sellable_shares // 3 // 100) * 100
    return {"sellable_shares": sellable_shares, "quantity": quantity,
            "reasons": ([] if quantity else ["partial_reduce_below_board_lot"]),
            "policy_scope": "research_only_p2_position_sizing_experiment"}
