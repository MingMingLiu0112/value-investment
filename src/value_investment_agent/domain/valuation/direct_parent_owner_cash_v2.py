"""Versioned parent-owner cash path with explicit finite distributions.

V2 preserves the V1 parent-only cash, financing, and stationary-terminal
contracts.  Each finite year additionally declares an owner distribution that
was implemented or explicitly scheduled after the valuation date.  That
distribution consumes non-borrowed cash headroom and distribution capacity
before any conditional payout is calculated.  It is never repeated in the
terminal period.

This remains conditional research arithmetic.  It does not certify legal
distribution capacity, financing availability, investment eligibility, or an
order.
"""

from decimal import Decimal, localcontext

from .direct_parent_owner_cash_v1 import (
    CONSTANT_DEBT_REFINANCING,
    FLOW_KEYS,
    STATE_KEYS,
    ZERO,
    _amounts,
    _flow,
    _terminal_financing,
)
from .parent_cash_policy import _number
from .parent_direct_operating_cash import SCOPE


VERSION = "direct-parent-owner-cash-v2"
YEAR_KEYS = frozenset(("year", "policy", "scheduled_owner_distribution_cny"))


def _annual_accounting(*, state, flow, total_distribution, shares, cost):
    """Return explicit clean-surplus arithmetic for one finite or tail year.

    A scheduled distribution may validly draw on previously accumulated
    distribution capacity and therefore exceed current-year profit.  The V1
    retention helper deliberately rejects negative retention, so V2 performs
    the same clean-surplus identities directly rather than weakening that
    helper's historical contract.
    """

    opening_book = state["book"]
    profit = flow["parent_profit"]
    closing_book = opening_book + profit - total_distribution
    if closing_book <= 0:
        raise ValueError("DIRECT_OWNER_NONPOSITIVE_CLOSING_BOOK")
    return {
        "opening_book_equity_cny": str(opening_book),
        "roe_assumption": str(profit / opening_book),
        "net_income_assumption_cny": str(profit),
        "retention_assumption": str(1 - total_distribution / profit),
        "dividend_assumption_cny": str(total_distribution),
        "residual_income_cny": str(profit - cost * opening_book),
        "closing_book_equity_cny": str(closing_book),
    }


def _step(state, flow, *, scheduled, year, shares, cost):
    if scheduled < 0:
        raise ValueError("DIRECT_OWNER_NEGATIVE_SCHEDULED_DISTRIBUTION")
    if flow["debt_repayment"] > state["debt"] + flow["new_borrowing"]:
        raise ValueError("DIRECT_OWNER_REPAYMENT_EXCEEDS_DEBT")

    mandatory = sum(
        flow[key]
        for key in (
            "maintenance_capex",
            "growth_capex",
            "commitments_outside_capex",
            "debt_repayment",
            "interest_outside_cfo",
            "other_mandatory_cash",
        )
    )
    net_cash = (
        flow["operating_cash"]
        + flow["investment_cash_received"]
        + flow["new_borrowing"]
        - mandatory
    )
    before = state["cash"] + net_cash
    if before < flow["cash_floor"]:
        raise ValueError(f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}")

    capacity = state["capacity"] + flow["parent_profit"] * (
        1 - flow["reserve_ratio"]
    )
    # A scheduled distribution must stand without current-year borrowing.  V1
    # policy semantics for the subsequent conditional payout remain unchanged.
    scheduled_cash_limit = (
        before - flow["new_borrowing"] - flow["cash_floor"]
    )
    if scheduled > 0 and scheduled > scheduled_cash_limit:
        raise ValueError(
            f"DIRECT_OWNER_SCHEDULED_DISTRIBUTION_REQUIRES_BORROWING_OR_CASH:{year}"
        )
    if scheduled > capacity:
        raise ValueError(
            f"DIRECT_OWNER_SCHEDULED_DISTRIBUTION_EXCEEDS_CAPACITY:{year}"
        )

    cash_after_scheduled = before - scheduled
    capacity_after_scheduled = capacity - scheduled
    conditional = min(
        flow["parent_profit"] * flow["payout_ratio"],
        cash_after_scheduled - flow["cash_floor"],
        capacity_after_scheduled,
    )
    total = scheduled + conditional
    accounting = _annual_accounting(
        state=state,
        flow=flow,
        total_distribution=total,
        shares=shares,
        cost=cost,
    )
    next_state = {
        "book": Decimal(accounting["closing_book_equity_cny"]),
        "cash": before - total,
        "capacity": capacity - total,
        "debt": state["debt"]
        + flow["new_borrowing"]
        - flow["debt_repayment"],
    }
    row = {
        "year": year,
        **accounting,
        "opening_cash_cny": str(state["cash"]),
        "opening_debt_cny": str(state["debt"]),
        "opening_distribution_capacity_cny": str(state["capacity"]),
        "direct_operating_cash_cny": str(flow["operating_cash"]),
        "net_cash_before_distribution_cny": str(net_cash),
        "cash_before_distribution_cny": str(before),
        "scheduled_owner_distribution_cny": str(scheduled),
        "conditional_distribution_cny": str(conditional),
        "total_owner_distribution_cny": str(total),
        "scheduled_nonborrowed_cash_limit_cny": str(scheduled_cash_limit),
        "scheduled_capacity_limit_cny": str(capacity),
        "cash_distribution_limit_cny": str(
            cash_after_scheduled - flow["cash_floor"]
        ),
        "capacity_distribution_limit_cny": str(capacity_after_scheduled),
        "closing_cash_cny": str(next_state["cash"]),
        "closing_debt_cny": str(next_state["debt"]),
        "closing_distribution_capacity_cny": str(next_state["capacity"]),
        "net_noncash_assets_cny": str(next_state["book"] - next_state["cash"]),
        "cash_policy": {key: str(value) for key, value in flow.items()},
    }
    return row, next_state


