from value_investment_agent.filing_extract import extract_annual_growth


HEADER = '2025 年 2024 年 本年比上年增减 2023 年\n'


def test_explicit_annual_growth_and_retained_basis():
    rows = extract_annual_growth(HEADER +
        '营业收入（千元） 456,451,731 407,149,600 12.11% 372,037,280\n'
        '归属于上市公司股东的净利润（千元） 43,945,411 38,537,237 14.03% 33,719,935', 9)
    assert [r['value'] for r in rows] == ['12.11', '14.03']
    assert all(r['unit'] == 'percent' and r['page'] == 9 for r in rows)
    assert all(r['status'] == 'candidate_pending_automated_verification' for r in rows)
    assert '407,149,600' in rows[0]['excerpt']


def test_ambiguous_or_inconsistent_growth_is_rejected():
    row = '营业收入 120 100 20% 90'
    assert not extract_annual_growth('2024 年 2025 年 本年比上年增减\n' + row, 1)
    assert not extract_annual_growth(HEADER + '调整前 调整后\n' + row, 1)
    assert not extract_annual_growth(HEADER + '营业收入 120 100 25% 90', 1)
    assert not extract_annual_growth(HEADER + '营业收入 120 0 20% 90', 1)
    assert not extract_annual_growth(HEADER + '营业收入 120 -100 20% 90', 1)
    assert not extract_annual_growth(HEADER + '营业总收入 120 100 20% 90', 1)


def test_negative_growth_is_valid_with_positive_base():
    assert extract_annual_growth(HEADER + '营业收入 90 100 -10% 80',1)[0]['value'] == '-10'


def test_wrapped_complete_parent_profit_label_without_using_adjusted_profit():
    page = HEADER + ('归属于上市公司股东\n的净利润（元）\n'
                     '702,615,804.90 676,188,915.08 3.91% 604,140,594.64\n'
                     '归属于上市公司股东\n的扣除非经常性损益\n的净利润（元）\n'
                     '633,571,937.01 617,412,025.92 2.62% 486,737,808.31')
    rows = extract_annual_growth(page,7)
    assert len(rows) == 1 and rows[0]['field_name'] == 'net_income_yoy'
    assert rows[0]['value'] == '3.91'
    assert not extract_annual_growth(HEADER + '归属于上市公司股东 120 100 20% 90',7)
def test_wrapped_growth_header_keeps_period_binding():
    from value_investment_agent.growth_evidence import official_growth_period_matches
    page = '2025 年 2024 年 本年比上年\n增减 2023 年\n营业收入（元） 7,108,021,024.76 7,136,130,278.47 -0.39% 8,721,543,019.15'
    rows = extract_annual_growth(page, 7)
    assert rows[0]['value'] == '-0.39'
    assert official_growth_period_matches(rows[0]['excerpt'], '2025-12-31')
    assert not official_growth_period_matches(rows[0]['excerpt'], '2024-12-31')
