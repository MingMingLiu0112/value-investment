from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_extracts_candidate_with_page_and_excerpt() -> None:
    candidates = extract_candidates_from_pages([
        "封面",
        "合并资产负债表\n货币资金 1 53,518,798,979.08 51,690,610,946.50\n短期借款 200.00",
    ])

    cash = next(candidate for candidate in candidates if candidate["field_name"] == "cash")
    assert cash["value"] == "53518798979.08"
    assert cash["page"] == 2
    assert cash["status"] == "candidate_pending_automated_verification"


def test_extracts_continuation_pages_without_repeating_the_table_title() -> None:
    candidates = extract_candidates_from_pages([
        "合并资产负债表\n货币资金 1 100.00",
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
    assert by_field["revenue"]["value"] == "91914"
    assert by_field["net_income"]["value"] == "27200"
    assert by_field["operating_cash_flow"]["value"] == "69063"
    assert by_field["eps_annual"]["unit"] == "CNY/share"
    assert by_field["roe"]["unit"] == "percent"
    assert all(candidate["status"] == "candidate_pending_automated_verification" for candidate in candidates)


def test_recognizes_bank_style_consolidated_cashflow_heading() -> None:
    candidates = extract_candidates_from_pages([
        "合并及银行现金流量表\n本集团 本银行\n"
        "经营活动产生的现金流量净额 69,063 42,495\n"
        "购建固定资产、无形资产和其他长期资产所支付的现金 16,898 16,688",
    ])

    assert {candidate["field_name"] for candidate in candidates} == {
        "operating_cash_flow", "capital_expenditure",
    }
