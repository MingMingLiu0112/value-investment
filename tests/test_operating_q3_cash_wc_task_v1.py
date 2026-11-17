"""Current Q3 facts and parent-only WC balances share one D2 request boundary."""
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from value_investment_agent.application.research.agent_review import (
    operating_q3_cash_source_loader_v1 as q3,
    operating_task_v2 as live,
    parent_wc_balance_request_v1 as wc_request,
)
from value_investment_agent.infrastructure.filings import parent_wc_history_600519_v1 as wc_source


NOW = datetime(2026, 11, 11, 15, 32, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_q3_loader_has_explicit_implementation_binding():
    binding = q3.implementation()
    assert q3.VERSION == "operating-q3-cash-source-loader-v1"
    assert q3.__name__ in binding
    assert any("operating_cash_policy_task_v4_q3_ocr" in name for name in binding)


def test_real_q3_and_parent_wc_sources_compose_without_cash_default():
    source_root = os.environ.get("TEST_Q3_WC_ROOT")
    if not source_root:
        pytest.skip("Set TEST_Q3_WC_ROOT to replay real public Q3/FY/H1 originals")
    root = Path(source_root)
    context = q3.load_current(root=root, symbol="600519", now=NOW)
    history = wc_source.read_parent_wc_history(root, NOW)
    enriched, request, anchor = wc_request.build_request_with_parent_wc_balance(
        live.research_context(context, drivers=True), [2027], history=history, as_of=NOW
    )
    assert context["symbol"] == history["symbol"] == "600519"
    assert len(enriched["evidence"]) == len(context["evidence"]) + 2
    assert len(anchor["historical_balance_anchors"]) == 2
    assert anchor["operating_wc_cash_cny"] == "UNKNOWN"
    assert "SOURCE_BOUND_PARENT_WC_BALANCE_RISK_ANCHOR=" in request.user
    assert "balance delta as cash flow" in request.system
