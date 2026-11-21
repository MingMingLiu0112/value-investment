from datetime import datetime, timezone
from types import SimpleNamespace

from value_investment_agent.application.research import operating_cash_consumption_v7 as mod


NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def test_transport_admission_is_the_only_failed_repair_path(monkeypatch, tmp_path):
    spec = dict(symbol="600323", task_id="repair", created_at=NOW.isoformat(),
                repair_requested_at=NOW.isoformat(), repair_of={"task_id": "original"})
    state = dict(status="FAILED", updated_at=NOW.isoformat())
    service = SimpleNamespace(_directory=lambda value: tmp_path,
                              _lock=lambda value: __import__("contextlib").nullcontext(),
                              _load=lambda value: (spec, state, {}))
    monkeypatch.setattr(mod.repair, "OperatingHorizonTaskService", lambda root: service)
    captured = {}
    monkeypatch.setattr(mod.transport, "admit", lambda **kwargs: captured.update(kwargs) or {"status": "admitted"})
    monkeypatch.setattr(mod, "_compile", lambda **kwargs: {"status": "compiled", "years": {}})
    (tmp_path / "input.json").write_text("{}")
    result = mod.read_annual_supplement(root=tmp_path, symbol="600323", now=NOW)
    assert result["status"] == "compiled"
    assert captured["original_task_id"] == "original" and captured["repair_task_id"] == "repair"


