"""WEB-D3 P4: one real company must reach the Web detail through the shared chain."""
from __future__ import annotations

from datetime import datetime
import json
from types import SimpleNamespace

from test_read_api import _fixture
from test_d2_conditional_shared_service import synthetic_chain

from value_investment_agent.application.product import quote_bridge
from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE

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

def _pin_web_quote(tmp_path, monkeypatch, *, research_as_of: str = "2026-10-11"):
    """Register one archived close in the temp project the API reads."""
    bundle = tmp_path / "runtime/quotes/600519-bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(json.dumps({"finished_at": "2026-10-12T09:23:13+00:00",
                                  "references": {"600519": {}}, "documents": {}}), encoding="utf-8")
    package = tmp_path / "runtime/cases/600519-package.json"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text(json.dumps({"symbol": "600519",
                                   "package_version": "pending-600519-2026-10-11-web",
                                   "point_in_time": {"research_as_of": research_as_of}},
                                  ensure_ascii=False), encoding="utf-8")
    quote_bridge.pin_quote_bridge_for_symbol(tmp_path, "600519", bundle, package,
                                             registered_at="2026-10-13T00:00:00+00:00")
    providers = [{"kind": "quote_provider_document", "provider": name, "sha256": "a" * 64,
                  "source_url": "https://example.invalid/" + name, "fetched_at": "2026-10-12T09:23:12+00:00"}
                 for name in ("tencent", "sina")]
    monkeypatch.setattr(quote_bridge, "quote_snapshot_from_bundle_file", lambda *a, **k:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE,
                        quote_date=datetime(2026, 10, 12).date(), current_price="27.96",
                        blockers=[], evidence_refs=providers))
    monkeypatch.setattr(quote_bridge, "resolve_session_reference",
                        lambda *a: {"calendar_exchange": "SSE", "calendar_documents": []})
    monkeypatch.setattr(quote_bridge, "latest_sse_2026_session",
                        lambda *a: ("2026-10-12", ["b" * 64]))


