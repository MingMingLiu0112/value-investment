from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.investment_decision import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    STATUS_HOLD,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_MANUAL_ADD_REVIEW,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_MANUAL_EXIT_REVIEW,
    STATUS_MANUAL_REDUCE_REVIEW,
    STATUS_WATCH,
    STATUS_WAIT_FOR_PRICE,
)
from value_investment_agent.portfolio_contracts import (
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_RECONCILED,
    RISK_BALANCED,
    InvestorPolicyStatement,
    PortfolioHolding,
    PortfolioInputBundle,
    PortfolioSnapshot,
)
from value_investment_agent.portfolio_risk import (
    LIQUIDITY_LIQUID,
    LIQUIDITY_RESTRICTED,
)
from value_investment_agent.position_guidance import (
    BUDGET_CONSTRAINED,
    BUDGET_EXHAUSTED,
    CONFIDENCE_HIGH as POSITION_CONFIDENCE_HIGH,
    INTENT_ADD,
    INTENT_BUY,
    INTENT_HOLD,
    LINE_ELIGIBLE,
    LINE_REVIEW_REQUIRED,
    LINE_WAIT,
    NAMESPACE_ACTUAL as POSITION_NAMESPACE_ACTUAL,
    STATUS_BUDGET_CONFLICT,
    STATUS_INCOMPLETE,
    STATUS_READY,
    STATUS_REVIEW_REQUIRED,
    TIER_MAX,
    TIER_NORMAL,
    TIER_STARTER,
    PositionCandidateInput,
    PositionTierPolicy,
    build_position_guidance,
)
from value_investment_agent.price_attractiveness import STATUS_RESEARCH_ATTRACTIVE


AS_OF = date(2026, 9, 22)
CONFIRMED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
GENERATED_AT = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)


def _policy(**changes) -> InvestorPolicyStatement:
    payload = {
        "policy_id": "position-policy-v1",
        "policy_version": "20260922-v1",
        "as_of": AS_OF,
        "confirmation_status": CONFIRMATION_HUMAN,
        "confirmed_at": CONFIRMED_AT,
        "account_scope": "个人A股长期账户",
        "investable_assets_cny": Decimal("1000000"),
        "minimum_cash_cny": Decimal("100000"),
        "emergency_cash_cny": Decimal("150000"),
        "liquidity_needs_cny": Decimal("50000"),
        "time_horizon_years": Decimal("10"),
        "max_single_security_pct": Decimal("15"),
        "max_single_industry_pct": Decimal("30"),
        "max_cyclical_exposure_pct": Decimal("25"),
        "dividend_income_goal_cny": Decimal("30000"),
        "risk_tolerance": RISK_BALANCED,
        "concentration_allowed": False,
        "tax_regime": "中国大陆个人证券账户",
        "restrictions": ("no_order", "no_leverage"),
        "evidence_refs": ({"id": "position-policy-confirmation"},),
    }
    payload.update(changes)
    return InvestorPolicyStatement(**payload)


def _holding(symbol="600519", market_value=Decimal("160000")) -> PortfolioHolding:
    return PortfolioHolding(
        symbol=symbol,
        exchange="SSE",
        quantity=Decimal("100"),
        cost_basis_cny=Decimal("150000"),
        market_value_cny=market_value,
        quantity_source=QUANTITY_HUMAN_CONFIRMED,
        corporate_action_adjusted=True,
        evidence_refs=({"id": f"holding-{symbol}"},),
    )


def _snapshot(
    *,
    namespace: str = NAMESPACE_ACTUAL,
    cash: Decimal = Decimal("200000"),
    holdings=(_holding(),),
    **changes,
) -> PortfolioSnapshot:
    payload = {
        "snapshot_id": "position-snapshot-v1",
        "snapshot_version": "20260922-v1",
        "as_of": AS_OF,
        "available_at": AVAILABLE_AT,
        "account_scope": "个人A股长期账户",
        "namespace": namespace,
        "cash_cny": cash,
        "holdings": holdings,
        "reconciliation_status": RECONCILIATION_RECONCILED,
        "reconciled_at": CONFIRMED_AT,
        "evidence_refs": ({"id": "position-broker-statement"},),
    }
    payload.update(changes)
    return PortfolioSnapshot(**payload)


def _tier_policy() -> PositionTierPolicy:
    return PositionTierPolicy(
        policy_id="position-tier-policy-v1",
        policy_version="20260922-v1",
        as_of=AS_OF,
        confirmation_status=CONFIRMATION_HUMAN,
        confirmed_at=CONFIRMED_AT,
        starter_cap_pct=Decimal("5"),
        normal_cap_pct=Decimal("10"),
        max_cap_pct=Decimal("15"),
        evidence_refs=({"id": "tier-policy-confirmation"},),
    )


