"""Funding conditions and profit denominator must survive D2 handoff."""
from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v8 as source
from value_investment_agent.application.research.agent_review.operating_cash_policy_task_v1 import OperatingCashPolicyTaskService
from value_investment_agent.application.research.agent_review.operating_cash_policy_task_v2 import OperatingCashPolicyTaskServiceV2
from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService


def test_v8_rejects_changed_funding_condition_and_original(tmp_path, monkeypatch):
    original = tmp_path / "runtime" / "original.pdf"
    original.parent.mkdir()
    original.write_bytes(b"TEST_ONLY original")
    evidence = [
        dict(id="cninfo:1224808850:conditional-return-plan", pdf_sha256=source._hash(original.read_bytes()),
             physical_page=2, period="2025-12-31"),
        dict(id="cninfo:1225321219:approved-return-plan"),
    ]
    base = dict(evidence=evidence, supplemental_sources=[dict(source_id="cninfo:1224808850",
        path="runtime/original.pdf", sha256=source._hash(original.read_bytes()),
        available_at="2026-11-11T00:00:00+00:00")])
    monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *a, **k: [
        source.CONDITION, source.PROCEDURE])
    row = source._conditions(tmp_path, base, datetime.now(timezone.utc))
    assert row["physical_pages"] == [1, 2]
    assert row["text_composition"] == "TWO_VERBATIM_FRAGMENTS_FROM_SEPARATE_PAGES"
    monkeypatch.setattr(source.pdf_text, "extract_pages", lambda *a, **k: [
        source.CONDITION.replace("资金需求", "零资金需求"), source.PROCEDURE])
    with pytest.raises(ValueError, match="CONDITIONS_NOT_PROVEN"):
        source._conditions(tmp_path, base, datetime.now(timezone.utc))
    original.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ORIGINAL_CHANGED"):
        source._conditions(tmp_path, base, datetime.now(timezone.utc))


def test_v8_result_refuses_parent_profit_and_ambiguous_denominator(tmp_path, monkeypatch):
    service = OperatingCashPolicyTaskServiceV2(tmp_path)

    def result(rationale):
        term = dict(classification="FORECAST_ASSUMPTION", value="0.75", unit="ratio",
                    rationale=rationale, evidence_ids=["cninfo:1224808850:conditional-return-plan"])
        return dict(years={"2027": {"shareholder_cash_paths": {
            "bear": {"terms": {"target_payout_ratio": term}},
            "base": {"terms": {"target_payout_ratio": term}},
            "bull": {"terms": {"target_payout_ratio": term}},
        }}})

    monkeypatch.setattr(OperatingCashPolicyTaskService, "_result", lambda *a: result("parent net profit"))
    with pytest.raises(ValueError, match="DENOMINATOR_CONFLICT"):
        service._result({}, {}, {})
    monkeypatch.setattr(OperatingCashPolicyTaskService, "_result", lambda *a: result("profit"))
    with pytest.raises(ValueError, match="DENOMINATOR_NOT_EXPLICIT"):
        service._result({}, {}, {})
    monkeypatch.setattr(OperatingCashPolicyTaskService, "_result", lambda *a: result(
        "75% of consolidated profit attributable to parent shareholders"))
    assert service._result({}, {}, {})["years"]["2027"]
    monkeypatch.setattr(OperatingCashPolicyTaskService, "_result", lambda *a: result(
        "75% of consolidated profit attributable to parent shareholders, not standalone-parent net profit"))
    assert service._result({}, {}, {})["years"]["2027"]


def test_real_v8_context_and_prompt_are_distinct_from_v7():
    root_var = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_var:
        pytest.skip("Explicit official originals required")
    root = Path(root_var).resolve()
    now = datetime.now(timezone.utc)
    value = source.build_operating_horizon_source_context(root=root, symbol="600887", now=now)
    replay = source.build_operating_horizon_source_context(
        root=root, symbol="600887", now=now, binding=value["source_binding"])
    assert replay == value and len(value["evidence"]) == 66
    assert NoticeAwareTaskService._version(value["source_binding"]) == "v8"
    service = OperatingCashPolicyTaskServiceV2(root, source_loader=source.build_operating_horizon_source_context)
    request = service._request(dict(years=[2027], config=dict(max_completion_tokens_cap=4096)), value)
    assert "SOURCE_BOUND_APPROVED_CONDITIONAL_RETURN_PLAN=" in request.user
    assert "consolidated_profit_attributable_to_parent_shareholders" in request.user
    assert "NEVER standalone-parent net profit" in request.system
    for key in ("cninfo:1224808850:conditional-return-plan",
                "cninfo:1224808850:return-plan-conditions",
                "cninfo:1225321219:approved-return-plan"):
        assert key in request.user
