from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.model_validity import MaterialEvent, ModelValidity, evaluate_model_validity
from value_investment_agent.price_bridge import bridge, pending_price_bridge_for_incomplete_valuation
from value_investment_agent.valuation_models.base import ValuationResult


def valuation():
    return ValuationResult("600519", "fixture", date(2026, 9, 16), Decimal("400"), Decimal("500"),
                           Decimal("600"), "中", {}, [], [{"id": "model"}], [], "ready", "fixture-v1")


def validity(status="VALID"):
    return ModelValidity("model", "600519", date(2026, 9, 16), date(2026, 9, 16),
                         date(2026, 9, 18) if status == "VALID" else None,
                         False, False, False if status == "VALID" else None, status,
                         [] if status == "VALID" else ["event check missing"], [{"id": "events"}] if status == "VALID" else [])


def test_missing_quote_keeps_valuation_and_returns_pending_bridge():
    outcome = bridge(valuation(), validity(), quote_date=None, current_price=None,
                     quote_status="PENDING_EXTERNAL_DATA", evidence_refs=[])
    assert outcome.bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.current_price is None
    assert valuation().base_value == Decimal("500")


def test_valid_later_quote_can_bridge_without_same_date_model():
    outcome = bridge(valuation(), validity(), quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                     quote_status="verified_close", evidence_refs=[{"id": "quote"}])
    assert outcome.bridge_status == "READY"
    assert outcome.margin_to_base == Decimal("0.1")


def test_evaluator_allows_later_quote_after_no_material_event():
    checked = evaluate_model_validity(
        model_id="model", symbol="600519", model_as_of=date(2026, 9, 16), valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18), events=[], event_scan_evidence_refs=[{"id": "event-scan"}],
    )
    outcome = bridge(valuation(), checked, quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                     quote_status="verified_close", evidence_refs=[{"id": "quote"}])
    assert checked.status == "VALID"
    assert outcome.bridge_status == "READY"


def test_evaluator_stales_model_when_new_filing_precedes_quote():
    event = MaterialEvent(date(2026, 9, 17), "financial_statement", "interim filing", [{"id": "filing"}])
    checked = evaluate_model_validity(
        model_id="model", symbol="600519", model_as_of=date(2026, 9, 16), valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18), events=[event], event_scan_evidence_refs=[{"id": "event-scan"}],
    )
    outcome = bridge(valuation(), checked, quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                     quote_status="verified_close", evidence_refs=[{"id": "quote"}])
    assert checked.status == "STALE"
    assert outcome.bridge_status == "STALE_MODEL"


def test_evaluator_requires_event_scan_evidence():
    checked = evaluate_model_validity(
        model_id="model", symbol="600519", model_as_of=date(2026, 9, 16), valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18), events=[], event_scan_evidence_refs=[],
    )
    assert checked.status == "UNKNOWN"
    assert bridge(valuation(), checked, quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                  quote_status="verified_close", evidence_refs=[{"id": "quote"}]).bridge_status == "INVALID"


def test_bridge_refuses_unchecked_validity_after_quote_date():
    unchecked = ModelValidity("model", "600519", date(2026, 9, 16), date(2026, 9, 16), date(2026, 9, 17),
                              False, False, False, "VALID", [], [{"id": "event-scan"}])
    outcome = bridge(valuation(), unchecked, quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                     quote_status="verified_close", evidence_refs=[{"id": "quote"}])
    assert outcome.bridge_status == "INVALID"


def test_stale_model_refuses_price_comparison():
    stale = ModelValidity("model", "600519", date(2026, 9, 16), date(2026, 9, 16), date(2026, 9, 18),
                          True, False, True, "STALE", ["new report"], [{"id": "event"}])
    outcome = bridge(valuation(), stale, quote_date=date(2026, 9, 18), current_price=Decimal("450"),
                     quote_status="verified_close", evidence_refs=[{"id": "quote"}])
    assert outcome.bridge_status == "STALE_MODEL"


def test_incomplete_valuation_keeps_a_pending_bridge_without_inventing_validity():
    incomplete = ValuationResult(
        "000333", "FCFF", date(2025, 12, 31), None, None, None, "低",
        {"scope": "input gate"}, [], [{"id": "facts"}], ["missing_input"],
        "not_ready", "fcff-input-gate-v1",
    )
    outcome = pending_price_bridge_for_incomplete_valuation(
        incomplete,
        evidence_refs=incomplete.evidence_refs,
    )

    assert outcome.bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.model_validity_status == "UNKNOWN"
    assert outcome.quote_status == "PENDING_EXTERNAL_DATA"
    assert (outcome.current_price, outcome.margin_to_bear, outcome.margin_to_base) == (None, None, None)
    assert "正式估值未形成，价格桥接不启用" in outcome.blockers
    assert outcome.evidence_refs == [{"id": "facts"}]


def test_incomplete_bridge_adapter_rejects_an_existing_scenario_value():
    with pytest.raises(ValueError, match="only valid when no scenario value exists"):
        pending_price_bridge_for_incomplete_valuation(
            valuation(),
            evidence_refs=valuation().evidence_refs,
        )