def _candidate(
    *,
    symbol="600519",
    intent=INTENT_HOLD,
    confidence=POSITION_CONFIDENCE_HIGH,
    liquidity=LIQUIDITY_LIQUID,
    research=True,
    approval=True,
    event=True,
    model=True,
    price=True,
    breakers=(),
    industry="白酒",
    cyclical=False,
    **changes,
) -> PositionCandidateInput:
    payload = {
        "symbol": symbol,
        "review_intent": intent,
        "confidence": confidence,
        "research_gate_passed": research,
        "human_approval_valid": approval,
        "event_review_clean": event,
        "model_valid": model,
        "price_assessable": price,
        "thesis_breakers": breakers,
        "liquidity_profile": liquidity,
        "industry": industry,
        "cyclical": cyclical,
        "evidence_refs": ({"id": f"candidate-{symbol}"},),
    }
    payload.update(changes)
    return PositionCandidateInput(**payload)


def _decision_bound_candidate(
    *,
    status: str,
    intent: str,
    symbol: str = "600519",
) -> PositionCandidateInput:
    return _candidate(
        symbol=symbol,
        intent=intent,
        decision_binding_required=True,
        decision_review_id=f"{symbol}-decision-review-v1",
        decision_review_sha256="b" * 64,
        decision_status=status,
        decision_as_of=AS_OF,
        price_attractiveness_status=STATUS_RESEARCH_ATTRACTIVE,
    )


def _result(
    *,
    bundle=None,
    candidates=None,
    tier_policy=None,
    namespace=POSITION_NAMESPACE_ACTUAL,
    snapshot=None,
    **changes,
):
    payload = {
        "bundle": bundle
        or PortfolioInputBundle(policy=_policy(), snapshot=snapshot or _snapshot()),
        "candidates": candidates
        if candidates is not None
        else {"600519": _candidate()},
        "tier_policy": tier_policy or _tier_policy(),
        "as_of": AS_OF,
        "generated_at": GENERATED_AT,
        "assessment_id": "position-guidance-v1",
        "assessment_namespace": namespace,
    }
    payload.update(changes)
    return build_position_guidance(**payload)


def test_eligible_candidate_uses_confidence_specific_tier():
    result = _result(snapshot=_snapshot(cash=Decimal("300000")))
    assert result.status == STATUS_READY
    line = result.lines()[0]
    assert line.status == LINE_ELIGIBLE
    assert line.tier == TIER_MAX
    assert line.ceiling_pct == Decimal("0.15")

    medium = _result(
        snapshot=_snapshot(cash=Decimal("300000")),
        candidates={"600519": _candidate(confidence=CONFIDENCE_MEDIUM)},
    ).lines()[0]
    low = _result(
        snapshot=_snapshot(cash=Decimal("300000")),
        candidates={"600519": _candidate(confidence=CONFIDENCE_LOW)},
    ).lines()[0]
    assert medium.tier == TIER_NORMAL
    assert low.tier == TIER_STARTER
    assert low.ceiling_pct == Decimal("0.05")


@pytest.mark.parametrize(
    ("decision_status", "intent"),
    [
        (STATUS_MANUAL_BUY_REVIEW, INTENT_BUY),
        (STATUS_MANUAL_ADD_REVIEW, INTENT_ADD),
    ],
)
def test_only_valid_positive_decision_reviews_create_new_buy_capacity(
    decision_status: str,
    intent: str,
):
    candidate = _decision_bound_candidate(status=decision_status, intent=intent)

    assert candidate.has_valid_decision_binding() is True
    assert candidate.allows_new_buy_capacity() is True


@pytest.mark.parametrize(
    "decision_status",
    [
        STATUS_INSUFFICIENT_RESEARCH,
        STATUS_WATCH,
        STATUS_WAIT_FOR_PRICE,
        STATUS_HOLD,
        STATUS_MANUAL_REDUCE_REVIEW,
        STATUS_MANUAL_EXIT_REVIEW,
    ],
)
def test_non_positive_decision_statuses_never_create_new_buy_capacity(
    decision_status: str,
):
    candidate = _decision_bound_candidate(
        status=decision_status,
        intent=INTENT_BUY,
    )

    assert candidate.allows_new_buy_capacity() is False


def test_hold_decision_never_creates_new_buy_capacity():
    candidate = _decision_bound_candidate(status=STATUS_HOLD, intent=INTENT_HOLD)

    assert candidate.allows_new_buy_capacity() is False


def test_incomplete_decision_binding_fails_closed():
    with pytest.raises(ValueError, match="complete M3 binding"):
        _candidate(decision_binding_required=True)

    with pytest.raises(ValueError, match="SHA-256 hex"):
        _candidate(
            decision_binding_required=True,
            decision_review_id="600519-decision-review-v1",
            decision_review_sha256="not-a-hash",
            decision_status=STATUS_MANUAL_BUY_REVIEW,
            decision_as_of=AS_OF,
            price_attractiveness_status=STATUS_RESEARCH_ATTRACTIVE,
        )


