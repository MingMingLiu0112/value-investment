from decimal import Decimal
import pytest
from value_investment_agent.domain.valuation.cash_capex_proxy import cash_capex_proxy
from value_investment_agent.application.historical_validation.reported_cash_proxy import reported_cash_proxies


def review():
    binding = dict(path='runtime/source.pdf', sha256='a'*64, source_url='https://example.test/annual.pdf')
    return dict(schema_version='disclosed-metric-review-v1', symbol='600887', action='no_order',
        financial_gate_admitted=False, facts=[dict(metric_name=name, period='2025', value=value,
            unit='CNY', statement_scope='CONSOLIDATED', source_binding=dict(binding), physical_page=page)
            for name, value, page in [('reported_operating_cash_flow', '100', 89), ('reported_cash_capex', '30', 90)]])


@pytest.mark.parametrize('fault', ['none', 'scope', 'unit', 'report', 'missing'])
def test_proxy_requires_matched_original_and_scope(fault):
    payload = review()
    if fault == 'scope': payload['facts'][1]['statement_scope'] = 'PARENT'
    if fault == 'unit': payload['facts'][1]['unit'] = 'percent'
    if fault == 'report': payload['facts'][1]['source_binding']['sha256'] = 'b'*64
    if fault == 'missing': payload['facts'].pop()
    if fault in {'scope', 'unit', 'report'}:
        with pytest.raises(ValueError): reported_cash_proxies(payload)
        return
    output = reported_cash_proxies(payload)
    assert not output['dividend_sustainability_admitted']
    if fault == 'missing':
        assert output['rows'][0]['status'] == 'NOT_ASSESSABLE'
    else:
        assert output['rows'][0]['proxy_cny'] == '70'
        assert not output['rows'][0]['fcff']
        assert not output['rows'][0]['distributable_cash_proven']


def test_negative_operating_cash_flow_is_not_hidden():
    result = cash_capex_proxy(cfo=Decimal('-10'), cash_capex=Decimal('30'))
    assert result['proxy_cny'] == '-40'
    with pytest.raises(ValueError): cash_capex_proxy(cfo=Decimal('100'), cash_capex=Decimal('-30'))
