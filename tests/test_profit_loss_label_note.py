import pytest

from value_investment_agent.filing_extract import _number_after_label, extract_candidates_from_pages


@pytest.mark.parametrize('dash', ['-', '—', '－'])
def test_explicit_profit_loss_note_before_amount(dash):
    text = '归属于母公司股东的净利润\n（净亏损以“' + dash + '”号填列） 195,202,027.43 248,519,109.21'
    result = _number_after_label(text, '归属于母公司股东的净利润', monetary=True, wrapped_label=True)
    assert result[0] == '195202027.43'


def test_arbitrary_parenthesis_not_skipped():
    text = '归属于母公司股东的净利润（预测金额） 195,202,027.43 248,519,109.21'
    assert _number_after_label(text, '归属于母公司股东的净利润', monetary=True, wrapped_label=True) is None


@pytest.mark.parametrize('newline', ['\n', '\r\r\n'])
def test_wrapped_note_in_consolidated_continuation(newline):
    pages = ['合并利润表\n单位：元\n项目 2026 年半年度 2025 年半年度',
             '1.归属于母公司股东的净利润（净亏损以“—”号' + newline
             + '填列）' + newline + '5,901,665,221.78 226,923,357.58']
    rows = extract_candidates_from_pages(pages)
    profit = [row for row in rows if row['field_name'] == 'net_income']
    assert len(profit) == 1
    assert (profit[0]['value'], profit[0]['unit'], profit[0]['page']) == ('5901665221.78', 'CNY', 2)
    assert profit[0]['status'] == 'candidate_pending_automated_verification'


def test_wrapped_note_does_not_enable_parent_only_statement():
    pages = ['母公司利润表\n单位：元\n归属于母公司股东的净利润（净亏损以“—”号\n填列） 5,901,665,221.78 226,923,357.58']
    assert extract_candidates_from_pages(pages) == []


def test_wrapped_arbitrary_note_is_not_skipped():
    text = '归属于母公司股东的净利润（净亏损以“—”号\n预测填列） 5,901,665,221.78 226,923,357.58'
    assert _number_after_label(text, '归属于母公司股东的净利润', monetary=True, wrapped_label=True) is None
