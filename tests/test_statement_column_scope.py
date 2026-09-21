import pytest
from value_investment_agent.filing_extract import extract_candidates_from_pages


@pytest.mark.parametrize('header', [
    '项目 2018 年 12 月 31 日 2019 年 1 月 1 日 调整数',
    '2020 年（已重述）2021 年（已重述）2022 年（已重述）2023 年 2024 年',
    '2023 年 2024 年',
])
def test_noncurrent_columns_cannot_start_current_balance_scope(header):
    pages = ['合并资产负债表\n单位：元\n' + header + '\n流动资产：\n货币资金 10.00 20.00',
             '资产总计 30.00 40.00\n负债合计 5.00 6.00']
    assert extract_candidates_from_pages(pages) == []


def test_standard_statement_survives_later_adjustment_table():
    pages = ['合并资产负债表\n单位：元\n2024 年 12 月 31 日\n项目 2024 年 2023 年\n货币资金 20.00 10.00',
             '合并资产负债表\n单位：元\n项目 2023 年 12 月 31 日 2024 年 1 月 1 日 调整数\n货币资金 10.00 11.00 1.00',
             '资产总计 30.00 40.00']
    facts = extract_candidates_from_pages(pages)
    assert [(r['field_name'], r['value']) for r in facts] == [('cash', '20.00')]


def test_five_year_income_summary_not_current_operating_cost():
    pages = ['合并利润表\n单位：百万元\n2020 年 2021 年 2022 年 2023 年 2024 年\n营业收入 1 2 3 4 5\n营业成本 148,147 225,101 210,059 219,922 223,192']
    assert extract_candidates_from_pages(pages) == []


def test_adjustment_header_on_next_page_ends_scope():
    pages = ['合并资产负债表\n单位：元',
             '2021 年年度报告\n项目 2020 年 12 月 31 日 2021 年 1 月 1 日 调整数\n流动资产：\n货币资金 10.00 11.00',
             '资产总计 30.00 31.00']
    assert extract_candidates_from_pages(pages) == []
