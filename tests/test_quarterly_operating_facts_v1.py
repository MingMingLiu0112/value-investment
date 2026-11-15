"""Bounded quarterly parser; real originals require explicit public-source opt-in."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.quarterly_operating_facts_v1 import (
    CASH_FIELDS, FIELDS, parse_quarterly_operating_facts,
)


def sample():
    values = {"pre_tax_profit": "100.00", "tax": "20.00",
              "group_profit": "80.00", "parent_profit": "75.00", "nci": "5.00"}
    income = "".join(label + values.get(field, "10.00") + " " +
                     values.get(field, "10.00") for field, label in FIELDS.items())
    cash = "".join(label + "10.00 10.00" for label in CASH_FIELDS.values())
    return [
        "测试股份有限公司2026年第三季度报告 证券代码：123456 公告正文",
        "测试股份有限公司2026年第三季度报告 "
        "1、合并资产负债表 编制单位：测试股份有限公司 2026年09月30日 "
        "单位：元 项目期末余额期初余额",
        "2、合并年初到报告期末利润表 单位：元 项目本期发生额上期发生额" + income,
        "3、合并年初到报告期末现金流量表 单位：元 项目本期发生额上期发生额" + cash,
    ]


def parse(pages, symbol="123456", basis=None):
    return parse_quarterly_operating_facts(pages, symbol=symbol, currency_basis=(
        {"currency": "CNY", "evidence_refs": ["TEST_ONLY_INDEPENDENT_CURRENCY"]}
        if basis is None else basis))


def test_supported_period_and_verbatim_rows():
    pages = sample()
    result = parse(pages)
    assert result["period_end"] == "2026-09-30"
    assert result["comparative_end"] == "2025-09-30"
    assert result["action"] == "no_order" and not result["formal_eligibility"]
    for row in result["fields"].values():
        assert row["excerpt"] in pages[row["physical_page"] - 1]


@pytest.mark.parametrize("damage", [
    "cover_year", "second_title", "body_title", "statement_year",
    "statement_day", "missing_statement_date", "duplicate_statement_date",
])
def test_period_conflicts_or_unsupported_date_fail_closed(damage):
    pages = sample()
    if damage == "cover_year":
        pages[0] = pages[0].replace("2026", "2027")
    elif damage == "second_title":
        pages[0] += "2025年第三季度报告"
    elif damage == "body_title":
        pages[1] = pages[1].replace("2026年第三季度报告", "2025年第三季度报告")
    elif damage == "statement_year":
        pages[1] = pages[1].replace("2026年09月30日", "2025年09月30日")
    elif damage == "statement_day":
        pages[1] = pages[1].replace("2026年09月30日", "2026年06月30日")
    elif damage == "missing_statement_date":
        pages[1] = pages[1].replace("2026年09月30日", "")
    else:
        pages.append("合并资产负债表2026年09月30日")
    with pytest.raises(ValueError, match="QUARTERLY_(TITLE|STATEMENT_PERIOD)"):
        parse(pages)


def test_title_alias_and_prior_year_comparative_not_conflicts():
    pages = [p.replace("第三季度报告", "三季度报告") for p in sample()]
    pages[1] += "上年同期为2025年1月至9月"
    assert parse(pages)["period_end"] == "2026-09-30"


@pytest.mark.parametrize("damage", ["symbol", "summary", "unit", "nci", "currency", "missing_cfo"])
def test_existing_identity_currency_and_arithmetic_guards(damage):
    pages = sample()
    basis = None
    if damage == "symbol":
        pages[0] = pages[0].replace("123456", "654321")
    elif damage == "summary":
        pages[0] += "摘要"
    elif damage == "unit":
        pages = [p.replace("单位：元", "单位：万元") for p in pages]
    elif damage == "nci":
        pages[2] = pages[2].replace("2.少数股东损益5.00", "2.少数股东损益6.00")
    elif damage == "currency":
        basis = {"currency": "CNY", "evidence_refs": []}
    else:
        pages[3] = pages[3].replace("经营活动产生的现金流量净额", "缺项")
    with pytest.raises(ValueError):
        parse(pages, basis=basis)


@pytest.fixture(scope="module")
def real_pages():
    configured = os.environ.get("QUARTERLY_OPERATING_REAL_ROOT")
    if configured is None:
        if os.environ.get("QUARTERLY_OPERATING_REAL_REQUIRED") == "1":
            pytest.fail("QUARTERLY_OPERATING_REAL_ROOT required")
        pytest.skip("Explicit retained public originals required")
    assert configured.strip(), "Explicit source root cannot be empty"
    root = Path(configured).resolve(strict=True)
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    folder = root / "runtime/value-000568-current-alignment-20261101"
    receipt = json.loads((folder / "source-receipt.json").read_bytes())
    rows = [r for r in receipt["records"] if r["source_id"] == "cninfo:1225639079"]
    assert len(rows) == 1 and rows[0]["status"] == "ACQUIRED"
    source = rows[0]
    path = root / source["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    h1root = root / "runtime/e2-first-input-000568-20261031"
    h1source = json.loads((h1root / "receipt.json").read_bytes())["source"]
    h1path = root / h1source["path"]
    assert hashlib.sha256(h1path.read_bytes()).hexdigest() == h1source["sha256"]
    h1pages = extract_pages(h1path)
    assert "以人民币为记账本位币" in h1pages[55]
    basis = {"currency": "CNY", "evidence_refs": [
        {"path": h1source["path"], "sha256": h1source["sha256"], "physical_page": 56}]}
    pages = extract_pages(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    return pages, basis


def test_real_report_and_original_two_period_counterexamples(real_pages):
    pages, basis = real_pages
    result = parse(pages, "000568", basis)
    assert result["period_end"] == "2026-09-30" and len(result["fields"]) == 16
    for key, value, page in [
        ("revenue", "14667616562.73", 8), ("parent_profit", "5671059241.53", 9),
        ("cfo", "4445413276.27", 10), ("cash_capex", "947762368.34", 11),
    ]:
        row = result["fields"][key]
        assert row["current"] == value and row["physical_page"] == page
    for row in result["fields"].values():
        assert row["excerpt"] in pages[row["physical_page"] - 1]
    for damage in ("cover_year", "second_title"):
        changed = deepcopy(pages)
        if damage == "cover_year":
            changed[0] = changed[0].replace("2026", "2027")
        else:
            changed[0] += "\n2025年第三季度报告"
        with pytest.raises(ValueError, match="QUARTERLY_TITLE"):
            parse(changed, "000568", basis)



def test_explicit_quarterly_table_retains_source_rows_and_rejects_reversed_columns():
    from value_investment_agent.infrastructure.filings.quarterly_operating_facts_explicit_columns import (
        parse_explicit_columns_quarterly_facts,
    )

    original = sample()
    headings = ["2、合并年初到报告期末利润表", "3、合并年初到报告期末现金流量表"]
    labels = ["合并利润表", "合并现金流量表"]
    columns = "项目 2026 年前三季度（1-9 月） 2025 年前三季度（1-9 月）"
    table_header = "\n2026 年 1—9 月\n编制单位：测试股份有限公司\n单位：元 币种：人民币 审计类型：未经审计\n"
    pages = original[:2] + [
        page.replace(heading + " 单位：元 项目本期发生额上期发生额", label + table_header + columns + "\n")
        for page, heading, label in zip(original[2:], headings, labels, strict=True)
    ] + ["母公司资产负债表\n"]
    basis = {"currency": "CNY", "evidence_refs": ["TEST_ONLY"]}
    result = parse_explicit_columns_quarterly_facts(pages, symbol="123456", currency_basis=basis)
    assert set(result["fields"]) == set(FIELDS) | set(CASH_FIELDS)
    for row in result["fields"].values():
        assert row["excerpt"] in pages[row["physical_page"] - 1]
    pages[3] = pages[3].replace(columns, "项目 2025 年前三季度（1-9 月） 2026 年前三季度（1-9 月）")
    with pytest.raises(ValueError, match="EXPLICIT_QUARTERLY_YTD_COLUMNS_NOT_VERIFIED"):
        parse_explicit_columns_quarterly_facts(pages, symbol="123456", currency_basis=basis)
