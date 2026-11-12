from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from test_operating_horizon_task_v4 import env
from test_operating_horizon_sources_v1 import source_env  # noqa: F401 - dependency of shared v4 fixture
from test_operating_horizon_draft_v1 import NOW, context  # noqa: F401 - dependency of source fixture
from test_operating_horizon_task_v5_wc import wps_hardlink_fallback  # noqa: F401
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v1 import (
    read_d2_cash_policy_e2_input,
    read_v4_cash_policy_e2_input,
    read_split_d2_e2_input,
)


def test_v6_same_task_e2_projection_requires_both_sealed_stages_and_wc_pin(monkeypatch, request):
    """TEST_ONLY with explicit real public WC originals; no model/network call."""
    from test_operating_horizon_task_v5_wc import env as wc_env, NOW as wc_now
    from test_operating_horizon_task_v6_split import service as split_service

    environment = wc_env.__wrapped__(request.getfixturevalue("tmp_path"), monkeypatch)
    runner, calls = split_service(environment, monkeypatch)
    original = runner.source_loader

    def enriched_source(**kwargs):
        context = original(**kwargs)
        context["action"] = "no_order"
        for row in context["evidence"]:
            if row.get("unit") == "CNY":
                row["kind"] = "VERIFIED_REPORTED_FACT"
                row["physical_page"] = 1
        pbt = next(row for row in context["evidence"] if row.get("field") == "pre_tax_profit")
        for field, amount, scope in (("tax", "91", "consolidated"),
                                     ("parent_profit", "346", "consolidated_parent")):
            row = deepcopy(pbt)
            row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
            context["evidence"].append(row)
        return context

    runner.source_loader = enriched_source
    task = runner.create(symbol="600519", request_key="V6_E2_SAME_TASK", years=[2026], now=wc_now)
    assert runner.run(task["task_id"], now=wc_now)["status"] == "SUCCEEDED"
    assert calls == ["annual", "cash"]
    result = read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
        now=wc_now + timedelta(hours=1), service=runner)
    assert result["annual_operating_status"] == "SAME_TASK_COMPILED", result["annual_operating_error"]
    assert result["annual_operating_candidates"]["2026"]["task_id"] == task["task_id"]
    assert result["input_manifest"]["split_contract"]["action"] == "no_order"
    assert len(result["input_manifest"]["source_bindings"]) == 5
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None

    from types import SimpleNamespace
    view = runner.read(task["task_id"])
    projected = SimpleNamespace(read=lambda _: view, source_loader=runner.source_loader,
        _load=runner._load, _context=runner._context)
    del view["stage_responses"]
    with pytest.raises(ValueError, match="D2_V6_SPLIT_RESPONSE_BINDING_REQUIRED"):
        read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
            now=wc_now + timedelta(hours=1), service=projected)
    view.update(runner.read(task["task_id"]))
    term = view["research_result"]["years"]["2026"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"]
    term.update(classification="UNKNOWN", value=None, unit="not_quantified")
    with pytest.raises(ValueError, match="D2_V6_UNKNOWN_CASH_TERM_NOT_E2_INPUT"):
        read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
            now=wc_now + timedelta(hours=1), service=projected)
    view.update(runner.read(task["task_id"]))
    view["wc_source_binding"] = {**view["wc_source_binding"], "originals": []}
    with pytest.raises(ValueError, match="D2_V6_TASK_SOURCE_PIN_CHANGED"):
        read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
            now=wc_now + timedelta(hours=1), service=projected)


def test_v7_same_task_e2_input_preserves_unknown_and_requires_sealed_stages(monkeypatch, request):
    from test_operating_horizon_task_v5_wc import env as wc_env, NOW as wc_now
    from test_operating_horizon_task_v7_split import service as split_service
    from types import SimpleNamespace

    environment = wc_env.__wrapped__(request.getfixturevalue("tmp_path"), monkeypatch)
    runner, calls = split_service(environment, monkeypatch)
    task = runner.create(symbol="600519", request_key="V7_E2_SAME_TASK", years=[2026], now=wc_now)
    assert runner.run(task["task_id"], now=wc_now)["status"] == "SUCCEEDED"
    assert calls == ["annual", "cash"]
    result = read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
        now=wc_now + timedelta(hours=1), service=runner)
    assert result["status"] == "SOURCE_BOUND_D2_V7_CASH_POLICY_READY_FOR_E2"
    assert result["input_manifest"]["task_contract"] == "operating-horizon-task-v7-split"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None
    view = runner.read(task["task_id"])
    projected = SimpleNamespace(read=lambda _: view, source_loader=runner.source_loader,
        _load=runner._load, _context=runner._context)
    del view["stage_responses"]
    with pytest.raises(ValueError, match="D2_V7_SPLIT_RESPONSE_BINDING_REQUIRED"):
        read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
            now=wc_now + timedelta(hours=1), service=projected)
    view.update(runner.read(task["task_id"]))
    term = view["research_result"]["years"]["2026"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"]
    term.update(classification="UNKNOWN", value=None, unit="not_quantified")
    with pytest.raises(ValueError, match="D2_V7_UNKNOWN_CASH_TERM_NOT_E2_INPUT"):
        read_d2_cash_policy_e2_input(root=environment.root, task_id=task["task_id"],
            now=wc_now + timedelta(hours=1), service=projected)


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


def test_v5_wc_policy_requires_its_independent_source_binding(env):
    """TEST_ONLY projection: WC evidence must join the E2 input fingerprint."""
    from types import SimpleNamespace
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v5_wc import (
        CONTRACT as WC_CONTRACT,
    )
    from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v1 import (
        read_d2_cash_policy_e2_input,
    )

    service, task_id = _task(env)
    row = service.read(task_id)
    row["workflow"] = WC_CONTRACT
    row["wc_source_binding"] = {
        "registry": {"path": "config/test-only-wc.json", "sha256": "a" * 64},
        "originals": [],
        "history_sha256": "b" * 64,
    }
    projected = SimpleNamespace(read=lambda _: row, source_loader=service.source_loader)
    result = read_d2_cash_policy_e2_input(
        root=env.root, task_id=task_id, now=datetime.now(timezone.utc), service=projected
    )
    assert result["input_manifest"]["task_contract"] == WC_CONTRACT
    assert result["input_manifest"]["source_bindings"][2] == row["wc_source_binding"]
    assert result["action"] == "no_order" and result["condition_price"] is None
    del row["wc_source_binding"]
    with pytest.raises(ValueError, match="D2_WC_SOURCE_BINDING_REQUIRED"):
        read_d2_cash_policy_e2_input(
            root=env.root, task_id=task_id, now=datetime.now(timezone.utc), service=projected
        )


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
