from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from value_investment_agent.application.product.prospective_registration import (
    register_prospective_research_plan,
)
import value_investment_agent.application.product.prospective_registration as service
from value_investment_agent.domain.research.prospective_registration import (
    prospective_registration_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "config" / "prospective-research-observation-plan-v1.json"


def _plan() -> dict[str, object]:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_committed_plan_is_bounded_no_order_and_excludes_moutai_stop_case():
    registration = prospective_registration_from_payload(_plan())

    assert registration.action == "no_order"
    assert [case.symbol for case in registration.cases] == ["000333", "600887", "601088"]
    assert registration.declared_registered_at.isoformat() == "2026-09-27T09:30:00+08:00"
    assert any("600519" in reason for reason in registration.exclusions)


def test_future_baseline_or_execution_semantics_fail_closed():
    future = copy.deepcopy(_plan())
    future["cases"][0]["baseline_cutoff_at"] = "2026-09-28T09:30:00+08:00"
    with pytest.raises(ValueError, match="baseline_cutoff_at"):
        prospective_registration_from_payload(future)

    execution = copy.deepcopy(_plan())
    execution["action"] = "buy"
    with pytest.raises(ValueError, match="action=no_order"):
        prospective_registration_from_payload(execution)


def test_registration_receipt_is_runtime_only_and_does_not_observe_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "project"
    config = root / "config"
    runtime = root / "runtime"
    config.mkdir(parents=True)
    plan = config / "plan.json"
    plan.write_text(PLAN.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(service, "_git_head", lambda _: "a" * 40)

    result = register_prospective_research_plan(
        root=root,
        plan_path=plan,
        output_path=runtime / "receipt.json",
    )

    receipt = json.loads((runtime / "receipt.json").read_text(encoding="utf-8"))
    assert result["action"] == receipt["action"] == "no_order"
    assert receipt["git_commit"] == "a" * 40
    assert receipt["receipt_created_at"].endswith("+00:00")
    assert receipt["pit_time_anchor"] == "receipt_created_at"
    assert receipt["outcomes_observed"] is False
    assert receipt["valuation_executed"] is False
    assert receipt["decision_signal_created"] is False
    assert receipt["portfolio_data_used"] is False


def test_receipt_after_observation_start_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "project"
    config = root / "config"
    config.mkdir(parents=True)
    plan = config / "plan.json"
    payload = _plan()
    payload["schema_version"] = "prospective-research-registration-v2"
    payload["declared_registered_at"] = payload.pop("registered_at")
    for case in payload["cases"]:
        case["observation_start_at"] = "2020-01-01T00:00:00+00:00"
        case["baseline_cutoff_at"] = "2020-01-01T00:00:00+00:00"
    plan.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(service, "_git_head", lambda _: "a" * 40)

    with pytest.raises(ValueError, match="on or before observation_start_at"):
        register_prospective_research_plan(
            root=root, plan_path=plan, output_path=root / "runtime" / "receipt.json",
        )


def test_registration_refuses_non_runtime_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "project"
    config = root / "config"
    config.mkdir(parents=True)
    plan = config / "plan.json"
    plan.write_text(PLAN.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(service, "_git_head", lambda _: "a" * 40)

    with pytest.raises(ValueError, match="under runtime"):
        register_prospective_research_plan(
            root=root,
            plan_path=plan,
            output_path=root / "receipt.json",
        )
