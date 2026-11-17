"""The original return-plan terms must be independently proven and replayable."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v7 as source
from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService
from value_investment_agent.application.research.agent_review.operating_policy_denominator_review_v1 import review_task_view
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v1 import read_d2_cash_policy_e2_input


def test_plan_requires_exact_original_issuer_terms_and_cutoff(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = runtime / "original.pdf"
    original.write_bytes(b"TEST_ONLY original")
    receipt = dict(schema_version="bound-public-notice-v1", symbol="600887",
        issuer_name="内蒙古伊利实业集团股份有限公司", source_id="cninfo:1224808850",
        published_date="2025-11-18",
        source_url="https://static.cninfo.com.cn/finalpage/2025-11-18/1224808850.PDF",
        path="runtime/original.pdf", sha256=source._hash(original.read_bytes()),
        acquired_at="2025-11-19T00:00:00+00:00", action="no_order")
    receipt_path = runtime / "receipt.json"
    receipt_path.write_bytes(source._bytes(receipt))
    selected = dict(receipt_path="runtime/receipt.json",
        receipt_sha256=source._hash(receipt_path.read_bytes()),
        source_id="cninfo:1224808850", published_date="2025-11-18", plan_period="2025-12-31")
    terms = ("在满足公司生产经营的资金需求及《公司章程》利润分配政策下，"
        "2025-2027年度，公司每年度现金分红总额占当年归属于母公司股东净利润的比例不低于75%，"
        "且每股派发现金红利金额不低于2024年度每股派发现金红利1.22元（含税）")
    monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *a, **k: [
        "600887 内蒙古伊利实业集团股份有限公司\n" + terms])
    now = datetime(2025, 11, 20, tzinfo=timezone.utc)
    row, ref = source._plan(tmp_path, "600887", receipt["issuer_name"], selected, now)
    assert row["kind"] == "PLAN_TARGET_NOT_FUTURE_CASH_OR_PAYMENT"
    assert "75%" in row["text"] and "1.22" in row["text"]
    assert ref["sha256"] == receipt["sha256"]
    with pytest.raises(ValueError, match="AFTER_CUTOFF"):
        source._plan(tmp_path, "600887", receipt["issuer_name"], selected,
                     datetime(2025, 11, 18, tzinfo=timezone.utc))
    for changed in (terms.replace("75%", "70%"), terms.replace("1.22", "1.20"),
                    terms.replace("归属于母公司股东", "母公司")):
        monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *a, text=changed, **k: [
            "600887 内蒙古伊利实业集团股份有限公司\n" + text])
        with pytest.raises(ValueError, match="TERMS_NOT_PROVEN"):
            source._plan(tmp_path, "600887", receipt["issuer_name"], selected, now)
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="ORIGINAL_CHANGED"):
        source._plan(tmp_path, "600887", receipt["issuer_name"], selected, now)


def test_real_return_plan_joins_approved_vote_without_forecast():
    root_var = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit official originals required")
    root = Path(root_var).resolve()
    now = datetime.now(timezone.utc)
    value = source.build_operating_horizon_source_context(root=root, symbol="600887", now=now)
    replay = source.build_operating_horizon_source_context(
        root=root, symbol="600887", now=now, binding=value["source_binding"])
    assert replay == value
    assert NoticeAwareTaskService._version(value["source_binding"]) == "v7"
    assert value["action"] == "no_order" and value["formal_eligibility"] is False
    plan = [row for row in value["evidence"] if row.get("scope") == "DISCLOSED_CONDITIONAL_RETURN_PLAN"]
    approved = [row for row in value["evidence"] if row.get("scope") == "SHAREHOLDER_APPROVED_RETURN_PLAN"]
    assert len(plan) == len(approved) == 1
    assert plan[0]["physical_page"] == 2 and "75%" in plan[0]["text"]
    assert "审议结果：通过" in approved[0]["text"]


def test_approved_plan_profit_denominator_conflict_is_not_consumable(tmp_path):
    def task(rationale):
        return {"research_result": {"years": {"2027": {"shareholder_cash_paths": {
            "base": {"terms": {"target_payout_ratio": {
                "classification": "FORECAST_ASSUMPTION", "value": "0.75", "unit": "ratio",
                "rationale": rationale,
                "evidence_ids": ["cninfo:1224808850:conditional-return-plan"]}}}}}}}}
    bad = review_task_view(task("75% of parent net profit"))
    assert bad["economic_validation"]["reason"] == "SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT"
    assert bad["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["target_payout_ratio"]["value"] == "0.75"
    good = review_task_view(task("75% of consolidated profit attributable to parent shareholders"))
    assert good["economic_validation"]["status"] == "NO_DETECTED_DENOMINATOR_CONFLICT"

    class Service:
        def read(self, task_id):
            assert task_id == "task"
            return bad

    with pytest.raises(ValueError, match="SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT"):
        read_d2_cash_policy_e2_input(root=tmp_path, task_id="task",
                                     now=datetime.now(timezone.utc), service=Service())


def test_real_v7_task_is_readable_but_denominator_conflict_rejected():
    root_var = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit official originals required")
    root = Path(root_var).resolve()
    service = NoticeAwareTaskService(root, kind="cash")
    row = service.read("rt-57e23201babaf6275ce6c33445b5c26b")
    assert row["status"] == "SUCCEEDED"
    assert row["economic_validation"]["reason"] == "SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT"
    with pytest.raises(ValueError, match="SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT"):
        read_d2_cash_policy_e2_input(root=root, task_id=row["task_id"],
                                     now=datetime.now(timezone.utc), service=service)
