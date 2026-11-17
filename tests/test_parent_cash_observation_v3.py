"""Explicit real-source acceptance for a blank comparative parent-cash table."""
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.parent_cash_observation_v3 import (
    replay_blank_safe_parent_cash_observations,
)
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import _supplement
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import build_operating_horizon_source_context


def _bindings(root):
    rels = (
        ("2025-12-31", "runtime/public-evidence/20261030-a-first/0/acquisition/receipt.json"),
        ("2026-06-30", "runtime/value-d2-600519-20261110/h12026-20261110T131035Z/receipt.json"),
    )
    return [dict(period=period, receipt_binding=dict(path=rel,
        sha256=sha256((root / rel).read_bytes()).hexdigest())) for period, rel in rels]


def test_real_600519_blank_comparatives_remain_unknown():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    root = Path(name).resolve()
    result = replay_blank_safe_parent_cash_observations(root=root, symbol="600519",
        issuer_name="贵州茅台酒股份有限公司", receipt_bindings=_bindings(root),
        now=datetime.now(timezone.utc))
    annual, interim = result["historical_statements"]
    assert result["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert result["whole_statement_reconciled"] is False
    assert annual["rows"]["cfo_cny"]["columns"][0]["value"] == "32618216666.91"
    assert interim["rows"]["gross_capex_cny"]["columns"][0]["value"] == "828735611.53"
    assert all("borrowings_received_cny" not in row["rows"] for row in (annual, interim))
    assert all("borrowings_received_cny" in row["unknown_fields"] for row in (annual, interim))
    assert len(result["gaps"]) == 4


def test_real_600519_receipt_hash_mismatch_is_rejected():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    root = Path(name).resolve()
    bindings = _bindings(root)
    bindings[1]["receipt_binding"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        replay_blank_safe_parent_cash_observations(root=root, symbol="600519",
            issuer_name="贵州茅台酒股份有限公司", receipt_bindings=bindings,
            now=datetime.now(timezone.utc))


def test_real_600519_cash_rows_reach_existing_d2_source_projection():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    root = Path(name).resolve()
    rows, sources, gaps = _supplement(root, "600519", dict(
        issuer_name="贵州茅台酒股份有限公司", parent_cash_layout="LEGACY_BLANK_SAFE_V3",
        parent_cash_observation_receipts=_bindings(root), excerpts=[]),
        datetime.now(timezone.utc))
    assert len(sources) == 2
    assert len([row for row in rows if row.get("kind") == "SOURCE_BOUND_REPORTED_STATEMENT_ROW"]) == 46
    assert any(row.get("field") == "revenue" and row.get("period") == "2025-12-31"
               and row.get("value") == "168838102514.79" for row in rows)
    assert any(row.get("field") == "revenue" and row.get("period") == "2026-06-30"
               and row.get("value") == "90703260964.48" for row in rows)
    assert any(row.get("field") == "investment_income_cash_cny"
               and row.get("value") == "49653138761.40" for row in rows)
    assert any(row.get("field") == "gross_capex_cny"
               and row.get("value") == "828735611.53" for row in rows)
    assert any(gap.get("reason", "").endswith("borrowings_received_cny") for gap in gaps)
    assert all(row.get("kind") != "FORECAST_ASSUMPTION" for row in rows)


def test_real_600519_registered_d2_context_cold_replays():
    name = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not name:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for explicit official-source replay")
    root = Path(name).resolve()
    now = datetime.now(timezone.utc)
    current = build_operating_horizon_source_context(root=root, symbol="600519", now=now)
    replayed = build_operating_horizon_source_context(root=root, symbol="600519", now=now,
        binding=current["source_binding"])
    assert current == replayed
    assert current["financial_basis"] == "2026-06-30"
    assert len(current["evidence"]) == 69
    commitments = [row for row in current["evidence"]
                   if row.get("kind") == "OFFICIAL_EXCERPT_NOT_VERIFIED_ECONOMIC_CLAIM"
                   and row.get("physical_page") in {101, 135}]
    assert {row["period"] for row in commitments} == {"2025-12-31", "2026-06-30"}
    assert all("尚未履行的认缴出资余额" in row["text"] and "30 亿元" in row["text"]
               for row in commitments)
    assert {(row["period"], row["value"]) for row in current["evidence"]
            if row.get("field") == "parent_net_profit"} == {
        ("2025-12-31", "85305341965.73"),
        ("2026-06-30", "17062381326.67")}
    assert len(current["statement_basis_gaps"]) == 4
    assert current["formal_eligibility"] is False
    assert current["action"] == "no_order"
