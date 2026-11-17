"""Registry tests: one authoritative writer per decision-state scope."""
from copy import deepcopy
from pathlib import Path

from value_investment_agent.operations.decision_writer_registry import (
    audit,
    compare_observed_tasks,
    load_registry,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "decision-writers-registry-v1.json"


def _registry() -> dict:
    return load_registry(REGISTRY)


def test_current_registry_matches_observed_tasks_and_passes():
    observed = {
        "ValueInvestmentAgent-DailyUpdate": "Ready",
        "ValueInvestmentAgent-MoutaiB1ExcelPublish": "Ready",
        "ValueInvestmentAgent-MoutaiPostclosePolicyStage": "Disabled",
        "ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh": "Ready",
    }
    report = audit(_registry(), observed=observed)
    assert report["status"] == "PASS"
    assert report["errors"] == []


def test_two_effective_writers_in_one_scope_are_rejected():
    payload = deepcopy(_registry())
    duplicate = deepcopy(payload["pipelines"][0])
    duplicate["id"] = "second-public-packet-writer"
    payload["pipelines"].append(duplicate)
    errors = validate_registry(payload)
    assert any(error.startswith("MULTIPLE_AUTHORITATIVE_WRITERS:public_daily_observation")
               for error in errors)


def test_undeclared_scheduled_writer_is_rejected():
    observed = {"ValueInvestmentAgent-UnknownWriter": "Ready"}
    errors = compare_observed_tasks(_registry(), observed)
    assert "UNDECLARED_WRITER_TASK:ValueInvestmentAgent-UnknownWriter" in errors


def test_legacy_observer_cannot_be_consumed_by_current_product():
    payload = deepcopy(_registry())
    legacy = next(item for item in payload["pipelines"] if item["kind"] == "LEGACY")
    legacy["consumed_by_current_product"] = True
    errors = validate_registry(payload)
    assert f"OBSERVER_MARKED_AS_CURRENT_CONSUMER:{legacy['id']}" in errors


def test_effective_writer_needs_a_declared_authority_scope():
    payload = deepcopy(_registry())
    payload["pipelines"][0]["writes_scopes"].append("undeclared_scope")
    errors = validate_registry(payload)
    assert any(error.startswith("UNKNOWN_AUTHORITY_SCOPE:daily-public-packet") for error in errors)