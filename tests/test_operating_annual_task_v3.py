"""TEST_ONLY proof of version isolation and exact annual residual anchor."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_sources_v1 import source_env, NOW
from test_operating_horizon_draft_v1 import context, payload
from value_investment_agent.application.research.agent_review import operating_annual_task_v3 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def env(source_env, monkeypatch):
    root = source_env.root
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    cfg = dict(endpoint="https://test-only.invalid/v1/chat/completions", model_id="TEST_ONLY",
        api_key_env="VALUE_AGENT_TEST_ONLY_KEY", timeout_seconds=1,
        max_completion_tokens_cap=4096, max_run_cost="10",
        input_cost_per_million="1", output_cost_per_million="2", authorized=True,
        authorization_reference="TEST_ONLY", currency="CNY", daily_cost_limit="10")
    (root / mod.live.CONFIG).write_bytes(mod._bytes(cfg))
    calls = []

    def complete(req):
        calls.append(req)
        data = payload([2026])
        for path in data["years"]["2026"]["operating_paths"].values():
            path["unit_cost_mechanism"] = "UNRESOLVED_SENSITIVITY"
            path["drivers"]["other_pretax_cny"]["evidence_ids"] = ["test:pre_tax_profit"]
        return LLMResponse(json.dumps(data), 100, 50, "TEST_ONLY")

    provider = SimpleNamespace(complete=complete)
    return SimpleNamespace(root=root, source=source_env, calls=calls,
        service=lambda: mod.OperatingHorizonTaskService(root, test_provider=provider))


def test_v3_runs_separately_and_preserves_old_annual_contract(env):
    old = mod.v2.implementation()
    service = env.service()
    task = service.create(symbol="123456", request_key="TEST_ONLY_v3",
                          years=[2026], now=NOW)
    spec, _, _ = service._load(task["task_id"])
    assert spec["task_contract"] == mod.CONTRACT
    assert spec["implementation_sha256"][mod.draft.__name__]
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["schema_version"] == mod.draft.VERSION
    assert len(env.calls) == 1
    with pytest.raises(PermissionError, match="HORIZON_UNCHANGED_SOURCE_ALREADY_RESEARCHED"):
        service.create(symbol="123456", request_key="TEST_ONLY_second_v3",
                       years=[2026], now=NOW)
    assert len(env.calls) == 1
    assert "2026: test:pre_tax_profit" in env.calls[0].system
    assert "2026: test:pre_tax_profit" in env.calls[0].transport_output_contract
    assert mod.v2.implementation() == old
    with pytest.raises(FileNotFoundError):
        mod.v2.OperatingHorizonTaskService(env.root).read(task["task_id"])
    env.source.original.write_bytes(b"changed")
    assert env.service().read(task["task_id"])["status"] == "FAILED"


def test_v3_still_rejects_missing_residual_anchor(env):
    service = env.service()
    original = service.test_provider.complete

    def missing(req):
        result = original(req)
        data = json.loads(result.text)
        for path in data["years"]["2026"]["operating_paths"].values():
            path["drivers"]["other_pretax_cny"]["evidence_ids"] = ["test:revenue"]
        return replace(result, text=json.dumps(data))

    service.test_provider.complete = missing
    task = service.create(symbol="123456", request_key="TEST_ONLY_bad_v3",
                          years=[2026], now=NOW)
    result = service.run(task["task_id"])
    assert result["status"] == "FAILED"
    assert result["research_result"] is None
