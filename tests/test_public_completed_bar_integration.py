"""Product-session integration for retained 60m/15m completed-bar observation."""
from copy import deepcopy
from datetime import timedelta
import json

from test_current_price_registry import register
from test_hotspot_current_price_case import NOW as BOUND_AT
from test_intraday_plan_observation import NOW as PLAN_NOW
from test_intraday_observation import bundle, field
from test_public_observation_session import bars, wait_stopped
from value_investment_agent.application.hotspot.current_registry import load_price_conditions
from value_investment_agent.application.hotspot.intraday_plan_observation import bind_quote_plan
from value_investment_agent.application.hotspot.public_observation_session import PublicObservationSession


def binding_for(tmp_path):
    register(tmp_path)
    plan = load_price_conditions(tmp_path, now=BOUND_AT, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    qualified = deepcopy(plan)
    qualified["opportunity_quality"]["structure_tier"] = "STRUCTURE_QUALIFIED_OBSERVATION"
    return bind_quote_plan(qualified, symbol="600519", now=BOUND_AT)


def quote_collector(at):
    def collect(symbols):
        at[0] += timedelta(seconds=1)
        data = bundle(now=at[0])
        field(data, "tencent", 3, "14")
        field(data, "sina", 3, "14")
        return data
    return collect


def test_normal_plan_session_collects_completed_bars_deduplicates_and_replays(tmp_path):
    binding = binding_for(tmp_path)
    at = [PLAN_NOW]
    session = PublicObservationSession(tmp_path, clock=lambda: at[0],
        collector=quote_collector(at), bar_collector=lambda symbol: bars(at[0]),
        max_samples=2, interval_seconds=.001)
    try:
        session.start("600519", plan_binding=binding)
        view = wait_stopped(session)
        assert view["completed_plan_observation"]["status"] == "WAITING_CONFIRMATION"
        assert view["completed_plan_observation"]["structure_confirmation"] is False
        history = view["notification_inbox"]["history"]
        events = [row for row in history if row["input_kind"] == "COMPLETED_BAR"
                  and row["completed_bar"] is True]
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "BAR_CONFIRMATION_PENDING"
        assert event["period"] == "60m+15m"
        assert event["bar_end"] == "2026-09-28T02:30:00+00:00"
        assert set(event["completed_periods"]) == {"60m", "15m"}
        assert all(row["completed"] is True for row in event["completed_periods"].values())
        assert event["action"] == "no_order" and event["eligibility"] is False

        restored = PublicObservationSession(tmp_path, clock=lambda: at[0])
        assert restored.read() == view
        bar_file = next(session.directory.glob("*.60m.bar.json"))
        bar_file.write_bytes(json.dumps({"tampered": True}).encode())
        assert restored.read()["status"] == "CORRUPT"
        restored.close()
    finally:
        session.close()


def test_missing_period_fails_closed_and_never_claims_completed_structure(tmp_path):
    binding = binding_for(tmp_path)
    at = [PLAN_NOW]
    session = PublicObservationSession(tmp_path, clock=lambda: at[0],
        collector=quote_collector(at),
        bar_collector=lambda symbol: {"60m": bars(at[0])["60m"]},
        max_samples=1, interval_seconds=.001)
    try:
        session.start("600519", plan_binding=binding)
        view = wait_stopped(session)
        assert view["completed_plan_observation"]["status"] == "INSUFFICIENT_DATA"
        assert not any(row["event_type"] == "STRUCTURE_CONFIRMED_OBSERVATION"
                       for row in view["notification_inbox"]["history"])
        stale = next(row for row in view["notification_inbox"]["history"]
                     if row["input_kind"] == "COMPLETED_BAR")
        assert stale["event_type"] == "DATA_STALE" and stale["completed_bar"] is False
    finally:
        session.close()


def test_bar_receipt_captured_after_quote_uses_the_post_collection_sample_clock(tmp_path):
    binding = binding_for(tmp_path)
    at = [PLAN_NOW]

    def collect_quote(symbols):
        at[0] += timedelta(seconds=1)
        data = bundle(now=at[0])
        field(data, "tencent", 3, "14")
        field(data, "sina", 3, "14")
        return data

    def collect_bars(symbol):
        # The bar request finishes after the quote's receipt. Before the fix this
        # made fetched_at newer than the already-recorded sample checked_at.
        at[0] += timedelta(seconds=5)
        documents = bars(at[0])
        return documents

    session = PublicObservationSession(tmp_path, clock=lambda: at[0],
        collector=collect_quote, bar_collector=collect_bars,
        max_samples=1, interval_seconds=.001)
    try:
        session.start("600519", plan_binding=binding)
        view = wait_stopped(session)
        assert view["samples"][0]["bar_collection_status"] == "CAPTURED"
        assert all(item["status"] != "STALE_OR_UNAVAILABLE"
                   for item in view["completed_plan_observation"]["periods"].values())
        assert view["completed_plan_observation"]["status"] == "WAITING_CONFIRMATION"
        assert view["completed_plan_observation"]["action"] == "no_order"
    finally:
        session.close()
