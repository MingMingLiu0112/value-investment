"""TEST_ONLY real loader plans and dual-source quote replay; no M5 admission."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from test_current_price_registry import register
from test_hotspot_current_price_case import NOW as BOUND_AT, display_capture
from test_intraday_observation import bundle, field
from value_investment_agent.application.hotspot.current_registry import load_price_conditions
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.application.hotspot.intraday_observation import project_intraday_observation
from value_investment_agent.application.hotspot import intraday_plan_observation as module


NOW = datetime.fromisoformat("2026-09-28T10:30:05+08:00")


@pytest.fixture
def plan(tmp_path):
    register(tmp_path)
    result = load_price_conditions(tmp_path, now=BOUND_AT, research_version="TEST_ONLY")
    assert len(result["items"]) == 1
    return result["items"][0]["price_action_plan"]


def quote(price="14", now=NOW):
    data = bundle(now=now)
    field(data, "tencent", 3, price)
    field(data, "sina", 3, price)
    result = project_intraday_observation(data, symbol="600519", now=now, max_age=module.AGE)
    assert result["status"] == "QUOTE_VERIFIED", result
    return result["observation"]


def bind(plan):
    return module.bind_quote_plan(plan, symbol="600519", now=BOUND_AT)


def evaluate(binding, observation=None, *, previous=None, now=NOW):
    return module.evaluate_quote_plan(binding, observation, previous=previous, now=now)


def test_real_loader_snapshot_exact_levels_and_quote_reference_only(plan):
    original = deepcopy(plan)
    binding = bind(plan)
    assert binding["symbol"] == "600519"
    assert binding["plan"] == original
    assert binding["source_url"] == "https://qt.gtimg.cn/q=sh600519"
    assert binding["valid_until"] == "2026-09-28T07:00:00+00:00"
    result = evaluate(binding, quote())
    assert [row["kind"] for row in result["states"]] == ["ENTRY_REFERENCE_GT", "INVALIDATION_REFERENCE_LT"]
    assert [row["status"] for row in result["states"]] == ["STRUCTURE_OBSERVATION", "NOT_TRIGGERED"]
    entry = result["states"][0]
    assert entry["condition"]["threshold"] == str(original["entry_trigger_price"])
    assert entry["condition"]["operator"] == "GT"
    assert result["states"][1]["condition"]["threshold"] == str(original["invalidation_price"])
    assert result["transitions"][0]["source_refs"] == quote()["evidence_refs"]
    assert result["transitions"][0]["price"] == "14"
    assert result["plan_status"] == "REFERENCE_ONLY"
    for row in result["states"]:
        assert row["state"]["namespace"] == "ACTUAL"
        assert row["state"]["admitted"] is row["state"]["eligibility"] is False
    for item in (result, *result["transitions"]):
        assert item["action"] == "no_order" and item["eligibility"] is item["m5_admitted"] is False
        assert all(blocker in item["blockers"] for blocker in original["blockers"])
        assert module.BOUNDARY in item["blockers"]
    assert plan == original
    plan["entry_trigger_price"] = "999"
    assert binding["plan"] == original


def test_display_only_real_case_allowed_as_reference_and_empty_session_replays(tmp_path):
    case = display_capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(case_path=case["case_path"], case_sha256=case["case_sha256"])
    binding = bind(plan)
    assert binding["plan"]["reference_price_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert binding["plan"]["expires_after_session"] is None
    empty = evaluate(binding, now=BOUND_AT)
    assert all(row["status"] == "STALE_OR_UNAVAILABLE" for row in empty["states"])
    assert empty["eligibility"] is empty["m5_admitted"] is False
    assert module._binding(json.loads(json.dumps(binding)), BOUND_AT) == binding
    assert evaluate(binding, now=BOUND_AT) == empty
    restored = evaluate(binding, quote(), previous=empty)
    assert restored["states"][0]["status"] == "STRUCTURE_OBSERVATION"


def test_invalidation_is_risk_review_never_confirmed_exit(plan):
    result = evaluate(bind(plan), quote("10"))
    assert result["states"][1]["state"]["status"] == "STRUCTURE_OBSERVATION"
    assert result["states"][1]["status"] == "RISK_REVIEW"
    assert result["transitions"][0]["kind"] == "INVALIDATION_REFERENCE_LT"
    assert result["transitions"][0]["status"] == "RISK_REVIEW"
    assert "PRIVATE_GATES" in result["transitions"][0]["next_step"]


def test_restart_unchanged_poll_then_pullback_and_rearm_no_duplicates(plan):
    binding = bind(plan)
    first = evaluate(binding, quote())
    previous = json.loads(json.dumps(first))
    repeated = evaluate(binding, quote(), previous=previous, now=NOW + timedelta(seconds=1))
    assert repeated["transitions"] == []
    assert repeated["states"][0]["state"]["cycle"] == first["states"][0]["state"]["cycle"]
    below = evaluate(binding, quote("12", NOW + timedelta(seconds=2)), previous=repeated,
                     now=NOW + timedelta(seconds=2))
    assert len(below["transitions"]) == 1 and below["transitions"][0]["status"] == "NOT_TRIGGERED"
    again = evaluate(binding, quote("14", NOW + timedelta(seconds=3)), previous=below,
                     now=NOW + timedelta(seconds=3))
    assert again["transitions"][0]["transition_id"] != first["transitions"][0]["transition_id"]
    assert evaluate(binding, quote("14", NOW + timedelta(seconds=3)), previous=below,
                    now=NOW + timedelta(seconds=3)) == again


def test_missing_stale_quote_and_expired_plan_do_not_trigger(plan):
    binding = bind(plan)
    first = evaluate(binding, quote())
    missing = evaluate(binding, previous=first, now=NOW + timedelta(seconds=1))
    assert all(row["status"] == "STALE_OR_UNAVAILABLE" for row in missing["states"])
    assert all(row["price"] is None and row["source_refs"] == [] for row in missing["transitions"])
    repeated = evaluate(binding, previous=missing, now=NOW + timedelta(seconds=2))
    assert repeated["transitions"] == []
    stale = evaluate(binding, quote(), now=NOW + timedelta(seconds=121))
    assert all(row["status"] == "STALE_OR_UNAVAILABLE" for row in stale["states"])
    closed = NOW.replace(hour=15, minute=0, second=0)
    expired = evaluate(binding, previous=first, now=closed)
    assert expired["plan_status"] == "STALE_OR_UNAVAILABLE"
    assert "PLAN_REFERENCE_EXPIRED" in expired["blockers"]
    with pytest.raises(ValueError, match="expired"):
        module.bind_quote_plan(plan, symbol="600519", now=closed)


@pytest.mark.parametrize("change", [
    {"schema_version": "price-action-plan-historical-v1"}, {"symbol": "000333"},
    {"model_or_rule_version": "unsupported"}, {"signal_state": "STALE"}, {"signal_state": "BLOCKED"},
    {"candidate_lifecycle": "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"},
    {"entry_trigger_price": "NaN"}, {"invalidation_price": "Infinity"}, {"entry_trigger_price": "0"},
    {"case_path": "../case.json"}, {"case_path": "D:/case.json"}, {"case_path": "/case.json"},
    {"case_sha256": "a"}, {"market_trade_date": "2026-09-25"},
    {"data_available_at": "2099-01-01T12:00:00+08:00"},
    {"expires_after_session": "2026-09-29"}, {"formal_eligibility": True}, {"action_eligibility": True},
    {"action": "order"}, {"exchange": "SZSE"},
])
def test_bad_or_unsupported_plan_is_rejected_not_coerced(plan, change):
    with pytest.raises(ValueError):
        bind({**plan, **change})


def test_reference_date_level_and_binding_tampering_rejected(plan):
    for mutate in (
        lambda p: p["current_reference_close"].update(price="999"),
        lambda p: p["current_reference_close"]["provider_times"].update(tencent="2026-09-23T15:00:00+08:00"),
        lambda p: p["levels"]["60m"].update(prior_max_high="999"),
    ):
        altered = deepcopy(plan)
        mutate(altered)
        with pytest.raises(ValueError):
            bind(altered)
    binding = bind(plan)
    altered = deepcopy(binding)
    altered["plan"]["blockers"] = []
    with pytest.raises(ValueError, match="binding changed"):
        evaluate(altered)
    with pytest.raises(ValueError):
        evaluate(None)


def test_changed_foreign_future_or_permission_bearing_previous_rejected(plan):
    binding = bind(plan)
    first = evaluate(binding, quote())
    for change in ({"eligibility": True}, {"binding_sha256": "a" * 64}, {"namespace": "SIMULATED"}):
        altered = {**first, **change}
        body = {key: value for key, value in altered.items() if key != "result_sha256"}
        altered["result_sha256"] = module._digest(body)
        with pytest.raises(ValueError):
            evaluate(binding, quote(), previous=altered)
    altered = deepcopy(first)
    altered["states"][0]["state"]["cycle"] += 1
    with pytest.raises(ValueError):
        evaluate(binding, quote(), previous=altered)
    with pytest.raises(ValueError, match="clock"):
        evaluate(binding, quote(), previous=first, now=NOW - timedelta(seconds=1))


@pytest.mark.parametrize("change", [{"symbol": "000333"}, {"source_id": "sina"},
    {"source_url": "https://qt.gtimg.cn/q=sz000333"}, {"completed": True}, {"input_kind": "COMPLETED_BAR"},
    {"eligibility": True}, {"source_at": "2026-09-28T10:31:00+08:00"}])
def test_wrong_source_security_type_or_clock_cannot_match(plan, change):
    result = evaluate(bind(plan), {**quote(), **change})
    assert all(row["status"] == "STALE_OR_UNAVAILABLE" for row in result["states"])
    assert not any(row["status"] in {"RISK_REVIEW", "STRUCTURE_OBSERVATION"} for row in result["transitions"])


def test_equal_thresholds_are_not_matches_and_inputs_remain_unchanged(plan):
    binding = bind(plan)
    for price in (plan["entry_trigger_price"], plan["invalidation_price"]):
        observation = quote(str(price))
        before = deepcopy((binding, observation))
        result = evaluate(binding, observation)
        assert all(row["status"] == "NOT_TRIGGERED" for row in result["states"])
        assert result["transitions"] == []
        assert (binding, observation) == before


@pytest.mark.parametrize("mutate", [
    lambda p: p["states"][0]["state"].update(symbol="000333"),
    lambda p: p["states"][0].update(status="RISK_REVIEW"),
    lambda p: p["states"][0]["state"].update(last_received_at="2099-01-01T00:00:00+00:00"),
    lambda p: p["states"][0]["state"].update(last_fingerprint="broken"),
])
def test_previous_nested_identity_and_clock_rejected_even_with_new_checksum(plan, mutate):
    binding = bind(plan)
    prior = evaluate(binding, quote())
    mutate(prior)
    prior.pop("result_sha256")
    prior["result_sha256"] = module._digest(prior)
    with pytest.raises(ValueError):
        evaluate(binding, quote(), previous=prior)


def test_invalid_observation_and_server_clock_fail_closed(plan):
    binding = bind(plan)
    malformed = evaluate(binding, ["not a quote"])
    assert all(row["status"] == "STALE_OR_UNAVAILABLE" for row in malformed["states"])
    with pytest.raises(ValueError, match="Aware"):
        evaluate(binding, now=NOW.replace(tzinfo=None))
