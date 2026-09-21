import pytest

from value_investment_agent.historical_bvps import extract_dated_bvps


PAGE = '''本集团 2019 年度主要财务指标如下：
2019 年 2018 年 变化
期末净资产收益率 % 12.3 13.4
于 2019 年 12 月 31 日 于 2018 年 12 月 31 日 变化
每股净资产 元/股 17.69 16.48 增长 7.4%
'''


def test_explicit_dated_bvps_is_only_a_scoped_candidate():
    rows = extract_dated_bvps(['', PAGE])
    assert len(rows) == 1
    assert rows[0]['value'] == '17.69'
    assert rows[0]['period_label'] == '2019-12-31'
    assert rows[0]['page'] == 2
    assert not rows[0]['equity_scope_verified']


@pytest.mark.parametrize('restated', ['', '（重述）\n'])
def test_two_year_wrapped_dates_and_percentage_header(restated):
    page = PAGE.replace('于 2019 年 12 月 31 日 于 2018 年 12 月 31 日 变化',
                        '于 2019 年\n12 月 31 日\n于 2018 年\n12 月 31 日\n'
                        + restated + '变化\n（%）')
    page = page.replace('增长 7.4%', '(7.4)')
    row, = extract_dated_bvps([page])
    assert row['value'] == '17.69'
    assert row['comparative_restatement_columns'] == bool(restated)


@pytest.mark.parametrize('change', ['(7.4', '7.4)', '--', '7.4 9.0'])
def test_percentage_table_requires_three_valid_columns(change):
    page = PAGE.replace('日 变化', '日 变化（%）').replace('增长 7.4%', change)
    assert not extract_dated_bvps([page])


@pytest.mark.parametrize('old,new', [
    ('元/股', '百万元'), ('本集团', '母公司'), ('如下：', '预测如下：'),
    ('2019 年 12 月 31 日', '2019 年 2 月 31 日'),
    ('2018 年 12 月 31 日', '2017 年 12 月 31 日'),
    ('每股净资产', '每股有形净资产'),
])
def test_unsupported_scope_or_dates_do_not_produce_candidates(old, new):
    assert not extract_dated_bvps([PAGE.replace(old, new)])


WRAPPED = '''(二) 主要财务指标
于2020年12
月31日
于2019年12月31日
变化(%) 于2018年12月31日
每股净资产(元/股) 18.13 17.69 2.5 16.48
八、境内外会计准则下会计数据差异
按国际财务报告准则
'''


def test_wrapped_three_year_header_stops_before_accounting_reconciliation():
    rows = extract_dated_bvps([WRAPPED])
    assert len(rows) == 1
    assert rows[0]['value'] == '18.13'
    assert rows[0]['period_label'] == '2020-12-31'


@pytest.mark.parametrize('old,new', [('2019年', '2017年'), ('2018年', '2021年'),
                                   ('元/股', '万元'), ('主要财务指标', '预测主要财务指标')])
def test_wrapped_ambiguous_columns_rejected(old, new):
    assert not extract_dated_bvps([WRAPPED.replace(old, new)])


def test_comparative_restatement_columns_do_not_replace_current_value():
    page = WRAPPED.replace('每股净资产', '重述后 重述前 重述后 重述前\n每股净资产')
    page = page.replace('18.13 17.69 2.5 16.48', '18.13 17.69 17.69 2.5 16.48 16.48')
    rows = extract_dated_bvps([page])
    assert len(rows) == 1
    assert rows[0]['value'] == '18.13'
    assert rows[0]['comparative_restatement_columns'] is True


def test_unknown_restatement_layout_is_not_assumed():
    page = WRAPPED.replace('每股净资产', '重述后 重述前\n每股净资产')
    assert not extract_dated_bvps([page])


def test_single_restatement_group_with_complete_columns():
    page = WRAPPED.replace('每股净资产', '重述后 重述前\n每股净资产')
    page = page.replace('18.13 17.69 2.5 16.48', '18.13 17.69 2.5 16.48 16.47')
    row, = extract_dated_bvps([page])
    assert row['value'] == '18.13'
    assert row['comparative_restatement_groups'] == 1


@pytest.mark.parametrize('values', ['18.13 17.69', '18.13 17.69 2.5 16.48 16.48',
                                   '18.13 17.69 -- 16.48'])
def test_wrong_numeric_column_count_or_missing_values_fail(values):
    assert not extract_dated_bvps([WRAPPED.replace('18.13 17.69 2.5 16.48', values)])