def test_executed_price_bridge_reaches_the_page_without_inventing_a_position(tmp_path, monkeypatch):
    _pin_web_quote(tmp_path, monkeypatch)
    body = _fixture(tmp_path, explanation_extra={"decision_as_of": "2026-10-11"}).get(
        "/api/v1/decisions/600519").json()
    research = body["decision"]["research"]
    execution = research["price_bridge_execution"]
    assert body["action"] == "no_order"
    assert execution["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert execution["quote_date"] == "2026-10-12"
    assert execution["display_price"] == "27.96"
    assert execution["price_admitted"] is False
    assert execution["comparison_eligible"] is False
    assert execution["research_day"] == "2026-10-11"
    assert execution["research_version"] == "pending-600519-2026-10-11-web"
    assert execution["next_step"]
    assert {row["provider"] for row in execution["sources"]} == {"tencent", "sina"}
    # The research-bound price view stays untouched: no price, margin or position is invented.
    assert research["price"]["current_price"] is None
    assert research["margin_to_base"] is None and research["margin_to_bear"] is None
    assert research["position_guidance"] is None
    assert research["action"] == "no_order"


def test_price_bridge_block_is_absent_without_a_registration(tmp_path):
    research = _fixture(tmp_path).get("/api/v1/decisions/600519").json()["decision"]["research"]
    execution = research["price_bridge_execution"]
    assert execution["status"] == "POINTER_UNAVAILABLE"
    assert execution["price_admitted"] is False
    assert execution["comparison_eligible"] is False


def test_detail_forwards_native_coverage_without_promoting_historical_validity(synthetic_chain, monkeypatch):
    from test_incremental_quote_bridge import production_chain, NOW, CUTOFF, SYMBOL
    from value_investment_agent.application.product import incremental_validity as service
    from value_investment_agent.presentation.web_api import app as web_app

    root, ref, _, _, raw = production_chain.__wrapped__(synthetic_chain)
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(web_app, "datetime", Clock)
    expected = quote_bridge.execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    # ASGI TestClient only: real producer and projection, no socket or HTTP collection.
    client = _fixture(root, explanation_extra=EXPLANATION, company_extra=COMPANY)
    body = client.get("/api/v1/decisions/600519").json()
    research = body["decision"]["research"]
    execution = research["price_bridge_execution"]
    assert execution["current_event_coverage"] == expected["current_event_coverage"]
    assert execution["historical_model_validity"] == {"status": "VALID"}
    assert execution["incremental_validity"] == {
        "status": "UNKNOWN", "review_cutoff": CUTOFF.isoformat(), "announcement_count": 0,
        "blockers": expected["incremental_validity"]["blockers"],
        "observed_at": "2026-09-23T00:00:00+00:00", "full_calendar_window_elapsed": True}
    assert execution["price_admitted"] is False
    assert execution["comparison_eligible"] is False
    assert execution["quote_date"] == CUTOFF.isoformat()
    assert research["decision_cutoff"] == EXPLANATION["decision_as_of"]
    assert research["position_guidance"] is None
    assert body["action"] == "no_order"

    raw.write_bytes(b"TEST_ONLY invalid original after successful replay")
    failed = client.get("/api/v1/decisions/600519").json()["decision"]["research"]["price_bridge_execution"]
    assert failed["status"] == "INCREMENTAL_VALIDITY_BLOCKED"
    assert failed["current_event_coverage"] is None
    assert failed["incremental_validity"]["observed_at"] is None
    assert failed["incremental_validity"]["full_calendar_window_elapsed"] is None
    assert failed["comparison_eligible"] is False


def _admitted(root, symbol, *, today):
    return {"schema_version": "quote-bridge-execution-v1", "action": "no_order", "symbol": symbol,
            "status": "QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "reason": None, "next_step": "复核模型有效性",
            "price_admitted": True, "research_day": "2026-10-12",
            "research_case": {"package_version": "pending-600519-2026-10-12-web"},
            "quote": {"quote_date": "2026-10-12", "display_price": "9.99"},
            "pointer": {"path": "config/current-quote-bridge.json", "sha256": "a" * 64},
            "sources": []}


def _bridge_context(monkeypatch, bridge_status: str):
    from value_investment_agent.presentation.web_api import app as web_app

    monkeypatch.setattr(web_app, "execute_quote_bridge_for_symbol", _admitted)
    return {"price_context": {"price_bridge": {"quote_date": None, "current_price": None,
                                               "quote_status": "PENDING_EXTERNAL_DATA",
                                               "bridge_status": bridge_status,
                                               "blockers": []}}}


def test_price_comparison_needs_both_the_admission_and_the_published_bridge(
        tmp_path, monkeypatch):
    ready = _fixture(tmp_path, explanation_extra=_bridge_context(monkeypatch, "READY"))
    research = ready.get("/api/v1/decisions/600519").json()["decision"]["research"]
    assert research["price_bridge_execution"]["price_admitted"] is True
    assert research["price_bridge_execution"]["comparison_eligible"] is True
    assert research["price_bridge_execution"]["compatibility"] is None

    pending = _fixture(tmp_path / "second",
                       explanation_extra=_bridge_context(monkeypatch, "PENDING_EXTERNAL_DATA"))
    research = pending.get("/api/v1/decisions/600519").json()["decision"]["research"]
    assert research["price_bridge_execution"]["price_admitted"] is True
    assert research["price_bridge_execution"]["comparison_eligible"] is False


def test_price_compatibility_ladder_reaches_the_page_verbatim(tmp_path, monkeypatch):
    from value_investment_agent.presentation.web_api import app as web_app

    def _with_ladder(root, symbol, *, today):
        payload = _admitted(root, symbol, today=today)
        payload["compatibility"] = {
            "verified_quote": {"eligible": True, "reason": "双源核验通过"},
            "research_compatible": {"eligible": False, "reason": "报价晚于研究截止日"},
            "historical_reconstruction_eligible": {"eligible": False, "reason": "未覆盖"},
            "comparison_eligible": {"eligible": False, "reason": "尚未准入"},
            "formal_decision_eligible": {"eligible": False, "reason": "需人工门"},
        }
        return payload

    monkeypatch.setattr(web_app, "execute_quote_bridge_for_symbol", _with_ladder)
    research = _fixture(tmp_path).get("/api/v1/decisions/600519").json()["decision"]["research"]
    ladder = research["price_bridge_execution"]["compatibility"]
    assert ladder["verified_quote"]["eligible"] is True
    assert ladder["research_compatible"] == {"eligible": False, "reason": "报价晚于研究截止日"}
    assert ladder["formal_decision_eligible"]["eligible"] is False
    # A ladder entry never upgrades a price, margin or position by itself.
    assert research["price"]["current_price"] is None
    assert research["margin_to_base"] is None

def test_incremental_review_projection_preserves_original_cutoff_and_pending_eligibility():
    from value_investment_agent.presentation.read_models.value_decision_detail import _price_bridge_execution
    result = _price_bridge_execution({
        'schema_version': 'quote-bridge-execution-v1', 'status': 'INCREMENTAL_VALIDITY_BLOCKED',
        'price_admitted': False, 'research_day': '2026-10-11',
        'quote': {'quote_date': '2026-10-15', 'display_price': '28.10'},
        'incremental_validity': {'status': 'UNKNOWN', 'review_cutoff': '2026-10-15',
            'announcement_count': 2, 'blockers': ['pending_complete_event_materiality_review']},
    }, 'READY')
    assert result['research_day'] == '2026-10-11'
    assert result['incremental_validity']['review_cutoff'] == '2026-10-15'
    assert result['incremental_validity']['announcement_count'] == 2
    assert result['comparison_eligible'] is False

