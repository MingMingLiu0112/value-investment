from value_investment_agent.filing_extract import extract_candidates_from_pages
import pytest


def test_interim_explicit_header_wrapped_profit_and_cashflow():
    page = ('主要会计数据和财务指标\n本报告期 上年同期 本报告期比上年同期增减\n'
            '归属于上市公司股东的净利\n润（元） 1,902,740,083.22 1,704,877,034.43 11.61%\n'
            '经营活动产生的现金流量净\n额（元） 2,999,796,790.45 3,879,790,159.07 -22.68%\n')
    rows = extract_candidates_from_pages([page])
    values = {r['field_name']: (r['value'], r['unit']) for r in rows}
    assert values['net_income'] == ('1902740083.22', 'CNY')
    assert values['operating_cash_flow'] == ('2999796790.45', 'CNY')
    assert 'net_income_yoy' not in values


def test_unrecognized_interim_header_does_not_enable_wrapped_guess():
    page = ('主要会计数据和财务指标\n预测期 上年同期 预计增减\n'
            '归属于上市公司股东的净利\n润（元） 100.00 90.00 11.11%\n')
    assert not any(r['field_name'] == 'net_income' for r in extract_candidates_from_pages([page]))


@pytest.mark.parametrize('warning', ['调整前 调整后', '重述后', '预测', '母公司'])
def test_ambiguous_interim_summary_not_accepted_even_with_matching_header(warning):
    page = ('主要会计数据和财务指标\n本报告期 上年同期 本报告期比上年同期增减\n'
            + warning + '\n归属于上市公司股东的净利润（元） 100.00 90.00 11.11%\n')
    assert not any(r['field_name'] == 'net_income' for r in extract_candidates_from_pages([page]))
