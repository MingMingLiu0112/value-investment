"""Direct tests for the source-bound D2-to-E2 preparation boundary."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import operating_horizon_cash_followup_v1 as mod


NOW = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)


def _supplement(scope="STABLE_SCOPE_VERIFIED"):
    return dict(status="ANNUAL_SUPPLEMENT_COMPILED_NOT_CASH_POLICY", action="no_order",
        formal_eligibility=False, task_id="task-1", research_as_of=NOW.isoformat(),
        source_binding={"path":"runtime/horizon.json", "sha256":"a" * 64},
        context_fingerprint="b" * 64, scope_decomposition_status=scope,
        years={"2027": {"scenarios": {"base": {"model_year": 1}}}})


def _context():
    return dict(snapshot_fingerprint="b" * 64, issuer_name="测试公司", financial_basis="2025-12-31",
        parent_cash_observation_receipts=[dict(period="2025-12-31",
            receipt_binding={"path":"runtime/receipt.json", "sha256":"c" * 64})])


def test_preparation_replays_bound_d2_and_parent_cash_without_policy(monkeypatch, tmp_path):
    supplement = _supplement()
    context = _context()
    observed = dict(source_bindings=[{"path":"runtime/receipt.json", "sha256":"c" * 64}],
        statement_scope="listed_parent_only", balances=[{"period":"FY2025"}])
    monkeypatch.setattr(mod.annual, "read_annual_supplement", lambda **_: deepcopy(supplement))
    monkeypatch.setattr(mod, "build_operating_horizon_source_context", lambda **_: deepcopy(context))
    monkeypatch.setattr(mod, "replay_bound_parent_cash_observations", lambda **_: deepcopy(observed))
    result = mod.prepare_operating_horizon_cash_followup(root=tmp_path, symbol="123456", now=NOW)
    assert result["status"] == "SOURCE_BOUND_ANNUAL_AND_PARENT_CASH_READY_FOR_POLICY"
    assert result["action"] == "no_order" and result["cash_model_ready"] is False
    assert result["input_manifest"]["annual_task_id"] == "task-1"
    assert result["input_manifest"]["parent_cash_source_bindings"] == observed["source_bindings"]
    assert {item["code"] for item in result["current_blockers"]} >= {
        "EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED"}


@pytest.mark.parametrize("status,reason", [
    ("FAILED", "SOURCE_BOUND_ANNUAL_D2_SUPPLEMENT_REQUIRED"),
    ("TEST_ONLY_NOT_REAL_RESEARCH", "SOURCE_BOUND_ANNUAL_D2_SUPPLEMENT_REQUIRED"),
])
def test_preparation_refuses_non_consumable_d2_output(monkeypatch, tmp_path, status, reason):
    bad = _supplement(); bad.update(status=status, reason="SOURCE_OR_IMPLEMENTATION_CHANGED")
    monkeypatch.setattr(mod.annual, "read_annual_supplement", lambda **_: bad)
    result = mod.prepare_operating_horizon_cash_followup(root=tmp_path, symbol="123456", now=NOW)
    assert result["status"] == "NOT_READY" and result["reason"] == reason
    assert result["annual_supplement_reason"] == "SOURCE_OR_IMPLEMENTATION_CHANGED"


@pytest.mark.parametrize("scope", ["SCOPE_CHANGE_APPLICABILITY_NOT_DECLARED", "UNSUPPORTED"])
def test_preparation_refuses_missing_or_unknown_scope_applicability(monkeypatch, tmp_path, scope):
    monkeypatch.setattr(mod.annual, "read_annual_supplement", lambda **_: _supplement(scope))
    result = mod.prepare_operating_horizon_cash_followup(root=tmp_path, symbol="123456", now=NOW)
    assert result["status"] == "NOT_READY"
    assert result["reason"] == "SOURCE_BOUND_SCOPE_APPLICABILITY_REQUIRED"


def test_context_or_receipt_mismatch_fails_closed(monkeypatch, tmp_path):
    supplement = _supplement(); context = _context(); context["snapshot_fingerprint"] = "z" * 64
    monkeypatch.setattr(mod.annual, "read_annual_supplement", lambda **_: supplement)
    monkeypatch.setattr(mod, "build_operating_horizon_source_context", lambda **_: context)
    with pytest.raises(ValueError, match="SOURCE_CONTEXT_CHANGED"):
        mod.prepare_operating_horizon_cash_followup(root=tmp_path, symbol="123456", now=NOW)


def test_batch_health_keeps_each_registered_issuer_independent(monkeypatch, tmp_path):
    config = tmp_path / mod.HORIZON_CONFIG
    config.parent.mkdir()
    config.write_text('{"schema_version":"operating-horizon-sources-v1","action":"no_order",'
        '"cases":{"123456":{},"654321":{}}}', encoding="utf-8")
    def prepare(*, symbol, **_):
        if symbol == "123456":
            return {"status":"SOURCE_BOUND_ANNUAL_AND_PARENT_CASH_READY_FOR_POLICY", "symbol":symbol}
        return {"status":"NOT_READY", "symbol":symbol, "reason":"MISSING_EVIDENCE"}
    monkeypatch.setattr(mod, "prepare_operating_horizon_cash_followup", prepare)
    result = mod.scan_operating_horizon_cash_followups(root=tmp_path, now=NOW)
    assert result["status"] == "PARTIAL"
    assert result["ready_symbols"] == ["123456"]
    assert result["results"]["654321"]["reason"] == "MISSING_EVIDENCE"


def test_batch_health_is_read_only_and_rejects_bad_registry(tmp_path):
    config = tmp_path / mod.HORIZON_CONFIG
    config.parent.mkdir()
    config.write_text('{"schema_version":"bad","action":"no_order","cases":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="REGISTRY_INVALID"):
        mod.scan_operating_horizon_cash_followups(root=tmp_path, now=NOW)
