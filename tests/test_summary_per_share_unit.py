from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_fullwidth_per_share_unit_preserves_annual_eps_and_excerpt():
    page = ('\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807\n'
            '2024\u5e74 2023\u5e74\n'
            '\u57fa\u672c\u6bcf\u80a1\u6536\u76ca\uff08\u5143\uff0f\u80a1\uff09 68.64 59.49')
    rows = extract_candidates_from_pages([page])
    assert len(rows) == 1
    row = rows[0]
    assert row['field_name'] == 'eps_annual'
    assert row['value'] == '68.64' and row['unit'] == 'CNY/share'
    assert '\uff0f' in row['excerpt']


def test_amount_field_rejects_per_share_unit():
    page = ('\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807\n'
            '2024\u5e74 2023\u5e74\n'
            '\u8425\u4e1a\u6536\u5165\uff08\u5143\uff0f\u80a1\uff09 68.64 59.49')
    assert not extract_candidates_from_pages([page])
