from value_investment_agent.filing_extract import extract_candidates_from_pages


def pages(next_text='债\n其他流动负债 100.00 90.00', title='合并资产负债表'):
    return [title + '\n单位：元\n一年内到期的非流动负 七、43 468,249,668.22 503,078,639.77',
            '测试公司2025 年年度报告\n81 / 281\n' + next_text]


def test_cross_page_final_character_retains_both_pages():
    rows = extract_candidates_from_pages(pages())
    row = next(r for r in rows if r['field_name'] == 'current_portion_long_term_debt')
    assert row['value'] == '468249668.22'
    assert row['page'] == 1
    assert 'PDF第2页' in row['excerpt']
    assert '七、43' in row['excerpt']


def test_missing_continuation_does_not_guess_label():
    assert extract_candidates_from_pages(pages('其他流动负债 100.00 90.00')) == []


def test_parent_scope_stays_excluded():
    assert extract_candidates_from_pages(pages(title='母公司资产负债表')) == []


def test_continuation_after_other_content_is_not_joined():
    assert extract_candidates_from_pages(pages('母公司资产负债表\n债')) == []


def test_truncated_row_not_at_page_end_is_not_joined():
    texts = pages()
    texts[0] += '\n其他流动负债 100.00 90.00'
    assert extract_candidates_from_pages(texts) == []
