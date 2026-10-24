"""Current conditions consume real retained validation without inheriting admission."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot import independent_price_conditions as projection
from value_investment_agent.application.hotspot import replay_read_model as read_model
from value_investment_agent.application.hotspot import validation_evidence
from value_investment_agent.application.hotspot.current_case_review import suppress_current_price_conditions
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from test_hotspot_current_price_case import capture, NOW
from test_independent_hotspot_projection import isolated


ROOT = Path(__file__).resolve().parents[1]
REPLAY_NOW = datetime(2026, 10, 22, 16, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def retained_validation():
    return read_model.load_current_hotspot_validation(root=ROOT, now=REPLAY_NOW)


def current_plan(root):
    case = capture(root)
    plan = project_current_price_action_plan(case)
    plan.update(case_path=case["case_path"], case_sha256=case["case_sha256"])
    return plan


def test_real_retained_validation_is_recomputed_with_unknown_execution(retained_validation):
    result = retained_validation
    assert result["status"] == "PARTIAL" and result["source_integrity"] == "VERIFIED"
    assert result["namespace"] == "ACTUAL"
    assert (result["signal_event_count"], result["mature_five_session_count"],
            result["right_censored_count"]) == (161, 150, 11)
    assert len(result["case_bindings"]) == 5 and len(result["source_bindings"]) == 19
    assert result["trade_count"] is None
    assert result["execution_metrics"]["cost_sensitivity"] is None
    assert result["execution_metrics"]["t_plus_one_feasibility"] == "UNKNOWN"
    assert result["strict_pit_admitted"] is result["strict_oos_admitted"] is False
    assert result["elapsed_real_shadow_sessions"] == 0
    assert result["strategy_validation"] == "NOT_PROVEN"


def test_current_plan_carries_three_timeframes_conditions_and_validation(
        tmp_path, monkeypatch, retained_validation):
    # The price fixture is synthetic; the real historical sample is unrelated.
    source = current_plan(tmp_path)
    before = deepcopy(source)
    monkeypatch.setattr(projection, "load_current_hotspot_validation",
                        lambda **kwargs: retained_validation)
    result = projection.project_independent_price_condition(tmp_path,
        symbol=source["symbol"], plan=source, now=NOW)
    assert source == before
    assert result["validation"]["applicability"] == "HISTORICAL_OTHER_CASES_NOT_CURRENT_STRUCTURE"
    assert result["validation"]["current_rule_matches_replayed_rule"] is True
    conditions = result["operational_conditions"]
    assert conditions["validation_evidence_sha256"] == retained_validation["evidence_sha256"]
    assert conditions["case_binding"]["sha256"] == source["case_sha256"]
    assert conditions["timeframes"]["60m"]["prior_max_high"] == source["entry_trigger_price"]
    assert conditions["timeframes"]["60m"]["volume_ratio"] == source["levels"]["60m"]["volume_ratio"]
    assert conditions["timeframes"]["daily"]["role"] == "TREND_CONTEXT"
    assert conditions["timeframes"]["15m"]["role"] == "AUXILIARY_OBSERVATION_ONLY"
    assert set(conditions["conditions"]) == {"OPEN", "ADD", "REDUCE", "EXIT"}
    assert conditions["conditions"]["OPEN"]["rule"] == projection.INDEPENDENT_OPEN_RULE
    assert conditions["conditions"]["EXIT"]["price"] == source["invalidation_price"]
    assert conditions["risk_reward_scope"] == "STRUCTURAL_DISTANCE_BEFORE_COST_NOT_EXPECTED_RETURN"
    assert "RETAINED_SAMPLE_DOES_NOT_VALIDATE_CURRENT_CASE" in conditions["blockers"]
    assert "VALUE_GATE_NOT_PROVEN" not in conditions["blockers"]
    assert conditions["holdings_status"] == "UNKNOWN" and conditions["position_guidance"] is None
    assert conditions["formal_eligibility"] is conditions["personal_permission"] is False
    assert conditions["action"] == "no_order"
    result["validation"]["case_bindings"].clear()
    assert len(retained_validation["case_bindings"]) == 5


@pytest.mark.parametrize("changed", [None, "hash", "path", "symbol", "rule"])
def test_same_case_requires_exact_identity_and_frozen_rule(
        tmp_path, monkeypatch, retained_validation, changed):
    source = current_plan(tmp_path)
    row = retained_validation["case_bindings"][0]
    source.update(symbol=row["symbol"], case_path=row["case_path"], case_sha256=row["case_sha256"])
    if changed == "hash":
        source["case_sha256"] = "0" * 64
    elif changed == "path":
        source["case_path"] = "another-case.json"
    elif changed == "symbol":
        source["symbol"] = "000001"
    elif changed == "rule":
        source["model_or_rule_version"] = "TEST_ONLY-different-rule"
    monkeypatch.setattr(projection, "load_current_hotspot_validation",
                        lambda **kwargs: retained_validation)
    result = projection.project_independent_price_condition(tmp_path,
        symbol=source["symbol"], plan=source, now=NOW)
    assert result["validation"]["applicability"] == (
        "SAME_CASE_DESCRIPTIVE_ONLY" if changed is None else
        "HISTORICAL_OTHER_CASES_NOT_CURRENT_STRUCTURE")
    assert result["risk_review_eligible"] is result["formal_eligibility"] is False


def test_batch_replays_once_and_isolates_each_plan(tmp_path, monkeypatch, retained_validation):
    source = current_plan(tmp_path)
    calls = []
    def validation(**kwargs):
        calls.append(kwargs)
        return retained_validation
    monkeypatch.setattr(projection, "load_current_hotspot_validation", validation)
    monkeypatch.setattr(projection, "load_price_conditions", lambda *a, **kw:
        dict(items=[dict(symbol=source["symbol"], price_action_plan=source) for _ in range(3)]))
    result = projection.load_independent_price_conditions(tmp_path, now=NOW, research_version=None)
    assert len(calls) == 1
    assert result["validation"] == retained_validation
    first, second = [row["price_action_plan"] for row in result["items"][:2]]
    first["validation"]["blockers"].append("TEST_ONLY_MUTATION")
    assert "TEST_ONLY_MUTATION" not in second["validation"]["blockers"]
    assert "TEST_ONLY_MUTATION" not in retained_validation["blockers"]


def test_empty_current_selection_still_exposes_separate_retained_validation(
        tmp_path, monkeypatch, retained_validation):
    monkeypatch.setattr(projection, "load_current_hotspot_validation",
                        lambda **kwargs: retained_validation)
    monkeypatch.setattr(projection, "load_price_conditions", lambda *a, **kw:
        dict(status="CURRENT_EMPTY_SELECTION", items=[]))
    result = projection.load_independent_price_conditions(tmp_path, now=NOW, research_version=None)
    assert result["status"] == "CURRENT_EMPTY_SELECTION" and result["items"] == []
    assert result["validation"]["signal_event_count"] == 161
    assert result["validation"]["trade_count"] is None


def test_batch_projection_reuses_verified_rows_without_reloading_registry(tmp_path, monkeypatch):
    source = current_plan(tmp_path)
    rows = [dict(symbol=source["symbol"], company_name="TEST_ONLY", price_action_plan=source)]
    before = deepcopy(rows)
    def unexpected(*args, **kwargs):
        raise AssertionError("Caller already verified its rows")
    monkeypatch.setattr(projection, "load_price_conditions", unexpected)
    result = projection.project_independent_price_conditions(tmp_path, items=rows, now=NOW)
    assert rows == before
    assert result["items"][0]["company_name"] == "TEST_ONLY"
    assert result["items"][0]["price_action_plan"]["operational_conditions"]["conditions"]["OPEN"]
    assert result["validation"]["status"] == "NOT_RUN"


@pytest.mark.parametrize("state", ["STALE", "BLOCKED", "EXPIRED"])
def test_expired_conditions_never_reappear_from_valid_historical_sample(
        tmp_path, monkeypatch, retained_validation, state):
    source = current_plan(tmp_path)
    source["signal_state"] = state
    monkeypatch.setattr(projection, "load_current_hotspot_validation",
                        lambda **kwargs: retained_validation)
    result = projection.project_independent_price_condition(tmp_path,
        symbol=source["symbol"], plan=source, now=NOW)
    operational = result["operational_conditions"]
    assert operational["status"] == "UNAVAILABLE_CURRENT_CONDITIONS"
    assert operational["conditions"] == operational["timeframes"] == {}
    assert operational["risk_reward_ratio"] is operational["expires_after_session"] is None
    assert result["validation"]["signal_event_count"] == 161
    assert suppress_current_price_conditions(result)["operational_conditions"] is None


@pytest.mark.parametrize("pins", [None, {}, [], {"action": "order"},
    {"action": "no_order", "retained_manifest_binding": {"path": "missing", "sha256": "0" * 64}}])
def test_missing_or_invalid_validation_does_not_hide_verified_prices(tmp_path, pins):
    source = current_plan(tmp_path)
    if pins is not None:
        pointer = tmp_path / read_model.REVIEW_POINTER
        pointer.parent.mkdir(exist_ok=True)
        pointer.write_text(json.dumps(pins), encoding="utf-8")
    result = projection.project_independent_price_condition(tmp_path,
        symbol=source["symbol"], plan=source, now=NOW)
    assert result["validation"]["status"] == ("NOT_RUN" if pins is None else "UNAVAILABLE")
    assert result["validation"]["trade_count"] is None
    assert result["current_data_status"] == "CURRENT"
    assert result["entry_trigger_price"] == source["entry_trigger_price"]
    assert result["operational_conditions"]["conditions"]["OPEN"]["price"] == source["entry_trigger_price"]
    assert result["risk_review_eligible"] is False


@pytest.mark.parametrize("namespace", ["TEST_ONLY", "SIMULATED"])
def test_configured_test_evidence_cannot_enter_actual_current_context(tmp_path, monkeypatch, namespace):
    pointer = tmp_path / read_model.REVIEW_POINTER
    pointer.parent.mkdir()
    pointer.write_text(json.dumps(dict(action="no_order", retained_manifest_binding={})), encoding="utf-8")
    monkeypatch.setattr(validation_evidence, "build_hotspot_quantitative_validation", lambda **kw: dict(
        schema_version="hotspot-retained-descriptive-validation-v1", namespace=namespace,
        scope="DESCRIPTIVE", action="no_order", formal_eligibility=False, trade_count=None))
    result = read_model.load_current_hotspot_validation(root=tmp_path, now=NOW)
    assert result["status"] == "UNAVAILABLE"
    assert result["source_integrity"] == "NOT_VERIFIED"
    assert result["case_bindings"] == []


def test_validation_context_rejects_naive_cutoff(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        read_model.load_current_hotspot_validation(root=tmp_path, now=datetime(2026, 10, 22))


@pytest.mark.parametrize("has_status", [False, True])
@pytest.mark.parametrize("has_levels", [False, True])
@pytest.mark.parametrize("has_validation", [False, True])
def test_legacy_optional_fields_support_single_and_batch_projection(
        isolated, tmp_path, has_status, has_levels, has_validation):
    rows = isolated[0]["items"]
    source = rows[0]["price_action_plan"]
    if has_status:
        source["current_data_status"] = "CURRENT"
    if has_levels:
        source["levels"] = {"60m": dict(prior_max_high="12.34", volume_ratio="1.2")}
    if has_validation:
        source["validation"] = dict(status="TEST_ONLY_UNVERIFIED_INPUT", formal_eligibility=True)
    before = deepcopy(rows)
    single = projection.project_independent_price_condition(tmp_path,
        symbol=source["symbol"], plan=source, now=NOW)
    batch = projection.project_independent_price_conditions(tmp_path, items=rows, now=NOW)
    assert batch["items"][0]["price_action_plan"] == single
    assert rows == before
    assert single["current_data_status"] == "CURRENT"
    assert single["validation"]["status"] == "NOT_RUN"
    assert single["validation"]["formal_eligibility"] is False
    primary = single["operational_conditions"]["timeframes"]["60m"]
    assert primary.get("prior_max_high") == ("12.34" if has_levels else None)
    assert single["operational_conditions"]["conditions"] == {}
