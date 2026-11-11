"""TEST_ONLY registration acceptance over real daily Mock research packets."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json

import pytest

from test_daily_agent_research import setup, financial_setup
from test_web_agent_research import build, register, state
from test_llm_agent_research import _replies
from value_investment_agent.application.research.agent_review.llm_pilot import run_llm_research_pilot
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review.daily_research import (
    run_daily_event_mock, run_daily_financial_mock,
)
from value_investment_agent.application.research.agent_review.web_research import (
    REGISTRY_PATH, REGISTRY_WORKFLOWS_SCHEMA, read_web_agent_research,
)


@pytest.fixture
def registrar():
    # A missing implementation is an explicit failure, not a skipped acceptance.
    module = importlib.import_module(
        "value_investment_agent.application.research.agent_review.daily_registration")
    return module.register_daily_draft_results


@pytest.fixture(autouse=True)
def forbid_provider_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Registration acceptance must remain offline")
    monkeypatch.setattr(
        "value_investment_agent.infrastructure.agent_runtime.provider.build_opener",
        forbidden)


def batch(*items):
    ready = sum(item["status"] == "DRAFT_READY" for item in items)
    return dict(schema_version="daily-agent-mock-batch-result-v1", action="no_order",
        mode="MOCK", plan_sha256="a" * 64,
        status="SUCCESS" if ready == len(items) else "PARTIAL" if ready else "BLOCKED",
        items=list(items), registered_or_published=False, approval_count=0,
        decision_changed=False)


def draft(root, workflow="event", *, args=None, output=None):
    args = args or (setup if workflow == "event" else financial_setup)(root)
    args = dict(args)
    if output is not None:
        args["output"] = output
    result = (run_daily_event_mock if workflow == "event" else run_daily_financial_mock)(**args)
    packet = json.loads(args["output"].read_text(encoding="utf-8"))
    now = datetime.fromisoformat(packet["generated_at"]) + timedelta(minutes=1)
    return args, dict(symbol=args["symbol"], workflow=workflow,
                     status="DRAFT_READY", result=result), now


def receipt(value, status, count):
    assert value["status"] == status, value
    assert value["registered_count"] == count
    assert value["approval_count"] == 0
    assert value["action"] == "no_order"
    for item in value["items"]:
        assert {"symbol", "workflow", "status"} <= item.keys()
        assert item["status"] in {"REGISTERED", "UNCHANGED", "SKIPPED", "REJECTED"}


def unapproved(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"admitted", "eligibility", "decision_changed", "financial_gate_admitted",
                       "forecast_assumptions_approved", "economic_comparability_approved"}:
                assert child is False, (key, child)
            if key == "approval_count":
                assert child == 0
            unapproved(child)
    elif isinstance(value, list):
        for child in value:
            unapproved(child)


@pytest.mark.parametrize("payload", [{}, batch(), batch(dict(
    symbol="600519", workflow="event", status="BLOCKED_INPUT", result={})),
    batch(dict(symbol="600519", workflow="event", status="DRAFT_READY", result={}))])
@pytest.mark.parametrize("existing", [False, True])
def test_empty_or_missing_inputs_do_not_change_registry(tmp_path, registrar, payload, existing):
    now = datetime.now(timezone.utc)
    if existing:
        _, _, _, _, _, now = build(tmp_path)
    before = state(tmp_path)
    if payload == {} or payload == batch():
        with pytest.raises(ValueError):
            registrar(root=tmp_path, batch_result=deepcopy(payload), now=now)
        assert state(tmp_path) == before
        return
    result = registrar(root=tmp_path, batch_result=deepcopy(payload), now=now)
    assert result["status"] == "BLOCKED"
    expected = "REJECTED" if payload["items"][0]["status"] == "DRAFT_READY" else "SKIPPED"
    assert result["items"][0]["status"] == expected
    assert result["registered_count"] == result["approval_count"] == 0
    assert result["action"] == "no_order"
    assert state(tmp_path) == before


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_real_draft_registration_web_verification_and_repeat_no_write(tmp_path, registrar, workflow):
    _, item, now = draft(tmp_path, workflow)
    original = deepcopy(item)
    result = registrar(root=tmp_path, batch_result=batch(item), now=now)
    receipt(result, "UPDATED", 1)
    assert result["items"][0]["status"] == "REGISTERED"
    assert item == original
    web = read_web_agent_research(tmp_path, symbol="600519", workflow=workflow, now=now)
    assert web["status"] == "VERIFIED", web
    assert web["workflow"] == workflow
    assert len(web["findings"]) == 3
    assert all(row["status"] == "PENDING_HUMAN_REVIEW" for row in web["findings"])
    registry = json.loads((tmp_path / REGISTRY_PATH).read_text(encoding="utf-8"))
    entry = registry["cases"]["600519"]["workflows"][workflow]
    assert entry["workflow_binding"] == item["result"]["workflow_binding"]
    assert entry["packet"] == item["result"]["packet"]
    unapproved([result, web, registry, item])
    before = state(tmp_path)
    repeated = registrar(root=tmp_path, batch_result=batch(item), now=now)
    receipt(repeated, "UNCHANGED", 0)
    assert repeated["items"][0]["status"] == "UNCHANGED"
    assert state(tmp_path) == before
    if workflow == "financial":
        missing = read_web_agent_research(tmp_path, symbol="600519", workflow="event", now=now)
        assert missing["status"] != "VERIFIED"


def test_v1_migration_preserves_legacy_and_adds_event(tmp_path, registrar):
    args, item, now = draft(tmp_path)
    path = tmp_path / "runtime/legacy.json"
    packet = run_llm_research_pilot(
        **{key: args[key] for key in ("root", "symbol", "workbench", "workbench_sha256", "source_requests")},
        output=path, mode="mock", provider=MockLLMProvider(_replies()))
    old = register(tmp_path, path, args["workbench"], packet["scope"])
    now = max(now, datetime.fromisoformat(packet["generated_at"]) + timedelta(minutes=1))
    legacy = deepcopy(old["cases"]["600519"])
    receipt(registrar(root=tmp_path, batch_result=batch(item), now=now), "UPDATED", 1)
    registry = json.loads((tmp_path / REGISTRY_PATH).read_text(encoding="utf-8"))
    assert registry["schema_version"] == REGISTRY_WORKFLOWS_SCHEMA
    assert registry["cases"]["600519"]["workflows"]["legacy"] == legacy
    for workflow in ("legacy", "event"):
        assert read_web_agent_research(tmp_path, symbol="600519", workflow=workflow,
                                      now=now)["status"] == "VERIFIED"


@pytest.mark.parametrize("fault", ["hash", "packet", "rehashed_packet", "workflow"])
def test_invalid_candidate_cannot_replace_good_registration(tmp_path, registrar, fault):
    args, good, now = draft(tmp_path)
    receipt(registrar(root=tmp_path, batch_result=batch(good), now=now), "UPDATED", 1)
    _, bad, now = draft(tmp_path, args=args, output=tmp_path / "runtime/candidate.json")
    if fault == "hash":
        bad["result"]["packet"]["sha256"] = "0" * 64
    elif fault == "workflow":
        bad["workflow"] = "financial"
    else:
        path = tmp_path / bad["result"]["packet"]["path"]
        packet = json.loads(path.read_text(encoding="utf-8"))
        packet["findings"][0]["claim"] = "Forged economic conclusion"
        path.write_text(json.dumps(packet), encoding="utf-8")
        if fault == "rehashed_packet":
            bad["result"]["packet"]["sha256"] = sha256_file(path)
    before = state(tmp_path)
    result = registrar(root=tmp_path, batch_result=batch(bad), now=now)
    receipt(result, "BLOCKED", 0)
    assert result["items"][0]["status"] == "REJECTED"
    assert state(tmp_path) == before
    assert read_web_agent_research(tmp_path, symbol="600519", workflow="event",
                                  now=now)["status"] == "VERIFIED"


@pytest.mark.parametrize("fault", ["missing_binding", "transcription", "event_label"])
def test_financial_requires_complete_original_binding(tmp_path, registrar, fault):
    args, item, now = draft(tmp_path, "financial")
    if fault == "missing_binding":
        item["result"].pop("workflow_binding")
    elif fault == "transcription":
        args["transcription"].write_text("changed", encoding="utf-8")
    else:
        item["workflow"] = "event"
    before = state(tmp_path)
    result = registrar(root=tmp_path, batch_result=batch(item), now=now)
    receipt(result, "BLOCKED", 0)
    assert result["items"][0]["status"] == "REJECTED"
    assert state(tmp_path) == before


def test_partial_batch_registers_only_ready_valid_draft(tmp_path, registrar):
    _, item, now = draft(tmp_path)
    skipped = dict(symbol="000333", workflow="event", status="FAILED", error_type="ValueError")
    invalid = dict(symbol="000651", workflow="financial", status="DRAFT_READY", result={})
    result = registrar(root=tmp_path, batch_result=batch(item, skipped, invalid), now=now)
    receipt(result, "PARTIAL", 1)
    assert [row["status"] for row in result["items"]] == ["REGISTERED", "SKIPPED", "REJECTED"]
    assert read_web_agent_research(tmp_path, symbol="600519", workflow="event",
                                  now=now)["status"] == "VERIFIED"
    unapproved(result)


def test_crash_left_registration_marker_does_not_block_real_registration(tmp_path, registrar):
    _, item, now = draft(tmp_path)
    marker = tmp_path / ".tmp/agent-research-registration.lock"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("crash-left", encoding="utf-8")
    result = registrar(root=tmp_path, batch_result=batch(item), now=now)
    receipt(result, "UPDATED", 1)
    assert marker.is_file()
    assert read_web_agent_research(tmp_path, symbol="600519", workflow="event",
                                  now=now)["status"] == "VERIFIED"
