from decimal import Decimal

import pytest

from value_investment_agent.valuation_bridge_review import (
    BRIDGE_REVIEW_SCHEMA,
    KIND_DEBT,
    KIND_MINORITY_INTEREST,
    KIND_NON_OPERATING_ASSET,
    RECOVERABILITY_CONTRACTUAL,
    RECOVERABILITY_PARTIALLY_SUPPORTED,
    RECOVERABILITY_UNKNOWN,
    BridgeComponentAssessment,
    bridge_component_from_payload,
    bridge_contribution_from_payload,
    build_bridge_contribution,
)


def _component(
    *,
    name: str = "cash",
    book_value: str = "100",
    kind: str = KIND_NON_OPERATING_ASSET,
    recoverability: str = RECOVERABILITY_PARTIALLY_SUPPORTED,
    bear_haircut: str | None = "0.5",
    base_haircut: str | None = "0.2",
    bull_haircut: str | None = "0.1",
    blockers: tuple[str, ...] = (),
) -> BridgeComponentAssessment:
    haircuts = (bear_haircut, base_haircut, bull_haircut)
    recoverable = (
        tuple(
            Decimal(book_value) * (Decimal("1") - Decimal(value))
            for value in haircuts
            if value is not None
        )
        if all(value is not None for value in haircuts)
        else (None, None, None)
    )
    return BridgeComponentAssessment(
        symbol="600519",
        name=name,
        kind=kind,
        book_value=Decimal(book_value),
        legal_availability="VERIFIED",
        liquidity="HIGH",
        recoverability=recoverability,
        bear_haircut=(
            Decimal(bear_haircut) if bear_haircut is not None else None
        ),
        base_haircut=(
            Decimal(base_haircut) if base_haircut is not None else None
        ),
        bull_haircut=(
            Decimal(bull_haircut) if bull_haircut is not None else None
        ),
        bear_recoverable_value=recoverable[0],
        base_recoverable_value=recoverable[1],
        bull_recoverable_value=recoverable[2],
        basis="explicit conservative assumption",
        confidence="低",
        evidence_refs=({"id": "annual-report"},),
        blockers=blockers,
    )


def _claim(name: str, value: str, kind: str) -> BridgeComponentAssessment:
    return _component(
        name=name,
        book_value=value,
        kind=kind,
        recoverability=RECOVERABILITY_CONTRACTUAL,
        bear_haircut="0",
        base_haircut="0",
        bull_haircut="0",
    )


def test_bridge_arithmetic_and_per_share_contribution_are_recalculable():
    components = (
        _component(),
        _claim("debt", "30", KIND_DEBT),
        _claim("minority", "10", KIND_MINORITY_INTEREST),
    )

    base = build_bridge_contribution(
        symbol="600519",
        valuation_scenario="base",
        currency="CNY",
        ordinary_shares=Decimal("10"),
        operating_enterprise_value=Decimal("200"),
        components=components,
        confidence="低",
        evidence_refs=({"id": "bridge-review"},),
    )

    assert base.gross_non_operating_assets == Decimal("80")
    assert base.net_equity_bridge == Decimal("40")
    assert base.net_bridge_per_share == Decimal("4")
    assert base.total_equity_value == Decimal("240")
    assert base.total_value_per_share == Decimal("24")
    assert base.bridge_share_of_equity_value == Decimal("1") / Decimal("6")
    assert base.action == "no_order"


def test_bear_base_bull_can_carry_different_haircuts():
    components = (_component(),)
    reviews = {
        scenario: build_bridge_contribution(
            symbol="600519",
            valuation_scenario=scenario,
            currency="CNY",
            ordinary_shares=Decimal("10"),
            operating_enterprise_value=Decimal("200"),
            components=components,
            confidence="低",
            evidence_refs=({"id": "bridge-review"},),
        )
        for scenario in ("bear", "base", "bull")
    }

    assert reviews["bear"].gross_non_operating_assets == Decimal("50")
    assert reviews["base"].gross_non_operating_assets == Decimal("80")
    assert reviews["bull"].gross_non_operating_assets == Decimal("90")


def test_unknown_recoverability_is_never_silently_converted_to_full_value():
    unknown = BridgeComponentAssessment(
        symbol="600519",
        name="finance-company-deposits",
        kind=KIND_NON_OPERATING_ASSET,
        book_value=Decimal("500"),
        legal_availability="UNKNOWN",
        liquidity="UNKNOWN",
        recoverability=RECOVERABILITY_UNKNOWN,
        bear_haircut=None,
        base_haircut=None,
        bull_haircut=None,
        bear_recoverable_value=None,
        base_recoverable_value=None,
        bull_recoverable_value=None,
        basis="legal-entity recoverability not established",
        confidence="低",
        evidence_refs=({"id": "announcement-1225515005"},),
        blockers=("restricted_cash_unverified",),
    )

    review = build_bridge_contribution(
        symbol="600519",
        valuation_scenario="base",
        currency="CNY",
        ordinary_shares=Decimal("10"),
        operating_enterprise_value=Decimal("200"),
        components=(unknown,),
        confidence="低",
        evidence_refs=({"id": "bridge-review"},),
    )

    assert review.gross_non_operating_assets == Decimal("0")
    assert any("unrecognized_non_operating_asset" in item for item in review.blockers)
    assert any("restricted_cash_unverified" in item for item in review.blockers)


