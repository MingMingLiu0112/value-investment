"""V4 dispatch proves the new D2 contract executes in its own durable slot."""
from types import SimpleNamespace
import json
import pytest

import test_operating_horizon_task_v2 as v2_tests
from test_operating_horizon_sources_v1 import source_env
from test_operating_horizon_draft_v1 import context
from test_operating_horizon_draft_v1 import NOW
from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_task_v4 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def env(source_env, monkeypatch):
    # Reuse the v2 fixture's exact source/config construction; only the runner
    # contract differs here. Calling its wrapped function avoids registering a
    # second fixture with hidden dependencies.
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    root = base.root
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    calls = []
    def complete(request):
        calls.append(request)
        return LLMResponse(json.dumps(payload()), 100, 50, "TEST_ONLY")
    provider = SimpleNamespace(complete=complete)
    return SimpleNamespace(root=root, calls=calls,
        service=lambda: mod.OperatingHorizonTaskService(root, test_provider=provider))


def test_v4_executes_cash_policy_contract_in_separate_durable_namespace(env):
    service = env.service()
    task = service.create(symbol="123456", request_key="TEST_ONLY_v4", years=[2026])
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    research = result["research_result"]
    assert research["schema_version"] == "operating-horizon-draft-v3-cash-policy"
    assert research["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert research["action"] == "no_order" and research["valuation_produced"] is False
    assert task["task_id"] != "rt-" + mod._hash(("operating-horizon-task-v2:TEST_ONLY_v4").encode())[:32]
    assert service.base.name == mod.STORE and len(env.calls) == 1


def test_v4_old_task_cannot_be_read_as_cash_policy_research(env):
    old = env.root / "runtime" / "operating-horizon-task-v2" / "rt-not-a-v4"
    old.mkdir(parents=True)
    with pytest.raises((ValueError, FileNotFoundError)):
        env.service().read("rt-not-a-v4")
