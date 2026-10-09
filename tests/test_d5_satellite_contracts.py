from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.domain.portfolio.sleeves import (
    PortfolioSleeve, SharedSleeveBudget,
)
from value_investment_agent.domain.portfolio.sentiment_contracts import (
    SentimentFeatureSnapshot, SentimentSignal, SwingTradePlan, TacticalRiskPolicy,
)


def _budget() -> SharedSleeveBudget:
    return SharedSleeveBudget(
        core_value_budget=D("0.40"), tactical_hotspot_budget=D("0.10"),
        cash_floor=D("0.20"), cross_sleeve_single_stock_cap=D("0.08"),
        cross_sleeve_sector_cap=D("0.25"), policy_scope="SYNTHETIC_POLICY_ONLY",
    )


def _signal() -> SentimentSignal:
    features = SentimentFeatureSnapshot(
        as_of=date(2026, 9, 21),
        available_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
        sector_relative_strength=D("0.2"), market_breadth=D("0.6"),
        turnover_change=D("0.1"), volume_price_confirmation=D("0.5"),
        theme_persistence=D("0.4"), crowding=D("0.3"),
        event_confirmation=D("0.5"), market_regime="synthetic-neutral",
        evidence_refs=("synthetic-feature-receipt",),
    )
    return SentimentSignal(
        symbol="600887", status="ENTRY_REVIEW", features=features,
        issuer_identity_passed=True, financial_sanity_passed=True,
        value_risk_floor_passed=True, liquidity_passed=True,
        event_risk_reviewed=True,
    )


def test_two_sleeves_reserve_one_shared_budget_without_duplicate_cash():
    budget = _budget()
    assert PortfolioSleeve.CORE_VALUE != PortfolioSleeve.TACTICAL_HOTSPOT
    assert budget.core_value_budget + budget.tactical_hotspot_budget + budget.cash_floor == D("0.70")
    with pytest.raises(ValueError, match="exceed one portfolio"):
        replace(budget, tactical_hotspot_budget=D("0.50"))
    with pytest.raises(ValueError, match="explicit policy provenance"):
        replace(budget, policy_scope="INFERRED_FROM_MARKET")


def test_tactical_entry_cannot_bypass_fundamental_or_liquidity_floor():
    signal = _signal()
    assert signal.action == "no_order"
    with pytest.raises(ValueError, match="cannot bypass"):
        replace(signal, value_risk_floor_passed=False)
    with pytest.raises(ValueError, match="cannot bypass"):
        replace(signal, liquidity_passed=False)
    with pytest.raises(ValueError, match="never an order"):
        replace(signal, action="buy")
    with pytest.raises(ValueError, match="production sentiment inputs"):
        replace(signal.features, scope="PRODUCTION")
    local_next_day = replace(
        signal.features, as_of=date(2026, 9, 22),
        available_at=datetime(2026, 9, 21, 16, 30, tzinfo=timezone.utc),
    )
    assert local_next_day.as_of == date(2026, 9, 22)


def test_swing_plan_is_synthetic_tactical_only_and_cannot_change_core_valuation():
    policy = TacticalRiskPolicy(
        budget=_budget(), liquidity_floor=D("1000000"), max_holding_days=20,
    )
    plan = SwingTradePlan(
        signal=_signal(), policy=policy,
        entry_trigger="synthetic close confirmation",
        stop_rule="synthetic invalidation", profit_take_rule="synthetic review",
        time_exit="20 sessions", slippage_model="synthetic cost assumption",
        failure_conditions=("theme weakens",),
    )
    assert plan.sleeve == PortfolioSleeve.TACTICAL_HOTSPOT
    assert plan.action == "no_order"
    assert not hasattr(plan, "bear_value")
    assert not hasattr(plan, "base_value")
    assert not hasattr(plan, "bull_value")
    with pytest.raises(ValueError, match="tactical sleeve"):
        replace(plan, sleeve=PortfolioSleeve.CORE_VALUE)
    with pytest.raises(ValueError, match="cannot place an order"):
        replace(plan, action="buy")
