from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from test_operating_horizon_task_v4 import env
from test_operating_horizon_sources_v1 import source_env  # noqa: F401 - dependency of shared v4 fixture
from test_operating_horizon_draft_v1 import NOW, context  # noqa: F401 - dependency of source fixture
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v1 import (
    read_v4_cash_policy_e2_input,
    read_split_d2_e2_input,
)


def test_split_d2_compiles_only_two_successful_same_source_tasks(source_env, monkeypatch):
    """TEST_ONLY source fixture; proves contract joining, not real issuer quality."""
    import json
    from types import SimpleNamespace
    import test_operating_horizon_task_v2 as annual_tests
    from test_operating_horizon_draft_v3 import payload as full_payload
    from value_investment_agent.application.research.agent_review import (
        operating_cash_policy_task_v1 as cash_task,
        operating_horizon_sources_v1 as sources,
    )
    from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

    fixture = annual_tests.env.__wrapped__(source_env, monkeypatch)
    bound = source_env.load(now=NOW)
    for row in bound["evidence"]:
        if row.get("unit") == "CNY":
            row["kind"] = "VERIFIED_REPORTED_FACT"
    pbt = next(row for row in bound["evidence"] if row.get("field") == "pre_tax_profit")
    for field, amount, scope in (("tax", "91", "consolidated"),
                                 ("parent_profit", "346", "consolidated_parent")):
        row = deepcopy(pbt)
        row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
        bound["evidence"].append(row)
    monkeypatch.setattr(sources, "build_operating_horizon_source_context",
                        lambda **kwargs: deepcopy(bound))
    annual_service = fixture.service()
    annual = annual_service.create(symbol="123456", request_key="SPLIT_TEST_ANNUAL",
                                   years=[2026], now=NOW)
    assert annual_service.run(annual["task_id"])["status"] == "SUCCEEDED"
    cash_response = {"years": {"2026": {"shareholder_cash_paths":
        full_payload()["years"]["2026"]["shareholder_cash_paths"]}}}
    provider = SimpleNamespace(complete=lambda request: LLMResponse(
        json.dumps(cash_response), 100, 50, "TEST_ONLY"))
    cash_service = cash_task.OperatingCashPolicyTaskService(fixture.root, test_provider=provider)
    cash = cash_service.create(symbol="123456", request_key="SPLIT_TEST_CASH",
                               years=[2026], now=NOW)
    assert cash_service.run(cash["task_id"])["status"] == "SUCCEEDED"
    joined = read_split_d2_e2_input(root=fixture.root, annual_task_id=annual["task_id"],
        cash_task_id=cash["task_id"], now=datetime.now(timezone.utc),
        annual_service=annual_service, cash_service=cash_service)
    assert joined["annual_operating_status"] == "SEPARATE_SAME_CORPUS_TASK_COMPILED"
    assert set(joined["annual_operating_candidates"]["2026"]["scenarios"]) == {
        "bear", "base", "bull"}
    assert joined["policy_years"]["2026"]["base"]["complete"] is True
    assert joined["action"] == "no_order" and joined["condition_price"] is None
    with pytest.raises(ValueError, match="SPLIT_D2_IDENTITY_OR_CUTOFF_INVALID"):
        read_split_d2_e2_input(root=fixture.root, annual_task_id=annual["task_id"],
            cash_task_id=annual["task_id"], now=datetime.now(timezone.utc),
            annual_service=annual_service, cash_service=cash_service)


def test_interim_source_date_never_becomes_annual_opening_basis():
    from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v1 import (
        _annual_opening_period,
    )
    row = {"operating_paths": {name: {"baseline_period": "2025-12-31"}
        for name in ("bear", "base", "bull")}}
    assert _annual_opening_period(row) == "2025-12-31"
    row["operating_paths"]["bear"]["baseline_period"] = "2026-06-30"
    with pytest.raises(ValueError, match="INCONSISTENT_OPERATING_BASELINE"):
        _annual_opening_period(row)
    row = {"operating_paths": {name: {"baseline_period": "2026-06-30"}
        for name in ("bear", "base", "bull")}}
    with pytest.raises(ValueError, match="COMPLETE_FY_OPERATING_BASELINE_REQUIRED"):
        _annual_opening_period(row)