def test_nonfailed_task_uses_existing_consumer(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_failed_repair", lambda root, symbol: None)
    monkeypatch.setattr(mod.prior, "read_annual_supplement", lambda **kwargs: {"status": "NOT_STARTED", "years": {}})
    assert mod.read_annual_supplement(root=tmp_path, symbol="600323", now=NOW)["status"] == "NOT_STARTED"


def test_scope_status_distinguishes_undeclared_stable_and_changed_scope():
    evidence = {"annual-p24", "annual-p183"}
    stable = [{"scope_kind": "LEGACY_ORGANIC", "revenue_change_cny": "10",
               "profit_change_cny": "2", "evidence_ids": ["annual-p24"]}]
    changed = stable + [{"scope_kind": "NEWLY_CONSOLIDATED", "revenue_change_cny": "8",
                         "profit_change_cny": "1", "evidence_ids": ["annual-p183"]}]
    assert mod._scope_decomposition_status(None, known_evidence_ids=evidence) == (
        "SCOPE_CHANGE_APPLICABILITY_NOT_DECLARED")
    assert mod._scope_decomposition_status(stable, known_evidence_ids=evidence) == (
        "STABLE_SCOPE_VERIFIED")
    assert mod._scope_decomposition_status(changed, known_evidence_ids=evidence) == (
        "SCOPE_CHANGE_VERIFIED")


def test_versioned_fy_candidate_and_cash_blockers_reach_public_projection(monkeypatch, tmp_path):
    import json
    from test_operating_cash_consumption_v1 import bridge_for, source_context
    from value_investment_agent.application.research import operating_cash_consumption_v1 as base
    from value_investment_agent.domain.research.operating_driver_bridge_v1 import build_basis, calculate_path

    context = source_context()
    context.update(d1_projection_version="existing-parent-profit-v2",
                   financial_basis="2025-12-31", source_binding={}, snapshot_fingerprint="test")
    bridge = bridge_for(context)
    basis = build_basis(context)
    for name, inputs in bridge["inputs"].items():
        inputs.update(baseline_period="2025-12-31", period_end="2027-12-31")
        bridge["paths"][name] = calculate_path(basis, inputs)
    task = dict(status="SUCCEEDED", scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED", symbol="000001",
                task_id="TEST_ONLY", research_as_of=NOW.isoformat(), source_binding={},
                context_fingerprint="test", operating_driver_bridge=bridge)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/current-operating-research-sources-v1.json").write_text('{"cases":{}}')
    monkeypatch.setattr(base, "_cold_task_context", lambda **kwargs: context)

    result = mod.read_operating_cash_consumption(root=tmp_path, task=task, now=NOW)
    annual = result["earnings_input_compilation"]
    assert all(row["missing_calendar_years"] == [2026, *range(2028, 2036)]
               for row in annual["scenarios"].values())
    assert annual["cash_model_ready"] is False and annual["selected_annual_rows"] is None
    assert "Current D2 is H1" not in json.dumps(result["current_blockers"])
    assert any(row["code"] == "SOURCE_BOUND_CASH_FOLLOWUP_SPEC_REQUIRED"
               for row in result["cash_followup_readiness"]["missing_evidence"])
    blockers = {row["code"]: row for row in result["current_blockers"]}
    assert "SOURCE_BOUND_CASH_FOLLOWUP_SPEC_REQUIRED" in blockers
    assert "parent_investment_cash" in blockers["PARENT_CASH_FLOW_FACTS_REQUIRED"]["explanation"]
    assert result["formal_eligibility"] is False and result["condition_price"] is None


def test_real_600323_versioned_d1_to_current_consumer():
    import json
    import os
    from pathlib import Path
    import pytest
    from unittest.mock import patch
    from test_operating_cash_consumption_v1 import no_io_effects
    from value_investment_agent.application.research.agent_review.operating_task_v2 import LiveOperatingTaskService

    configured = os.environ.get("OPERATING_CASH_600323_REAL_ROOT")
    if not configured:
        pytest.skip("Explicit frozen D1 Store required")
    root = Path(configured)
    now = datetime.now(timezone.utc)
    task_id = "rt-ee10b21acf245b6b4838a93ffca9b59f"
    service = LiveOperatingTaskService(root)
    original_open = os.open

    def existing_lock_only(path, flags, *args, **kwargs):
        if flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND):
            target = Path(path)
            assert target.name == "state.lock" and target.stat().st_size > 0
            assert not flags & (os.O_TRUNC | os.O_APPEND)
            flags &= ~os.O_CREAT
        return original_open(path, flags, *args, **kwargs)

    def existing_directory_only(path, *, parents=False, exist_ok=False):
        assert exist_ok and path.is_dir()

    def deny_write(*args, **kwargs):
        raise AssertionError("Unexpected low-level write")

    # The legacy supplement reader takes OS locks. Allow only established
    # lock files, with creation and all writes disabled.
    with (no_io_effects(), patch("os.open", existing_lock_only), patch("os.write", deny_write),
          patch.object(Path, "mkdir", existing_directory_only)):
        spec, state, pin = service._load(task_id, recover=False)
        task = service._view(spec, state, pin, now)
        assert task["status"] == "SUCCEEDED"
        assert pin["sha256"] == "3e89a7d4824bbd038f8ac7c5312681a5dffe6e57c4494d2ff1f36f8b74b1798f"
        assert spec["source_binding"]["sha256"] == "13574e2267aa7f90ed0a960fd8fad3f20a5ab1a27dd68e62a05095af3795dbf8"
        result = mod.read_operating_cash_consumption(root=root, task=task, now=now)
        assert service._load(task_id, recover=False) == (spec, state, pin)
    assert result["context_fingerprint"] == spec["context_fingerprint"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None and "annual_followup" not in result
    readiness = result["cash_followup_readiness"]
    assert readiness["status"] == "BLOCKED"
    compiled = result["earnings_input_compilation"]
    assert compiled["cash_model_ready"] is False and compiled["selected_annual_rows"] is None
    assert set(compiled["scenarios"]) == {"bear", "base", "bull"}
    for name, annual in compiled["scenarios"].items():
        assert result["scenarios"][name]["period_basis"] == "FY"
        assert annual["status"] == "ANNUAL_EARNINGS_CANDIDATES_COMPILED"
        assert annual["missing_calendar_years"] == [2026, *range(2028, 2036)]
        assert annual["selected_witness"] is None
        assert annual["candidates"]
    assert "Current D2 is H1" not in json.dumps(result["current_blockers"])
    assert {gap["code"] for gap in readiness["missing_evidence"]} <= {
        row["code"] for row in result["current_blockers"]}
    receipt = {key: result[key] for key in ("task_id", "status", "context_fingerprint",
                                           "source_binding", "consumption_fingerprint", "action")}
    receipt.update(task_record_binding=pin, task_input_sha256=state["input_sha256"],
                   saved_role_bindings=state["roles"],
                   historical_parent_cash=result["historical_parent_cash"],
                   blockers=result["cash_followup_readiness"]["missing_evidence"],
                   annual_compilation={name: dict(period_basis=result["scenarios"][name]["period_basis"],
                       status=row["status"], missing_calendar_years=row["missing_calendar_years"])
                       for name, row in compiled["scenarios"].items()},
                   cash_model_ready=compiled["cash_model_ready"], selected_annual_rows=compiled["selected_annual_rows"],
                   annual_supplement=result.get("annual_research_supplement", {}).get("status"),
                   scenario_names=sorted(result.get("scenarios", {})), new_api_calls=0)
    print(json.dumps(receipt, ensure_ascii=False))
