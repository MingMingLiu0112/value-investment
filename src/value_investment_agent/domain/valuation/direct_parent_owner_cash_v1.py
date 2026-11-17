"""Direct parent cash to constrained owner distributions; no WC relabelling.

Inputs are explicit parent-only CNY forecasts. CFO already includes working
capital and noncash-to-cash conversion. Gross capex is deducted once; neither
depreciation nor a second WC deduction is allowed. This is a conditional
cash-budget model, not certified legal distribution capacity.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
from .parent_cash_policy import _number
from .parent_direct_operating_cash import SCOPE
from ...valuation_models.residual_income_path_v4 import _annual_clean_surplus_row

VERSION = "direct-parent-owner-cash-v1"
FLOW_KEYS = frozenset((
    "parent_profit", "operating_cash", "investment_cash_received",
    "maintenance_capex", "growth_capex", "commitments_outside_capex",
    "debt_repayment", "new_borrowing", "interest_outside_cfo",
    "other_mandatory_cash", "cash_floor", "payout_ratio", "reserve_ratio",
))
STATE_KEYS = frozenset(("book", "cash", "capacity", "debt"))
ZERO = Decimal(0)
CONSTANT_DEBT_REFINANCING = "CONSTANT_DEBT_REFINANCING"


def _terminal_financing(terminal, state, flow):
    """Validate an explicit assumption, never certify refinancing availability."""
    if "financing" not in terminal:
        if state["debt"] or flow["new_borrowing"] or flow["debt_repayment"]:
            raise ValueError("DIRECT_OWNER_TERMINAL_DEBT_POLICY_UNSUPPORTED")
        return None  # Historical ZERO_DEBT contract and output stay unchanged.
    financing = terminal["financing"]
    if not isinstance(financing, dict) or set(financing) != {
            "mode", "rationale", "counter_evidence", "reopen_condition", "coverage"}:
        raise ValueError("DIRECT_OWNER_EXACT_TERMINAL_FINANCING_REQUIRED")
    if financing["mode"] != CONSTANT_DEBT_REFINANCING:
        raise ValueError("DIRECT_OWNER_TERMINAL_FINANCING_MODE_UNSUPPORTED")
    for key in ("rationale", "counter_evidence", "reopen_condition"):
        if not isinstance(financing[key], str) or not financing[key].strip():
            raise ValueError("DIRECT_OWNER_TERMINAL_FINANCING_EXPLANATION_REQUIRED:" + key)
    coverage = financing["coverage"]
    if (not isinstance(coverage, dict)
            or set(coverage) != {"interest_outside_cfo", "debt_scope"}
            or coverage["interest_outside_cfo"] is not True
            or coverage["debt_scope"] != "ALL_EXISTING_TERMINAL_DEBT"):
        raise ValueError("DIRECT_OWNER_TERMINAL_FINANCING_COVERAGE_REQUIRED")
    if (state["debt"] <= 0 or flow["new_borrowing"] != flow["debt_repayment"]
            or flow["debt_repayment"] > state["debt"]):
        raise ValueError("DIRECT_OWNER_CONSTANT_DEBT_REFINANCING_REQUIRED")
    if flow["interest_outside_cfo"] <= 0:
        raise ValueError("DIRECT_OWNER_POSITIVE_TERMINAL_CASH_INTEREST_REQUIRED")
    return dict(**deepcopy(financing), classification="FORECAST_ASSUMPTION",
                actual_refinancing_guaranteed=False,
                terminal_opening_debt_cny=str(state["debt"]), net_new_borrowing_cny="0")


def _amounts(raw, keys):
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("DIRECT_OWNER_EXACT_FIELDS_REQUIRED")
    return {key: _number(raw[key]) for key in keys}


def _flow(raw):
    row = _amounts(raw, FLOW_KEYS)
    if row["parent_profit"] <= 0:
        raise ValueError("DIRECT_OWNER_POSITIVE_PROFIT_RI_SCOPE_REQUIRED")
    if any(value < 0 for key, value in row.items() if key != "operating_cash"):
        raise ValueError("DIRECT_OWNER_NEGATIVE_POLICY_AMOUNT")
    if not 0 <= row["payout_ratio"] <= 1 or not 0 <= row["reserve_ratio"] <= 1:
        raise ValueError("DIRECT_OWNER_RATIO_OUT_OF_RANGE")
    return row


def _step(state, flow, *, year, shares, cost):
    if flow["debt_repayment"] > state["debt"] + flow["new_borrowing"]:
        raise ValueError("DIRECT_OWNER_REPAYMENT_EXCEEDS_DEBT")
    mandatory = sum(flow[key] for key in (
        "maintenance_capex", "growth_capex", "commitments_outside_capex",
        "debt_repayment", "interest_outside_cfo", "other_mandatory_cash"))
    net_cash = (flow["operating_cash"] + flow["investment_cash_received"]
                + flow["new_borrowing"] - mandatory)
    before = state["cash"] + net_cash
    if before < flow["cash_floor"]:
        raise ValueError(f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}")
    capacity = state["capacity"] + flow["parent_profit"] * (1-flow["reserve_ratio"])
    distribution = min(flow["parent_profit"] * flow["payout_ratio"],
                       before-flow["cash_floor"], capacity)
    retention = 1-distribution/flow["parent_profit"]
    # The existing shared RI annual arithmetic remains the authority for equity.
    accounting = _annual_clean_surplus_row(
        book=state["book"], shares=shares, cost=cost,
        roe=flow["parent_profit"]/state["book"], retention=retention)
    next_state = dict(book=Decimal(accounting["closing_book_equity_cny"]),
                      cash=before-distribution, capacity=capacity-distribution,
                      debt=state["debt"]+flow["new_borrowing"]-flow["debt_repayment"])
    row = dict(year=year, **accounting,
        opening_cash_cny=str(state["cash"]), opening_debt_cny=str(state["debt"]),
        opening_distribution_capacity_cny=str(state["capacity"]),
        direct_operating_cash_cny=str(flow["operating_cash"]),
        net_cash_before_distribution_cny=str(net_cash),
        cash_before_distribution_cny=str(before),
        conditional_distribution_cny=str(distribution),
        cash_distribution_limit_cny=str(before-flow["cash_floor"]),
        capacity_distribution_limit_cny=str(capacity),
        closing_cash_cny=str(next_state["cash"]),
        closing_debt_cny=str(next_state["debt"]),
        closing_distribution_capacity_cny=str(next_state["capacity"]),
        net_noncash_assets_cny=str(next_state["book"]-next_state["cash"]),
        cash_policy={key:str(value) for key,value in flow.items()})
    return row, next_state


def compile_direct_owner_cash_path(*, opening, years, terminal, ordinary_shares,
                                  cost_of_equity, scope, currency):
    """Compile actual annual distributions and a supported stationary cash tail.

    The terminal starts only after finite dated obligations are settled. New
    borrowing is never manufactured to fund distributions. Terminal financial
    debt defaults to zero. An explicit CONSTANT_DEBT_REFINANCING contract may
    instead retain debt with equal rollover cash flows and positive CFO-external
    interest. Neither future financing availability nor settlement is certified.
    """
    if scope != SCOPE or currency != "CNY":
        raise ValueError("DIRECT_OWNER_PARENT_CNY_REQUIRED")
    if not isinstance(years,list) or not years:
        raise ValueError("DIRECT_OWNER_EXPLICIT_YEARS_REQUIRED")
    shares, cost = _number(ordinary_shares), _number(cost_of_equity)
    if shares <= 0 or shares != shares.to_integral_value() or not 0 < cost < 1:
        raise ValueError("DIRECT_OWNER_SHARES_OR_COST_INVALID")
    state = _amounts(opening, STATE_KEYS)
    if state["book"] <= 0 or min(state.values()) < 0:
        raise ValueError("DIRECT_OWNER_OPENING_STATE_INVALID")
    terminal_keys = {"policy","remaining_scheduled_events","rationale","max_transition_years"}
    if not isinstance(terminal,dict) or set(terminal) not in (terminal_keys, terminal_keys | {"financing"}):
        raise ValueError("DIRECT_OWNER_EXPLICIT_TERMINAL_REQUIRED")
    if terminal["remaining_scheduled_events"] != []:
        raise ValueError("DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS")
    if not isinstance(terminal["rationale"],str) or not terminal["rationale"].strip():
        raise ValueError("DIRECT_OWNER_TERMINAL_RATIONALE_REQUIRED")
    limit = terminal["max_transition_years"]
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("DIRECT_OWNER_TERMINAL_LIMIT_INVALID")
    with localcontext() as context:
        context.prec=48
        initial_book=state["book"]
        rows=[]
        previous=None
        for raw in years:
            if not isinstance(raw,dict) or set(raw) != {"year","policy"}:
                raise ValueError("DIRECT_OWNER_YEAR_CONTRACT_INVALID")
            year=raw["year"]
            if type(year) is not int or not 1 <= year <= 9999 or previous is not None and year!=previous+1:
                raise ValueError("DIRECT_OWNER_NONCONTIGUOUS_YEARS")
            row,state=_step(state,_flow(raw["policy"]),year=year,shares=shares,cost=cost)
            rows.append(row)
            previous=year
        terminal_flow=_flow(terminal["policy"])
        financing = _terminal_financing(terminal, state, terminal_flow)
        if terminal_flow["commitments_outside_capex"]:
            raise ValueError("DIRECT_OWNER_FINITE_COMMITMENT_IN_TERMINAL")
        # Persistent reinvestment/interest/other spending is kept explicitly.
        terminal_net=(terminal_flow["operating_cash"]+terminal_flow["investment_cash_received"]
            -sum(terminal_flow[key] for key in ("maintenance_capex","growth_capex",
                 "interest_outside_cfo","other_mandatory_cash")))
        if financing is not None:
            # Explicit equal principal cash flows cannot finance any dividend.
            terminal_net += terminal_flow["new_borrowing"] - terminal_flow["debt_repayment"]
        if not 0 <= terminal_net <= terminal_flow["parent_profit"]:
            raise ValueError("DIRECT_OWNER_UNSUPPORTED_STATIONARY_CASH_CONVERSION")
        steady=min(terminal_flow["parent_profit"]*terminal_flow["payout_ratio"],
                   terminal_net,terminal_flow["parent_profit"]*(1-terminal_flow["reserve_ratio"]))
        if steady <= 0:
            raise ValueError("DIRECT_OWNER_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION")
        tail_rows=[]; tail_pv=ZERO
        for elapsed in range(1,limit+1):
            row,next_state=_step(state,terminal_flow,year=previous+elapsed,shares=shares,cost=cost)
            distribution=Decimal(row["conditional_distribution_cny"])
            tail_pv += distribution/(1+cost)**elapsed
            tail_rows.append(row)
            # Cash and capacity cannot decline thereafter; constant external
            # flows and payout imply this identical distribution every year.
            if (distribution == steady and next_state["cash"]>=state["cash"]
                    and next_state["capacity"]>=state["capacity"]):
                tail_value=tail_pv+steady/cost/(1+cost)**elapsed
                break
            state=next_state
        else:
            raise ValueError("DIRECT_OWNER_TERMINAL_NOT_PROVEN_WITHIN_LIMIT")
        dividends=ZERO; residual=initial_book
        for index,row in enumerate(rows,1):
            discount=(1+cost)**index
            dividends+=Decimal(row["conditional_distribution_cny"])/discount
            residual+=Decimal(row["residual_income_cny"])/discount
        closing_book=Decimal(rows[-1]["closing_book_equity_cny"])
        divisor=(1+cost)**len(rows)
        equity=dividends+tail_value/divisor
        ri=residual+(tail_value-closing_book)/divisor
        if abs(equity-ri)>max(Decimal("0.00000001"),abs(equity)*Decimal("1e-36")):
            raise ValueError("DIRECT_OWNER_RI_DISTRIBUTION_CROSSCHECK_FAILED")
        return dict(schema_version=VERSION,annual_rows=rows,terminal_rows=tail_rows,
            terminal_method="exact_stationary_direct_owner_distribution",
            terminal_equity_value_cny=str(tail_value),terminal_steady_distribution_cny=str(steady),
            conditional_equity_value_cny=str(equity),per_share_value=str(equity/shares),
            dividend_crosscheck_equity_value_cny=str(equity),
            residual_income_equity_value_cny=str(ri),crosscheck_difference_cny=str(ri-equity),
            terminal_truncation_error_cny="0",economic_uncertainty="NOT_PROVEN_BY_ARITHMETIC",
            cost_of_equity=str(cost),ordinary_shares=str(shares),
            working_capital_cash_component=None,legal_distribution_capacity_certified=False,
            formal_eligibility=False,action="no_order",
            **({"terminal_financing": financing} if financing is not None else {}))
