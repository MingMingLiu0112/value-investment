"""Deterministic, long-only virtual-account ledger for research simulations.

This is deliberately independent from a user's broker account.  It accepts
pre-validated daily prices and decision records, creates next-session orders,
and makes a single journal that can be replayed without duplicate fills.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR
from typing import Callable

from .historical_fees import statutory_components, current_sse_components


BUY_ACTIONS = {"proposed_entry", "proposed_add"}
SELL_ACTIONS = {"proposed_reduce", "proposed_exit"}
FeeCalculator = Callable[[str, int, Decimal, date], Decimal]
ORDER_TERMS_VERSION = "next-session-bounded-order-v1"


def _execution_terms(value: dict, submitted_on: date, quantity: int | None) -> dict:
    """Validate frozen order constraints, not the upstream model admission."""
    if not isinstance(value, dict) or value.get("version") != ORDER_TERMS_VERSION:
        raise ValueError("Unknown execution_terms version")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Bounded order requires an explicit positive quantity")
    valid = date.fromisoformat(value["valid_session"])
    liquidity_as_of = date.fromisoformat(value["liquidity_as_of"])
    if valid <= submitted_on or liquidity_as_of > submitted_on:
        raise ValueError("Order validity must follow submission; liquidity cannot use future data")
    if not isinstance(value.get("basis_id"), str) or not value["basis_id"].strip():
        raise ValueError("Bounded order requires its frozen decision basis_id")
    result = {"version": ORDER_TERMS_VERSION, "valid_session": valid.isoformat(),
              "liquidity_as_of": liquidity_as_of.isoformat(), "basis_id": value["basis_id"]}
    for key in ("limit_price", "cash_budget_cny", "liquidity_budget_cny", "slippage_bps"):
        number = Decimal(str(value[key]))
        if not number.is_finite() or number < 0 or (key == "limit_price" and number == 0):
            raise ValueError(f"Invalid bounded-order {key}")
        if key == "slippage_bps" and number >= 10000:
            raise ValueError("slippage_bps must be below 10000")
        result[key] = str(number)
    return result


def _bounded_fill(order: dict, row: dict, opening: Decimal) -> tuple[Decimal, str | None]:
    terms = order["execution_terms"]
    if row.get("execution_ready") is not True:
        return opening, "execution_state_unknown"
    if row["date"] > terms["valid_session"]:
        return opening, "order_expired"
    bounds = [row.get(key) for key in ("price_limit_down", "price_limit_up")]
    if any(value is None for value in bounds):
        return opening, "price_limit_state_unknown"
    lower, upper = (Decimal(str(value)) for value in bounds)
    if not all(value.is_finite() and value > 0 for value in (lower, upper)) or lower >= upper:
        return opening, "price_limit_state_unknown"
    if not lower < opening < upper:
        return opening, "opening_at_or_outside_price_limit"
    direction = Decimal(1) if order["side"] == "buy" else Decimal(-1)
    price = (opening * (1 + direction * Decimal(terms["slippage_bps"]) / 10000)).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING if order["side"] == "buy" else ROUND_FLOOR)
    if not lower < price < upper:
        return price, "slippage_reaches_price_limit"
    if Decimal(order["requested_quantity"]) * price > Decimal(terms["liquidity_budget_cny"]):
        return price, "prior_liquidity_budget_exceeded"
    return price, None


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


@dataclass
class VirtualAccount:
    cash: Decimal = Decimal("1000000.00")
    shares: int = 0
    lots: list[tuple[date, int]] = field(default_factory=list)
    filled_order_ids: set[str] = field(default_factory=set)
    entitlement_shares: dict[str, int] = field(default_factory=dict)
    receivables: Decimal = Decimal("0.00")
    bonus_lots: list[tuple[date, int]] = field(default_factory=list)
    processed_sessions: set[str] = field(default_factory=set)
    last_close: Decimal | None = None
    pending_order: dict | None = None

    def sellable_shares(self, session: date) -> int:
        """A-share T+1: shares acquired today cannot be sold today."""
        if any(not isinstance(acquired, date) or type(quantity) is not int or quantity <= 0
               for acquired, quantity in self.lots):
            raise ValueError("Virtual-account lots require positive integer shares and date acquisition times")
        if any(not isinstance(listing, date) or type(quantity) is not int or quantity <= 0
               for listing, quantity in self.bonus_lots):
            raise ValueError("Virtual-account bonus lots require positive integer shares and listing dates")
        return (sum(quantity for acquired, quantity in self.lots if acquired < session)
                + sum(quantity for listing, quantity in self.bonus_lots if listing <= session))

    def marked_nav(self) -> Decimal:
        if self.last_close is None:
            return money(self.cash + self.receivables)
        return money(self.cash + self.receivables + Decimal(self.shares) * self.last_close)

    def to_dict(self) -> dict:
        """Return an explicit, JSON-safe snapshot for the research account."""
        return {
            "cash": str(self.cash), "shares": self.shares,
            "lots": [{"acquired": acquired.isoformat(), "shares": quantity} for acquired, quantity in self.lots],
            "bonus_lots": [{"listing": listing.isoformat(), "shares": quantity} for listing, quantity in self.bonus_lots],
            "filled_order_ids": sorted(self.filled_order_ids), "entitlement_shares": self.entitlement_shares,
            "receivables": str(self.receivables), "processed_sessions": sorted(self.processed_sessions),
            "last_close": str(self.last_close) if self.last_close is not None else None,
            "pending_order": self.pending_order,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "VirtualAccount":
        if not isinstance(value, dict):
            raise ValueError("Virtual-account snapshot must be an object")
        account = cls(cash=Decimal(value["cash"]), shares=value["shares"],
                      receivables=Decimal(value["receivables"]), pending_order=value.get("pending_order"))
        if type(account.shares) is not int or account.shares < 0:
            raise ValueError("Virtual-account snapshot has invalid shares")
        account.lots = [(date.fromisoformat(row["acquired"]), row["shares"]) for row in value["lots"]]
        account.bonus_lots = [(date.fromisoformat(row["listing"]), row["shares"]) for row in value["bonus_lots"]]
        account.filled_order_ids = set(value["filled_order_ids"])
        account.entitlement_shares = dict(value["entitlement_shares"])
        account.processed_sessions = set(value["processed_sessions"])
        account.last_close = Decimal(value["last_close"]) if value.get("last_close") is not None else None
        account.sellable_shares(date.max)
        if account.cash < 0 or account.receivables < 0:
            raise ValueError("Virtual-account snapshot has negative cash or receivable")
        return account


def fee(side: str, quantity: int, price: Decimal,
        commission_rate: Decimal = Decimal("0.0003"),
        minimum_commission: Decimal = Decimal("5"),
        stamp_duty_rate: Decimal = Decimal("0.0005")) -> Decimal:
    if side not in {"buy", "sell"} or quantity <= 0 or price <= 0:
        raise ValueError("Positive price, quantity and known side are required")
    turnover = Decimal(quantity) * price
    commission = max(turnover * commission_rate, minimum_commission)
    stamp = turnover * stamp_duty_rate if side == "sell" else Decimal(0)
    return money(commission + stamp)


def dated_research_fee(side: str, quantity: int, price: Decimal, traded_on: date, *,
                       exchange: str = "SSE", commission_rate: Decimal = Decimal("0.0003"),
                       minimum_commission: Decimal = Decimal("5")) -> Decimal:
    """Return an explicit post-2015-08 A-share research fee scenario.

    The early-SSE transfer basis depends on evidence not represented by this
    virtual-account API, so it is rejected rather than silently assumed.
    """
    if exchange == "SSE" and traded_on < date(2015, 8, 1):
        raise ValueError("Early SSE research fee requires face-value and broker-retained-fee evidence")
    turnover = Decimal(quantity) * price
    statutory = statutory_components(traded_on, exchange, side, turnover)
    commission = max(turnover * commission_rate, minimum_commission)
    return money(statutory["statutory_subtotal_unrounded_cny"] + commission)


def board_lot_quantity(budget: Decimal, price: Decimal, fee_rate: Decimal) -> int:
    """Return the largest SSE/SZSE 100-share purchase that fits cash."""
    if budget <= 0 or price <= 0:
        return 0
    gross = (budget / (price * (Decimal(1) + fee_rate))).to_integral_value(rounding=ROUND_DOWN)
    return int(gross // 100 * 100)


def current_sse_research_fee(side: str, quantity: int, price: Decimal, traded_on: date, *,
                             commission_rate: Decimal = Decimal('0.0003'),
                             minimum_commission: Decimal = Decimal('5')) -> Decimal:
    """Reviewed-date SSE scenario, with exchange charges already in commission."""
    if type(quantity) is not int or quantity <= 0 or not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise ValueError('Current fee requires positive integer shares and a finite Decimal price')
    for amount in (commission_rate, minimum_commission):
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            raise ValueError('Commission assumptions must be finite nonnegative Decimals')
    turnover = Decimal(quantity) * price
    statutory = current_sse_components(traded_on, side, turnover)
    return money(statutory['statutory_subtotal_unrounded_cny']
                 + max(turnover * commission_rate, minimum_commission))


def _validate_sessions(sessions: list[dict]) -> None:
    previous: date | None = None
    for row in sessions:
        current = date.fromisoformat(row["date"])
        if previous is not None and current <= previous:
            raise ValueError("Sessions must be strictly increasing")
        previous = current
        close = Decimal(str(row["close"]))
        if not close.is_finite() or close <= 0:
            raise ValueError("Positive close price is required")
        # A close-only observation is useful for recording a decision, but it
        # can never support an opening execution.  Keep the missing opening
        # price explicit instead of silently substituting the close.
        if row.get("open") is not None:
            opening = Decimal(str(row["open"]))
            if not opening.is_finite() or opening <= 0:
                raise ValueError("Positive open price is required when supplied")
        elif row.get("execution_ready") is not False:
            raise ValueError("A close-only session must explicitly reject execution")
        if "execution_ready" in row and row["execution_ready"] is not None and type(row["execution_ready"]) is not bool:
            raise ValueError("execution_ready must be a boolean or explicit unknown")


def _validate_cash_events(cash_events: list[dict], sessions: list[dict]) -> dict[str, list[dict]]:
    available_dates = {row["date"] for row in sessions}
    by_date: dict[str, list[dict]] = {}
    event_ids: set[str] = set()
    for event in cash_events:
        required = ("event_id", "record_date", "ex_date", "payment_date", "cash_per_share")
        if any(not isinstance(event.get(field), str) or not event[field] for field in required):
            raise ValueError("Cash event requires ID, record/ex/payment dates and cash per share")
        if event["event_id"] in event_ids:
            raise ValueError("Cash event IDs must be unique")
        event_ids.add(event["event_id"])
        if not (event["record_date"] < event["ex_date"] <= event["payment_date"]):
            raise ValueError("Cash event dates must be ordered record < ex <= payment")
        if not {event["record_date"], event["ex_date"], event["payment_date"]} <= available_dates:
            raise ValueError("Cash event dates must all exist in the supplied price sessions")
        if Decimal(event["cash_per_share"]) < 0:
            raise ValueError("Cash distribution cannot be negative")
        bonus = event.get("bonus_shares_per_share")
        if bonus is not None:
            if Decimal(str(bonus)) <= 0 or not isinstance(event.get("bonus_listing_date"), str):
                raise ValueError("Bonus share distribution requires positive ratio and listing date")
            if not (event["ex_date"] <= event["bonus_listing_date"] and event["bonus_listing_date"] in available_dates):
                raise ValueError("Bonus listing date must be a supplied session on/after ex-date")
        # Ex-date and payment date are often the same. Index the event only
        # once for that session; replay below deliberately handles both steps.
        for key in {event["record_date"], event["ex_date"], event["payment_date"]}:
            by_date.setdefault(key, []).append(event)
    return by_date


def _request_from_decision(decision: dict, account: VirtualAccount, session: date) -> dict | None:
    state = decision.get("state")
    if state not in BUY_ACTIONS | SELL_ACTIONS:
        return None
    order_id = decision.get("decision_id")
    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("Trade proposal requires a stable decision_id")
    if order_id in account.filled_order_ids:
        return None
    requested = decision.get("quantity")
    if requested is not None and (type(requested) is not int or requested <= 0):
        raise ValueError("Requested quantity must be a positive integer")
    order = {"order_id": order_id, "side": "buy" if state in BUY_ACTIONS else "sell",
             "requested_quantity": requested, "submitted_on": session.isoformat(),
             "decision_state": state}
    if "execution_terms" in decision:
        order["execution_terms"] = _execution_terms(decision["execution_terms"], session, requested)
    return order


def replay(sessions: list[dict], decisions: dict[str, dict], account: VirtualAccount | None = None,
           commission_rate: Decimal = Decimal("0.0003"), cash_events: list[dict] | None = None,
           fee_calculator: FeeCalculator | None = None,
           decision_provider=None) -> tuple[VirtualAccount, list[dict]]:
    """Replay decisions on the next available session open and return journal rows.

    ``decisions`` is keyed by date.  A proposal made at a session close becomes
    eligible only at the following supplied session open.  Calling replay again
    with the returned account does not refill an already-filled order ID.
    """
    _validate_sessions(sessions)
    if decision_provider is not None and decisions:
        raise ValueError("Choose dated decisions or a close-time decision provider, not both")
    events_by_date = _validate_cash_events(cash_events or [], sessions)
    account = account or VirtualAccount()
    # Check restored constraints before any cash event or execution can mutate state.
    if account.pending_order is not None and "execution_terms" in account.pending_order:
        _execution_terms(account.pending_order["execution_terms"],
                         date.fromisoformat(account.pending_order["submitted_on"]),
                         account.pending_order["requested_quantity"])
    for decision_day, decision in decisions.items():
        if "execution_terms" in decision:
            _execution_terms(decision["execution_terms"], date.fromisoformat(decision_day), decision.get("quantity"))
    journal: list[dict] = []
    for session_row in sessions:
        session = date.fromisoformat(session_row["date"])
        if session.isoformat() in account.processed_sessions:
            continue
        opening_price = (Decimal(str(session_row["open"]))
                         if session_row.get("open") is not None else None)
        fill_price = opening_price
        close = Decimal(str(session_row["close"]))
        def execution_fee(side: str, quantity: int) -> Decimal:
            charge = (fee_calculator(side, quantity, fill_price, session)
                      if fee_calculator else fee(side, quantity, fill_price, commission_rate))
            if not isinstance(charge, Decimal) or not charge.is_finite() or charge < 0:
                raise ValueError("Fee calculator requires a finite nonnegative Decimal")
            return money(charge)
        distribution_events: list[dict] = []
        for event in events_by_date.get(session.isoformat(), []):
            event_id = event["event_id"]
            if session.isoformat() == event["ex_date"]:
                if event_id not in account.entitlement_shares:
                    raise ValueError("Cash event lacks a recorded entitlement snapshot")
                amount = money(Decimal(account.entitlement_shares[event_id]) * Decimal(event["cash_per_share"]))
                account.receivables = money(account.receivables + amount)
                distribution_events.append({"event_id": event_id, "kind": "accrual", "amount_cny": str(amount)})
                if event.get("bonus_shares_per_share") is not None:
                    added = Decimal(account.entitlement_shares[event_id]) * Decimal(str(event["bonus_shares_per_share"]))
                    if added != added.to_integral_value():
                        raise ValueError("Fractional bonus-share entitlement requires a separate allocation rule")
                    if added:
                        account.shares += int(added)
                        account.bonus_lots.append((date.fromisoformat(event["bonus_listing_date"]), int(added)))
                        distribution_events.append({"event_id": event_id, "kind": "bonus_credit", "shares": int(added),
                                                    "sellable_on": event["bonus_listing_date"]})
            if session.isoformat() == event["payment_date"]:
                if event_id not in account.entitlement_shares:
                    raise ValueError("Cash payment lacks a recorded entitlement snapshot")
                amount = money(Decimal(account.entitlement_shares[event_id]) * Decimal(event["cash_per_share"]))
                if account.receivables < amount:
                    raise ValueError("Cash payment exceeds recorded receivable")
                account.receivables = money(account.receivables - amount)
                account.cash = money(account.cash + amount)
                distribution_events.append({"event_id": event_id, "kind": "payment", "amount_cny": str(amount)})
        fill = None
        rejected = None
        order = account.pending_order
        terms = order.get("execution_terms") if order is not None else None
        deferred = bool(terms and session.isoformat() < terms["valid_session"])
        if order is not None and not deferred:
            quantity = order["requested_quantity"]
            status = session_row.get("execution_status", "")
            if terms and session.isoformat() > terms["valid_session"]:
                rejected = "order_expired"
            elif opening_price is None:
                rejected = "execution_state_unknown"
            elif "next_open_fill_eligible" in session_row and session_row["next_open_fill_eligible"] is not True:
                rejected = "session_not_executable"
            elif status.startswith("blocked"):
                rejected = "session_not_executable"
            elif "incomplete" in status:
                rejected = "execution_state_unknown"
            elif decision_provider is not None and "execution_ready" not in session_row:
                rejected = "execution_state_unknown"
            elif "execution_ready" in session_row and session_row["execution_ready"] is not True:
                rejected = "execution_state_unknown" if session_row["execution_ready"] is None else "session_not_executable"
            if rejected is None and terms:
                fill_price, rejected = _bounded_fill(order, session_row, opening_price)
            if rejected is None and order["side"] == "buy":
                quantity = quantity or board_lot_quantity(account.cash, fill_price, commission_rate)
                cost = (Decimal(quantity) * fill_price + execution_fee("buy", quantity)
                        if quantity > 0 else Decimal(0))
                if quantity <= 0 or quantity % 100 or cost > account.cash:
                    rejected = "insufficient_cash_or_board_lot"
                elif terms and cost / quantity > Decimal(terms["limit_price"]):
                    rejected = "buy_all_in_limit_exceeded"
                elif terms and cost > Decimal(terms["cash_budget_cny"]):
                    rejected = "reserved_cash_budget_exceeded"
                else:
                    account.cash = money(account.cash - cost)
                    account.shares += quantity
                    account.lots.append((session, quantity))
            elif rejected is None:
                if order["decision_state"] == "proposed_reduce" and quantity is None:
                    rejected = "reduce_quantity_required"
                else:
                    quantity = quantity or account.sellable_shares(session)
                if rejected is None and (quantity <= 0 or quantity > account.sellable_shares(session)):
                    rejected = "insufficient_t1_sellable_shares"
                if rejected is None:
                    proceeds = Decimal(quantity) * fill_price - execution_fee("sell", quantity)
                    if terms and proceeds / quantity < Decimal(terms["limit_price"]):
                        rejected = "sell_net_limit_not_met"
                if rejected is None:
                    account.cash = money(account.cash + proceeds)
                    account.shares -= quantity
                    remaining = quantity
                    kept: list[tuple[date, int]] = []
                    for acquired, lot_quantity in account.lots:
                        if acquired >= session:
                            kept.append((acquired, lot_quantity))
                            continue
                        sold = min(remaining, lot_quantity)
                        remaining -= sold
                        if lot_quantity > sold:
                            kept.append((acquired, lot_quantity - sold))
                    account.lots = kept
                    available_bonus, locked_bonus = [], []
                    for listing, lot_quantity in account.bonus_lots:
                        if listing <= session:
                            sold = min(remaining, lot_quantity)
                            remaining -= sold
                            if lot_quantity > sold:
                                available_bonus.append((listing, lot_quantity - sold))
                        else:
                            locked_bonus.append((listing, lot_quantity))
                    if remaining:
                        raise ValueError("Sellable-share inventory does not reconcile")
                    account.bonus_lots = available_bonus + locked_bonus
            if rejected:
                account.filled_order_ids.add(order["order_id"])
            else:
                account.filled_order_ids.add(order["order_id"])
                fill = {**order, "filled_on": session.isoformat(), "quantity": quantity,
                        "price": str(fill_price), "fee_cny": str(execution_fee(order["side"], quantity))}
                if terms:
                    fill["execution_scope"] = "daily_simulation_assumption_not_real_fill"
            account.pending_order = None

        # Record-date entitlement follows that session's executions, at close.
        for event in events_by_date.get(session.isoformat(), []):
            if session.isoformat() == event["record_date"]:
                account.entitlement_shares[event["event_id"]] = account.shares
                distribution_events.append({"event_id": event["event_id"], "kind": "record", "shares": account.shares})

        account.last_close = close
        if decision_provider is not None:
            # Detached state includes today's fills, distributions and close mark.
            # The provider cannot change the live ledger through these arguments.
            from copy import deepcopy
            decision = decision_provider(deepcopy(session_row), deepcopy(account.to_dict()))
        else:
            decision = decisions.get(session.isoformat())
        created = _request_from_decision(decision, account, session) if decision else None
        if created is not None:
            if account.pending_order is None:
                account.pending_order = created
            else:
                raise ValueError("Only one pending virtual order is supported")
        account.last_close = close
        account.processed_sessions.add(session.isoformat())
        journal.append({"date": session.isoformat(), "open": (str(opening_price) if opening_price is not None else None), "close": str(close),
                        "decision": decision.get("state") if decision else "no_decision",
                        "decision_details": decision,
                        "created_order": created, "fill": fill, "rejected_order_reason": rejected,
                        "rejected_order": order if rejected else None,
                        "deferred_order_id": order["order_id"] if deferred else None,
                        "execution_state_scope": "explicit_session_gate" if "execution_ready" in session_row or "execution_status" in session_row else "missing_dynamic_execution_evidence" if decision_provider is not None else "legacy_prevalidated_prices_only",
                        "execution_state_reason": session_row.get("execution_reason") or session_row.get("execution_limitation"),
                        "pending_order_id": account.pending_order["order_id"] if account.pending_order else None,
                        "cash_cny": str(account.cash), "holding_shares": account.shares,
                        "sellable_shares": account.sellable_shares(session),
                        "receivable_cny": str(account.receivables), "cash_events": distribution_events,
                        "nav_cny": str(money(account.cash + account.receivables + Decimal(account.shares) * close))})
    return account, journal
