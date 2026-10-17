"""Feed the confirmed private journal into the existing dual-sleeve risk engine.

WEB-D2 P1. The journal is the only source of confirmed private facts, so this
adapter maps it onto the frozen `dual-sleeve-risk-input-v1` contract and lets
`review_dual_sleeve_risk` decide. It never invents an IPS field, a sleeve
budget, a risk threshold, a security risk attribute or a market value: whatever
the journal does not carry is passed through as ``None`` so the engine answers
with its exact `BLOCKED_PRIVATE_INPUT` gap list instead of a fabricated number.

Two facts are deliberately conservative:

* market value and unrealized PnL stay ``None`` until an admitted quote bridge
  exists, so the engine reports `holding_market_value` as a gap;
* a journal that has no `RECONCILED_CONFIRMED` record projects a
  `PENDING_RECONCILIATION` snapshot, so the engine reports `reconciliation`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from ...domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
from ...portfolio_contracts import (
    NAMESPACE_ACTUAL,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_PENDING,
    RISK_UNKNOWN,
    RISK_TOLERANCES,
    SCHEMA_VERSION,
    PortfolioHolding,
    PortfolioSnapshot,
    portfolio_snapshot_from_payload,
)
from .private_portfolio_service import (
    PrivateJournal,
    PrivatePortfolioService,
    ReplayedPortfolio,
    reconciliation_state,
)

RISK_INPUT_SCHEMA = "dual-sleeve-risk-input-v1"
PRICE_ADMISSION_REASON = "尚未接入经核验的当前行情，无法计算市值、浮动盈亏与仓位权重"
_POLICY_AMOUNT_FIELDS = (
    "investable_assets_cny",
    "minimum_cash_cny",
    "emergency_cash_cny",
    "liquidity_needs_cny",
    "max_single_security_pct",
    "max_single_industry_pct",
    "max_cyclical_exposure_pct",
    "dividend_income_goal_cny",
)


def _evidence(replayed: ReplayedPortfolio) -> dict[str, str]:
    state = replayed.state
    if state.confirmation_evidence:
        return dict(state.confirmation_evidence)
    if state.baseline.evidence_refs:
        return dict(state.baseline.evidence_refs[0])
    return {"id": f"private-journal-{state.baseline.account_scope}", "kind": "user_confirmation"}


def _policy_payload(replayed: ReplayedPortfolio) -> dict[str, Any]:
    """Map the journal's confirmed IPS subset onto the frozen policy contract."""
    state = replayed.state
    stored = dict(replayed.policy)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": f"private-journal:{state.baseline.account_scope}",
        "policy_version": stored.get("_record_sha256") or f"v{state.version}",
        "as_of": stored.get("effective_date") or state.baseline.as_of.isoformat(),
        "confirmation_status": "HUMAN_CONFIRMED",
        "confirmed_at": stored.get("_confirmed_at") or state.baseline.available_at.isoformat(),
        "account_scope": state.baseline.account_scope,
    }
    for field in _POLICY_AMOUNT_FIELDS:
        payload[field] = stored.get(field)
    payload["time_horizon_years"] = stored.get("time_horizon_years")
    tolerance = stored.get("risk_tolerance")
    payload["risk_tolerance"] = tolerance if isinstance(tolerance, str) and tolerance in RISK_TOLERANCES else RISK_UNKNOWN
    payload["concentration_allowed"] = stored.get("concentration_allowed")
    payload["tax_regime"] = stored.get("tax_regime")
    payload["restrictions"] = list(stored.get("restrictions") or ["no_order"])
    payload["evidence_refs"] = [{"id": stored["_record_sha256"], "kind": "user_confirmation"}] if stored.get("_record_sha256") else [_evidence(replayed)]
    payload["sensitivity"] = "PRIVATE_USER_CONFIRMED"
    payload["action"] = "no_order"
    return payload


def _holdings(replayed: ReplayedPortfolio, evidence: dict[str, str]) -> tuple[PortfolioHolding, ...]:
    grouped: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for lot in replayed.state.lots:
        key = (lot.symbol, lot.exchange)
        quantity, cost = grouped.get(key, (Decimal(0), Decimal(0)))
        grouped[key] = (quantity + lot.quantity, cost + lot.cost_cny)
    return tuple(
        PortfolioHolding(symbol, exchange, quantity, cost, None,
                         QUANTITY_HUMAN_CONFIRMED, False, (evidence,))
        for (symbol, exchange), (quantity, cost) in sorted(grouped.items())
    )


