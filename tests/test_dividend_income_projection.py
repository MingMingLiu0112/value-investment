from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.distribution import (
    DIVIDEND_APPROVED,
    DIVIDEND_ORDINARY,
    DIVIDEND_SPECIAL,
)
from value_investment_agent.dividend_income_projection import (
    BASIS_DECLARED,
    BASIS_FORWARD,
    BASIS_NORMALIZED,
    BASIS_PAID,
    TAX_CALCULATED,
    TAX_PENDING_DISPOSAL,
    DividendIncomeObservation,
    PortfolioDividendIncomeProjection,
    SecurityDividendIncomeProjection,
    build_portfolio_dividend_income_projection,
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


AS_OF = date(2026, 9, 22)
CONFIRMED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
GENERATED_AT = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)


def _policy() -> InvestorPolicyStatement:
    return InvestorPolicyStatement(
        policy_id="dividend-policy-v1",
        policy_version="20260922-v1",
        as_of=AS_OF,
        confirmation_status=CONFIRMATION_HUMAN,
        confirmed_at=CONFIRMED_AT,
        account_scope="个人A股长期账户",
        investable_assets_cny=Decimal("1000000"),
        minimum_cash_cny=Decimal("100000"),
        emergency_cash_cny=Decimal("150000"),
        liquidity_needs_cny=Decimal("50000"),
        time_horizon_years=Decimal("10"),
        max_single_security_pct=Decimal("15"),
        max_single_industry_pct=Decimal("30"),
        max_cyclical_exposure_pct=Decimal("25"),
        dividend_income_goal_cny=Decimal("30000"),
        risk_tolerance=RISK_BALANCED,
        concentration_allowed=False,
        tax_regime="中国大陆个人证券账户",
        restrictions=("no_order", "no_leverage"),
        evidence_refs=({"id": "dividend-policy-confirmation"},),
    )


def _holding() -> PortfolioHolding:
    return PortfolioHolding(
        symbol="600519",
        exchange="SSE",
        quantity=Decimal("100"),
        cost_basis_cny=Decimal("150000"),
        market_value_cny=Decimal("160000"),
        quantity_source=QUANTITY_HUMAN_CONFIRMED,
        corporate_action_adjusted=True,
        evidence_refs=({"id": "holding-600519"},),
    )


def _snapshot(namespace=NAMESPACE_ACTUAL) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id="dividend-snapshot-v1",
        snapshot_version="20260922-v1",
        as_of=AS_OF,
        available_at=AVAILABLE_AT,
        account_scope="个人A股长期账户",
        namespace=namespace,
        cash_cny=Decimal("200000"),
        holdings=(_holding(),),
        reconciliation_status=RECONCILIATION_RECONCILED,
        reconciled_at=CONFIRMED_AT,
        evidence_refs=({"id": "dividend-broker-statement"},),
    )


def _paid(*, dividend_type=DIVIDEND_ORDINARY, gross="20") -> DividendIncomeObservation:
    return DividendIncomeObservation(
        observation_id=f"paid-{dividend_type}-600519",
        symbol="600519",
        basis=BASIS_PAID,
        dividend_type=dividend_type,
        gross_per_share=Decimal(gross),
        quantity=Decimal("100"),
        as_of=AS_OF,
        record_date=date(2025, 6, 10),
        payable_date=date(2025, 6, 25),
        account_type="mainland_individual_unrestricted_sse_szse",
        acquired=date(2020, 1, 10),
        disposal_settlement=date(2026, 9, 15),
        tax_regime="MOF-2015-101",
        evidence_refs=({"id": "paid-600519"},),
    )


def _declared(*, dividend_type=DIVIDEND_ORDINARY, gross="25") -> DividendIncomeObservation:
    return DividendIncomeObservation(
        observation_id=f"declared-{dividend_type}-600519",
        symbol="600519",
        basis=BASIS_DECLARED,
        dividend_type=dividend_type,
        gross_per_share=Decimal(gross),
        quantity=Decimal("100"),
        as_of=AS_OF,
        record_date=date(2026, 10, 2),
        payable_date=date(2026, 10, 20),
        approval_status=DIVIDEND_APPROVED,
        evidence_refs=({"id": "declared-600519"},),
    )


def _forward() -> DividendIncomeObservation:
    return DividendIncomeObservation(
        observation_id="forward-600519",
        symbol="600519",
        basis=BASIS_FORWARD,
        dividend_type=DIVIDEND_ORDINARY,
        gross_per_share=Decimal("30"),
        quantity=Decimal("100"),
        as_of=AS_OF,
        confidence="medium",
        period_start=date(2026, 9, 1),
        period_end=date(2027, 8, 31),
        evidence_refs=({"id": "forward-600519"},),
    )


def _normalized() -> DividendIncomeObservation:
    return DividendIncomeObservation(
        observation_id="normalized-600519",
        symbol="600519",
        basis=BASIS_NORMALIZED,
        dividend_type=DIVIDEND_ORDINARY,
        gross_per_share=Decimal("32"),
        quantity=Decimal("100"),
        as_of=AS_OF,
        scenario_id="normalized-base",
        period_start=date(2026, 9, 1),
        period_end=date(2027, 8, 31),
        evidence_refs=({"id": "normalized-600519"},),
    )


