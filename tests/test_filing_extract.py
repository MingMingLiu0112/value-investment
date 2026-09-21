from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_extracts_candidate_with_page_and_excerpt() -> None:
    candidates = extract_candidates_from_pages([
        "封面",
        "合并资产负债表\n单位：元\n货币资金 1 53,518,798,979.08 51,690,610,946.50\n短期借款 200.00",
    ])

    cash = next(candidate for candidate in candidates if candidate["field_name"] == "cash")
    assert cash["value"] == "53518798979.08"
    assert cash["page"] == 2
    assert cash["status"] == "candidate_pending_automated_verification"


def test_extracts_continuation_pages_without_repeating_the_table_title() -> None:
    candidates = extract_candidates_from_pages([
        "合并资产负债表\n单位：元\n货币资金 1 100.00",
        "长期借款 200.00\n应付债券 300.00",
        "母公司资产负债表\n长期借款 999.00",
    ])

    values = {candidate["field_name"]: candidate["value"] for candidate in candidates}
    assert values == {"cash": "100.00", "long_term_borrowings": "200.00", "bonds_payable": "300.00"}


def test_extracts_annual_summary_candidates_from_bank_style_report() -> None:
    candidates = extract_candidates_from_pages([
        "主要会计数据和财务指标\n（单位：百万元）\n"
        "营业收入 91,914 97,146\n"
        "归属于上市公司股东的净利润 27,200 27,676\n"
        "经营活动产生的现金流量净额 69,063 42,495\n"
        "基本每股收益 1.62 1.62\n"
        "加权平均净资产收益率 8.32 8.84\n"
        "归属于上市公司普通股股东的每股净资产 19.84 18.97",
    ])

    by_field = {candidate["field_name"]: candidate for candidate in candidates}
    assert by_field["revenue"]["value"] == "91914000000"
    assert by_field["net_income"]["value"] == "27200000000"
    assert by_field["operating_cash_flow"]["value"] == "69063000000"
    assert by_field["eps_annual"]["unit"] == "CNY/share"
    assert by_field["roe"]["unit"] == "percent"
    assert all(candidate["status"] == "candidate_pending_automated_verification" for candidate in candidates)


def test_summary_amount_uses_issuer_disclosed_table_unit() -> None:
    candidates = extract_candidates_from_pages([
        "主要会计数据和财务指标\n单位：亿元\n营业收入 12.34\n归属于上市公司股东的净利润 1.23",
    ])

    values = {candidate["field_name"]: candidate for candidate in candidates}
    assert values["revenue"]["unit"] == "CNY"
    assert values["revenue"]["value"] == "1234000000.00"
    assert values["net_income"]["unit"] == "CNY"
    assert values["net_income"]["value"] == "123000000.00"


def test_recognizes_bank_style_consolidated_cashflow_heading() -> None:
    candidates = extract_candidates_from_pages([
        "合并及银行现金流量表\n本集团 本银行\n单位：千元\n"
        "经营活动产生的现金流量净额 69,063 42,495\n"
        "购建固定资产、无形资产和其他长期资产所支付的现金 16,898 16,688",
    ])

    assert {candidate["field_name"] for candidate in candidates} == {
        "operating_cash_flow", "capital_expenditure",
    }


def test_extracts_total_assets_liabilities_and_operating_cost() -> None:
    candidates = extract_candidates_from_pages([
        "合并资产负债表\n单位：万元\n资产总计 1,000.00\n流动负债合计 200.00\n负债合计 600.00",
        "合并利润表\n单位：万元\n营业成本 450.00",
    ])

    values = {candidate["field_name"]: candidate["value"] for candidate in candidates}
    assert values == {"total_assets": "10000000.00", "total_liabilities": "6000000.00", "operating_cost": "4500000.00"}


def test_statement_amount_without_a_declared_unit_is_not_an_automatic_candidate() -> None:
    candidates = extract_candidates_from_pages(["合并资产负债表\n资产总计 1,000.00"])

    assert candidates == []


def test_annualized_summary_roe_is_not_unannualized_roe():
    page = ('\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807\n'
            '\u8d22\u52a1\u6bd4\u7387(%)\uff08\u5e74\u5316\uff09\n'
            '\u52a0\u6743\u5e73\u5747\u51c0\u8d44\u4ea7\u6536\u76ca\u7387 13.40 13.83\n')
    assert not any(c['field_name'] == 'roe' for c in extract_candidates_from_pages([page]))


def test_bank_parenthetical_rmb_scale_and_unadjusted_profit():
    page = ('主要会计数据和财务指标\n（人民币百万元，特别注明除外）\n'
            '营业收入 178,181 169,969\n'
            '扣除非经常性损益后归属于本行股东的净利润 76,339 74,819\n'
            '归属于本行股东的净利润 76,445 74,930\n'
            '经营活动产生的现金流量净额 304,611 134,461\n')
    facts = {c['field_name']: c for c in extract_candidates_from_pages([page])}
    assert facts['revenue']['value'] == '178181000000'
    assert facts['net_income']['value'] == '76445000000'
    assert facts['operating_cash_flow']['value'] == '304611000000'
    assert all(c['unit'] == 'CNY' for c in facts.values())


