from value_investment_agent.filing_extract import extract_candidates_from_pages


TITLE = '\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807'
LABEL = '\u7ecf\u8425\u6d3b\u52a8\u4ea7\u751f\u7684\u73b0\u91d1\u6d41\u91cf\u51c0\u989d'


def amounts(row):
    page = TITLE + '\n\u5355\u4f4d\uff1a\u5143\n2025\u5e74 2024\u5e74\n' + LABEL + '\n' + row
    return [r['value'] for r in extract_candidates_from_pages([page])
            if r['field_name'] == 'operating_cash_flow']


def test_two_column_decimal_wrap_from_600479():
    assert amounts('480,244,967.3\n7\n398,766,454.6\n0\n20.43') == ['480244967.37']


def test_two_column_integer_wrap():
    assert amounts('3,628,843,106\n.61\n3,629,804,492\n.14\n-0.03') == ['3628843106.61']


def test_space_after_decimal_point_requires_matching_previous_column():
    assert amounts('3,546,216,993. 66\n2,923,741,174. 25\n21.29') == ['3546216993.66']
    assert amounts('3,546,216,993. 66\n2,923,741,174.25\n21.29') == []
    assert amounts('3,546,216,993. 6\n2,923,741,174. 25\n21.29') == []


def test_lone_following_digit_is_ambiguous_not_permission_to_truncate():
    assert amounts('480,244,967.3\n7\n398,766,454.60') == []


def test_complete_amount_not_joined_with_next_value():
    assert amounts('480,244,967.37\n7\n398,766,454.60') == ['480244967.37']


def test_quarterly_explanation_cannot_create_annual_cashflow():
    page = TITLE + '\u7684\u8bf4\u660e\n\u5206\u5b63\u5ea6\u4e3b\u8981\u8d22\u52a1\u6570\u636e\n\u5355\u4f4d\uff1a\u4e07\u5143\n' + LABEL + ' -919,310.06 620,730.78'
    assert extract_candidates_from_pages([page]) == []


def test_annual_header_above_quarterly_table_does_not_authorize_quarterly_amount():
    page = TITLE + '\n2025\u5e74 2024\u5e74\n\u52a0\u6743\u5e73\u5747\u51c0\u8d44\u4ea7\u6536\u76ca\u7387 5.01 7.15\n'
    page += '\u4e5d\u3001 2025\u5e74\u5206\u5b63\u5ea6\u4e3b\u8981\u8d22\u52a1\u6570\u636e\n\u5355\u4f4d\uff1a\u4e07\u5143\n' + LABEL + ' -919,310.06 620,730.78'
    rows = extract_candidates_from_pages([page])
    assert not any(r['field_name'] == 'operating_cash_flow' for r in rows)
    assert any(r['field_name'] == 'roe' and r['value'] == '5.01' for r in rows)
