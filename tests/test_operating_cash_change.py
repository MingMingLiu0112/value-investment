from decimal import Decimal
import pytest
from value_investment_agent.domain.valuation.operating_cash_bridge import operating_cash_change_bridge


def values():
    return {key: Decimal(value) for key, value in dict(sales_receipts='100', interest_receipts='2',
        tax_refunds='3', other_receipts='5', purchases_paid='60', employees_paid='10', taxes_paid='5',
        other_payments='5', inflow_total='110', outflow_total='80', cfo='30').items()}


def test_cash_change_signs_reconcile_and_are_not_forecasts():
    prior = values()
    current = values()
    current.update(sales_receipts=Decimal('90'), employees_paid=Decimal('12'),
                   inflow_total=Decimal('100'), outflow_total=Decimal('82'), cfo=Decimal('18'))
    output = operating_cash_change_bridge(current, prior)
    assert output['cfo_change_cny'] == '-12'
    assert output['contributions_cny']['employees_paid'] == '-2'
    assert not output['sustainable_cash_proven']
    assert not output['forecast_approved']


@pytest.mark.parametrize('change', ['missing', 'subtotal', 'nonfinite'])
def test_cash_bridge_rejects_missing_and_unreconciled_values(change):
    current = values()
    if change == 'missing': del current['other_receipts']
    if change == 'subtotal': current['cfo'] += 1
    if change == 'nonfinite': current['sales_receipts'] = Decimal('NaN')
    with pytest.raises(ValueError): operating_cash_change_bridge(current, values())


def test_source_and_scope_cannot_be_mixed():
    from value_investment_agent.application.historical_validation.reported_cash_change import reported_cash_change
    facts = [dict(metric_name='cash_bridge_'+key, period=period, value=str(value), unit='CNY',
        statement_scope='CONSOLIDATED', verification_status='TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY',
        source_binding={'sha256': 'a'*64}) for period in ('2024', '2025') for key, value in values().items()]
    review = dict(schema_version='disclosed-metric-review-v1', symbol='600887', facts=facts,
                  financial_gate_admitted=False, action='no_order')
    assert reported_cash_change(review, current_period='2025', prior_period='2024')['cfo_change_cny'] == '0'
    facts[0]['source_binding'] = {'sha256': 'b'*64}
    with pytest.raises(ValueError): reported_cash_change(review, current_period='2025', prior_period='2024')
    facts[0]['source_binding'] = {'sha256': 'a'*64}
    facts[0]['statement_scope'] = 'PARENT'
    with pytest.raises(ValueError): reported_cash_change(review, current_period='2025', prior_period='2024')