def test_missing_precondition_waits_without_a_ceiling():
    candidate = _candidate(research=False)
    line = _result(candidates={"600519": candidate}).lines()[0]

    assert line.status == LINE_WAIT
    assert line.tier == "NONE"
    assert line.ceiling_pct is None
    assert line.remaining_ceiling_pct is None
    assert line.budget_status == "NOT_APPLICABLE"


def test_known_thesis_breaker_never_produces_positive_capacity():
    candidate = _candidate(breakers=("distribution_cut",))
    result = _result(candidates={"600519": candidate})

    assert result.lines()[0].status == LINE_WAIT
    assert result.lines()[0].tier == "NONE"
    assert result.lines()[0].blockers == ("distribution_cut",)


def test_shared_budget_is_conserved_instead_of_allocated_to_each_candidate():
    candidates = {
        "600519": _candidate(symbol="600519"),
        "000333": _candidate(
            symbol="000333",
            intent=INTENT_BUY,
            industry="耐用制造",
        ),
        "601088": _candidate(
            symbol="601088",
            intent=INTENT_BUY,
            industry="能源",
            cyclical=True,
        ),
    }
    result = _result(
        snapshot=_snapshot(cash=Decimal("300000")),
        candidates=candidates,
    )
    lines = {line.symbol: line for line in result.lines()}

    assert result.status == STATUS_BUDGET_CONFLICT
    assert lines["000333"].budget_status == BUDGET_CONSTRAINED
    assert lines["601088"].budget_status == BUDGET_CONSTRAINED
    assert "shared_budget_constrains_ceiling" in lines["000333"].stop_add_conditions
    assert "target_weight" not in json.dumps(result.as_policy(), ensure_ascii=False)
    assert "position_size" not in json.dumps(result.as_policy(), ensure_ascii=False)


def test_existing_exposure_at_ceiling_stops_adds():
    result = _result(
        snapshot=_snapshot(
            cash=Decimal("100000"),
            holdings=(_holding(market_value=Decimal("150000")),),
        ),
        candidates={"600519": _candidate(intent=INTENT_ADD)},
    )
    line = result.lines()[0]

    assert "current_exposure_at_ceiling" in line.stop_add_conditions
    assert line.remaining_ceiling_pct == Decimal("0")


def test_industry_and_cyclical_budgets_can_stop_adds_without_selling():
    result = _result(
        snapshot=_snapshot(
            cash=Decimal("100000"),
            holdings=(_holding(market_value=Decimal("300000")),),
        ),
        candidates={"600519": _candidate(industry="能源", cyclical=True)},
    )
    line = result.lines()[0]

    assert "industry_budget_at_limit" in line.stop_add_conditions
    assert "cyclical_budget_at_limit" in line.stop_add_conditions
    assert line.status == LINE_ELIGIBLE


def test_restricted_liquidity_requires_review_and_has_no_numeric_headroom():
    result = _result(
        candidates={"600519": _candidate(liquidity=LIQUIDITY_RESTRICTED)}
    )
    line = result.lines()[0]

    assert result.status == STATUS_REVIEW_REQUIRED
    assert line.status == LINE_REVIEW_REQUIRED
    assert line.remaining_ceiling_pct is None
    assert "liquidity_profile_requires_review" in line.stop_add_conditions


def test_all_cash_with_no_candidates_is_a_valid_ready_state():
    result = _result(
        snapshot=_snapshot(cash=Decimal("1000000"), holdings=()),
        candidates={},
    )

    assert result.status == STATUS_READY
    assert result.lines() == ()


def test_missing_private_inputs_and_namespace_mismatch_fail_closed():
    missing = _result(
        bundle=PortfolioInputBundle.missing(as_of=AS_OF),
        candidates={},
        tier_policy=PositionTierPolicy.missing(as_of=AS_OF),
    )

    assert missing.status == STATUS_INCOMPLETE
    assert "policy.human_confirmation" in missing.missing_inputs()
    assert "tier_policy.human_confirmation" in missing.missing_inputs()

    with pytest.raises(ValueError, match="namespace must match"):
        _result(
            namespace=POSITION_NAMESPACE_ACTUAL,
            snapshot=_snapshot(namespace=NAMESPACE_SIMULATED),
        )


def test_guidance_payload_never_contains_order_or_position_columns():
    payload = _result().as_policy()
    text = json.dumps(payload, ensure_ascii=False)

    assert payload["action"] == "no_order"
    assert "target_weight" not in text
    assert "position_size" not in text
    assert "order_quantity" not in text
    assert "proposed_entry" not in text