def test_haircut_and_claim_invariants_fail_closed():
    with pytest.raises(ValueError, match="within 0 and 1"):
        _component(bear_haircut="1.1")
    with pytest.raises(ValueError, match="bear >= base >= bull"):
        _component(bear_haircut="0.1", base_haircut="0.3", bull_haircut="0.2")
    with pytest.raises(ValueError, match="Claims must use CONTRACTUAL"):
        _component(
            name="debt",
            book_value="30",
            kind=KIND_DEBT,
            recoverability=RECOVERABILITY_PARTIALLY_SUPPORTED,
        )


def test_identity_currency_and_share_basis_conflicts_fail_closed():
    with pytest.raises(ValueError, match="symbol"):
        BridgeComponentAssessment(
            symbol="bad",
            name="cash",
            kind=KIND_NON_OPERATING_ASSET,
            book_value=Decimal("1"),
            legal_availability="VERIFIED",
            liquidity="HIGH",
            recoverability=RECOVERABILITY_PARTIALLY_SUPPORTED,
            bear_haircut=Decimal("0.1"),
            base_haircut=Decimal("0.1"),
            bull_haircut=Decimal("0.1"),
            bear_recoverable_value=Decimal("0.9"),
            base_recoverable_value=Decimal("0.9"),
            bull_recoverable_value=Decimal("0.9"),
            basis="test",
            confidence="低",
            evidence_refs=({"id": "source"},),
        )
    with pytest.raises(ValueError, match="currency"):
        build_bridge_contribution(
            symbol="600519",
            valuation_scenario="base",
            currency="JPY",
            ordinary_shares=Decimal("10"),
            operating_enterprise_value=Decimal("200"),
            components=(_component(),),
            confidence="低",
        )
    with pytest.raises(ValueError, match="positive integer"):
        build_bridge_contribution(
            symbol="600519",
            valuation_scenario="base",
            currency="CNY",
            ordinary_shares=Decimal("10.5"),
            operating_enterprise_value=Decimal("200"),
            components=(_component(),),
            confidence="低",
        )


def test_payload_round_trip_preserves_arithmetic_and_no_order_boundary():
    review = build_bridge_contribution(
        symbol="600519",
        valuation_scenario="base",
        currency="CNY",
        ordinary_shares=Decimal("10"),
        operating_enterprise_value=Decimal("200"),
        components=(_component(),),
        confidence="低",
        evidence_refs=({"id": "bridge-review"},),
    )
    payload = review.as_policy()
    restored = bridge_contribution_from_payload(payload)

    assert payload["schema_version"] == BRIDGE_REVIEW_SCHEMA
    assert restored == review
    assert restored.as_policy() == payload
    assert restored.action == "no_order"


def test_component_payload_round_trip_preserves_haircuts():
    component = _component()
    restored = bridge_component_from_payload(component.as_policy())
    assert restored == component
    assert restored.base_recoverable_value == Decimal("80")


def test_temporary_haircut_flags_round_trip_and_aggregate_fail_closed():
    component = _component(blockers=("stress-check",))
    component = BridgeComponentAssessment(
        **{
            **component.__dict__,
            "stress_test_only": True,
            "not_valuation_input": True,
            "not_price_assessment_input": True,
        }
    )
    restored = bridge_component_from_payload(component.as_policy())

    assert restored == component
    assert restored.stress_test_only is True
    assert restored.not_valuation_input is True
    assert restored.not_price_assessment_input is True

    review = build_bridge_contribution(
        symbol="600519",
        valuation_scenario="base",
        currency="CNY",
        ordinary_shares=Decimal("10"),
        operating_enterprise_value=Decimal("200"),
        components=(restored,),
        confidence="低",
        evidence_refs=({"id": "bridge-review"},),
    )
    assert review.stress_test_only is True
    assert review.not_valuation_input is True
    assert review.not_price_assessment_input is True
    assert bridge_contribution_from_payload(review.as_policy()) == review


def test_large_bridge_share_is_visible_without_being_an_automatic_failure():
    review = build_bridge_contribution(
        symbol="600519",
        valuation_scenario="base",
        currency="CNY",
        ordinary_shares=Decimal("10"),
        operating_enterprise_value=Decimal("10"),
        components=(_component(book_value="100"),),
        confidence="低",
        evidence_refs=({"id": "bridge-review"},),
    )

    assert review.bridge_share_of_equity_value == Decimal("8") / Decimal("9")
    assert "bridge share" not in review.blockers