def test_conflicting_amount_scales_do_not_produce_cny_candidates():
    page = '主要会计数据和财务指标\n单位：万元\n（人民币百万元，特别注明除外）\n营业收入 100.00'
    facts = extract_candidates_from_pages([page])
    assert facts[0]['unit'] == 'reported_amount'


def test_foreign_currency_parenthetical_is_not_assumed_cny():
    page = '主要会计数据和财务指标\n（美元百万元，特别注明除外）\n营业收入 100.00'
    assert extract_candidates_from_pages([page])[0]['unit'] == 'reported_amount'


def test_summary_integer_current_value_is_not_skipped_as_a_note():
    page = '主要会计数据和财务指标\n单位：百万元\n营业收入 12 99\n加权平均净资产收益率 8 15'
    facts = {c['field_name']: c for c in extract_candidates_from_pages([page])}
    assert facts['revenue']['value'] == '12000000'
    assert facts['roe']['value'] == '8'


def test_summary_explicit_parenthesized_footnote_is_supported():
    page = '主要会计数据和财务指标\n基本每股收益(1) 2.98 2.89'
    assert extract_candidates_from_pages([page])[0]['value'] == '2.98'


def test_summary_inline_units_from_midea_annual_report():
    page = ('主要会计数据和财务指标\n2025 年 2024 年 本年比上年增减\n'
            '营业收入（千元） 456,451,731 407,149,600 12.11%\n'
            '归属于上市公司股东的净利润（千元） 43,945,411 38,537,237 14.03%\n'
            '经营活动产生的现金流量净额（千元） 53,345,930 60,511,572 -11.84%\n'
            '基本每股收益（元/股） 5.80 5.44 6.62%')
    facts = {c['field_name']: c for c in extract_candidates_from_pages([page])}
    assert facts['revenue']['value'] == '456451731000'
    assert facts['net_income']['value'] == '43945411000'
    assert facts['operating_cash_flow']['value'] == '53345930000'
    assert facts['eps_annual']['value'] == '5.80'
    assert facts['eps_annual']['unit'] == 'CNY/share'


def test_summary_incompatible_inline_unit_is_rejected():
    page = '主要会计数据和财务指标\n营业收入（元/股） 100\n基本每股收益（千元） 5'
    assert extract_candidates_from_pages([page]) == []
def test_noncurrent_lease_liability_is_separate_from_current_maturities():
    pages = ['合并资产负债表\n单位：元\n一年内到期的非流动负债 18,602,410.48\n'
             '租赁负债 2,703,584.10 21,637,313.75',
             '母公司资产负债表\n单位：元\n租赁负债 16,124,482.00']
    values = {r['field_name']: r for r in extract_candidates_from_pages(pages)}
    assert values['lease_liabilities_noncurrent']['value'] == '2703584.10'
    assert values['current_portion_long_term_debt']['value'] == '18602410.48'
    assert values['lease_liabilities_noncurrent']['unit'] == 'CNY'
    assert values['lease_liabilities_noncurrent']['status'] == 'candidate_pending_automated_verification'


def test_lease_mapping_is_exact_and_does_not_change_legacy_debt_formula():
    from value_investment_agent.adapters import SinaFinancialStatementsAdapter
    from value_investment_agent.candidate_review import AUTOMATIC_FIELD_MAP
    assert SinaFinancialStatementsAdapter._exact_balance_items['lease_liabilities_noncurrent'] == '租赁负债'
    assert AUTOMATIC_FIELD_MAP['lease_liabilities_noncurrent'] == 'lease_liabilities_noncurrent'
    assert '租赁负债' not in SinaFinancialStatementsAdapter._debt_fields
def test_capex_wrapped_variant_stays_in_consolidated_statement():
    from value_investment_agent.filing_extract import extract_candidates_from_pages
    pages = [
        '合并现金流量表\n2024年1—12月\n单位：元 币种：人民币\n项目 2024年度 2023年度\n购建固定资产、无形资产和其他长期资\n产支付的现金 4,678,712,053.56 3,000,000,000.00',
        '母公司现金流量表\n单位：元 币种：人民币\n项目 2024年度 2023年度\n购建固定资产、无形资产和其他长期资产支付的现金 999.00 888.00',
    ]
    rows = [r for r in extract_candidates_from_pages(pages) if r['field_name'] == 'capital_expenditure']
    assert len(rows) == 1
    assert rows[0]['value'] == '4678712053.56'
    assert rows[0]['page'] == 1
def test_wrapped_chinese_note_reference_is_not_the_amount():
    from value_investment_agent.filing_extract import _number_after_label
    result = _number_after_label('其中：营业收入 （三十\n一） 30,921,801,316.60 26,455,335,152.99', '营业收入', monetary=True, wrapped_label=True)
    assert result[0] == '30921801316.60'
