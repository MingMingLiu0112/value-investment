"""Real official parent-profit replay and strict printed-table negatives."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os

import pytest

from value_investment_agent.infrastructure.filings.parent_income_basis_v1 import (
    extract_numbered_parent_income_facts,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
    build_operating_horizon_source_context,
)


def _official(root, folder, period):
    original = root / "runtime/value-d2-000568-20261110" / folder / "original.pdf"
    return extract_pages(original, limit=100), dict(period=period,
        sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        available_at="2026-11-10T00:00:00+00:00")


def test_real_parent_profit_is_separate_from_group_attributable_profit():
    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    root = Path(os.environ["VALUE_REAL_SOURCE_ROOT"])
    expected = (("fy2025", "2025-12-31", "8301545374.90"),
                ("h12026", "2026-06-30", "616197261.26"))
    for folder, period, profit in expected:
        pages, source = _official(root, folder, period)
        result = extract_numbered_parent_income_facts(pages=pages, source=source,
            source_id="official-test")
        assert not result["gaps"] and len(result["evidence"]) == 1
        row = result["evidence"][0]
        assert row["value"] == profit and row["scope"] == "parent"
        assert row["field"] == "parent_net_profit" and row["pdf_sha256"] == source["sha256"]
    context = build_operating_horizon_source_context(root=root, symbol="000568",
        now=datetime.now(timezone.utc))
    assert {(row["period"], row["value"]) for row in context["evidence"]
            if row.get("field") == "parent_net_profit"} == {
                (period, profit) for _, period, profit in expected}
    assert context["action"] == "no_order" and context["formal_eligibility"] is False
    commitment = [row for row in context["evidence"]
                  if row["id"] == "cninfo:1225501255:horizon-p129"]
    assert len(commitment) == 1
    assert commitment[0]["period"] == "2026-06-30"
    assert commitment[0]["pdf_sha256"] == source["sha256"]
    assert "资产负债表日存在的重要承诺\r\n无。" in commitment[0]["text"]
    assert commitment[0]["unit"] == "TEXT" and "value" not in commitment[0]


def test_parent_income_rejects_consolidated_title_unit_and_printed_amount_gap():
    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    pages, source = _official(Path(os.environ["VALUE_REAL_SOURCE_ROOT"]), "fy2025", "2025-12-31")
    title = next(i for i, page in enumerate(pages) if "4、母公司利润表" in page)
    changed = list(pages)
    changed[title] = changed[title].replace("4、母公司利润表", "4、合并利润表")
    result = extract_numbered_parent_income_facts(pages=changed, source=source, source_id="official-test")
    assert not result["evidence"] and "UNIQUE_NUMBERED_PARENT_INCOME_TITLE_REQUIRED" in result["gaps"]
    changed = list(pages)
    changed[title] = changed[title].replace("单位：元", "单位：万元")
    result = extract_numbered_parent_income_facts(pages=changed, source=source, source_id="official-test")
    assert not result["evidence"] and "NUMBERED_PARENT_INCOME_UNIT_OR_COLUMNS_INVALID" in result["gaps"]
    changed = list(pages)
    changed[title + 1] = changed[title + 1].replace(
        "8,301,545,374.90 11,298,498,996.31", "8,301,545,374.90")
    result = extract_numbered_parent_income_facts(pages=changed, source=source, source_id="official-test")
    assert not result["evidence"] and "PARENT_NET_PROFIT_TWO_PERIOD_AMOUNTS_REQUIRED" in result["gaps"]
