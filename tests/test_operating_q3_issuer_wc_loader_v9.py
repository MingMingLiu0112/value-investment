"""The optional D2 loader binds real parent balance risk evidence without cash inference."""
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from value_investment_agent.application.research.agent_review import (
    operating_horizon_task_v11_live as task,
    operating_q3_issuer_wc_loader_v9_600519 as loader,
)

NOW = datetime(2026, 11, 11, 22, 9, 33, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_unsupported_issuer_does_not_read_sources(tmp_path):
    with pytest.raises(ValueError, match="V9_PARENT_WC_IDENTITY_OR_BINDING_INVALID"):
        loader.load_current(root=tmp_path, symbol="600887", now=NOW)


def test_real_parent_balance_reaches_existing_d2_request_without_cash_default():
    source_root = os.environ.get("TEST_Q3_WC_ROOT")
    if not source_root:
        pytest.skip("Set TEST_Q3_WC_ROOT for sealed FY/H1/Q3/plan originals")
    root = Path(source_root)
    context = loader.load_current(root=root, symbol="600519", now=NOW)
    rows = [row for row in context["evidence"]
            if row.get("field") == "parent_three_line_wc_balance_change"]
    assert len(rows) == 2
    assert context["parent_wc_balance_anchor"]["operating_wc_cash_cny"] == "UNKNOWN"
    assert context["formal_eligibility"] is False
    assert context["action"] == "no_order"
    request = task.request_v11.build_annual_request(
        context, [2027], source_binding=context["source_binding"],
        max_completion_tokens=4096)
    assert all(row["id"] in request.user for row in rows)
    assert loader.load_current(root=root, symbol="600519", now=NOW,
                               binding=context["source_binding"])["snapshot_fingerprint"] == context["snapshot_fingerprint"]
    changed = dict(context["source_binding"])
    changed["parent_wc"] = dict(changed["parent_wc"], history_sha256="0" * 64)
    with pytest.raises(ValueError, match="V9_PARENT_WC_SOURCE_CHANGED"):
        loader.load_current(root=root, symbol="600519", now=NOW, binding=changed)
