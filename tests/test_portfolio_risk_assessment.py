from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

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
    ASSESSMENT_NAMESPACE_SIMULATED,
    FINDING_INDUSTRY,
    FINDING_MINIMUM_CASH,
    FINDING_SINGLE_SECURITY,
    LIQUIDITY_LIQUID,
    LIQUIDITY_RESTRICTED,
    STATUS_INCOMPLETE,
    STATUS_PASS,
    STATUS_REVIEW_REQUIRED,
    STATUS_VIOLATION,
    SecurityRiskAttributes,
    build_portfolio_risk_assessment,
    security_risk_attributes_from_payload,
)


AS_OF = date(2026, 9, 22)
CONFIRMED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
GENERATED_AT = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)


def _policy(**changes) -> InvestorPolicyStatement:
    payload = {
        "policy_id": "user-policy-v1",
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
        "max_single_security_pct": Decimal("60"),
        "max_single_industry_pct": Decimal("70"),
        "max_cyclical_exposure_pct": Decimal("70"),
        "dividend_income_goal_cny": Decimal("30000"),
        "risk_tolerance": RISK_BALANCED,
        "concentration_allowed": False,
        "tax_regime": "中国大陆个人证券账户",
        "restrictions": ("no_order", "no_leverage", "no_derivatives"),
        "evidence_refs": ({"id": "user-confirmation-v1"},),
    }
    payload.update(changes)
    return InvestorPolicyStatement(**payload)


def _holding(
    symbol: str = "600519",
    *,
    market_value_cny: Decimal = Decimal("160000"),
) -> PortfolioHolding:
    return PortfolioHolding(
        symbol=symbol,
        exchange="SSE" if symbol.startswith("6") else "SZSE",
        quantity=Decimal("100"),
        cost_basis_cny=Decimal("150000"),
        market_value_cny=market_value_cny,
        quantity_source=QUANTITY_HUMAN_CONFIRMED,
        corporate_action_adjusted=True,
        evidence_refs=({"id": f"holding-{symbol}"},),
    )


def _snapshot(
    *,
    namespace: str = NAMESPACE_ACTUAL,
    cash_cny: Decimal = Decimal("200000"),
    holdings=(_holding(),),
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id="snapshot-v1",
        snapshot_version="20260922-v1",
        as_of=AS_OF,
        available_at=AVAILABLE_AT,
        account_scope="个人A股长期账户",
        namespace=namespace,
        cash_cny=cash_cny,
        holdings=holdings,
        reconciliation_status=RECONCILIATION_RECONCILED,
        reconciled_at=CONFIRMED_AT,
        evidence_refs=({"id": "broker-statement-v1"},),
    )


def _attributes(
    symbol: str = "600519",
    *,
    industry: str = "白酒",
    cyclical: bool = False,
    liquidity_profile: str = LIQUIDITY_LIQUID,
    common_factors: tuple[str, ...] = (),
) -> SecurityRiskAttributes:
    return SecurityRiskAttributes(
        symbol=symbol,
        industry=industry,
        cyclical=cyclical,
        liquidity_profile=liquidity_profile,
        common_factors=common_factors,
        evidence_refs=({"id": f"risk-{symbol}"},),
    )


def _assessment(**changes):
    payload = {
        "bundle": PortfolioInputBundle(policy=_policy(), snapshot=_snapshot()),
        "security_attributes": {"600519": _attributes()},
        "as_of": AS_OF,
        "generated_at": GENERATED_AT,
        "assessment_id": "risk-assessment-v1",
    }
    payload.update(changes)
    return build_portfolio_risk_assessment(**payload)


def test_balanced_actual_portfolio_passes_with_reviewable_weights():
    assessment = _assessment()

    assert assessment.status == STATUS_PASS
    assert assessment.can_assess()
    assert assessment.total_assets_cny() == Decimal("360000")
    assert assessment.security_weights()["600519"] == Decimal("160000") / Decimal("360000")
    assert assessment.industry_exposures()["白酒"] == Decimal("160000") / Decimal("360000")
    assert assessment.cyclical_exposure() == Decimal("0")
    assert assessment.findings() == ()
    assert assessment.blockers() == ()


