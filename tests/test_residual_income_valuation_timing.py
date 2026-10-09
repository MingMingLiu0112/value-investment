"""Synthetic timing tests; no real-company or investment admission."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal as D, localcontext

import pytest

from test_residual_income_equity_valuation import case, complete_facts
from value_investment_agent.m1_valuation_package_builder import build_quality_facts
from value_investment_agent.research_input import facts_from_payload, facts_to_payload as facts_payload
from value_investment_agent.valuation_models.residual_income import (
    DATED_MODEL_VERSION, MODEL_VERSION, ResidualIncomeEquityValuationModel,
    ResidualIncomeScenarioInputs, ResidualIncomeValuationTiming,
    current_projection, current_value,
)

BASIS = datetime.fromisoformat('2025-12-31T23:59:59+08:00')
VALUATION = datetime.fromisoformat('2026-03-31T23:59:59+08:00')
REF = {'id': 'synthetic-timing-policy'}

def timing():
    return ResidualIncomeValuationTiming(BASIS, VALUATION, (REF,))

def test_zero_excess_return_has_an_independently_calculated_timing_value():
    scenario = ResidualIncomeScenarioInputs(D('0.10'), (D('0.10'),), D('0.10'), D('0.02'))
    facts = complete_facts(as_of=date(2026, 3, 31), valuation_timing=timing(),
        scenario_inputs={key: scenario for key in ('bear', 'base', 'bull')})
    result = ResidualIncomeEquityValuationModel().value(facts, case())
    with localcontext() as context:
        context.prec = 48
        expected = D('10') * D('1.10') ** (D(90) / D(365))
    assert abs(result.base_value - expected) < D('1e-40')
    assert result.model_version == DATED_MODEL_VERSION
    assert result.status == 'conditional_research_only'
    assert result.confidence == '低'
    assert result.assumptions['valuation_timing']['scope'] == 'conditional_cash_flow_timing_not_observed_current_equity'
    assert any(ref['id'] == REF['id'] for ref in result.evidence_refs)

def test_registered_forward_projection_matches_the_existing_dated_calculator():
    scenario = ResidualIncomeScenarioInputs(D('0.09'), tuple(current_projection(
        D('1000'), D('200'), D('0.09'), D('0'), D('0.75'), 5, 5)), D('0.09'), D('0.02'), D('0.25'))
    facts = complete_facts(as_of=date(2026, 3, 31), valuation_timing=timing(),
        scenario_inputs={key: scenario for key in ('bear', 'base', 'bull')})
    expected = current_value(D('1000'), D('100'), D('200'), D('0.09'),
        D('0'), D('0.75'), 5, 5, D('0.02'), BASIS, VALUATION)
    result = ResidualIncomeEquityValuationModel().value(facts, case())
    assert abs(result.base_value - D(expected['conditional_value_per_current_disclosed_share_cny'])) < D('1e-38')
    assert all(abs(D(row['dividend_crosscheck_difference'])) < D('0.01') for row in result.sensitivities)

@pytest.mark.parametrize('basis,valuation,refs', [
    (BASIS.replace(tzinfo=None), VALUATION, (REF,)),
    (BASIS, VALUATION.replace(tzinfo=None), (REF,)),
    (BASIS, BASIS.replace(year=2026), (REF,)),
    (BASIS, BASIS.replace(year=2024), (REF,)),
    (BASIS, VALUATION, ()),
])
def test_unsupported_or_unproven_timing_is_rejected(basis, valuation, refs):
    with pytest.raises(ValueError):
        ResidualIncomeValuationTiming(basis, valuation, refs)

def test_timing_cannot_be_relabelled_as_another_valuation_date():
    with pytest.raises(ValueError, match='does not match facts'):
        ResidualIncomeEquityValuationModel().value(complete_facts(valuation_timing=timing()), case())

def test_timing_is_roundtripped_and_legacy_facts_remain_unchanged():
    legacy = complete_facts()
    assert 'valuation_timing' not in facts_payload(legacy)
    assert ResidualIncomeEquityValuationModel().value(legacy, case()).model_version == MODEL_VERSION
    dated = replace(legacy, as_of=date(2026, 3, 31), valuation_timing=timing())
    payload = facts_payload(dated)
    assert facts_payload(facts_from_payload(payload)) == payload
    package_facts = dict(payload, kind='quality_compounder')
    assert build_quality_facts(package_facts).valuation_timing == dated.valuation_timing
