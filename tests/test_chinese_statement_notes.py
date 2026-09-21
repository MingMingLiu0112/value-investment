from value_investment_agent.filing_extract import extract_candidates_from_pages
import pytest


@pytest.mark.parametrize('note', ['七、45', '七、 45', '七、45（1）'])
def test_delimited_note_is_not_borrowing_amount(note):
    pages = ['合并资产负债表\n单位：元\n长期借款 ' + note +
             ' 172,310,624,303.31 158,815,759,451.94']
    rows = extract_candidates_from_pages(pages)
    assert [(r['field_name'], r['value']) for r in rows] == [
        ('long_term_borrowings', '172310624303.31')]


def test_delimited_note_does_not_enable_parent_balance():
    assert extract_candidates_from_pages(['母公司资产负债表\n单位：元\n长期借款 七、45 123.45 100.00']) == []


def test_amount_without_note_is_retained():
    rows = extract_candidates_from_pages(['合并资产负债表\n单位：元\n长期借款 172,310,624,303.31 158,815,759,451.94'])
    assert rows[0]['value'] == '172310624303.31'


def test_chinese_note_reference_is_not_a_financial_value():
    pages = ['\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
             '\u8d27\u5e01\u8d44\u91d1 \u4e94\uff08\u4e00\uff091 634,149,047.10 283,502,522.87']
    records = extract_candidates_from_pages(pages)
    assert len(records) == 1
    assert records[0]['field_name'] == 'cash'
    assert records[0]['value'] == '634149047.10'
    assert records[0]['status'] == 'candidate_pending_automated_verification'


def test_parent_income_statement_and_continuation_are_excluded():
    pages = ['\u5408\u5e76\u5229\u6da6\u8868\n\u5355\u4f4d\uff1a\u5143\n'
             '\u8425\u4e1a\u6210\u672c \u4e94\uff08\u4e8c\uff091 938,586,553.45 948,517,513.75',
             '\u6bcd\u516c\u53f8\u5229\u6da6\u8868\n\u5355\u4f4d\uff1a\u5143\n'
             '\u8425\u4e1a\u6210\u672c \u5341\u516d\uff08\u4e8c\uff091 556,546,108.69 536,454,335.03',
             '\u8425\u4e1a\u6210\u672c 123.00 100.00']
    records = extract_candidates_from_pages(pages)
    assert [(r['page'], r['value']) for r in records] == [(1, '938586553.45')]
