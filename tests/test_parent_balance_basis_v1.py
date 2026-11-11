from value_investment_agent.infrastructure.filings.parent_balance_basis_v1 import extract_parent_balance_facts


SOURCE = dict(period="2025-12-31", sha256="a" * 64,
              available_at="2026-04-25T00:00:00+08:00")


def _extract(pages):
    return extract_parent_balance_facts(
        pages=pages, source=SOURCE, source_id="official",
        issuer_name="示例股份有限公司")


def test_parent_rows_only_and_exact_current_column():
    pages = ["合并资产负债表\n货币资金 999.00 999.00\n盈余公积 999.00 999.00\n"
             "母公司资产负债表\n2025年12月31日\n编制单位：示例股份有限公司\n"
             "单位：元币种：人民币\n2025年12月31日 2024年12月31日\n"
             "货币资金 858,513,233.12 1,111,936,322.48\n",
             "实收资本（或股本） 七、40 815,347,146.00 815,347,146.00\n"
             "盈余公积 500,055,954.09 500,055,954.09\n"
             "未分配利润 2,873,877,496.76 2,449,927,439.12\n合并利润表"]
    result = _extract(pages)
    assert not result["gaps"]
    assert {row["field"]: row["value"] for row in result["evidence"]} == {
        "parent_cash_balance": "858513233.12",
        "parent_ordinary_share_capital": "815347146.00",
        "parent_surplus_reserve": "500055954.09",
        "parent_retained_earnings": "2873877496.76",
    }
    assert all(row["scope"] == "parent" for row in result["evidence"])


def test_missing_or_ambiguous_parent_row_does_not_admit_consolidated_value():
    pages = ["合并资产负债表\n货币资金 999.00 999.00\n"
             "母公司资产负债表\n2025年12月31日\n编制单位：示例股份有限公司\n"
             "单位：元币种：人民币\n2025年12月31日 2024年12月31日\n"
             "货币资金 111.00 100.00\n货币资金 112.00 100.00\n合并利润表"]
    result = _extract(pages)
    assert not result["evidence"]
    assert "UNIQUE_PARENT_BALANCE_ROW_REQUIRED:parent_cash_balance" in result["gaps"]


def test_wrong_issuer_or_unit_rejects_table():
    page = ("母公司资产负债表\n2025年12月31日\n编制单位：其他公司\n"
            "单位：万元币种：人民币\n2025年12月31日 2024年12月31日\n"
            "货币资金 111.00 100.00\n合并利润表")
    result = _extract([page])
    assert not result["evidence"]
    assert result["gaps"] == ["PARENT_BALANCE_OWNER_UNIT_OR_COLUMNS_INVALID"]


def test_interim_current_and_prior_columns_are_distinct():
    pages = ["母公司资产负债表\n2026年6月30日\n编制单位：示例股份有限公司\n"
             "单位：元币种：人民币\n项目 2026年6月30日 2025年12月31日\n"
             "货币资金 600,768,219.73 858,513,233.12\n",
             "盈余公积 500,055,954.09 500,055,954.09\n"
             "未分配利润 2,880,231,868.02 2,873,877,496.76\n"
             "实收资本（或股本） 815,347,146.00 815,347,146.00\n合并利润表"]
    source = {**SOURCE, "period": "2026-06-30"}
    result = extract_parent_balance_facts(
        pages=pages, source=source, source_id="official",
        issuer_name="示例股份有限公司")
    assert not result["gaps"]
    cash = next(row for row in result["evidence"] if row["field"] == "parent_cash_balance")
    assert (cash["value"], cash["period_basis"]) == ("600768219.73", "H1")
