from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.valuation_assumptions import (
    STATUS_INVALID,
    STATUS_NOT_READY,
    STATUS_PARTIAL,
    STATUS_READY,
    ValuationAssumption,
    assumption_set_from_payload,
    build_valuation_assumption_set,
)


def normalized_coal_price(**overrides):
    values = {
        "name": "normalized_coal_price",
        "unit": "CNY/tonne",
        "bear": Decimal("550"),
        "base": Decimal("700"),
        "bull": Decimal("850"),
        "basis": "Historical index range, supply/demand balance and cost support",
        "rationale": "Bear is cost pressure, base is the long-run observed envelope and bull is tight supply",
        "as_of": date(2026, 9, 22),
        "confidence": "medium",
        "sensitivity": "high",
        "evidence_refs": [{"id": "coal_price_history"}],
        "blockers": [],
    }
    values.update(overrides)
    return ValuationAssumption(**values)


def set_from(*assumptions):
    return build_valuation_assumption_set(
        symbol="601088",
        profile_id="cyclical_cash_return",
        model_type="cyclical_normalized",
        as_of=date(2026, 9, 22),
        assumptions=list(assumptions),
        evidence_refs=[{"id": "coal_price_history"}],
    )


def test_complete_reviewed_assumption_set_is_ready():
    outcome = set_from(normalized_coal_price())

    assert outcome.status == STATUS_READY
    assert outcome.blockers == []
    assert outcome.assumptions[0].has_complete_scenarios()


def test_partial_scenario_is_explicitly_partial_not_silently_ready():
    outcome = set_from(normalized_coal_price(bull=None))

    assert outcome.status == STATUS_PARTIAL
    assert "assumption_scenarios_missing:normalized_coal_price:bull" in outcome.blockers


def test_unexplained_assumption_fails_closed():
    with pytest.raises(ValueError, match="basis and rationale"):
        normalized_coal_price(rationale="")


def test_numeric_scenarios_must_be_ordered():
    with pytest.raises(ValueError, match="registered ordering"):
        normalized_coal_price(bull=Decimal("400"))


def test_duplicate_named_assumptions_invalidate_the_set():
    outcome = set_from(
        normalized_coal_price(),
        normalized_coal_price(name="normalized_coal_price"),
    )

    assert outcome.status == STATUS_INVALID
    assert "duplicate_assumptions:normalized_coal_price" in outcome.blockers


def test_empty_set_cannot_claim_ready():
    assert set_from().status == STATUS_NOT_READY


def test_json_roundtrip_preserves_the_fail_closed_contract():
    original = set_from(normalized_coal_price(bull=None))
    restored = assumption_set_from_payload(original.as_policy())

    assert restored.symbol == original.symbol
    assert restored.status == STATUS_PARTIAL
    assert Decimal(restored.assumptions[0].bear) == Decimal("550")
    assert restored.assumptions[0].bull is None
