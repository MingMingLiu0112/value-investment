import pytest

from value_investment_agent.filing_extract import extract_candidates_from_pages


PREVIOUS = '六、主要会计数据和财务指标\n2015 年 2014 年 本年比上年增减\n'
NEXT = '''美的集团股份有限公司 2015 年年度报告
10
基本每股收益（元/股） 2.99 2.49
稀释每股收益（元/股） 2.99 2.49
加权平均净资产收益率 29.06% 29.49%
2015 年末 2014 年末
用最新股本计算的全面摊薄每股收益（元/股） 2.98
八、分季度主要财务指标
'''


def test_adjacent_summary_retains_actual_page_and_header_evidence():
    rows = extract_candidates_from_pages([PREVIOUS, NEXT])
    assert {r['field_name']: r['value'] for r in rows} == {
        'eps_annual': '2.99', 'roe': '29.06'}
    assert all(r['page'] == 2 and r['header_page'] == 1 for r in rows)
    assert all('2.98' not in r['excerpt'] for r in rows)


@pytest.mark.parametrize('previous', [
    PREVIOUS.replace('2015 年 2014 年', '2014 年 2015 年'),
    PREVIOUS + '\n七、其他资料', PREVIOUS + '\n季度',
    PREVIOUS + '\n母公司', PREVIOUS + '\n预测',
])
def test_no_unsafe_header_carry(previous):
    assert not extract_candidates_from_pages([previous, NEXT])


def test_no_carry_across_nonadjacent_pages():
    assert not extract_candidates_from_pages([PREVIOUS, '其他内容', NEXT])


def test_roe_only_continuation_with_dashed_page_number():
    next_page = '2016 年年度报告\n- 9 -\n加权平均净资产收益率 26.88% 29.06%\n2016 年末 2015 年末'
    rows = extract_candidates_from_pages([PREVIOUS.replace('2015 年 2014 年', '2016 年 2015 年'), next_page])
    assert [(r['field_name'], r['value']) for r in rows] == [('roe', '26.88')]
    assert rows[0]['header_page'] == 1


def test_deducted_eps_continuation_never_promotes_eps_or_deducted_roe():
    next_page = '2018 年年度报告\n6 / 112\n扣除非经常性损益后的基本每\n股收益（元／股） 28.33 21.67\n加权平均净资产收益率（%） 34.46 32.95\n扣除非经常性损益后的加权平均净资产收益率（%） 34.84 33.13\n八、境内外会计准则差异'
    rows = extract_candidates_from_pages([PREVIOUS.replace('2015 年 2014 年', '2018 年 2017 年'), next_page])
    assert [(r['field_name'], r['value']) for r in rows] == [('roe', '34.46')]