def _snapshot_matches_state(snapshot: PortfolioSnapshot, replayed: ReplayedPortfolio) -> bool:
    """The stored snapshot may only be reused while it equals the confirmed state."""
    expected: dict[str, Decimal] = {}
    for lot in replayed.state.lots:
        expected[lot.symbol] = expected.get(lot.symbol, Decimal(0)) + lot.quantity
    actual = {holding.symbol: holding.quantity for holding in snapshot.holdings}
    return snapshot.cash_cny == replayed.state.cash_cny and actual == expected


def _snapshot_payload(replayed: ReplayedPortfolio, prices=None) -> dict[str, Any]:
    """Use the stored reconciliation only while it still matches the ledger.

    WEB-D3 P0.1: after a newer ``FILL_CONFIRMED`` the stored snapshot is
    superseded. Feeding it to the risk engine would describe a portfolio that no
    longer exists, so a superseded or mismatched snapshot is projected afresh
    from the confirmed state and reported as pending reconciliation.
    """
    stored = replayed.snapshot
    if stored is not None and replayed.snapshot_version == replayed.state.version:
        candidate = portfolio_snapshot_from_payload(stored)
        if _snapshot_matches_state(candidate, replayed):
            payload = candidate.as_policy()
            return _mark_snapshot(payload, prices or {}, replayed.policy)
    state = replayed.state
    evidence = _evidence(replayed)
    snapshot = PortfolioSnapshot(
        snapshot_id=f"private-journal-projection-{state.version}",
        snapshot_version=f"v{state.version}",
        as_of=state.last_trade_date,
        available_at=state.confirmed_at or state.baseline.available_at,
        account_scope=state.baseline.account_scope,
        namespace=NAMESPACE_ACTUAL,
        cash_cny=state.cash_cny,
        holdings=_holdings(replayed, evidence),
        reconciliation_status=RECONCILIATION_PENDING,
        reconciled_at=None,
        evidence_refs=(evidence,),
    )
    return _mark_snapshot(snapshot.as_policy(), prices or {}, replayed.policy)


def _mark_snapshot(payload, prices, policy):
    # This is a current projection of unchanged confirmed quantities, not a
    # backdated rewrite of the stored reconciliation artifact.
    dates = [payload["as_of"], *[row["trade_date"] for row in prices.values()]]
    if policy.get("effective_date"):
        dates.append(policy["effective_date"])
    payload["as_of"] = max(dates)
    if policy.get("_confirmed_at"):
        payload["available_at"] = max(datetime.fromisoformat(payload["available_at"]),
            datetime.fromisoformat(policy["_confirmed_at"])).isoformat()
    for holding in payload["holdings"]:
        price = prices.get(holding["symbol"])
        holding["market_value_cny"] = str(Decimal(holding["quantity"]) * Decimal(price["price_cny"])) if price else None
    return payload


def _verified_prices(root, replayed, now):
    """Use existing read-time source verification, never trust an HTTP price flag."""
    try:
        return _load_verified_prices(root, replayed, now)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        # Public evidence failure must not hide confirmed private ledger facts.
        return {}


def _price_permissions(*sources):
    """Carry independent admission evidence; verified observation is not admission."""
    scopes = [source[key] for source in sources for key in
              ("scope", "display_scope", "observation_scope", "reference_price_scope")
              if source.get(key) is not None]
    admissions = [source["price_admitted"] for source in sources if "price_admitted" in source]
    pit = [source["current_pit"] for source in sources if "current_pit" in source]
    display = any("DISPLAY_ONLY" in str(scope) or "HISTORICAL" in str(scope) for scope in scopes)
    admitted = (False if display or False in admissions or False in pit else
                True if any(value is True for value in admissions) else None)
    return {"scope": scopes[0] if scopes else "VERIFIED_CLOSE_ADMISSION_UNKNOWN",
        "observation_scope": next((s["observation_scope"] for s in sources if s.get("observation_scope")), None),
        "current_pit": False if False in pit or display else True if True in pit else None,
        "price_admitted": admitted, "formal_eligibility": False}


