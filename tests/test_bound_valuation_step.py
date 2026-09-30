from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.domain.research.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult
from value_investment_agent.presentation.read_models.valuation_step import bound_valuation_step


def result():
    return ValuationResult(
        symbol="600887", model_type="fixture", valuation_date=date(2026, 6, 30),
        bear_value=Decimal("8"), base_value=Decimal("11"), bull_value=Decimal("13"),
        confidence="低", assumptions={}, sensitivities=[], evidence_refs=[{"id": "fixture"}],
        blockers=["PIT unproven"], status="conditional_research_only", model_version="fixture-v1",
    )


@pytest.mark.parametrize("symbol", ["600887", "000333", "601088"])
def test_bound_scenario_is_conditional_and_price_independent(symbol):
    valuation = replace(result(), symbol=symbol)
    step = bound_valuation_step(valuation, expected_sha256=valuation_result_sha256(valuation), assessment_id="fixture-run")
    assert step.key == "valuation"
    assert step.status == "CONDITIONAL"
    assert "2026-06-30" in step.reason
    assert "PIT unproven" in step.reason
    assert "PriceBridge" in step.next_action
    assert step.evidence_refs == ("fixture",)


def test_changed_valuation_cannot_reuse_old_binding():
    valuation = result()
    with pytest.raises(ValueError, match="binding mismatch"):
        bound_valuation_step(replace(valuation, base_value=Decimal("12")), expected_sha256=valuation_result_sha256(valuation), assessment_id="fixture-run")


def test_missing_scenario_stays_blocked():
    valuation = replace(result(), bear_value=None)
    step = bound_valuation_step(valuation, expected_sha256=valuation_result_sha256(valuation), assessment_id="fixture-run")
    assert step.status == "BLOCKED"


@pytest.mark.parametrize("missing", [False, True])
def test_company_projection_updates_only_valuation_and_preserves_gates(missing):
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    from value_investment_agent.presentation.read_models.valuation_step import company_with_bound_valuation

    card = product_workbench_from_payload(_payload()).companies[0]
    valuation = replace(result(), symbol=card.symbol, bear_value=None if missing else Decimal("8"))
    projected = company_with_bound_valuation(card, valuation, expected_sha256=valuation_result_sha256(valuation), assessment_id="bound-run")
    assert projected.price == card.price
    assert projected.margin_of_safety == card.margin_of_safety
    assert projected.research_status == card.research_status
    assert projected.decision_review == card.decision_review
    assert projected.action == "no_order"
    assert projected.valuation.available is (not missing)
    assert all(s.assessment.available is (not missing) for s in projected.scenarios)
    assert all(new == old for new, old in zip(projected.decision_process, card.decision_process) if new.key != "valuation")
    assert projected.sections[3].summary == projected.decision_process[3].reason
    assert "fixture" in projected.evidence_refs


def test_company_projection_rejects_cross_company_result():
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    from value_investment_agent.presentation.read_models.valuation_step import company_with_bound_valuation

    card = product_workbench_from_payload(_payload()).companies[0]
    with pytest.raises(ValueError, match="symbol mismatch"):
        company_with_bound_valuation(card, result(), expected_sha256=valuation_result_sha256(result()), assessment_id="bound-run")


def _bound_workbench():
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload

    model = product_workbench_from_payload(_payload())
    record = model.audit_evidence[0]
    valuation = replace(result(), symbol=model.companies[0].symbol,
                        evidence_refs=[{"id": record.evidence_id, "sha256": record.sha256}])
    return model, valuation


def test_workbench_projection_keeps_price_portfolio_and_all_nonvaluation_states():
    from value_investment_agent.presentation.read_models.valuation_step import workbench_with_bound_valuation

    model, valuation = _bound_workbench()
    updated = workbench_with_bound_valuation(model, valuation, expected_sha256=valuation_result_sha256(valuation), assessment_id="bound-run")
    assert updated.companies[0].valuation.available
    assert updated.opportunities[0].valuation_status == updated.companies[0].valuation.status
    assert updated.portfolio == model.portfolio
    assert updated.overview == model.overview
    assert updated.today_items == model.today_items
    assert updated.audit_evidence == model.audit_evidence
    assert updated.companies[0].price == model.companies[0].price


@pytest.mark.parametrize("fault", ["missing", "hash", "url", "undated", "future", "basis"])
def test_workbench_projection_rejects_unbound_or_future_evidence(fault):
    from value_investment_agent.presentation.read_models.valuation_step import workbench_with_bound_valuation

    model, valuation = _bound_workbench()
    record = model.audit_evidence[0]
    if fault == "missing":
        valuation = replace(valuation, evidence_refs=[{"id": "absent", "sha256": record.sha256}])
    elif fault == "hash":
        valuation = replace(valuation, evidence_refs=[{"id": record.evidence_id, "sha256": "b" * 64}])
    elif fault == "url":
        valuation = replace(valuation, evidence_refs=[{"id": record.evidence_id, "sha256": record.sha256, "url": "https://example.org/source.pdf"}])
    elif fault in {"undated", "future"}:
        model = replace(model, audit_evidence=(replace(record, available_at=None if fault == "undated" else date(2099, 1, 1)),))
    else:
        valuation = replace(valuation, valuation_date=date(2099, 1, 1))
    with pytest.raises(ValueError):
        workbench_with_bound_valuation(model, valuation, expected_sha256=valuation_result_sha256(valuation), assessment_id="bound-run")