def compile_direct_owner_cash_path_v2(
    *,
    opening,
    years,
    terminal,
    ordinary_shares,
    cost_of_equity,
    scope,
    currency,
):
    """Compile scheduled plus conditional distributions and a V1-style tail."""

    if scope != SCOPE or currency != "CNY":
        raise ValueError("DIRECT_OWNER_PARENT_CNY_REQUIRED")
    if not isinstance(years, list) or not years:
        raise ValueError("DIRECT_OWNER_EXPLICIT_YEARS_REQUIRED")
    shares, cost = _number(ordinary_shares), _number(cost_of_equity)
    if shares <= 0 or shares != shares.to_integral_value() or not 0 < cost < 1:
        raise ValueError("DIRECT_OWNER_SHARES_OR_COST_INVALID")
    state = _amounts(opening, STATE_KEYS)
    if state["book"] <= 0 or min(state.values()) < 0:
        raise ValueError("DIRECT_OWNER_OPENING_STATE_INVALID")

    terminal_keys = {
        "policy",
        "remaining_scheduled_events",
        "rationale",
        "max_transition_years",
    }
    if isinstance(terminal, dict) and (
        "scheduled_owner_distribution_cny" in terminal
        or isinstance(terminal.get("policy"), dict)
        and "scheduled_owner_distribution_cny" in terminal["policy"]
    ):
        raise ValueError("DIRECT_OWNER_SCHEDULED_DISTRIBUTION_NOT_ALLOWED_IN_TERMINAL")
    if not isinstance(terminal, dict) or set(terminal) not in (
        terminal_keys,
        terminal_keys | {"financing"},
    ):
        raise ValueError("DIRECT_OWNER_EXPLICIT_TERMINAL_REQUIRED")
    if terminal["remaining_scheduled_events"] != []:
        raise ValueError("DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS")
    if not isinstance(terminal["rationale"], str) or not terminal[
        "rationale"
    ].strip():
        raise ValueError("DIRECT_OWNER_TERMINAL_RATIONALE_REQUIRED")
    limit = terminal["max_transition_years"]
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("DIRECT_OWNER_TERMINAL_LIMIT_INVALID")

    with localcontext() as context:
        context.prec = 48
        initial_book = state["book"]
        rows = []
        previous = None
        for raw in years:
            if not isinstance(raw, dict) or set(raw) != YEAR_KEYS:
                raise ValueError("DIRECT_OWNER_V2_YEAR_CONTRACT_INVALID")
            year = raw["year"]
            if (
                type(year) is not int
                or not 1 <= year <= 9999
                or previous is not None
                and year != previous + 1
            ):
                raise ValueError("DIRECT_OWNER_NONCONTIGUOUS_YEARS")
            scheduled = _number(raw["scheduled_owner_distribution_cny"])
            row, state = _step(
                state,
                _flow(raw["policy"]),
                scheduled=scheduled,
                year=year,
                shares=shares,
                cost=cost,
            )
            rows.append(row)
            previous = year

        terminal_flow = _flow(terminal["policy"])
        financing = _terminal_financing(terminal, state, terminal_flow)
        if terminal_flow["commitments_outside_capex"]:
            raise ValueError("DIRECT_OWNER_FINITE_COMMITMENT_IN_TERMINAL")
        terminal_net = (
            terminal_flow["operating_cash"]
            + terminal_flow["investment_cash_received"]
            - sum(
                terminal_flow[key]
                for key in (
                    "maintenance_capex",
                    "growth_capex",
                    "interest_outside_cfo",
                    "other_mandatory_cash",
                )
            )
        )
        if financing is not None:
            terminal_net += (
                terminal_flow["new_borrowing"]
                - terminal_flow["debt_repayment"]
            )
        if not 0 <= terminal_net <= terminal_flow["parent_profit"]:
            raise ValueError("DIRECT_OWNER_UNSUPPORTED_STATIONARY_CASH_CONVERSION")
        steady = min(
            terminal_flow["parent_profit"] * terminal_flow["payout_ratio"],
            terminal_net,
            terminal_flow["parent_profit"]
            * (1 - terminal_flow["reserve_ratio"]),
        )
        if steady <= 0:
            raise ValueError(
                "DIRECT_OWNER_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION"
            )

        tail_rows = []
        tail_pv = ZERO
        for elapsed in range(1, limit + 1):
            row, next_state = _step(
                state,
                terminal_flow,
                scheduled=ZERO,
                year=previous + elapsed,
                shares=shares,
                cost=cost,
            )
            distribution = Decimal(row["total_owner_distribution_cny"])
            tail_pv += distribution / (1 + cost) ** elapsed
            tail_rows.append(row)
            if (
                distribution == steady
                and next_state["cash"] >= state["cash"]
                and next_state["capacity"] >= state["capacity"]
            ):
                tail_value = tail_pv + steady / cost / (1 + cost) ** elapsed
                break
            state = next_state
        else:
            raise ValueError("DIRECT_OWNER_TERMINAL_NOT_PROVEN_WITHIN_LIMIT")

        distributions = ZERO
        residual = initial_book
        for index, row in enumerate(rows, 1):
            discount = (1 + cost) ** index
            distributions += Decimal(row["total_owner_distribution_cny"]) / discount
            residual += Decimal(row["residual_income_cny"]) / discount
        closing_book = Decimal(rows[-1]["closing_book_equity_cny"])
        divisor = (1 + cost) ** len(rows)
        equity = distributions + tail_value / divisor
        ri = residual + (tail_value - closing_book) / divisor
        if abs(equity - ri) > max(
            Decimal("0.00000001"), abs(equity) * Decimal("1e-36")
        ):
            raise ValueError("DIRECT_OWNER_RI_DISTRIBUTION_CROSSCHECK_FAILED")

        result = {
            "schema_version": VERSION,
            "annual_rows": rows,
            "terminal_rows": tail_rows,
            "terminal_method": "exact_stationary_direct_owner_distribution",
            "terminal_equity_value_cny": str(tail_value),
            "terminal_steady_distribution_cny": str(steady),
            "conditional_equity_value_cny": str(equity),
            "per_share_value": str(equity / shares),
            "dividend_crosscheck_equity_value_cny": str(equity),
            "residual_income_equity_value_cny": str(ri),
            "crosscheck_difference_cny": str(ri - equity),
            "terminal_truncation_error_cny": "0",
            "economic_uncertainty": "NOT_PROVEN_BY_ARITHMETIC",
            "cost_of_equity": str(cost),
            "ordinary_shares": str(shares),
            "working_capital_cash_component": None,
            "legal_distribution_capacity_certified": False,
            "formal_eligibility": False,
            "action": "no_order",
        }
        if financing is not None:
            result["terminal_financing"] = financing
        return result


compile_direct_owner_cash_path = compile_direct_owner_cash_path_v2


__all__ = [
    "CONSTANT_DEBT_REFINANCING",
    "FLOW_KEYS",
    "VERSION",
    "compile_direct_owner_cash_path",
    "compile_direct_owner_cash_path_v2",
]
