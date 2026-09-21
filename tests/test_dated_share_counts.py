import pytest
from value_investment_agent.historical_bvps import extract_dated_share_counts


def test_explicit_year_end_share_count_preserves_date_and_unit():
    row, = extract_dated_share_counts(['截至2024年12月31日，公司总股本为125,619.78万股。'])
    assert row['value'] == '1256197800.00'
    assert row['period_label'] == '2024-12-31'
    assert row['unit'] == 'shares'


@pytest.mark.parametrize('text', [
    '截至2025年3月31日，公司总股本为1,256,197,800股。',
    '截至2024年12月31日，公司总股本为125,619.78万元。',
    '截至2024年12月31日，公司总股本扣除回购专户后为125,619.78万股。',
    '截至2024年12月31日，公司总股本为0股。',
])
def test_no_wrong_date_currency_or_dividend_denominator(text):
    assert not extract_dated_share_counts([text])