def _formal_price_input(row):
    permissions = _price_permissions(row)
    return permissions["price_admitted"] is True


def _load_verified_prices(root, replayed, now):
    if root is None:
        return {}
    from ..product.quote_bridge import execute_quote_bridge_for_symbol
    from ..hotspot.current_registry import load_price_conditions
    needed = {lot.symbol for lot in replayed.state.lots}
    prices = {}
    for symbol in needed:
        try:
            execution = execute_quote_bridge_for_symbol(Path(root), symbol, today=now)
            quote = execution.get("quote") or {}
            if ((execution.get("compatibility") or {}).get("verified_quote", {}).get("eligible") is True
                    and quote.get("quote_date") == quote.get("latest_completed_session")
                    and quote.get("quote_date") and quote.get("display_price")):
                value = Decimal(quote["display_price"])
                if value.is_finite() and value > 0:
                    date.fromisoformat(quote["quote_date"])
                    prices[symbol] = {"price_cny": str(value), "trade_date": quote["quote_date"],
                        "bundle_sha256": quote["bundle_sha256"], **_price_permissions(quote, execution)}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            continue
    if needed - prices.keys():
        try:
            observations = load_price_conditions(Path(root), now=now, research_version=None)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            observations = {"items": []}
        for row in observations["items"]:
            try:
                if row["symbol"] in needed and row["symbol"] not in prices:
                    plan = row["price_action_plan"]
                    value = Decimal(plan["current_reference_price"])
                    if value.is_finite() and value > 0:
                        date.fromisoformat(plan["market_trade_date"])
                        prices[row["symbol"]] = {"price_cny": str(value), "trade_date": plan["market_trade_date"],
                            "case_sha256": plan["case_sha256"],
                            **_price_permissions(plan, plan.get("current_reference_close") or {})}
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                continue
    # Explicit private held refresh stores ordinary immutable cases, without a
    # public membership registry. Reverify them for factual display only.
    if needed - prices.keys():
        from .held_continuity import _case_history
        from ...infrastructure.hotspot.current_price_case import load_current_price_case
        for symbol in sorted(needed - prices.keys()):
            try:
                paths = _case_history(Path(root), symbol)
            except OSError:
                continue
            for path in paths:
                try:
                    case = load_current_price_case(root=Path(root), symbol=symbol,
                        case_path=path, now=now)
                    value = Decimal(case["current_reference_price"])
                    if not value.is_finite() or value <= 0:
                        continue
                    date.fromisoformat(case["market_trade_date"])
                    prices[symbol] = {"price_cny": str(value), "trade_date": case["market_trade_date"],
                        "case_path": case["case_path"], "case_sha256": case["case_sha256"],
                        "bundle_sha256": case["current_reference_close"]["bundle_sha256"],
                        "available_at": case["verified_available_at"],
                        "scope": "VERIFIED_LATEST_COMPLETED_CLOSE_DISPLAY_ONLY",
                        "observation_scope": case.get("observation_scope", "SAME_SESSION_B1"),
                        "current_pit": False, "price_admitted": False, "formal_eligibility": False}
                    break
                except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                    continue
    # Quotes predating a confirmed trade cannot mark the resulting position.
    return {symbol: row for symbol, row in prices.items()
            if date.fromisoformat(row["trade_date"]) >= replayed.state.last_trade_date}


def _verified_attributes(root, replayed, now, *, candidate_symbol=None):
    symbols = {lot.symbol for lot in replayed.state.lots}
    if candidate_symbol is not None:
        symbols.add(candidate_symbol)
    if not symbols:
        return []
    if root is None:
        return None
    from .security_attributes import load_verified_security_attributes
    return load_verified_security_attributes(Path(root), symbols, now=now)


