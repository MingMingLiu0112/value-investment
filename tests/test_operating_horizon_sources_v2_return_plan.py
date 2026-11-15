"""The extra official policy source is pinned without rewriting old facts."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

from test_operating_horizon_task_v19_generic import setup as v19_setup
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from value_investment_agent.application.research.agent_review import (
    operating_horizon_sources_v2_return_plan as source,
)
from value_investment_agent.application.research.agent_review import (
    operating_horizon_task_v25_canonical as task,
)
from value_investment_agent.application.research.agent_review import (
    operating_cash_policy_draft_v16_generic as cash,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def test_plan_overlay_binds_base_and_replays_without_current_selection(tmp_path, monkeypatch):
    base_context = dict(schema_version="operating-horizon-sources-v1", symbol="600887",
        issuer_name="TEST_ONLY ISSUER", as_of=NOW.isoformat(),
        source_binding=dict(path="runtime/base.json", sha256="a" * 64),
        evidence=[dict(id="base:fact")], supplemental_sources=[], limitations=[],
        snapshot_fingerprint="b" * 64, action="no_order", formal_eligibility=False)
    selected = dict(source_id="cninfo:123", receipt_path="runtime/plan/receipt.json")
    monkeypatch.setattr(source.base, "build_operating_horizon_source_context",
        lambda **kwargs: deepcopy(base_context))
    monkeypatch.setattr(source.plan, "_selection", lambda *args: (selected, dict(path="config/plan.json", sha256="c" * 64)))
    monkeypatch.setattr(source.plan, "_plan", lambda *args: (
        dict(id="cninfo:123:conditional-return-plan", kind="PLAN_TARGET_NOT_FUTURE_CASH_OR_PAYMENT"),
        dict(source_id="cninfo:123", sha256="d" * 64)))
    result = source.build_operating_horizon_source_context(root=tmp_path, symbol="600887", now=NOW)
    assert result["schema_version"] == "operating-horizon-sources-v1"
    assert result["source_adapter_version"] == source.VERSION
    assert len(result["evidence"]) == 2
    assert result["formal_eligibility"] is False and result["action"] == "no_order"
    monkeypatch.setattr(source.plan, "_selection", lambda *args: (_ for _ in ()).throw(
        AssertionError("replay must not read current selector")))
    assert source.build_operating_horizon_source_context(root=tmp_path, symbol="600887",
        now=NOW, binding=result["source_binding"]) == result
    base_context["evidence"][0]["id"] = "changed"
    with pytest.raises(ValueError, match="RETURN_PLAN_BASE_CHANGED"):
        source.build_operating_horizon_source_context(root=tmp_path, symbol="600887",
            now=NOW, binding=result["source_binding"])


def test_real_official_plan_joins_current_facts_when_originals_explicitly_available():
    root_value = os.environ.get("VALUE_INVESTMENT_REAL_SOURCE_ROOT")
    if not root_value:
        pytest.skip("Explicit official originals required")
    root = Path(root_value).resolve()
    assert source.configured_for(root, "600887") is True
    assert source.configured_for(root, "600519") is False
    now = datetime.now(timezone.utc)
    value = source.build_operating_horizon_source_context(root=root, symbol="600887", now=now)
    assert source.build_operating_horizon_source_context(root=root, symbol="600887",
        now=now, binding=value["source_binding"]) == value
    plan_rows = [row for row in value["evidence"]
                 if row.get("kind") == "PLAN_TARGET_NOT_FUTURE_CASH_OR_PAYMENT"]
    assert len(plan_rows) == 1
    assert plan_rows[0]["id"] == "cninfo:1224808850:conditional-return-plan"
    assert "75%" in plan_rows[0]["text"]
    assert plan_rows[0]["id"] in cash.candidates(value, value["source_binding"])[
        "target_payout_ratio"]
    assert value["formal_eligibility"] is False and value["action"] == "no_order"


def test_test_only_v25_task_pins_plan_loader_without_provider_call(v19_setup, monkeypatch):
    old, facts, calls = v19_setup
    facts.setdefault("supplemental_sources", [])
    facts.setdefault("limitations", [])
    monkeypatch.setattr(source.base, "build_operating_horizon_source_context",
        lambda **kwargs: deepcopy(facts))
    monkeypatch.setattr(source.plan, "_selection", lambda *args: (
        dict(source_id="cninfo:123"), dict(path="config/plan.json", sha256="c" * 64)))
    plan_row = deepcopy(facts["evidence"][0])
    plan_row.update(id="cninfo:123:conditional-return-plan",
        source_id="cninfo:123", scope="DISCLOSED_CONDITIONAL_RETURN_PLAN",
        kind="PLAN_TARGET_NOT_FUTURE_CASH_OR_PAYMENT",
        text="TEST_ONLY conditional payout floor is not a cash payment")
    monkeypatch.setattr(source.plan, "_plan", lambda *args: (
        deepcopy(plan_row), dict(source_id="cninfo:123", sha256="d" * 64)))
    service = task.OperatingHorizonTaskService(old.root,
        source_loader=source.build_operating_horizon_source_context,
        source_loader_version=source.VERSION, test_provider=old.test_provider)
    created = service.create(symbol="600887", request_key="TEST_V25_PLAN_BOUND",
        years=[2027], now=NOW)
    assert created["status"] == "QUEUED"
    assert service.read(created["task_id"])["status"] == "QUEUED"
    assert calls == []
