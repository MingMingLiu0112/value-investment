"""Approved-plan notice is historical evidence, never future cash eligibility."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v6 as source
from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService
from value_investment_agent.application.research.agent_review.operating_cash_policy_task_v1 import OperatingCashPolicyTaskService


def test_approved_plan_original_vote_is_bound_and_not_a_forecast(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = runtime / "resolution.pdf"
    original.write_bytes(b"TEST_ONLY original")
    url = "https://static.cninfo.com.cn/finalpage/2026-05-21/1225321219.PDF"
    receipt = dict(schema_version="bound-public-notice-v1", symbol="600887",
        issuer_name="内蒙古伊利实业集团股份有限公司", source_id="cninfo:1225321219",
        published_date="2026-05-21", source_url=url, path="runtime/resolution.pdf",
        sha256=source._hash(original.read_bytes()), acquired_at="2026-05-21T10:00:00+00:00",
        action="no_order")
    receipt_path = runtime / "receipt.json"
    receipt_path.write_bytes(source._bytes(receipt))
    selected = dict(receipt_path="runtime/receipt.json", receipt_sha256=source._hash(receipt_path.read_bytes()),
        source_id="cninfo:1225321219", published_date="2026-05-21",
        plan_period="2025-12-31",
        resolution_title="《公司未来三年（2025-2027 年）股东回报规划》")
    approved = "3、议案名称：" + selected["resolution_title"] + "\n审议结果：通过\n"
    monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *args, **kwargs: [
        "600887 内蒙古伊利实业集团股份有限公司\n" + approved])
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    row, _ = source._resolution(tmp_path, "600887", dict(issuer_name=receipt["issuer_name"]), selected, now)
    assert row["scope"] == "SHAREHOLDER_APPROVED_RETURN_PLAN"
    assert row["kind"] == "APPROVED_PLAN_NOT_FUTURE_PAYMENT_OR_CASH_CAPACITY"
    monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *args, **kwargs: [
        "600887 内蒙古伊利实业集团股份有限公司\n" + approved.replace("通过", "未通过")])
    with pytest.raises(ValueError, match="VOTE_NOT_PROVEN"):
        source._resolution(tmp_path, "600887", dict(issuer_name=receipt["issuer_name"]), selected, now)
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="ORIGINAL_CHANGED"):
        source._resolution(tmp_path, "600887", dict(issuer_name=receipt["issuer_name"]), selected, now)


def test_real_600887_approved_plan_context_cold_replay():
    root_var = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit official originals required")
    root = Path(root_var).resolve()
    now = datetime.now(timezone.utc)
    value = source.build_operating_horizon_source_context(root=root, symbol="600887", now=now)
    replay = source.build_operating_horizon_source_context(
        root=root, symbol="600887", now=now, binding=value["source_binding"])
    assert replay == value
    assert NoticeAwareTaskService._version(value["source_binding"]) == "v6"
    rows = [row for row in value["evidence"] if row.get("scope") == "SHAREHOLDER_APPROVED_RETURN_PLAN"]
    assert len(rows) == 1 and "审议结果：通过" in rows[0]["text"]
    assert value["formal_eligibility"] is False and value["action"] == "no_order"
    task = OperatingCashPolicyTaskService(root, source_loader=source.build_operating_horizon_source_context)
    request = task._request(dict(years=[2027], config=dict(max_completion_tokens_cap=4096)), value)
    assert request.max_completion_tokens == 4096
    assert rows[0]["id"] in request.user
    assert "SOURCE_BOUND_PARENT_CASH_CONVERSION_HISTORY=" in request.user
    assert "11200348776.89" in request.user
    assert "35551654301.69" in request.user
