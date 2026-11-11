"""D2 parent cash arithmetic, with real official replay when configured."""
from datetime import datetime, timezone
from pathlib import Path
import os

import pytest

from value_investment_agent.application.research.agent_review.parent_cash_conversion_anchor_v1 import (
    historical_parent_cash_conversion,
)
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
    build_operating_horizon_source_context,
)
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v6 import (
    build_operating_horizon_source_context as build_approved_plan_context,
)


def test_rejects_mixed_original_or_missing_cash_components():
    rows = [dict(id=f"TEST_ONLY:{field}", field=field, period="2025-12-31",
        period_basis="FY", scope=("parent" if field == "parent_net_profit"
                                   else "ISSUER_PARENT_STANDALONE"), unit="CNY",
        source_id="TEST_ONLY:source", pdf_sha256="a" * 64,
        available_at="2026-01-01T00:00:00+00:00", value=value)
        for field, value in (("parent_net_profit", "10"), ("cfo_cny", "8"),
                             ("gross_capex_cny", "2"))]
    anchor = historical_parent_cash_conversion({"evidence": rows})
    assert anchor["periods"][0]["cfo_less_profit_cny"] == "-2"
    assert anchor["periods"][0]["cfo_less_gross_capex_cny"] == "6"
    rows[1]["pdf_sha256"] = "b" * 64
    assert historical_parent_cash_conversion({"evidence": rows}) is None
    rows[1]["pdf_sha256"] = "a" * 64
    rows.pop()
    assert historical_parent_cash_conversion({"evidence": rows}) is None


def test_parent_statement_aliases_join_only_the_same_original():
    original = "a" * 64
    rows = [
        dict(id="TEST_ONLY:profit", field="parent_net_profit", scope="parent",
             source_id="cninfo:test", value="10"),
        dict(id="TEST_ONLY:cfo", field="parent_cfo", scope="parent",
             source_id="official:" + original, value="8"),
        dict(id="TEST_ONLY:capex", field="parent_capex", scope="parent",
             source_id="official:" + original, value="2"),
    ]
    for row in rows:
        row.update(period="2025-12-31", period_basis="FY", unit="CNY",
                   pdf_sha256=original, available_at="2026-01-01T00:00:00+00:00")
    anchor = historical_parent_cash_conversion({"evidence": rows})
    assert anchor["periods"][0]["cfo_less_profit_cny"] == "-2"
    assert anchor["periods"][0]["evidence_ids"] == [
        "TEST_ONLY:profit", "TEST_ONLY:cfo", "TEST_ONLY:capex"]
    rows[2]["pdf_sha256"] = "b" * 64
    assert historical_parent_cash_conversion({"evidence": rows}) is None
    rows[2]["pdf_sha256"] = original
    rows[2]["source_id"] = "official:" + "b" * 64
    assert historical_parent_cash_conversion({"evidence": rows}) is None


def test_real_600887_parent_cash_history_reaches_d2_request():
    root_var = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit official originals required")
    context = build_approved_plan_context(
        root=Path(root_var), symbol="600887", now=datetime.now(timezone.utc))
    anchor = historical_parent_cash_conversion(context)
    assert anchor is not None and anchor["action"] == "no_order"
    periods = {row["period"]: row for row in anchor["periods"]}
    assert set(periods) == {"2025-12-31", "2026-06-30"}
    assert periods["2025-12-31"]["parent_profit_cny"] == "11200348776.89"
    assert periods["2025-12-31"]["parent_cfo_cny"] == "7150459122.43"
    assert periods["2025-12-31"]["parent_gross_capex_cny"] == "631984543.41"
    assert periods["2026-06-30"]["parent_profit_cny"] == "9246690145.31"


def test_real_parent_cash_conversion_is_arithmetic_not_future_policy():
    if not os.environ.get("VALUE_REAL_SOURCE_ROOT"):
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    context = build_operating_horizon_source_context(
        root=Path(os.environ["VALUE_REAL_SOURCE_ROOT"]), symbol="000568",
        now=datetime.now(timezone.utc))
    anchor = historical_parent_cash_conversion(context)
    assert anchor["action"] == "no_order"
    periods = {row["period"]: row for row in anchor["periods"]}
    assert set(periods) == {"2025-12-31", "2026-06-30"}
    assert periods["2025-12-31"]["cfo_less_profit_cny"] == "-3795473694.17"
    assert periods["2026-06-30"]["cfo_less_profit_cny"] == "833614194.31"
    assert periods["2025-12-31"]["parent_gross_capex_cny"] == "652780256.66"
    assert len(periods["2025-12-31"]["evidence_ids"]) == 3
    assert "not working-capital cash" in anchor["limitation"]