def _allocations_payload(replayed: ReplayedPortfolio, sellable_as_of: date) -> list[dict[str, Any]]:
    """Real per-sleeve share counts straight from the replayed lots."""
    grouped = {}
    for lot in replayed.state.lots:
        row = grouped.setdefault((lot.sleeve, lot.symbol), {
            "sleeve": lot.sleeve,
            "symbol": lot.symbol,
            "quantity": Decimal(0), "sellable_quantity": Decimal(0), "cost_basis_cny": Decimal(0),
            "committed_risk_cny": None,
            "evidence_ref": f"private-lot-{lot.symbol}-{lot.sleeve}",
        })
        row["quantity"] += lot.quantity
        row["cost_basis_cny"] += lot.cost_cny
        if lot.sellable_on <= sellable_as_of:
            row["sellable_quantity"] += lot.quantity
    return [{key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
            for row in grouped.values()]


def _sleeve_policy(replayed):
    policy = replayed.policy
    if not policy.get("_confirmed_at"):
        return None, None, None
    total = Decimal(policy["investable_assets_cny"])
    shared = dict(core_value_budget=str(Decimal(policy["core_value_budget_cny"]) / total),
        tactical_hotspot_budget=str(Decimal(policy["hotspot_budget_cny"]) / total),
        cash_floor=str(Decimal(policy["cash_reserve_cny"]) / total),
        cross_sleeve_single_stock_cap=str(Decimal(policy["max_single_security_pct"]) / 100),
        cross_sleeve_sector_cap=str(Decimal(policy["max_single_industry_pct"]) / 100),
        policy_scope="USER_CONFIRMED", action="no_order")
    sleeves = {}
    for sleeve in ("CORE_VALUE", "HOTSPOT_SATELLITE"):
        stored = policy["sleeves"][sleeve]
        cash = Decimal(stored["cash_cny"])
        for trade in replayed.trades[policy["_state_version"]:]:
            if trade["sleeve"] == sleeve:
                gross = Decimal(trade["quantity"]) * Decimal(trade["price_cny"])
                fee = Decimal(trade["fees_cny"])
                cash += gross - fee if trade["side"] == "SELL" else -gross - fee
        sleeves[sleeve] = dict(cash_cny=str(cash), risk_budget_cny=stored["risk_budget_cny"],
            max_single_security_fraction=shared["cross_sleeve_single_stock_cap"],
            max_industry_fraction=shared["cross_sleeve_sector_cap"],
            max_factor_fraction=str(Decimal(policy["max_factor_pct"]) / 100),
            single_trade_risk_fraction=str(Decimal(policy["hotspot_single_trade_risk_pct"]) / 100) if sleeve == "HOTSPOT_SATELLITE" else None,
            single_security_risk_cny=stored.get("single_security_risk_cny"), realized_pnl_cny=None,
            financing_allowed=policy["financing_allowed"], risk_tools_allowed=policy["risk_tools_allowed"],
            capital_budget_cny=policy["core_value_budget_cny"] if sleeve == "CORE_VALUE" else policy["hotspot_budget_cny"],
            confirmed_at=policy["_confirmed_at"], evidence_ref=policy["_record_sha256"])
    return shared, sleeves, policy["cash_reserve_cny"]


def build_risk_input(
    replayed: ReplayedPortfolio,
    *,
    sellable_as_of: date,
    namespace: str = NAMESPACE_ACTUAL,
    repository_root: Path | None = None,
    generated_at: datetime | None = None,
    hotspot_request: dict[str, Any] | None = None,
    _prices=None,
) -> dict[str, Any]:
    now = generated_at or datetime.now().astimezone()
    prices = _verified_prices(repository_root, replayed, now) if _prices is None else _prices
    # Explicit hypothetical prices belong only to the existing SIMULATED
    # contract; the domain engine still requires allow_synthetic=True. Prices
    # discovered from production providers never inherit that exception.
    synthetic_assumptions = namespace == "SIMULATED" and _prices is not None
    if not synthetic_assumptions:
        prices = {symbol: row for symbol, row in prices.items() if _formal_price_input(row)}
    shared, sleeves, reserve = _sleeve_policy(replayed)
    snapshot = _snapshot_payload(replayed, prices)
    if shared is not None and all(h["market_value_cny"] is not None for h in snapshot["holdings"]):
        equity = Decimal(snapshot["cash_cny"]) + sum(
            (Decimal(h["market_value_cny"]) for h in snapshot["holdings"]), Decimal(0))
        fixed_reserve = Decimal(reserve)
        if equity > 0 and fixed_reserve <= equity:
            # IPS reserves an amount, whereas the frozen engine accepts a fraction
            # of marked equity. Avoid a rounding-only violation at the exact floor.
            floor = fixed_reserve / equity
            if equity * floor > fixed_reserve:
                floor = floor.next_minus()
            shared["cash_floor"] = str(floor)
            core = Decimal(shared["core_value_budget"])
            hotspot = Decimal(shared["tactical_hotspot_budget"])
            remaining = Decimal(1) - floor
            if core + hotspot > remaining:
                # Losses cannot fund all reservations: shrink sleeve caps, never
                # the fixed reserve. Keep their original relative allocation.
                core = remaining * core / (core + hotspot)
                shared["core_value_budget"] = str(core)
                shared["tactical_hotspot_budget"] = str(remaining - core)
    return {
        "schema_version": RISK_INPUT_SCHEMA,
        "action": "no_order",
        "namespace": namespace,
        "portfolio": {
            "policy": _policy_payload(replayed),
            "snapshot": snapshot,
            "action": "no_order",
        },
        "shared_budget": shared,
        "sleeves": sleeves,
        "cash_reserve_cny": reserve,
        "allocations": _allocations_payload(replayed, sellable_as_of),
        "security_attributes": _verified_attributes(repository_root, replayed, now,
            candidate_symbol=hotspot_request["symbol"] if hotspot_request is not None else None),
        "hotspot_request": hotspot_request,
    }


def _account_time_blockers(replayed: ReplayedPortfolio, generated_at: datetime) -> list[str]:
    state = replayed.state
    day = generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    blockers = []
    if max(state.baseline.as_of, state.last_trade_date) > day:
        blockers.append("ACCOUNT_AS_OF_IN_FUTURE")
    if (state.baseline.available_at > generated_at
            or (state.confirmed_at is not None and state.confirmed_at > generated_at)):
        blockers.append("ACCOUNT_FACTS_NOT_YET_AVAILABLE")
    return blockers


def _facts(replayed: ReplayedPortfolio, prices=None, *, generated_at: datetime | None = None) -> dict[str, Any]:
    prices = prices or {}
    time_blockers = _account_time_blockers(replayed, generated_at or datetime.now().astimezone())
    if time_blockers:
        prices = {}
    state = replayed.state
    reconciliation = reconciliation_state(replayed)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for lot in state.lots:
        entry = grouped.setdefault((lot.symbol, lot.exchange), {
            "symbol": lot.symbol, "exchange": lot.exchange,
            "quantity": Decimal(0), "cost_basis_cny": Decimal(0), "sleeves": {},
        })
        entry["quantity"] += lot.quantity
        entry["cost_basis_cny"] += lot.cost_cny
        sleeve = entry["sleeves"].setdefault(lot.sleeve, {"sleeve": lot.sleeve, "quantity": Decimal(0)})
        sleeve["quantity"] += lot.quantity
    positions = []
    for key in sorted(grouped):
        entry = grouped[key]
        quote = prices.get(entry["symbol"])
        market = entry["quantity"] * Decimal(quote["price_cny"]) if quote else None
        positions.append({
            "symbol": entry["symbol"],
            "exchange": entry["exchange"],
            "quantity": str(entry["quantity"]),
            "cost_basis_cny": str(entry["cost_basis_cny"]),
            "market_value_cny": str(market) if market is not None else None,
            "unrealized_pnl_cny": str(market - entry["cost_basis_cny"]) if market is not None else None,
            "quote_binding": quote,
            "sleeves": [{"sleeve": row["sleeve"], "quantity": str(row["quantity"])}
                        for row in sorted(entry["sleeves"].values(), key=lambda item: item["sleeve"])],
        })
    marked = not time_blockers and all(position["market_value_cny"] is not None for position in positions)
    total_market = sum((Decimal(position["market_value_cny"]) for position in positions), Decimal(0)) if marked else None
    return {
        "revision": replayed.revision,
        "account_scope": state.baseline.account_scope,
        "as_of": state.last_trade_date.isoformat(),
        "cash_cny": str(state.cash_cny),
        "realized_pnl_cny": str(state.realized_pnl_cny),
        "cost_basis_total_cny": str(sum((lot.cost_cny for lot in state.lots), Decimal(0))),
        "positions": positions,
        "market_value_total_cny": str(total_market) if marked else None,
        "total_equity_cny": str(state.cash_cny + total_market) if marked else None,
        "unrealized_pnl_total_cny": str(total_market - sum((lot.cost_cny for lot in state.lots), Decimal(0))) if marked else None,
        "current_drawdown_pct": None,
        "confirmed_fill_count": state.version,
        "reconciliation_status": reconciliation["status"],
        "reconciliation": reconciliation,
        "price_status": ("CASH_ONLY_NO_QUOTE_REQUIRED" if not positions else "VERIFIED_LATEST_COMPLETED_CLOSE") if marked else "PRICE_NOT_ADMITTED",
        "price_reason": "账户日期或事实可用时间晚于本次读取时点；保留账本事实，不提供当前估值" if time_blockers else (None if marked else PRICE_ADMISSION_REASON),
        "valuation_blockers": time_blockers,
    }


def review_private_risk_rehearsal(
    journal: PrivateJournal,
    *,
    generated_at: datetime,
    today: date | None = None,
    repository_root: Path | None = None,
    hotspot_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the real engine on real confirmed facts; report the exact gaps."""
    service = PrivatePortfolioService(journal)
    records = service.records()
    if not records:
        return {
            "action": "no_order",
            "status": "NOT_CONNECTED",
            "blockers": ["PRIVATE_PORTFOLIO_NOT_CONNECTED"],
            "engine": None,
            "facts": None,
        }
    replayed = service._replay(records)
    assert replayed is not None
    sellable_as_of = max(replayed.state.last_trade_date, today or datetime.now().astimezone().date())
    prices = _verified_prices(repository_root, replayed, generated_at)
    payload = build_risk_input(replayed, sellable_as_of=sellable_as_of,
        repository_root=repository_root, generated_at=generated_at, hotspot_request=hotspot_request, _prices=prices)
    extra = _account_time_blockers(replayed, generated_at)
    if replayed.policy.get("effective_date") and date.fromisoformat(replayed.policy["effective_date"]) > generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date():
        extra.append("POLICY_NOT_EFFECTIVE")
    if payload["sleeves"] and any(Decimal(row["cash_cny"]) < 0 for row in payload["sleeves"].values()):
        extra.append("SLEEVE_CASH_OVERDRAWN")
    if extra:
        from ...domain.portfolio.dual_sleeve_risk import _blocked
        report = _blocked(NAMESPACE_ACTUAL, extra, generated_at)
    else:
        report = review_dual_sleeve_risk(payload, generated_at=generated_at)
    if any(not _formal_price_input(row) for row in prices.values()):
        report["blockers"] = list(dict.fromkeys([*report["blockers"],
            "DISPLAY_ONLY_HELD_MARK_NOT_FORMAL_PRICE_INPUT"]))
    if payload["security_attributes"] is None:
        report["blockers"] = list(dict.fromkeys([*report["blockers"], "security_attributes.missing"]))
    if reconciliation_state(replayed)["scope"] != "EXTERNAL_ACCOUNT_STATEMENT":
        # Internal arithmetic is useful accounting evidence, but cannot assert
        # that the user's external account has been reconciled.
        report["blockers"] = list(dict.fromkeys([*report["blockers"], "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING"]))
        report["status"] = "BLOCKED_PRIVATE_INPUT"
        report["position_guidance"] = None
        report["trade_eligible"] = False
        if report.get("hotspot_quantity_review"):
            report["hotspot_quantity_review"] = {**report["hotspot_quantity_review"],
                "review_quantity": None, "status": "BLOCKED",
                "blockers": list(dict.fromkeys([*report["hotspot_quantity_review"].get("blockers", []),
                    "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING"]))}
    return {
        "action": "no_order",
        "status": report["status"],
        "blockers": list(report.get("blockers") or ()),
        "engine": report,
        "facts": _facts(replayed, prices, generated_at=generated_at),
        "security_attributes": payload["security_attributes"],
        "policy": {"confirmation_status": "HUMAN_CONFIRMED" if replayed.policy.get("_confirmed_at") else "INCOMPLETE_LEGACY_POLICY",
            "effective_date": replayed.policy.get("effective_date"), "max_drawdown_pct": replayed.policy.get("max_drawdown_pct"),
            "dividend_income_goal_cny": replayed.policy.get("dividend_income_goal_cny"),
            "financing_allowed": replayed.policy.get("financing_allowed")},
    }