def _task(environment):
    service = environment.service()
    created = service.create(symbol="123456", request_key="TEST_ONLY_E2_POLICY", years=[2026], now=NOW)
    assert service.run(created["task_id"])["status"] == "SUCCEEDED"
    return service, created["task_id"]


def test_reads_complete_v4_policy_as_source_bound_e2_input(env):
    service, task_id = _task(env)
    result = read_v4_cash_policy_e2_input(root=env.root, task_id=task_id,
                                          now=datetime.now(timezone.utc), service=service)
    assert result["status"] == "SOURCE_BOUND_D2_V4_CASH_POLICY_READY_FOR_E2"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["policy_years"]["2026"]["base"]["complete"] is True
    assert result["annual_operating_status"] == "ANNUAL_OPERATING_INPUT_UNASSESSABLE"
    assert result["annual_operating_error"].startswith("UNIQUE_REPORTED_FACT_REQUIRED")
    assert result["annual_operating_candidates"] == {}
    assert result["condition_price"] is None and result["main_range_adopted"] is False


def test_rejects_incomplete_or_future_task_result(env):
    service, task_id = _task(env)
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AT_E2_CUTOFF"):
        read_v4_cash_policy_e2_input(root=env.root, task_id=task_id,
                                     now=NOW - timedelta(seconds=1), service=service)
    with pytest.raises(ValueError, match="timezone-aware"):
        read_v4_cash_policy_e2_input(root=env.root, task_id=task_id,
                                     now=NOW.replace(tzinfo=None), service=service)
    # A new task is not a completed cash-policy input.
    queued = service.create(symbol="123456", request_key="TEST_ONLY_E2_QUEUED", years=[2026], now=NOW + timedelta(days=1))
    with pytest.raises(ValueError, match="SUCCEEDED_BOUND"):
        read_v4_cash_policy_e2_input(root=env.root, task_id=queued["task_id"], now=NOW + timedelta(days=1), service=service)


def test_complete_test_only_annual_facts_compile_from_same_task(env, source_env, monkeypatch):
    """Positive mechanism fixture; not real issuer research or model acceptance."""
    from value_investment_agent.application.research.agent_review import operating_horizon_task_v4 as v4

    bound = source_env.load(now=NOW)
    for row in bound["evidence"]:
        if row.get("unit") == "CNY":
            row["kind"] = "VERIFIED_REPORTED_FACT"
    pbt = next(row for row in bound["evidence"] if row.get("field") == "pre_tax_profit")
    for field, value, scope in (("tax", "91", "consolidated"),
                                ("parent_profit", "346", "consolidated_parent")):
        anchor = deepcopy(pbt)
        anchor.update(id="TEST_ONLY:" + field, field=field, value=value, scope=scope)
        bound["evidence"].append(anchor)
    monkeypatch.setattr(v4.sources, "build_operating_horizon_source_context",
                        lambda **kwargs: deepcopy(bound))
    service = env.service()
    task = service.create(symbol="123456", request_key="TEST_ONLY_E2_COMPLETE_ANNUAL", years=[2026], now=NOW)
    assert service.run(task["task_id"])["status"] == "SUCCEEDED"
    result = read_v4_cash_policy_e2_input(root=env.root, task_id=task["task_id"],
                                           now=datetime.now(timezone.utc), service=service)
    assert result["annual_operating_status"] == "SAME_TASK_COMPILED"
    assert set(result["annual_operating_candidates"]["2026"]["scenarios"]) == {"bear", "base", "bull"}
    assert result["annual_operating_candidates"]["2026"]["task_id"] == task["task_id"]
    assert result["condition_price"] is None and result["formal_eligibility"] is False
