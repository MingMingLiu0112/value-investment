from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from value_investment_agent.application.product.prospective_registration import (
    register_prospective_research_plan,
    verify_prospective_registration_receipt,
)
import value_investment_agent.application.product.prospective_registration as service
from value_investment_agent.domain.research.prospective_registration import (
    prospective_registration_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "config" / "prospective-research-observation-plan-v1.json"


def _plan() -> dict[str, object]:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def _commit_plan(root: Path, plan: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Prospective test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "prospective-test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", plan.relative_to(root).as_posix()], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "register prospective test plan"], cwd=root, check=True)


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
    plan.write_bytes(PLAN.read_bytes())
    _commit_plan(root, plan)
    payload = _plan()
    fixed_now = min(
        datetime.fromisoformat(case["observation_start_at"])
        for case in payload["cases"]
    ) - timedelta(seconds=1)

    class FixedClock:
        @staticmethod
        def now(tz=timezone.utc):
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(service, "datetime", FixedClock)

    result = register_prospective_research_plan(
        root=root,
        plan_path=plan,
        output_path=runtime / "receipt.json",
    )

    receipt = json.loads((runtime / "receipt.json").read_text(encoding="utf-8"))
    assert result["action"] == receipt["action"] == "no_order"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=True).stdout.decode().strip()
    assert receipt["git_commit"] == head
    assert receipt["receipt_created_at"].endswith("+00:00")
    assert receipt["pit_time_anchor"] == "receipt_created_at"
    assert receipt["outcomes_observed"] is False
    assert receipt["valuation_executed"] is False
    assert receipt["decision_signal_created"] is False
    assert receipt["portfolio_data_used"] is False


@pytest.mark.parametrize("change", ["modified", "missing_at_head"])
def test_registration_refuses_plan_not_matching_head_without_writing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
):
    root = tmp_path / "project"
    config = root / "config"
    config.mkdir(parents=True)
    plan = config / "plan.json"
    plan.write_bytes(PLAN.read_bytes())
    _commit_plan(root, plan)
    fixed_now = min(
        datetime.fromisoformat(case["observation_start_at"])
        for case in _plan()["cases"]
    ) - timedelta(seconds=1)

    class FixedClock:
        @staticmethod
        def now(tz=timezone.utc):
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(service, "datetime", FixedClock)
    if change == "modified":
        plan.write_bytes(plan.read_bytes() + b"\n")
    else:
        subprocess.run(["git", "rm", "-q", "--", "config/plan.json"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remove prospective test plan"], cwd=root, check=True)
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_bytes(PLAN.read_bytes())

    receipt = root / "runtime" / "receipt.json"
    with pytest.raises(ValueError, match="match the file committed at HEAD"):
        register_prospective_research_plan(root=root, plan_path=plan, output_path=receipt)

    assert not receipt.exists()


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


def test_receipt_verifier_rejects_future_claimed_creation_time(tmp_path: Path):
    root = tmp_path / "project"
    config = root / "config"
    config.mkdir(parents=True)
    plan = config / "plan.json"
    payload = _plan()
    for case in payload["cases"]:
        case["observation_start_at"] = "2031-01-01T00:00:00+00:00"
        case["baseline_cutoff_at"] = "2031-01-01T00:00:00+00:00"
    plan.write_text(json.dumps(payload), encoding="utf-8")
    _commit_plan(root, plan)
    receipt_path = root / "runtime" / "receipt.json"
    register_prospective_research_plan(root=root, plan_path=plan, output_path=receipt_path)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["receipt_created_at"] = "2030-01-01T00:00:00+00:00"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="cannot be in the future"):
        verify_prospective_registration_receipt(
            root=root,
            receipt_path="runtime/receipt.json",
            receipt_sha256=receipt_sha256,
            plan_path="config/plan.json",
        )
