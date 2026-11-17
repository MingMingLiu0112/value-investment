"""The retained 600887 original is the positive fixture; all pages are replayed."""

from hashlib import sha256
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.infrastructure.filings.quarterly_parent_operating_facts import (
    build_quarterly_parent_operating_observations,
    parse_quarterly_parent_operating_facts,
)


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "runtime/value-d2-600887-20261115-q3/1225644500.pdf"
SHA256 = "e165e6ee19441a1c0a59199991016bbf78098073981c469f3432e533cb3ce7a0"
ISSUER = "内蒙古伊利实业集团股份有限公司"
ARGS = {"symbol": "600887", "issuer_name": ISSUER, "period_end": "2026-09-30"}


@pytest.fixture(scope="module")
def pages():
    assert sha256(PDF.read_bytes()).hexdigest() == SHA256
    result = extract_pages(PDF)
    assert len(result) == 15
    return result


def test_full_original_parent_income_and_cash_positive(pages):
    facts = parse_quarterly_parent_operating_facts(pages, **ARGS)
    assert facts["scope"] == "ISSUER_PARENT_STANDALONE"
    assert facts["period_basis"] == "YTD_9M"
    assert facts["currency"] == "CNY"
    assert {key: (row["current"], row["comparative"], row["physical_page"])
            for key, row in facts["fields"].items()} == {
                "revenue": ("85092248709.66", "82629405489.25", 13),
                "cost": ("60171113619.92", "59327889043.07", 13),
                "net_profit": ("11224391992.81", "10706315706.21", 13),
            }
    result = build_quarterly_parent_operating_observations(pages, **ARGS)
    assert [row["period_end"] for row in result] == ["2026-09-30", "2025-09-30"]
    assert [row["period_start"] for row in result] == ["2026-01-01", "2025-01-01"]
    assert [row["cfo"] for row in result] == ["39649908007.27", "11110910149.55"]
    assert [row["customer_cash"] for row in result] == ["86598684465.44", "80433948590.47"]
    assert [row["supplier_cash"] for row in result] == ["37294783977.28", "60220357917.43"]
    assert all(row["classification"] == "FACT" and row["source_binding_required"]
               and {ref["physical_page"] for ref in row["source_refs"]} == {13, 14}
               and row["action"] == "no_order" for row in result)


@pytest.mark.parametrize("mutate,error", [
    (lambda p: p.__setitem__(12, p[12].replace("母公司利润表", "合并利润表")),
     "INCOME_STATEMENT_REQUIRED"),
    (lambda p: p.__setitem__(12, p[12].replace("单位：元", "单位：万元")),
     "COLUMNS_SCOPE_OR_CURRENCY_INVALID"),
    (lambda p: p.__setitem__(12, p[12].replace("一、营业收入 85,092", "一、其他收入 85,092")),
     "ROW_MISSING_OR_AMBIGUOUS:revenue"),
    (lambda p: p.__setitem__(12, p[12] + "\n" + next(
        line for line in p[12].splitlines() if "85,092,248,709.66" in line)),
     "ROW_MISSING_OR_AMBIGUOUS:revenue"),
    (lambda p: p.__setitem__(12, p[12].replace(ISSUER, "错误发行人")),
     "COLUMNS_SCOPE_OR_CURRENCY_INVALID"),
    (lambda p: p.__setitem__(13, p[13].replace("母公司现金流量表", "合并现金流量表")),
     "PARENT_QUARTER_STATEMENT_REQUIRED"),
])
def test_reject_missing_or_conflicting_parent_rows(pages, mutate, error):
    changed = list(pages)
    mutate(changed)
    with pytest.raises(ValueError, match=error):
        build_quarterly_parent_operating_observations(changed, **ARGS)


def test_reject_wrong_report_identity_and_period(pages):
    with pytest.raises(ValueError, match="COVER_MISMATCH"):
        parse_quarterly_parent_operating_facts(pages, **{**ARGS, "symbol": "600519"})
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        parse_quarterly_parent_operating_facts(pages, **{**ARGS, "period_end": "2026-06-30"})
