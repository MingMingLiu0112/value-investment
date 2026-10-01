from copy import deepcopy
from decimal import Decimal

import pytest

from value_investment_agent.domain.research.reported_trends import reported_change
from value_investment_agent.application.historical_validation.reported_earnings_cash_trends import reported_earnings_cash_trends


def review():
    facts = []
    for name, values in {'reported_parent_net_profit': ('100', '120'),
                         'reported_operating_cash_flow': ('150', '90')}.items():
        for period, value in zip(('2024', '2025'), values):
            facts.append(dict(symbol='600887', metric_name=name, period=period, value=value,
                              unit='CNY', physical_page=1, verification_status='TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY',
                              source_binding={'sha256': 'a' * 64}))
    return dict(schema_version='disclosed-metric-review-v1', symbol='600887', facts=facts,
                action='no_order', financial_gate_admitted=False,
                forecast_assumptions_approved=False, strict_pit_admitted=False)


def test_opposite_trends_are_not_same_scope_cash_conversion_or_quality_approval():
    output = reported_earnings_cash_trends(review())
    row = output['rows'][0]
    assert row['parent_profit']['growth_rate'] == '0.2'
    assert row['operating_cash']['growth_rate'] == '-0.4'
    assert row['opposite_directions'] is True
    assert output['cash_conversion_ratio'] is None
    assert output['quality_assessment_admitted'] is False
    assert output['action'] == 'no_order'


@pytest.mark.parametrize('prior', ['0', '-10'])
def test_nonpositive_base_does_not_create_misleading_growth(prior):
    assert reported_change(Decimal(prior), Decimal('5'))['growth_rate'] is None


@pytest.mark.parametrize('fault', ['source', 'duplicate', 'unit', 'period', 'nonfinite', 'admission'])
def test_trend_review_fails_closed(fault):
    value = deepcopy(review())
    if fault == 'source': value['facts'][0]['source_binding']['sha256'] = 'b' * 64
    if fault == 'duplicate': value['facts'].append(deepcopy(value['facts'][0]))
    if fault == 'unit': value['facts'][0]['unit'] = 'percent'
    if fault == 'period': value['facts'][0]['period'] = '2024H1'
    if fault == 'nonfinite': value['facts'][0]['value'] = 'NaN'
    if fault == 'admission': value['financial_gate_admitted'] = True
    with pytest.raises(ValueError):
        reported_earnings_cash_trends(value)


def test_missing_series_and_nonadjacent_periods_do_not_manufacture_yoy():
    value = review()
    value['facts'] = value['facts'][:2]
    assert reported_earnings_cash_trends(value) is None
    value = review()
    for fact in value['facts']:
        if fact['period'] == '2024': fact['period'] = '2022'
    assert reported_earnings_cash_trends(value)['rows'] == []


def test_financial_projection_shows_trends_without_changing_any_gate():
    from dataclasses import replace
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord, product_workbench_from_payload
    from value_investment_agent.presentation.read_models.reported_financials import project_reported_financials
    from value_investment_agent.presentation.read_models.conditional_expectations import render_company_review_cards

    model = product_workbench_from_payload(_payload())
    model = replace(model, companies=(replace(model.companies[0], symbol='600887'),))
    value = review()
    trends = reported_earnings_cash_trends(value)
    evidence = EvidenceRecord('trend-source', 'Synthetic reviewed rows', 'test', 'fixture.json', 'a' * 64, model.as_of)
    projected = project_reported_financials(model, value, None, evidence, earnings_cash_trends=trends)
    assert projected.companies[0].decision_process == model.companies[0].decision_process
    assert projected.companies[0].scenarios == model.companies[0].scenarios
    assert projected.portfolio == model.portfolio
    assert '两项变动方向相反' in render_company_review_cards(projected)
    trends['quality_assessment_admitted'] = True
    with pytest.raises(ValueError, match='cannot approve quality'):
        project_reported_financials(model, value, None, evidence, earnings_cash_trends=trends)
