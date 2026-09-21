import pytest

from value_investment_agent.filing_extract import extract_candidates_from_pages


PAGE = '''2014 年年度报告
5 / 97
(二) 主要财务指标
主要财务指标 2014年 2013年 本期比上年同期增减
(%) 2012年
基本每股收益（元／股） 13.44 13.25 1.41 11.65
扣除非经常性损益后的基本每股收益（元／股） 13.59 13.53 0.45 11.74
加权平均净资产收益率（%） 31.96 39.43 减少7.47个百分点 45.00
'''


def test_standalone_annual_indicators_retain_current_column():
    rows = extract_candidates_from_pages([PAGE])
    assert {r['field_name']: r['value'] for r in rows} == {
        'eps_annual': '13.44', 'roe': '31.96'}
    assert all(r['status'] == 'candidate_pending_automated_verification' for r in rows)


@pytest.mark.parametrize('bad', [
    PAGE.replace('2014年 2013年', '2013年 2014年'),
    PAGE.replace('2014年 2013年', '2014年 2012年'),
    PAGE + '\n季度数据', PAGE + '\n预测', PAGE + '\n母公司',
])
def test_ambiguous_indicator_tables_not_enabled(bad):
    assert not extract_candidates_from_pages([bad])


@pytest.mark.parametrize('number', ['(二)', '（二）', '(2)'])
def test_numbered_title_and_separate_year_header(number):
    page = (number + ' 主要财务指标\n2019年 2018年 2019年比2018年增减(%)\n'
            '基本每股收益（元/股） 2.174 2.205\n'
            '加权平均净资产收益率（%） 12.73 13.94\n'
            '期末净资产收益率（%） 12.3 13.4')
    assert {r['field_name']: r['value'] for r in extract_candidates_from_pages([page])} == {
        'eps_annual': '2.174', 'roe': '12.73'}


def test_prose_heading_is_not_a_numbered_summary_table():
    page = ('本集团2019年度主要财务指标\n2019年 2018年\n'
            '基本每股收益（元/股） 2.174 2.205')
    assert not extract_candidates_from_pages([page])
