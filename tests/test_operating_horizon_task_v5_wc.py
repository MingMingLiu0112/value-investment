"""TEST_ONLY durable D2 WC task using sealed response and real public originals."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_task_v5_wc as mod
from value_investment_agent.application.research.agent_review import operating_horizon_task_v4 as v4
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def wps_hardlink_fallback(monkeypatch):
    """WPS virtual drive denies hard links; emulate exclusive creation in tests."""
    def link(source, target):
        with open(source, "rb") as incoming, open(target, "xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    monkeypatch.setattr(os, "link", link)


@pytest.fixture
def env(tmp_path, monkeypatch):
    public_root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not public_root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for real public-original task replay")
    public_root = Path(public_root)
    for relative in ("config/parent-wc-history-600519-v1.json",
                     "runtime/fy2025-600519-wc/original.pdf",
                     "runtime/h1-2026-ocr/original.pdf"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(public_root / relative, target)
    cfg = dict(endpoint="https://test-only.invalid/v1/chat/completions", model_id="TEST_ONLY",
        api_key_env="VALUE_AGENT_TEST_ONLY_KEY", timeout_seconds=1,
        max_completion_tokens_cap=4096, max_run_cost="10", input_cost_per_million="1",
        output_cost_per_million="2", authorized=True, authorization_reference="TEST_ONLY",
        currency="CNY", daily_cost_limit="10")
    config = tmp_path / mod.live.CONFIG
    config.parent.mkdir(exist_ok=True)
    config.write_bytes(mod._bytes(cfg))
    values = dict(revenue="1000", cost="500", surcharges="10", selling="10",
                  admin="20", research="5", pre_tax_profit="455")
    context = dict(symbol="600519", issuer_name="贵州茅台酒股份有限公司",
        as_of=NOW.isoformat(), snapshot_fingerprint="a" * 64,
        financial_basis="2025-12-31",
        evidence=[dict(id="test:" + field, source_id="TEST_ONLY",
            pdf_sha256="b" * 64, available_at="2026-04-01T00:00:00+00:00",
            period="2025-12-31", period_basis="FY", scope="consolidated",
            unit="CNY", field=field, value=value, text="TEST_ONLY baseline row")
            for field, value in values.items()])
    source_file = tmp_path / "runtime/test-only-base-context.json"
    source_file.write_bytes(mod._bytes(context))
    source_pin = dict(path="runtime/test-only-base-context.json",
                      sha256=hashlib.sha256(source_file.read_bytes()).hexdigest())
    context["source_binding"] = source_pin
    def source_loader(*, root, symbol, now, binding=None):
        if (symbol != "600519" or binding not in (None, source_pin)
                or hashlib.sha256(source_file.read_bytes()).hexdigest() != source_pin["sha256"]):
            raise ValueError("TEST_ONLY_BASE_SOURCE_CHANGED")
        return deepcopy(context)
    sealed = tmp_path / "runtime/test-only-sealed-response.json"
    sealed.write_text(json.dumps(payload(unknown=True), ensure_ascii=False), encoding="utf-8")
    sealed_sha = hashlib.sha256(sealed.read_bytes()).hexdigest()
    def set_sealed(value):
        nonlocal sealed_sha
        sealed.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        sealed_sha = hashlib.sha256(sealed.read_bytes()).hexdigest()
    calls = []
    def complete(request):
        if hashlib.sha256(sealed.read_bytes()).hexdigest() != sealed_sha:
            raise ValueError("TEST_ONLY_SEALED_RESPONSE_CHANGED")
        calls.append(request)
        return LLMResponse(sealed.read_text(encoding="utf-8"), 100, 50, "TEST_ONLY")
    provider = SimpleNamespace(complete=complete)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    return SimpleNamespace(root=tmp_path, calls=calls, sealed=sealed, set_sealed=set_sealed,
        service=lambda: mod.OperatingHorizonTaskService(tmp_path,
            test_provider=provider, source_loader=source_loader,
            source_loader_version="test-only-source-v1"))


def test_requires_test_only_provider(tmp_path):
    with pytest.raises(PermissionError, match="EXECUTION_MODE_REQUIRED"):
        mod.OperatingHorizonTaskService(tmp_path, test_provider=None)


def test_live_preflight_requires_credential(env, monkeypatch):
    monkeypatch.delenv("VALUE_AGENT_TEST_ONLY_KEY", raising=False)
    service = mod.OperatingHorizonTaskService(env.root, allow_live=True,
        source_loader=env.service().source_loader, source_loader_version="test-only-source-v1")
    with pytest.raises(PermissionError, match="MODEL_CREDENTIAL_REQUIRED"):
        service.create(symbol="600519", request_key="LIVE_PREFLIGHT_ONLY", years=[2026], now=NOW)
    assert env.calls == []


def test_live_source_identity_deduplicates_request_keys(env, monkeypatch):
    monkeypatch.setenv("VALUE_AGENT_TEST_ONLY_KEY", "dummy-preflight-only")
    service = mod.OperatingHorizonTaskService(env.root, allow_live=True,
        source_loader=env.service().source_loader, source_loader_version="test-only-source-v1")
    first = service.create(symbol="600519", request_key="LIVE_SOURCE_KEY_A", years=[2026], now=NOW)
    second = service.create(symbol="600519", request_key="LIVE_SOURCE_KEY_B", years=[2026], now=NOW)
    assert first["task_id"] == second["task_id"]
    assert first["execution_mode"] == "LIVE_OPERATING"
    assert first["status"] == "QUEUED" and first["new_llm_calls"] == 0
    assert first["operating_wc_cash_cny"] == "UNKNOWN"
    assert first["d2_handoff_readiness"] == "INCOMPLETE_OR_UNVERIFIED"
    assert env.calls == []


def test_live_rejects_multi_year_and_changed_config(env, monkeypatch):
    monkeypatch.setenv("VALUE_AGENT_TEST_ONLY_KEY", "dummy-preflight-only")
    service = mod.OperatingHorizonTaskService(env.root, allow_live=True,
        source_loader=env.service().source_loader, source_loader_version="test-only-source-v1")
    with pytest.raises(ValueError):
        service.create(symbol="600519", request_key="LIVE_MULTI_YEAR", years=[2026, 2027], now=NOW)
    first = service.create(symbol="600519", request_key="LIVE_CONFIG_FIRST", years=[2026], now=NOW)
    config = env.root / mod.live.CONFIG
    changed = json.loads(config.read_text(encoding="utf-8"))
    changed["max_run_cost"] = "9"
    config.write_bytes(mod._bytes(changed))
    with pytest.raises(ValueError, match="REQUEST_KEY_CONFLICT"):
        service.create(symbol="600519", request_key="LIVE_CONFIG_SECOND", years=[2026], now=NOW)
    assert first["new_llm_calls"] == 0 and env.calls == []


def test_real_wc_task_sealed_response_create_run_read(env):
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_REAL", years=[2026], now=NOW)
    spec, _, _ = service._load(task["task_id"])
    assert spec["task_contract"] == mod.CONTRACT
    assert spec["wc_source_binding"]["history_sha256"]
    assert len(spec["wc_source_binding"]["originals"]) == 2
    assert service.base.name == mod.STORE
    run = service.run(task["task_id"])
    assert run["status"] == "SUCCEEDED", run
    assert run["new_llm_calls"] == 0
    assert len(env.calls) == 1
    assert "SOURCE_BOUND_PARENT_WC_BALANCE_RISK_ANCHOR=" in env.calls[0].user
    assert "operating_wc_cash_cny to zero" in env.calls[0].system
    assert run["research_result"]["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert run["research_result"]["formal_eligibility"] is False
    assert run["operating_wc_cash_cny"] == "UNKNOWN"
    assert run["d2_handoff_readiness"] == "INCOMPLETE_OR_UNVERIFIED"
    assert run["condition_price"] is None and run["d2_three_role_complete"] is False
    again = env.service().read(task["task_id"])
    assert again["status"] == "SUCCEEDED" and again["research_result"] == run["research_result"]
    assert len(env.calls) == 1
    with pytest.raises((ValueError, FileNotFoundError)):
        v4.OperatingHorizonTaskService(env.root, test_provider=SimpleNamespace(complete=lambda _: None)).read(task["task_id"])


def test_synthetic_complete_assumptions_enable_d2_handoff_only(env):
    response = payload()
    for path in response["years"]["2026"]["operating_paths"].values():
        for item in path["capital_assumptions"]:
            item.update(classification="FORECAST", lower="1", upper="2", unit="CNY",
                rationale="TEST_ONLY conditional capital sensitivity; source ID anchors context, not future fact",
                evidence_ids=["test:pre_tax_profit"])
    env.set_sealed(response)
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_COMPLETE", years=[2026], now=NOW)
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["d2_handoff_readiness"] == "VALIDATED_COMPLETE_UNAPPROVED_FOR_E2_REVIEW"
    assert result["operating_wc_cash_cny"] == "UNKNOWN"
    assert result["formal_eligibility"] is False and result["condition_price"] is None
    assert result["new_llm_calls"] == 0 and len(env.calls) == 1


def test_cash_complete_with_unknown_capital_remains_incomplete(env):
    env.set_sealed(payload())
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_CAP_UNKNOWN", years=[2026], now=NOW)
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["d2_handoff_readiness"] == "INCOMPLETE_OR_UNVERIFIED"


def test_changed_original_blocks_run_before_provider(env):
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_CHANGED", years=[2026], now=NOW)
    with (env.root / "runtime/h1-2026-ocr/original.pdf").open("ab") as file:
        file.write(b"changed")
    result = service.run(task["task_id"])
    assert result["status"] == "FAILED"
    assert env.calls == []


def test_sealed_response_change_fails_without_paid_retry(env):
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_RESPONSE", years=[2026], now=NOW)
    with env.sealed.open("ab") as file:
        file.write(b"changed")
    result = service.run(task["task_id"])
    assert result["status"] == "FAILED"
    assert len(env.calls) == 0


def test_registry_change_blocks_read_after_success(env):
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_REGISTRY", years=[2026], now=NOW)
    assert service.run(task["task_id"])["status"] == "SUCCEEDED"
    registry = env.root / "config/parent-wc-history-600519-v1.json"
    registry.write_bytes(registry.read_bytes() + b" ")
    checked = env.service().read(task["task_id"])
    assert checked["status"] == "FAILED"
    assert checked["error_code"] == "SOURCE_OR_IMPLEMENTATION_CHANGED"


def test_missing_original_fails_closed(env):
    (env.root / "runtime/fy2025-600519-wc/original.pdf").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        env.service().create(symbol="600519", request_key="TEST_ONLY_WC_V5_MISSING", years=[2026], now=NOW)
    assert env.calls == []


def test_source_loader_version_change_rejects_bound_replay(env):
    service = env.service()
    task = service.create(symbol="600519", request_key="TEST_ONLY_WC_V5_LOADER", years=[2026], now=NOW)
    changed = mod.OperatingHorizonTaskService(env.root,
        test_provider=service.test_provider, source_loader=service.source_loader,
        source_loader_version="test-only-source-v2")
    checked = changed.read(task["task_id"])
    assert checked["status"] == "FAILED"
    assert checked["error_code"] == "SOURCE_OR_IMPLEMENTATION_CHANGED"
    assert env.calls == []
