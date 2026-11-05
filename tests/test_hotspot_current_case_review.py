from copy import deepcopy
from datetime import datetime
import json

import pytest

from value_investment_agent.application.hotspot.current_case_review import (
    expire_price_action_plan, inspect_current_price_case, is_stale_current_price_error,
)
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.application.hotspot import independent_price_conditions as independent
from value_investment_agent.quote_sessions import CHINA
from test_hotspot_current_price_case import capture, NOW


def inspect(root, case, now=NOW):
    return inspect_current_price_case(root=root, symbol=case["symbol"],
        case_binding=dict(path=case["case_path"], sha256=case["case_sha256"]), now=now)


@pytest.mark.parametrize("message,expected", [
    ("B1 current close rejected: stale_quote", True),
    ("Display close is not calendar-bound latest completed session: stale_quote", True),
    ("B1 current close rejected: source_conflict", False),
    ("Current source hash/identity/availability mismatch", False),
    ("Display bundle hash mismatch", False),
])
def test_only_explicit_market_expiry_can_retain_history(message, expected):
    assert is_stale_current_price_error(ValueError(message)) is expected


def test_verified_stale_source_is_not_invalid_or_strategy_approved(tmp_path):
    case = capture(tmp_path)
    result = inspect(tmp_path, case, datetime(2026, 9, 28, 16, tzinfo=CHINA))
    assert result["data_status"] == "STALE"
    assert result["source_integrity"] == "VERIFIED"
    assert result["current_pit"] is False
    assert result["case"]["case_sha256"] == case["case_sha256"]
    assert result["strategy_validation"] == "NOT_EVALUATED"


@pytest.mark.parametrize("target", ["case", "minute", "quote"])
def test_corrupted_stale_evidence_does_not_become_history(tmp_path, target):
    case = capture(tmp_path)
    name = (case["case_path"] if target == "case" else
            case["source_bindings"]["60m"]["path"] if target == "minute" else
            case["current_reference_close"]["bundle_path"])
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b" ")
    result = inspect(tmp_path, case, datetime(2026, 9, 28, 16, tzinfo=CHINA))
    assert result["data_status"] == "INVALID" and result["case"] is None
    assert result["source_integrity"] == "NOT_VERIFIED"


def test_future_availability_and_naive_cutoff_are_not_stale(tmp_path):
    case = capture(tmp_path)
    assert inspect(tmp_path, case, datetime(2026, 9, 24, 14, tzinfo=CHINA))["data_status"] == "INVALID"
    with pytest.raises(ValueError, match="timezone-aware"):
        inspect(tmp_path, case, datetime(2026, 9, 28))


def test_expiry_clears_all_current_actions_but_retains_verified_history(tmp_path):
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    before = deepcopy(plan)
    result = expire_price_action_plan(plan,
        review=inspect(tmp_path, case, datetime(2026, 9, 28, 16, tzinfo=CHINA)))
    for field in ("entry_condition", "add_condition", "reduce_condition", "exit_condition",
                  "security_risk_trigger", "current_reference_price", "price_behavior"):
        assert result[field] is None
    assert result["conditional_action_rules"] == {}
    assert result["historical_observation"]["current_reference_price"] == plan["current_reference_price"]
    assert result["historical_observation"]["action_intent"] == "WATCH"
    assert plan == before


def test_signed_release_cannot_discard_current_integrity_blocker(tmp_path, monkeypatch):
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(case_path=case["case_path"], case_sha256=case["case_sha256"],
        signal_state="TRIGGER_OBSERVED", opportunity_quality={"structure_tier": "STRUCTURE_QUALIFIED_OBSERVATION"},
        blockers=["VALUE_GATE_NOT_PROVEN", "CURRENT_CASE_CHANGED_OR_STALE"])
    monkeypatch.setattr(independent, "load_independent_admission", lambda *a, **kw: dict(
        risk_review_eligible=True, blockers=[], rule_version=plan["model_or_rule_version"],
        gate_source_bindings={"price_structure": [dict(path=case["case_path"], sha256=case["case_sha256"])]}))
    result = independent.project_independent_price_condition(tmp_path, symbol=case["symbol"], plan=plan, now=NOW)
    assert result["risk_review_eligible"] is False
    assert "CURRENT_CASE_CHANGED_OR_STALE" in result["blockers"]
    assert "VALUE_GATE_NOT_PROVEN" not in result["blockers"]


def test_stale_projection_also_suppresses_held_conditions(tmp_path):
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(signal_state="STALE", current_data_status="CURRENT")
    output = independent.project_independent_price_condition(tmp_path, symbol=case["symbol"],
        plan=plan, now=NOW)
    assert output["current_data_status"] == "STALE"
    assert output["current_reference_price"] is output["add_condition"] is output["reduce_condition"] is None
    assert output["conditional_action_rules"] == {}
    assert output["action_intent"] == "WATCH"


def test_retired_rows_cannot_make_current_registry_look_current(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import current_registry as registry
    from hashlib import sha256

    case = capture(tmp_path)
    report = dict(observation_list=[dict(symbol=case["symbol"])])
    watch = tmp_path / "runtime/watch.json"
    watch.write_text(json.dumps(report), encoding="utf-8")
    source = dict(path="runtime/watch.json", sha256=sha256(watch.read_bytes()).hexdigest())
    row = dict(symbol=case["symbol"], company_name="TEST_ONLY", case_path=case["case_path"],
               case_sha256=case["case_sha256"])
    path = tmp_path / registry.REGISTRY
    path.parent.mkdir()
    path.write_text(json.dumps(dict(schema_version="current-price-conditions-v1", action="no_order",
        watch_source_binding=source, watch_source_scope="TEST_ONLY", items=[row])), encoding="utf-8")
    now = datetime(2026, 9, 28, 16, tzinfo=CHINA)
    result = registry.load_price_conditions(tmp_path, now=now, research_version=None)
    assert result["status"] == "BLOCKED" and result["items"] == []
    result = registry.load_price_conditions(tmp_path, now=now, research_version=None, retain_stale_observations=True)
    assert result["status"] == "BLOCKED"
    assert result["case_reviews"][0]["data_status"] == "STALE"
    assert result["items"][0]["price_action_plan"]["current_reference_price"] is None
