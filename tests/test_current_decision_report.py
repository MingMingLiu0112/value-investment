"""Current reports admit only replay-verified nonpersonalized research."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_current_decision_surface import decision_workbench, forged_candidate
from value_investment_agent.domain.decision.decision_recommendation import LEGACY_DECISION_RECOMMENDATION_SCHEMA
import value_investment_agent.presentation.read_models.existing_research_report as report_module
from value_investment_agent.presentation.read_models.existing_research_report import render_current_research_readiness


@pytest.mark.parametrize("confidence, expected", [("中", "BUY_CANDIDATE"), ("低", "NO_ACTION")])
def test_current_report_renders_replayed_v2_without_private_position(confidence, expected):
    payload = decision_workbench(confidence=confidence)
    before = deepcopy(payload)
    report = render_current_research_readiness(payload)
    assert f"当前建议类型：{expected}" in report
    assert "非个性化" in report
    assert "BLOCKED_PRIVATE_INPUT" in report
    assert "position_guidance=null" in report
    assert "action=no_order" in report
    assert "conditional_research_only" in report
    assert "current-financial_facts" in report
    assert "当前不形成买入" not in report
    if expected == "NO_ACTION":
        assert "不代表卖出" in report
    assert payload == before


@pytest.mark.parametrize("field, value", [
    ("action", "order"), ("position_guidance", {"weight": "0.1"}),
    ("portfolio_input_status", "PASS"), ("canonical_workbook_written", True),
    ("suggested_state", "NOT_READY"), ("symbol", "600519"),
])
def test_current_report_rejects_scope_or_identity_drift(field, value):
    payload = decision_workbench()
    payload[field] = value
    with pytest.raises(ValueError):
        render_current_research_readiness(payload)


def test_current_report_rejects_unbound_candidate():
    payload = decision_workbench()
    payload.pop("artifact_bundle")
    with pytest.raises(ValueError, match="replayable"):
        render_current_research_readiness(payload)


def test_current_report_rejects_tampered_dependency():
    payload = decision_workbench()
    payload["artifact_bundle"]["artifacts"][0]["canonical_payload"] += " "
    with pytest.raises(ValueError):
        render_current_research_readiness(payload)


def test_current_report_accepts_legacy_v1_via_existing_decoder():
    payload = decision_workbench(schema_version=LEGACY_DECISION_RECOMMENDATION_SCHEMA)
    assert "当前建议类型：BUY_CANDIDATE" in render_current_research_readiness(payload)


def test_current_report_rejects_rehashed_candidate_without_approval():
    with pytest.raises(ValueError, match="full repository replay"):
        render_current_research_readiness(forged_candidate())


def stopped_workbench():
    return {
        "schema_version": "product-current-workbench-request-v1", "symbol": "600887",
        "research_status": "BLOCKED_BY_RESEARCH_SCHEDULER", "action": "no_order",
        "suggested_state": "NOT_READY", "position_guidance": None,
        "canonical_workbook_written": False, "evidence_stops": [],
        "schedule_gate": {"allowed": False, "status": "STOPPED", "reason": "retained stop"},
        "research_receipt": {"input_sha256": {"evidence_stop_ledger": "a" * 64}},
    }


def test_stopped_readiness_keeps_existing_evidence_stop_scope():
    report = render_current_research_readiness(stopped_workbench())
    assert "当前不形成买入" in report
    assert "retained stop" in report
    assert "a" * 64 in report
    assert "action=no_order" in report


@pytest.mark.parametrize("field", ["decision_recommendation", "artifact_bundle", "price_attractiveness"])
def test_stopped_report_cannot_smuggle_current_results(field):
    payload = stopped_workbench()
    payload[field] = {}
    with pytest.raises(ValueError, match="stopped research"):
        render_current_research_readiness(payload)


def test_current_report_handles_no_quote_risk_reduction(monkeypatch):
    recommendation = SimpleNamespace(
        symbol="000651",
        decision_as_of="2026-09-22",
        thesis="原论点已破裂，进入人工退出复核。",
        confidence="中",
        valuation_range=SimpleNamespace(bear="20", base="30", bull="40"),
        price_bridge_status="PENDING_EXTERNAL_DATA",
        price_attractiveness_status="NOT_ASSESSABLE",
        recommendation_reasons=("thesis_broken",),
        blockers=("quote_unavailable",),
        next_events=({"text": "等待可验证报价"},),
        recommendation_type="SELL_CANDIDATE",
    )
    dependency = SimpleNamespace(
        artifact_id="decision-valuation",
        envelope=SimpleNamespace(payload_sha256="a" * 64),
    )
    restored = SimpleNamespace(
        recommendation=recommendation,
        dependencies={"valuation": dependency},
        dependency_objects={
            "valuation": SimpleNamespace(status="conditional_research_only")
        },
    )
    monkeypatch.setattr(
        report_module,
        "verify_current_decision_workbench",
        lambda payload: restored,
    )
    payload = {
        "schema_version": "product-current-workbench-request-v1",
        "action": "no_order",
        "position_guidance": None,
        "canonical_workbook_written": False,
        "research_status": "COMPLETED",
        "suggested_state": "SELL_CANDIDATE",
    }
    report = render_current_research_readiness(payload)
    assert "价格状态：暂不可评估" in report
    assert "所需证据：可验证报价" in report
    assert "人工退出复核" in report
    assert "暂不进入人工买入复核" not in report
    assert "action=no_order" in report
