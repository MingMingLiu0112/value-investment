import pytest

from value_investment_agent.institution_metrics import parse_tables


HEADER = ('(三) 母公司的净资本及风险控制指标\n单位：元 币种：人民币\n'
          '项目 本报告期末 上年度末\n净资本 20,118.91 18,754.81\n'
          '净资产 24,326.24 22,171.55\n净资本/各项风险准备之和（%） 235.76 220.00\n'
          '净资本/净资产（%） 82.70 84.59\n净资本/负债（%） 41.92 39.10\n')
BODY = ('某证券2026年半年度报告\n12 / 212\n净资产/负债（%） 50.69 46.23\n'
        '自营固定收益类证券/净资本（%） 188.18 208.36\n资本杠杆率（%） 21.18 19.62\n'
        '流动性覆盖率（%） 300.67 628.70\n净稳定资金率（%） 177.09 165.87\n'
        '各项风险准备之和 8,533.57 8,524.32\n八、境内外会计准则\n')


def test_adjacent_parent_table_with_percent_in_label():
    facts = parse_tables([HEADER, BODY], 'broker', '2026-06-30')
    assert {f['field_name']: f['value'] for f in facts} == {
        'capital_leverage': '21.18', 'liquidity_coverage': '300.67',
        'net_stable_funding': '177.09'}
    assert all(f['page_number'] == 2 and f['period_header_page'] == 1
               and f['statement_scope'] == '母公司（原文明确）' for f in facts)


@pytest.mark.parametrize('header,body', [
    (HEADER.replace('母公司', '子公司'), BODY),
    (HEADER.replace('本报告期末 上年度末', '上年度末 本报告期末'), BODY),
    (HEADER + '另一个表格\n', BODY),
    (HEADER, BODY.replace('净资产/负债', '净资本/负债')),
    (HEADER, BODY.replace('资本杠杆率', '八、新章节\n资本杠杆率')),
])
def test_reject_unproven_continuation(header, body):
    assert not parse_tables([header, body], 'broker', '2026-06-30')


def test_do_not_cross_empty_page():
    assert not parse_tables([HEADER, '', BODY], 'broker', '2026-06-30')
