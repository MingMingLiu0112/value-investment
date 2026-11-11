"""Strict unnumbered standalone-parent profit replay from retained originals."""
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.infrastructure.filings.parent_income_basis_v2 import (
    extract_unnumbered_parent_income_facts,
)
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
    build_operating_horizon_source_context,
)
from value_investment_agent.application.research.agent_review.parent_cash_conversion_anchor_v1 import (
    historical_parent_cash_conversion,
)
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v3
from value_investment_agent.application.research.agent_review.operating_task_v2 import research_context


def _real(root, period):
    rel = ("runtime/public-evidence/20261030-a-first/0/acquisition/original.pdf"
           if period == "2025-12-31" else
           "runtime/value-d2-600519-20261110/h12026-20261110T131035Z/original-retry-2.pdf")
    original = root / rel
    return extract_pages(original, limit=100), dict(period=period,
        sha256=sha256(original.read_bytes()).hexdigest(),
        available_at="2026-11-10T00:00:00+00:00")


def test_real_600519_parent_profit_reaches_same_original_cash_anchor():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    root = Path(name).resolve()
    for period, expected in (("2025-12-31", "85305341965.73"),
                             ("2026-06-30", "17062381326.67")):
        pages, source = _real(root, period)
        result = extract_unnumbered_parent_income_facts(
            pages=pages, source=source, source_id="official-test")
        assert not result["gaps"] and len(result["evidence"]) == 1
        row = result["evidence"][0]
        assert row["value"] == expected and row["scope"] == "parent"
        assert row["field"] == "parent_net_profit" and row["pdf_sha256"] == source["sha256"]
    context = build_operating_horizon_source_context(
        root=root, symbol="600519", now=datetime.now(timezone.utc))
    assert context["action"] == "no_order" and context["formal_eligibility"] is False
    anchor = historical_parent_cash_conversion(context)
    assert anchor is not None
    assert [row["period"] for row in anchor["periods"]] == ["2025-12-31", "2026-06-30"]
    assert anchor["periods"][0]["parent_profit_cny"] == "85305341965.73"
    request = operating_horizon_draft_v3.build_request(
        research_context(context, drivers=True), [2027])
    assert "SOURCE_BOUND_HISTORICAL_PARENT_CASH_BRIDGE=" in request.user
    assert "85305341965.73" in request.user
    assert "unknown payment years" in request.system


def test_parent_income_rejects_wrong_table_unit_columns_and_partial_amounts():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    pages, source = _real(Path(name).resolve(), "2025-12-31")
    table = next(i for i, page in enumerate(pages)
                 if "母公司利润表" in page.splitlines())
    cases = (
        ("母公司利润表", "合并利润表", "UNIQUE_UNNUMBERED_PARENT_INCOME_TITLE_REQUIRED"),
        ("单位：元", "单位：万元", "UNNUMBERED_PARENT_INCOME_UNIT_OR_COLUMNS_INVALID"),
        ("2024 年度", "2023 年度", "UNNUMBERED_PARENT_INCOME_UNIT_OR_COLUMNS_INVALID"),
        ("85,305,341,965.73 76,370,303,842.59", "85,305,341,965.73",
         "PARENT_NET_PROFIT_TWO_PERIOD_AMOUNTS_REQUIRED"),
    )
    for old, new, reason in cases:
        changed = list(pages)
        assert old in changed[table]
        changed[table] = changed[table].replace(old, new, 1)
        result = extract_unnumbered_parent_income_facts(
            pages=changed, source=source, source_id="official-test")
        assert not result["evidence"] and reason in result["gaps"]
