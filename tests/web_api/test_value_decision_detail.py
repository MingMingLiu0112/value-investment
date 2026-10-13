"""WEB-D3 P4: one real company must reach the Web detail through the shared chain."""
from __future__ import annotations

from test_read_api import _fixture

GATE = {"key": "financial_facts", "status": "PASS", "reason": "已绑定财务事实", "next_action": "复核",
        "evidence_refs": ["decision-workbench-600519-x"]}
DECISION_PROCESS = [
    GATE,
    {"key": "business_quality", "status": "PASS", "reason": "已绑定商业论点", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "model_applicability", "status": "BLOCKED", "reason": "模型有效性未通过", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "valuation", "status": "CONDITIONAL", "reason": "仅有条件性研究情景", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "price_bridge", "status": "BLOCKED", "reason": "行情未准入", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "research_gate", "status": "BLOCKED", "reason": "研究门未通过", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "portfolio_gate", "status": "BLOCKED", "reason": "BLOCKED_PRIVATE_INPUT",
     "next_action": "补齐真实 IPS 与组合输入。", "evidence_refs": ["decision-workbench-600519-x"]},
    {"key": "decision_gate", "status": "BLOCKED", "reason": "尚无 G3 人工批准", "next_action": "复核",
     "evidence_refs": ["decision-workbench-600519-x"]},
]
EXPLANATION = {
    "company_name": "贵州茅台", "research_version": "pending-600519-2026-10-11-x-0123456789ab",
    "decision_as_of": "2026-10-11", "research_status": "financial_scope_approved",
    "financial_period": "2026-06-30", "evidence_scope": "RETAINED_RESEARCH",
    "candidate_action": "NO_ACTION", "requires_human_review": False,
    "valuation": {"model_type": "residual_income_or_equity_value", "valuation_date": "2026-10-11",
                  "bear_value": "9.10", "base_value": "10.20", "bull_value": "11.30",
                  "confidence": "低", "model_version": "residual-income-equity-shared-dated-v2",
                  "assumptions": {"status": "conditional_research_only", "disclaimer": "no price"}},
    "valuation_range": {"bear": "9.10", "base": "10.20", "bull": "11.30", "currency": "CNY",
                        "basis": "valuation_result"},
    "model_validity": {"status": "UNKNOWN", "model_id": None, "model_as_of": None,
                       "valid_from": None, "last_material_event_check": None, "blockers": []},
    "price_context": {"price_bridge": {"quote_date": None, "current_price": None,
                                       "margin_to_bear": None, "margin_to_base": None,
                                       "quote_status": "PENDING_EXTERNAL_DATA",
                                       "bridge_status": "PENDING_EXTERNAL_DATA",
                                       "model_validity_status": "UNKNOWN",
                                       "model_version": "residual-income-equity-shared-dated-v2",
                                       "blockers": ["等待已验证收盘行情"]},
                      "price_attractiveness": {"status": "NOT_ASSESSABLE",
                                               "display_status": "不可判断价格吸引力"}},
    "rule_evidence": {"full_buy_gate_passed": False, "blockers": ["formal G3 approval not present"]},
    "exit_conditions": ["原始逻辑破坏时复盘"],
    "evidence_refs": [{"id": "cninfo:1", "path": "runtime/filings/600519.pdf", "sha256": "a" * 64}],
    "next_events": [{"kind": "fact", "text": "观察下一份季报", "evidence_refs": ["cninfo:1"]}],
    "position_guidance": None, "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
}
COMPANY = {"research_status": {"code": "PARTIAL", "user_label": "研究仍在进行"},
           "price": {"status": {"code": "UNAVAILABLE", "user_label": "暂无可用价格"},
                     "available": False, "value_text": None,
                     "unavailable_reason": "当前没有可验证的同口径行情。",
                     "needed_evidence": "补齐已绑定的价格证据。", "evidence_refs": ["w-1"]},
           "decision_process": DECISION_PROCESS,
           "decision_review": [["研究版本与日期", "600519-m1-valuation-v1 / 2026-09-22"],
                               ["下一触发", "观察下一份季报"]]}


def _research(tmp_path, **kwargs):
    kwargs.setdefault("explanation_extra", EXPLANATION)
    kwargs.setdefault("company_extra", COMPANY)
    return _fixture(tmp_path, **kwargs).get("/api/v1/decisions/600519").json()["decision"]["research"]