def _security(
    *,
    observations=None,
    symbol="600519",
) -> SecurityDividendIncomeProjection:
    return SecurityDividendIncomeProjection(
        projection_id=f"projection-{symbol}",
        symbol=symbol,
        quantity=Decimal("100"),
        observations=observations
        if observations is not None
        else (_paid(), _declared(), _forward(), _normalized()),
        as_of=AS_OF,
        generated_at=GENERATED_AT,
    )


def _portfolio(*, namespace=NAMESPACE_ACTUAL, **changes) -> PortfolioDividendIncomeProjection:
    payload = {
        "bundle": PortfolioInputBundle(
            policy=_policy(),
            snapshot=_snapshot(namespace=namespace),
        ),
        "security_projections": {"600519": _security()},
        "as_of": AS_OF,
        "generated_at": GENERATED_AT,
        "assessment_id": "dividend-projection-v1",
        "assessment_namespace": namespace,
    }
    payload.update(changes)
    return build_portfolio_dividend_income_projection(**payload)


def test_four_bases_are_separate_and_known_paid_net_is_calculated():
    projection = _portfolio()
    summaries = {item.basis: item for item in projection.summaries()}

    assert projection.status == "READY"
    assert summaries[BASIS_PAID].gross_income == Decimal("2000")
    assert summaries[BASIS_PAID].net_income == Decimal("2000")
    assert summaries[BASIS_PAID].tax_status == TAX_CALCULATED
    assert summaries[BASIS_DECLARED].gross_income == Decimal("2500")
    assert summaries[BASIS_DECLARED].net_income is None
    assert summaries[BASIS_FORWARD].gross_income == Decimal("3000")
    assert summaries[BASIS_NORMALIZED].gross_income == Decimal("3200")
    assert summaries[BASIS_DECLARED].goal_gap == Decimal("27500")


def test_special_dividend_is_not_merged_or_annualized_into_forward_or_normalized():
    observations = (
        _paid(),
        _paid(dividend_type=DIVIDEND_SPECIAL, gross="8"),
        _declared(),
        _forward(),
        _normalized(),
    )
    projection = _portfolio(security_projections={"600519": _security(observations=observations)})
    security = projection.security_projections["600519"]
    paid = security.observations_for(BASIS_PAID)

    assert [item.dividend_type for item in paid] == [
        DIVIDEND_ORDINARY,
        DIVIDEND_SPECIAL,
    ]
    assert security.ordinary_special_separated is True
    assert security.gross_by_basis()[BASIS_PAID] == Decimal("2800")
    assert security.gross_by_basis()[BASIS_FORWARD] == Decimal("3000")
    assert security.gross_by_basis()[BASIS_NORMALIZED] == Decimal("3200")

    with pytest.raises(ValueError, match="cannot be forward-estimated"):
        _forward().__class__(
            observation_id="bad-special-forward",
            symbol="600519",
            basis=BASIS_FORWARD,
            dividend_type=DIVIDEND_SPECIAL,
            gross_per_share=Decimal("5"),
            quantity=Decimal("100"),
            as_of=AS_OF,
            confidence="medium",
            period_start=date(2026, 9, 1),
            period_end=date(2027, 8, 31),
            evidence_refs=({"id": "bad-special"},),
        )


def test_unsettled_declared_and_forward_income_keeps_tax_unknown():
    projection = _portfolio()
    observation = projection.security_projections["600519"].observations_for(BASIS_DECLARED)[0]

    assert observation.net_income_cny() is None
    assert observation.tax_treatment.status == TAX_PENDING_DISPOSAL
    assert "target_weight" not in json.dumps(projection.as_policy(), ensure_ascii=False)
    assert "position_size" not in json.dumps(projection.as_policy(), ensure_ascii=False)


def test_missing_basis_is_partial_and_names_missing_inputs():
    projection = _portfolio(
        security_projections={
            "600519": _security(observations=(_paid(), _declared(), _forward()))
        }
    )

    assert projection.status == "PARTIAL"
    assert "600519:missing_basis:normalized_scenario" in projection.blockers()


def test_quantity_mismatch_and_namespace_mismatch_fail_closed():
    with pytest.raises(ValueError, match="quantity must match"):
        SecurityDividendIncomeProjection(
            projection_id="quantity-mismatch",
            symbol="600519",
            quantity=Decimal("90"),
            observations=(_paid(), _declared(), _forward(), _normalized()),
            as_of=AS_OF,
            generated_at=GENERATED_AT,
        )

    with pytest.raises(ValueError, match="namespace must match"):
        _portfolio(
            bundle=PortfolioInputBundle(
                policy=_policy(),
                snapshot=_snapshot(namespace=NAMESPACE_SIMULATED),
            ),
            namespace=NAMESPACE_ACTUAL,
        )


def test_missing_private_inputs_are_incomplete():
    projection = _portfolio(
        bundle=PortfolioInputBundle.missing(as_of=AS_OF),
        security_projections={},
    )

    assert projection.status == "INCOMPLETE"
    assert projection.summaries() == ()
    assert "policy.human_confirmation" in projection.missing_inputs()
