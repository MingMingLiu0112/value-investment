from decimal import Decimal

import pytest

from value_investment_agent.broker_regulatory_reference import reference


@pytest.mark.parametrize('field,minimum,warning', [
    ('risk_coverage', '100', '120'), ('capital_leverage', '8', '9.6'),
    ('liquidity_coverage', '100', '120'), ('net_stable_funding', '100', '120')])
def test_official_general_thresholds(field, minimum, warning):
    result = reference(field, '2026-06-30', 300)
    assert result['minimum'] == Decimal(minimum)
    assert result['warning'] == Decimal(warning)
    assert result['regulatory_compliance_verified'] is False


@pytest.mark.parametrize('value,expected', [
    ('7.99', '数值低于一般监管下限'), ('8', '数值处于一般预警区间'),
    ('9.6', '数值处于一般预警区间'), ('9.61', '数值高于一般预警线'),
    (None, '缺值，不能对照'), ('NaN', '缺值，不能对照'),
    ('Infinity', '缺值，不能对照'), (True, '缺值，不能对照'), (-1, '缺值，不能对照')])
def test_boundary_and_invalid_values(value, expected):
    assert reference('capital_leverage', '2026-06-30', value)['position'] == expected


@pytest.mark.parametrize('period', ['2024-12-31', '2026-09-09', '', 'invalid'])
def test_no_unreviewed_rule_period(period):
    assert reference('risk_coverage', period, 200) is None


def test_do_not_apply_broker_rules_to_other_metrics():
    assert reference('cet1_ratio', '2026-06-30', 10) is None