def test_research_block_projects_the_bound_artifacts(tmp_path):
    research = _research(tmp_path)
    assert research["action"] == "no_order"
    assert research["company_name"] == "贵州茅台"
    assert research["research_binding"]["status"] == "VERIFIED"
    assert research["research_binding"]["sha256"].startswith(research["research_binding"]["sha256"][:12])
    assert research["decision_cutoff"] == "2026-10-11"
    assert research["research_version"] == "pending-600519-2026-10-11-x-0123456789ab"
    assert research["source_version"] == "residual-income-equity-shared-dated-v2"
    assert research["financial_facts_status"]["status"] == "PASS"
    assert research["business_quality_status"]["status"] == "PASS"
    assert research["valuation"] == {
        "model_type": "residual_income_or_equity_value",
        "model_version": "residual-income-equity-shared-dated-v2",
        "valuation_date": "2026-10-11", "status": "conditional_research_only", "confidence": "低",
        "bear": "9.10", "base": "10.20", "bull": "11.30", "currency": "CNY",
        "basis": "valuation_result", "disclaimer": "no price",
        "scope": None}
    assert research["valuation_model"] == "residual_income_or_equity_value"
    assert research["valuation_confidence"] == "低"
    assert research["model_validity"]["status"] == "UNKNOWN"
    assert research["price"]["current_price"] is None
    assert research["price"]["quote_admission_status"] == "PENDING_EXTERNAL_DATA"
    assert research["price"]["unavailable_reason"] == "当前没有可验证的同口径行情。"
    assert research["price"]["needed_evidence"] == "补齐已绑定的价格证据。"
    assert research["margin_to_base"] is None and research["margin_to_bear"] is None
    assert [gate["key"] for gate in research["gates"]] == [
        "financial_facts", "business_quality", "model_applicability", "valuation", "price_bridge",
        "research_gate", "portfolio_gate", "decision_gate"]
    assert research["research_gate"]["status"] == "BLOCKED"
    assert research["decision_gate"]["reason"] == "尚无 G3 人工批准"
    assert research["portfolio_gate"]["next_action"] == "补齐真实 IPS 与组合输入。"
    assert research["suggested_state"]["value"] == "NO_ACTION"
    assert research["position_guidance"] is None
    assert research["portfolio_input_status"] == "BLOCKED_PRIVATE_INPUT"
    assert research["blockers"] == ["G3"]
    assert research["reopen_triggers"] == ["观察下一份季报"]
    assert research["exit_conditions"] == ["原始逻辑破坏时复盘"]
    assert research["evidence_refs"] == [
        {"id": "cninfo:1", "path": "runtime/filings/600519.pdf", "sha256": "a" * 64}]
    assert research["reading_order"][0] == {"label": "研究版本与日期",
                                            "value": "600519-m1-valuation-v1 / 2026-09-22"}


def test_gate_list_pads_missing_steps_with_null(tmp_path):
    research = _research(tmp_path, company_extra={"research_status": {"code": "PARTIAL"}})
    assert research["gates"] == [None] * 8
    assert research["research_gate"] is None
    assert research["decision_gate"] is None


def test_missing_explanation_keeps_the_card_and_reports_null_fields(tmp_path):
    research = _fixture(tmp_path, explanation_extra={"valuation": None}).get(
        "/api/v1/decisions/600519").json()["decision"]["research"]
    assert research["valuation"]["bear"] is None
    assert research["valuation"]["base"] is None
    assert research["valuation_model"] is None
    assert research["model_validity"]["status"] is None
    assert research["suggested_state"]["value"] is None


def test_unreadable_explanation_flags_the_binding_instead_of_inventing_one(tmp_path):
    client = _fixture(tmp_path, company_extra=COMPANY)
    (tmp_path / "runtime/600519-value-decision-explanation.json").write_text("{", encoding="utf-8")
    detail = client.get("/api/v1/decisions/600519").json()
    research = detail["decision"]["research"]
    assert detail["status"] == "RESEARCH_ONLY"
    assert research["research_binding"]["status"] == "UNAVAILABLE"
    assert research["blockers"] == ["VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
    assert detail["decision"]["blockers"] == ["VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
    assert research["financial_facts_status"]["status"] == "PASS"
    assert research["valuation"]["bear"] is None


def test_company_without_bound_explanation_reports_not_bound(tmp_path):
    client = _fixture(tmp_path)
    detail = client.get("/api/v1/decisions/600519").json()
    assert detail["decision"]["research"]["research_binding"]["status"] == "VERIFIED"
    detail = client.get("/api/v1/decisions/600741").json()
    assert detail["status"] == "PENDING_RESEARCH"
    assert "research" not in detail["decision"]
