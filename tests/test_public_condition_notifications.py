"""TEST_ONLY source replay through the normal observation inbox contract."""
import base64
from datetime import timedelta
import hashlib
import json

import pytest

from test_current_price_registry import register
from test_hotspot_current_price_case import NOW as BOUND_AT
from test_intraday_plan_observation import NOW as PLAN_NOW
from test_intraday_observation import bundle, field
from test_public_observation_session import wait_stopped
from value_investment_agent.application.hotspot.current_registry import load_price_conditions
from value_investment_agent.application.hotspot.intraday_plan_observation import bind_quote_plan
from value_investment_agent.application.hotspot.public_observation_session import PublicObservationSession
from value_investment_agent.infrastructure.hotspot.sina_price_case import ENDPOINT


def bars(now, price="14"):
    result = {}
    for period in ("60m", "15m"):
        rows = [dict(day="2026-09-28 10:30:00", open=price, high=price,
                     low=price, close=price, volume="100", amount="1400")]
        raw = ("/*TEST_ONLY*/=(" + json.dumps(rows) + ");").encode()
        result[period] = dict(raw_base64=base64.b64encode(raw).decode(),
            sha256=hashlib.sha256(raw).hexdigest(),
            source_url=ENDPOINT + f"?symbol=sh600519&scale={period[:-1]}&ma=no&datalen=8",
            http_status=200, fetched_at=(now - timedelta(seconds=1)).isoformat())
    return result


def test_real_contract_inbox_deduplicates_and_survives_restart_and_next_session(tmp_path):
    register(tmp_path)
    plan = load_price_conditions(tmp_path, now=BOUND_AT, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    binding = bind_quote_plan(plan, symbol="600519", now=BOUND_AT)
    at = [PLAN_NOW]
    def collect(symbols):
        at[0] += timedelta(seconds=1)
        data = bundle(now=at[0])
        field(data, "tencent", 3, "14")
        field(data, "sina", 3, "14")
        return data
    session = PublicObservationSession(tmp_path, clock=lambda: at[0], collector=collect,
                                       bar_collector=lambda symbol: bars(at[0]),
                                       max_samples=2, interval_seconds=.001)
    try:
        session.start("600519", plan_binding=binding)
        view = wait_stopped(session)
        inbox = view["notification_inbox"]
        entry = next(event for event in inbox["history"] if event["event_type"] == "BAR_CONFIRMATION_PENDING"
                     and event["completed_bar"] is False)
        assert len([row for row in inbox["history"] if row["event_id"] == entry["event_id"]]) == 1
        alert = next(row for row in inbox["alerts"] if row["event_id"] == entry["event_id"])
        updated = session.transition_notification(alert_id=alert["alert_id"], operation="ACKNOWLEDGE",
                                                  expected_snapshot_sha256=inbox["snapshot_sha256"])
        assert session.transition_notification(alert_id=alert["alert_id"], operation="ACKNOWLEDGE",
            expected_snapshot_sha256=inbox["snapshot_sha256"]) == updated
        assert next(row for row in updated["notification_inbox"]["alerts"]
                    if row["alert_id"] == alert["alert_id"])["status"] == "ACKNOWLEDGED"
        restored = PublicObservationSession(tmp_path, clock=lambda: at[0])
        assert restored.read()["notification_inbox"] == updated["notification_inbox"]
        session.start("600519", plan_binding=binding)
        repeated = wait_stopped(session)["notification_inbox"]
        assert len([row for row in repeated["history"] if row["event_id"] == entry["event_id"]]) == 1
        assert next(row for row in repeated["alerts"] if row["alert_id"] == alert["alert_id"])["status"] == "ACKNOWLEDGED"
        assert all(row["eligibility"] is False for row in repeated["alerts"])
        prices = iter(["10", "14"])
        def recross(symbols):
            at[0] += timedelta(seconds=1)
            data = bundle(now=at[0])
            price = next(prices)
            field(data, "tencent", 3, price)
            field(data, "sina", 3, price)
            return data
        session.collector = recross
        session.start("600519", plan_binding=binding)
        recrossed = wait_stopped(session)["notification_inbox"]
        entries = [row for row in recrossed["history"] if row["event_type"] == "BAR_CONFIRMATION_PENDING"
                   and row["completed_bar"] is False]
        assert len(entries) == 2
        assert len({row["event_id"] for row in entries}) == 2
        assert next(row for row in recrossed["alerts"] if row["alert_id"] == alert["alert_id"])["status"] == "ACKNOWLEDGED"
        restored.close()
    finally:
        session.close()


def test_normal_inbox_does_not_accept_fabricated_alert_actions(tmp_path):
    session = PublicObservationSession(tmp_path, clock=lambda: PLAN_NOW)
    with pytest.raises(ValueError):
        session.transition_notification(alert_id="made-up", operation="ACKNOWLEDGE",
                                        expected_snapshot_sha256="a" * 64)
    assert not session.directory.exists()


def test_normal_api_exposes_verified_observation_inbox_and_read_actions(tmp_path, monkeypatch):
    from web_api.test_held_continuity_api import client_for, unlock
    from value_investment_agent.presentation.web_api import condition_alert_routes as routes
    register(tmp_path)
    plan = load_price_conditions(tmp_path, now=BOUND_AT, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    binding = bind_quote_plan(plan, symbol="600519", now=BOUND_AT)
    def collect(symbols):
        data = bundle(now=PLAN_NOW)
        field(data, "tencent", 3, "14")
        field(data, "sina", 3, "14")
        return data
    session = PublicObservationSession(tmp_path, clock=lambda: PLAN_NOW, collector=collect,
        bar_collector=lambda symbol: bars(PLAN_NOW),
        max_samples=1, interval_seconds=.001)
    session.start("600519", plan_binding=binding)
    wait_stopped(session)
    monkeypatch.setattr(routes, "PublicObservationSession", lambda *args, **kwargs: session)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    url = "/api/v1/condition-alerts"
    assert client.get(url).status_code == 401
    unlock(client, secret)
    result = client.get(url).json()
    assert result["test_only"] is False
    assert result["status"] == "OBSERVATION_ONLY"
    assert result["history"][0]["event_type"] == "BAR_CONFIRMATION_PENDING"
    alert = result["alerts"][0]
    route = f"{url}/observation/{alert['alert_id']}/acknowledge"
    payload = dict(acknowledged=True, expected_snapshot_sha256=result["snapshot_sha256"])
    assert client.post(route, json={**payload, "test_only": True}).status_code == 422
    updated = client.post(route, json=payload)
    assert updated.status_code == 200
    assert updated.json()["alerts"][0]["status"] == "ACKNOWLEDGED"
    assert client.post(route, json=payload).status_code == 200
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()
    session.close()
