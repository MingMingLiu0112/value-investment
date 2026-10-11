"""Synthetic ownership and period contracts, not investment approval."""
from decimal import Decimal

import pytest

from value_investment_agent.application.product.statement_equity_bridge import reconcile_statement_equity
from value_investment_agent.domain.valuation.equity_reconciliation import reconcile_equity_movements


def synthetic_bridge():
    labels = {'opening': '二、本年期初余额', 'closing': '四、本期期末余额',
        'change': '三、本期增减变动金额', 'comprehensive': '（一）综合收益总额',
        'contribution': '（二）所有者投入和减少资本', 'distribution': '（三）利润分配',
        'reserve': '（五）专项储备', 'other': '（六）其他'}
    values = {'opening': ('950', '100', '1050'), 'closing': ('1000', '110', '1110'),
        'change': ('50', '10', '60'), 'comprehensive': ('60', '10', '70'),
        'contribution': ('0', '2', '2'), 'distribution': ('-20', '-2', '-22'),
        'reserve': ('5', '0', '5'), 'other': ('5', '0', '5')}
    rows = {}
    for key, amounts in values.items():
        numbers = amounts if key != 'contribution' else amounts[1:]
        if key == 'comprehensive':
            numbers = ('-10', '70', *numbers)
        rows[key] = dict(physical_page=1, parent_value=amounts[0],
            evidence_excerpt=labels[key] + ' ' + ' '.join(f'{Decimal(v):,.2f}' for v in numbers))
    spec = dict(schema_version='consolidated-equity-statement-bridge-v1', period_end='2026-06-30',
        source_id='synthetic', unit='CNY', scope='consolidated_parent_attributable', header_page=1,
        rows=rows, comprehensive_components=dict(parent_profit_cny='70', parent_oci_cny='-10'))
    header = '合并所有者权益变动表\n2026年1—6月\n归属于母公司所有者权益\n少数股东权益 所有者权益合计\n单位：元 币种：人民币'
    pages = {'synthetic': [header + '\n' + '\n'.join(row['evidence_excerpt'] for row in rows.values())]}
    return spec, pages


def calculate(spec, pages):
    def verify(source, page, text):
        if ''.join(text.split()) not in ''.join(pages[source][page-1].split()):
            raise ValueError('synthetic original excerpt mismatch')
    return reconcile_statement_equity(spec=spec, period_end='2026-06-30', expected_equity=Decimal('1000'),
        current_source_id='synthetic', pages=pages, verify_excerpt=verify)


def test_historical_accounting_closes_without_approving_future_behavior():
    spec, pages = synthetic_bridge()
    result = calculate(spec, pages)
    assert result['unexplained_difference_cny'] == '0'
    assert Decimal(result['naive_profit_distribution_equity_cny']) == 1000
    assert result['ownership_amounts']['closing']['minority'] == '110.00'
    assert result['action'] == 'no_order'
    assert not any(result[key] for key in ('future_clean_surplus_assumption_approved',
                                         'sustainable_distribution_approved', 'normalized_profit_approved'))


@pytest.mark.parametrize('change', ['scope', 'unit', 'source', 'period', 'minority-as-parent',
                                  'wrong-page', 'missing-row', 'altered-excerpt', 'reported-profit', 'oci-sign'])
def test_wrong_ownership_and_bound_rows_cannot_close_equity(change):
    spec, pages = synthetic_bridge()
    if change in {'scope', 'unit', 'source', 'period'}:
        spec[{'source': 'source_id', 'period': 'period_end'}.get(change, change)] = 'wrong'
    elif change == 'minority-as-parent':
        spec['rows']['closing']['parent_value'] = '110'
    elif change == 'wrong-page':
        spec['rows']['closing']['physical_page'] = 3
    elif change == 'missing-row':
        del spec['rows']['other']
    elif change == 'altered-excerpt':
        spec['rows']['distribution']['evidence_excerpt'] += ' 1.00'
    else:
        spec['comprehensive_components']['parent_profit_cny' if change == 'reported-profit' else 'parent_oci_cny'] = '80'
    with pytest.raises(ValueError):
        calculate(spec, pages)


def test_plausible_wrong_period_table_is_rejected():
    spec, pages = synthetic_bridge()
    pages['synthetic'][0] = pages['synthetic'][0].replace('2026年1—6月', '2025年1—6月')
    with pytest.raises(ValueError, match='header'):
        calculate(spec, pages)


def test_omitted_movement_is_not_a_zero_fact():
    spec, pages = synthetic_bridge()
    pages['synthetic'][0] = pages['synthetic'][0].replace('（六）其他 5.00 0.00 5.00', '（六）其他 0.00 0.00 0.00')
    spec['rows']['other'].update(parent_value='0', evidence_excerpt='（六）其他 0.00 0.00 0.00')
    with pytest.raises(ValueError, match='movements'):
        calculate(spec, pages)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_arithmetic_rejects_nonfinite_financial_amounts(value):
    spec, pages = synthetic_bridge()
    result = calculate(spec, pages)
    amounts = {key: {scope: Decimal(amount) for scope, amount in row.items()}
               for key, row in result['ownership_amounts'].items()}
    amounts['opening']['parent'] = Decimal(value)
    with pytest.raises(ValueError, match='finite'):
        reconcile_equity_movements(amounts=amounts, expected_equity=Decimal('1000'), profit=Decimal('70'), oci=Decimal('-10'))


@pytest.mark.parametrize('change', [None, 'applicable', 'old-period'])
def test_treasury_disclosure_is_scoped_to_the_current_report(change):
    spec, pages = synthetic_bridge()
    note = '56、库存股 □适用 √不适用'
    pages['synthetic'].append('2026年半年度报告\n' + note)
    spec['treasury_disclosure'] = dict(physical_page=2, evidence_excerpt=note)
    if change == 'applicable':
        spec['treasury_disclosure']['evidence_excerpt'] = '56、库存股 √适用 □不适用'
        pages['synthetic'][1] = '2026年半年度报告\n' + spec['treasury_disclosure']['evidence_excerpt']
    elif change == 'old-period':
        pages['synthetic'][1] = pages['synthetic'][1].replace('2026', '2025')
    if change is None:
        result = calculate(spec, pages)
        assert result['treasury_disclosure']['status'].startswith('H1_DISCLOSED_NOT_APPLICABLE')
    else:
        with pytest.raises(ValueError):
            calculate(spec, pages)
