from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_explicit_bse_summary_extracts_current_amount_not_growth():
    page = ('第三节 会计数据和财务指标\n单位：元\n'
            '2025 年 2024 年 本年比上年增减 2023 年\n'
            '营业收入 1,400,481,807.34 1,378,671,309.91 1.58% 1,503,076,483.57\n'
            '基本每股收益 1.54 1.55 -0.65% 1.95')
    records = extract_candidates_from_pages([page])
    values = {r['field_name']: r['value'] for r in records}
    assert values == {'revenue': '1400481807.34', 'eps_annual': '1.54'}
    assert all(r['status'] == 'candidate_pending_automated_verification' for r in records)
    assert next(r for r in records if r['field_name'] == 'revenue')['unit'] == 'CNY'


def test_summary_heading_mentioned_in_prose_is_not_a_table():
    page = '请参考第三节 会计数据和财务指标的分析\n单位：元\n营业收入 100 90'
    assert not extract_candidates_from_pages([page])
