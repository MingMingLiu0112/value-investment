"""Quarterly D2 source contract; real-original replay is explicit, not a CI fixture."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v5 as source
from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService


def test_quarterly_source_selection_rejects_unpinned_paths(tmp_path):
    config = tmp_path / source.CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"schema_version": "operating-quarterly-source-selection-v1",
        "action": "no_order", "cases": {"000568": {"receipt_path": "../outside.json",
        "receipt_sha256": "a" * 64, "pdf_path": "runtime/file.pdf", "pdf_sha256": "b" * 64,
        "source_id": "cninfo:123"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="CASE_NOT_CONFIGURED"):
        source._selection(tmp_path, "000568")


def test_official_quarterly_source_replays_without_annualizing_or_cash_admission():
    root_var = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit real original root required; synthetic CI is not real acceptance")
    root = Path(root_var).resolve()
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    result = source.build_operating_horizon_source_context(root=root, symbol="000568", now=now)
    reread = source.build_operating_horizon_source_context(
        root=root, symbol="000568", now=now, binding=result["source_binding"])
    assert reread == result
    rows = [row for row in result["evidence"] if row["source_id"] == "cninfo:1225639079"]
    assert len(rows) == 6 and all(row["period_basis"] == "YTD_9M" for row in rows)
    assert {(row["field"], row["period"]): row["value"] for row in rows}[("revenue", "2026-09-30")] == "14667616562.73"
    assert {(row["field"], row["period"]): row["value"] for row in rows}[("parent_profit", "2026-09-30")] == "5671059241.53"
    assert result["financial_basis"] == "2026-06-30"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"
    assert NoticeAwareTaskService._version(result["source_binding"]) == "v5"
