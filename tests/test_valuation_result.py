from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.reverse_valuation import solve_bounded_monotonic
from value_investment_agent.valuation_models.base import ValuationResult


def result(**overrides):
    values = dict(symbol="600519", model_type="fixture", valuation_date=date(2026, 9, 20),
                  bear_value=Decimal("1"), base_value=Decimal("2"), bull_value=Decimal("3"), confidence="低",
                  assumptions={}, sensitivities=[], evidence_refs=[{"id": "fixture"}], blockers=["gap"],
                  status="conditional_research_only", model_version="fixture-v1")
    values.update(overrides)
    return ValuationResult(**values)


def test_scenarios_are_ordered_and_serializable():
    assert '"base_value": "2"' in result().to_json()
    with pytest.raises(ValueError, match="bear"):
        result(bear_value=Decimal("4"))


def test_reverse_valuation_does_not_extend_a_registered_envelope():
    answer = solve_bounded_monotonic(target=Decimal("11"), lower=Decimal("0"), upper=Decimal("1"),
                                     value_at=lambda x: Decimal("1") + x)
    assert answer["status"] == "above_registered_envelope"
    assert answer["solution"] is None
