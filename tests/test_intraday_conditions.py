"""TEST_ONLY clocks and source assertions; no market requests or authorization."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from value_investment_agent.application.hotspot.intraday_conditions import evaluate_intraday_condition
from value_investment_agent.m5_event_core import EventLedger
from value_investment_agent.m5_event_outbox import OutboxLedger, alert_type_for_event_type


NOW = datetime.fromisoformat("2026-10-16T10:30:02+08:00")


def condition(**changes):
    result = dict(strategy="HOTSPOT_SATELLITE", symbol="600519", venue="SSE",
        condition_id="TEST_ONLY_close_above", rule_version="TEST_ONLY_explicit_price_v1",
        source_id="TEST_ONLY", source_url="https://example.invalid/TEST_ONLY",
        input_kind="COMPLETED_BAR", period="60m", operator="GT", threshold="10", action="no_order")
    return {**result, **changes}


def observation(now=NOW, **changes):
    return dict(symbol="600519", source_id="TEST_ONLY", source_url="https://example.invalid/TEST_ONLY",
        source_at=(now - timedelta(seconds=1)).isoformat(), received_at=now.isoformat(), price="11",
        quality="VERIFIED", suspended=False, completed=True, period="60m",
        bar_end=now.replace(hour=10, minute=30, second=0, microsecond=0).isoformat(),
        evidence_refs=[dict(id="TEST_ONLY_raw", sha256="a" * 64,
                            source_url="https://example.invalid/TEST_ONLY")], **changes)


def run(c=None, o=None, *, previous=None, now=NOW, namespace="SIMULATED"):
    return evaluate_intraday_condition(c or condition(), o, previous=previous, now=now,
        max_age=timedelta(seconds=30), namespace=namespace)


def test_complete_bar_transition_replay_and_real_m5_dedupe():
    c, o = condition(period="15m"), {**observation(), "period": "15m"}
    before = deepcopy((c, o))
    earlier = NOW.replace(hour=9, minute=45)
    baseline = run(c, {**observation(earlier), "period": "15m", "price": "9",
        "bar_end": earlier.replace(second=0).isoformat()}, now=earlier)
    assert baseline.state["status"] == "NOT_TRIGGERED" and not baseline.events
    later = NOW + timedelta(seconds=2)
    triggered = run(c, {**observation(later), "period": "15m"}, previous=baseline.state, now=later)
    assert triggered.state["status"] == "CONDITION_REVIEW"
    assert len(triggered.events) == 1
    assert not triggered.eligibility and not triggered.admitted and not triggered.b1_eligible
    assert triggered.action == "no_order"
    repeated = run(c, {**observation(later), "period": "15m"}, previous=triggered.state, now=later + timedelta(seconds=1))
    assert not repeated.events and repeated.state["cycle"] == triggered.state["cycle"]
    ledger = EventLedger(namespace="SIMULATED")
    accepted = ledger.append(triggered.events[0], observed_at=later)
    assert accepted.status == "ACCEPTED"
    assert ledger.append(triggered.events[0], observed_at=later).status == "DUPLICATE"
    outbox = OutboxLedger()
    alert_type = alert_type_for_event_type(accepted.event.event_type)
    assert outbox.enqueue_for_event(event=accepted.event, alert_type=alert_type, now=later).status == "ENQUEUED"
    assert outbox.enqueue_for_event(event=accepted.event, alert_type=alert_type, now=later).status == "DUPLICATE"
    assert (c, o) == before


def test_quote_observation_pullback_and_new_trigger_cycle():
    c = condition(input_kind="QUOTE", period="quote")
    first = run(c, observation())
    assert first.state["status"] == "STRUCTURE_OBSERVATION"
    t2 = NOW + timedelta(seconds=2)
    below = run(c, {**observation(t2), "price": "9"}, previous=first.state, now=t2)
    assert below.state["status"] == "NOT_TRIGGERED" and len(below.events) == 1
    t3 = t2 + timedelta(seconds=2)
    again = run(c, observation(t3), previous=below.state, now=t3)
    assert again.state["status"] == "STRUCTURE_OBSERVATION"
    assert again.events[0].source_event_id != first.events[0].source_event_id
    assert run(c, observation(t3), previous=below.state, now=t3).events == again.events


@pytest.mark.parametrize("change", [
    {"source_id": "foreign"}, {"symbol": "000001"}, {"source_url": "https://foreign.invalid"},
    {"source_at": "2026-10-16T10:31:00+08:00"}, {"received_at": "2026-10-16T10:29:59+08:00"},
    {"source_at": "2026-10-16T10:29:00+08:00"}, {"source_at": "2026-10-16T10:30:01"},
    {"completed": False}, {"completed": "true"}, {"period": "15m"},
    {"bar_end": "2026-10-16T10:30:01+08:00"}, {"bar_end": "2026-10-16T11:30:00+08:00"},
    {"bar_end": "2026-10-16T09:30:00+08:00"}, {"suspended": True}, {"quality": "FAILED"},
    {"price": "NaN"}, {"price": "-1"}, {"evidence_refs": []}, {"action": "order"},
])
def test_invalid_data_is_health_only_never_valid_condition(change):
    result = run(o={**observation(), **change})
    assert result.state["status"] == "STALE_OR_UNAVAILABLE"
    assert len(result.events) == 1 and result.events[0].event_type == "SOURCE_SCAN_FAILED"
    assert result.events[0].symbol == "SYSTEM"
    assert result.events[0].current_state["symbol"] == "600519"
    assert not result.eligibility and not result.admitted


@pytest.mark.parametrize("stamp", ["2026-10-16T12:00:00+08:00", "2026-10-16T09:29:00+08:00",
    "2026-10-16T15:01:00+08:00", "2026-10-17T10:30:02+08:00", "2026-10-01T10:30:02+08:00",
    "2027-01-04T10:30:02+08:00"])
def test_lunch_closed_holiday_and_uncovered_calendar_cannot_trigger(stamp):
    now = datetime.fromisoformat(stamp)
    result = run(condition(input_kind="QUOTE", period="quote"), observation(now), now=now)
    assert result.state["status"] == "STALE_OR_UNAVAILABLE"


def test_failure_recovery_and_restart_state_no_duplicate():
    first = run(o=observation())
    failed_at = NOW + timedelta(seconds=1)
    failed = run(previous=first.state, now=failed_at)
    assert failed.events[0].event_type == "SOURCE_SCAN_FAILED"
    assert not run(previous=failed.state, now=failed_at + timedelta(seconds=1)).events
    restored_at = failed_at + timedelta(seconds=2)
    restored = run(o=observation(restored_at), previous=failed.state, now=restored_at)
    assert [e.event_type for e in restored.events] == ["SOURCE_SCAN_RECOVERED", "PRICE_ATTRACTIVENESS_CHANGED"]
    import json
    restarted = json.loads(json.dumps(restored.state))
    assert not run(o=observation(restored_at), previous=restarted, now=restored_at).events
    assert first.state["cycle"] < failed.state["cycle"] < restored.state["cycle"]


def test_cross_day_rearms_and_foreign_rule_state_rejected():
    first = run(o=observation())
    monday = datetime.fromisoformat("2026-10-19T10:30:02+08:00")
    next_day = run(o=observation(monday), previous=first.state, now=monday)
    assert next_day.events[0].source_event_id != first.events[0].source_event_id
    for c in (condition(rule_version="new"), condition(strategy="CORE_VALUE"),
              condition(condition_id="different"), condition(symbol="000001", venue="SZSE")):
        with pytest.raises(ValueError, match="Prior state"):
            run(c, observation(), previous=first.state)


def test_actual_namespace_never_implies_admission_and_does_not_mix_state():
    actual = run(o=observation(), namespace="ACTUAL")
    assert actual.events[0].namespace == "ACTUAL"
    assert not actual.admitted and actual.state["admitted"] is False
    with pytest.raises(ValueError):
        run(o=observation(), previous=actual.state, namespace="SIMULATED")


def test_identical_source_time_with_changed_payload_and_out_of_order_fail_closed():
    first = run(o=observation())
    for o in ({**observation(), "price": "12"}, observation(NOW - timedelta(seconds=1))):
        assert run(o=o, previous=first.state).state["status"] == "STALE_OR_UNAVAILABLE"
    with pytest.raises(ValueError):
        run(o=observation(), previous=first.state, now=NOW - timedelta(seconds=1))


def test_duplicate_quote_new_receipt_is_noop_and_quality_recovery_needs_new_source():
    first = run(o=observation())
    later = NOW + timedelta(seconds=1)
    repeat = run(o={**observation(), "received_at": later.isoformat()}, previous=first.state, now=later)
    assert not repeat.events and repeat.state["status"] == "CONDITION_REVIEW"
    failure = run(previous=repeat.state, now=later)
    assert run(o=observation(), previous=failure.state, now=later).state["status"] == "STALE_OR_UNAVAILABLE"


def test_same_completed_bar_cannot_change_price_under_new_source_clock():
    first = run(o=observation())
    later = NOW + timedelta(seconds=2)
    result = run(o={**observation(later), "price": "9"}, previous=first.state, now=later)
    assert result.state["status"] == "STALE_OR_UNAVAILABLE"


def test_szse_core_value_less_than_condition_is_observation_only():
    c = condition(strategy="CORE_VALUE", symbol="000001", venue="SZSE", operator="LT",
                  input_kind="QUOTE", period="quote")
    result = run(c, {**observation(), "symbol": "000001", "price": "9"})
    assert result.state["status"] == "STRUCTURE_OBSERVATION"
    assert not result.eligibility
    equal = run(c, {**observation(), "symbol": "000001", "price": "10"})
    assert equal.state["status"] == "NOT_TRIGGERED"


@pytest.mark.parametrize("change", [{"action": "order"}, {"venue": "SZSE"}, {"period": "daily"},
    {"threshold": "NaN"}, {"operator": "GUESS"}, {"source_url": "http://example.invalid"}])
def test_bad_condition_contract_rejected(change):
    with pytest.raises(ValueError):
        run(condition(**change), observation())


def test_missing_prior_clock_rejected_instead_of_resetting_cycle():
    previous = run(o=observation()).state
    previous.pop("checked_at")
    with pytest.raises(ValueError, match="Prior state"):
        run(o=observation(), previous=previous)


def test_existing_simulated_persistence_restarts_and_actual_authorization_still_required(tmp_path):
    from test_m5_event_state_store import _kwargs
    from value_investment_agent.m5_event_run import run_event_batch_persisted
    from value_investment_agent.m5_event_state_store import JsonM5EventRunStateStore

    result = run(o=observation())
    args = _kwargs(batch_id="TEST_ONLY_intraday", event_id="unused", at=NOW)
    args["events"] = result.events
    args["namespace"] = "SIMULATED"
    store = JsonM5EventRunStateStore(tmp_path / "TEST_ONLY_m5")
    first = run_event_batch_persisted(store=store, **args)
    restarted = JsonM5EventRunStateStore(tmp_path / "TEST_ONLY_m5")
    replay = run_event_batch_persisted(store=restarted, **args)
    assert replay.idempotent_noop
    assert replay.receipt_id == first.receipt_id
    assert len(restarted.load(state_key=args["run_id"]).outbox.alerts()) == 1
    args.update(events=run(o=observation(), namespace="ACTUAL").events, namespace="ACTUAL",
                run_id="TEST_ONLY_unapproved_actual")
    with pytest.raises(ValueError, match="authorization|Authorization"):
        run_event_batch_persisted(store=store, **args)
