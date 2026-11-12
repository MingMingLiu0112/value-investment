"""Real-source acceptance for numbered parent balances; opt in explicitly."""
from datetime import datetime, timezone
from pathlib import Path
import os

import pytest

from value_investment_agent.infrastructure.filings.parent_balance_basis_v2 import (
    extract_numbered_parent_balance_facts,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
    build_operating_horizon_source_context,
)


def _source(root, period, folder):
    import hashlib
    original = root / "runtime/value-d2-000568-20261110" / folder / "original.pdf"
    return original, dict(period=period, sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                          available_at="2026-11-10T00:00:00+00:00")


def test_real_numbered_parent_balances_and_scope():
    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    root = Path(os.environ["VALUE_REAL_SOURCE_ROOT"])
    expected = (("2025-12-31", "fy2025", "25751391606.26", "1471941963.00"),
                ("2026-06-30", "h12026", "23927192164.41", "1471901463.00"))
    for period, folder, cash, shares in expected:
        original, source = _source(root, period, folder)
        rows = extract_numbered_parent_balance_facts(pages=extract_pages(original, limit=100),
            source=source, source_id="official-test", issuer_name="泸州老窖股份有限公司")
        facts = {row["field"]: row for row in rows["evidence"]}
        assert not rows["gaps"] and len(facts) == 4
        assert facts["parent_cash_balance"]["value"] == cash
        assert facts["parent_ordinary_share_capital"]["value"] == shares
        assert all(row["scope"] == "parent" for row in facts.values())
    context = build_operating_horizon_source_context(root=root, symbol="000568",
        now=datetime.now(timezone.utc))
    assert len([row for row in context["evidence"] if row.get("field") == "parent_cash_balance"]) == 2
    narratives = {row["physical_page"]: row for row in context["evidence"]
                  if row.get("unit") == "TEXT"}
    assert set(narratives) == {31, 129, 130}
    assert "保证正常经营和长远发展" in narratives[31]["text"]
    assert "1,471,901,463" in narratives[130]["text"]
    assert all(row["pdf_sha256"] and row["receipt_binding"] for row in narratives.values())
    assert context["action"] == "no_order" and context["formal_eligibility"] is False


def test_numbered_parent_balance_rejects_wrong_table_or_columns():
    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    root = Path(os.environ["VALUE_REAL_SOURCE_ROOT"])
    original, source = _source(root, "2025-12-31", "fy2025")
    pages = extract_pages(original, limit=100)
    title = next(i for i, page in enumerate(pages) if "母公司资产负债表" in page)
    altered = list(pages)
    altered[title] = altered[title].replace("2、母公司资产负债表", "2、合并资产负债表")
    result = extract_numbered_parent_balance_facts(pages=altered, source=source,
        source_id="official-test", issuer_name="泸州老窖股份有限公司")
    assert not result["evidence"] and "UNIQUE_NUMBERED_PARENT_BALANCE_TITLE_REQUIRED" in result["gaps"]
    altered = list(pages)
    altered[title] = altered[title].replace("单位：元", "单位：万元")
    result = extract_numbered_parent_balance_facts(pages=altered, source=source,
        source_id="official-test", issuer_name="泸州老窖股份有限公司")
    assert not result["evidence"] and "NUMBERED_PARENT_BALANCE_UNIT_OR_COLUMNS_INVALID" in result["gaps"]