def test_single_security_concentration_is_reported_not_removed():
    assessment = _assessment(
        bundle=PortfolioInputBundle(
            policy=_policy(max_single_security_pct=Decimal("15")),
            snapshot=_snapshot(),
        )
    )

    assert assessment.status == STATUS_VIOLATION
    assert [item.kind for item in assessment.findings()] == [FINDING_SINGLE_SECURITY]
    assert assessment.blockers() == (FINDING_SINGLE_SECURITY,)


def test_industry_cyclical_and_cash_violations_are_kept_separate():
    attributes = _attributes(
        industry="周期制造",
        cyclical=True,
        common_factors=("macro_cycle",),
    )
    assessment = _assessment(
        bundle=PortfolioInputBundle(
            policy=_policy(
                max_single_security_pct=Decimal("60"),
                max_single_industry_pct=Decimal("20"),
                max_cyclical_exposure_pct=Decimal("10"),
                minimum_cash_cny=Decimal("300000"),
            ),
            snapshot=_snapshot(cash_cny=Decimal("100000")),
        ),
        security_attributes={"600519": attributes},
    )
    kinds = [item.kind for item in assessment.findings()]

    assert assessment.status == STATUS_VIOLATION
    assert FINDING_INDUSTRY in kinds
    assert FINDING_MINIMUM_CASH in kinds
    assert "cyclical_exposure" in kinds
    assert "reserved_cash" in kinds


def test_non_liquid_exposure_requires_review_without_fabricating_a_limit():
    assessment = _assessment(
        security_attributes={"600519": _attributes(liquidity_profile=LIQUIDITY_RESTRICTED)}
    )

    assert assessment.status == STATUS_REVIEW_REQUIRED
    assert assessment.findings()[0].kind == "liquidity_profile"
    assert assessment.findings()[0].limit is None
    assert "liquidity_profile" in assessment.blockers()


def test_missing_and_simulated_private_inputs_remain_incomplete():
    missing = _assessment(
        bundle=PortfolioInputBundle.missing(as_of=AS_OF),
        security_attributes={},
    )

    assert missing.status == STATUS_INCOMPLETE
    assert "policy.human_confirmation" in missing.missing_inputs()
    with pytest.raises(ValueError, match="namespace must match"):
        _assessment(
            bundle=PortfolioInputBundle(
                policy=_policy(),
                snapshot=_snapshot(namespace=NAMESPACE_SIMULATED),
            ),
            security_attributes={"600519": _attributes()},
        )


def test_explicit_simulated_assessment_is_usable_but_publicly_labeled():
    assessment = _assessment(
        bundle=PortfolioInputBundle(
            policy=_policy(),
            snapshot=_snapshot(namespace=NAMESPACE_SIMULATED),
        ),
        security_attributes={"600519": _attributes()},
        assessment_namespace=ASSESSMENT_NAMESPACE_SIMULATED,
    )

    assert assessment.can_assess()
    assert assessment.status == STATUS_PASS
    assert assessment.as_policy()["assessment_namespace"] == "SIMULATED"
    assert assessment.sensitivity == "SIMULATED_PUBLIC_DEMONSTRATION"
    assert "actual_namespace" not in assessment.missing_inputs()


def test_missing_security_attribute_fails_closed():
    with pytest.raises(ValueError, match="Missing security risk attributes"):
        _assessment(security_attributes={})


def test_risk_attribute_loader_rejects_string_boolean():
    payload = _attributes().as_policy()
    payload["cyclical"] = "false"

    with pytest.raises(ValueError, match="must be boolean"):
        security_risk_attributes_from_payload(payload)


def test_risk_payload_has_no_position_or_order_columns():
    assessment = _assessment()
    payload = assessment.as_policy()
    text = json.dumps(payload, ensure_ascii=False)

    assert payload["status"] == STATUS_PASS
    assert payload["action"] == "no_order"
    assert "target_weight" not in text
    assert "position_size" not in text
    assert "order_quantity" not in text
