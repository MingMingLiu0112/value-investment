from value_investment_agent.filing_extract import extract_candidates_from_pages


DECLARATION = '第八节 财务报告\n二、财务报表\n财务附注中报表的单位为：元'


def test_explicit_report_unit_has_page_lineage():
    rows = extract_candidates_from_pages([DECLARATION, '合并资产负债表\n货币资金 100.00 90.00'])
    assert len(rows) == 1
    assert (rows[0]['value'], rows[0]['unit'], rows[0]['unit_evidence_page']) == ('100.00', 'CNY', 1)


def test_currency_policy_is_not_an_amount_scale():
    assert extract_candidates_from_pages(['本公司的记账本位币为人民币', '合并资产负债表\n货币资金 100.00 90.00']) == []


def test_explicit_table_unit_overrides_report_unit():
    rows = extract_candidates_from_pages([DECLARATION, '合并资产负债表\n单位：万元\n货币资金 100.00 90.00'])
    assert rows[0]['value'] == '1000000.00'
    assert 'unit_evidence_page' not in rows[0]


def test_conflicting_table_units_never_fall_back():
    assert extract_candidates_from_pages([DECLARATION, '合并资产负债表\n单位：万元\n单位：元\n货币资金 100.00 90.00']) == []


def test_plain_statement_cannot_inherit_consolidated_scope_or_unit():
    rows = extract_candidates_from_pages([DECLARATION, '合并现金流量表\n经营活动产生的现金流量净额 100.00 90.00\n现金流量表\n经营活动产生的现金流量净额 50.00 40.00'])
    assert [r['value'] for r in rows] == ['100.00']
