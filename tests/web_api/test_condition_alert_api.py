"""Local authorization and strict TEST_ONLY reminder-view separation."""
import pytest

from test_held_continuity_api import client_for, unlock


def test_missing_candidates_cannot_hide_running_session_or_stop(tmp_path, monkeypatch):
    from value_investment_agent.presentation.web_api import condition_alert_routes as routes

    class RunningSession:
        def __init__(self, *args, **kwargs):
            pass

        def read(self):
            return dict(status="RUNNING", monitor_running=True, session_id="retained-session", samples=[])

        def stop(self, *, expected_session_id):
            assert expected_session_id == "retained-session"
            return dict(status="STOPPED", monitor_running=False)

        def close(self):
            pass

    def unavailable(*args, **kwargs):
        raise ValueError("registry cannot be verified")

    monkeypatch.setattr(routes, "PublicObservationSession", RunningSession)
    monkeypatch.setattr(routes, "load_price_conditions", unavailable)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    response = client.get("/api/v1/condition-alerts")
    assert response.status_code == 200
    state = response.json()
    assert state["monitor_running"] is True
    assert state["public_observation"]["session_id"] == "retained-session"
    assert state["public_observation"]["choices_status"] == "UNAVAILABLE"
    stopped = client.post("/api/v1/condition-alerts/public-observation/stop",
        json=dict(acknowledged=True, expected_session_id="retained-session"))
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"


def test_alert_history_requires_session_and_never_initializes_store(tmp_path, monkeypatch):
    journal = tmp_path / "TEST_ONLY_private.jsonl"
    client, secret = client_for(tmp_path, journal, monkeypatch)
    route = "/api/v1/condition-alerts"
    assert client.get(route).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.get(route).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    response = client.get(route)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["status"] == "NOT_STARTED"
    assert response.json()["test_only"] is False
    assert response.json()["monitor_running"] is False
    assert response.json()["history"] == []
    rehearsal = client.get(route + "?test_only=true")
    assert rehearsal.status_code == 200
    assert rehearsal.json()["test_only"] is True
    assert rehearsal.json()["namespace"] == "SIMULATED"
    assert rehearsal.json()["history"] == []
    assert not (tmp_path / "runtime").exists()
    assert not journal.exists()


def test_test_only_corruption_is_not_a_current_alert(tmp_path, monkeypatch):
    path = tmp_path / "runtime/intraday-monitor/test-only.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"corrupt":true}', encoding="utf-8")
    before = path.read_bytes()
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    normal = client.get("/api/v1/condition-alerts")
    assert normal.status_code == 200 and normal.json()["history"] == []
    invalid = client.get("/api/v1/condition-alerts?test_only=true")
    assert invalid.status_code == 503
    assert invalid.json()["status"] == "UNAVAILABLE"
    assert invalid.json()["history"] == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("operation,status", [("cancel", "CANCELLED"), ("expire", "EXPIRED")])
def test_notification_termination_is_isolated_and_not_a_risk_approval(tmp_path, monkeypatch, operation, status):
    from datetime import datetime, timedelta
    from test_intraday_conditions import NOW
    from test_intraday_monitor import tick
    from value_investment_agent.presentation.web_api import condition_alert_routes
    class TestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (NOW + timedelta(days=1)).astimezone(tz)
    monkeypatch.setattr(condition_alert_routes, "datetime", TestClock)
    path = tmp_path / "runtime/intraday-monitor/test-only.json"
    initial = tick(path)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    route = f"/api/v1/condition-alerts/test-only/{initial['alerts'][0]['alert_id']}/{operation}"
    payload = dict(test_only=True, acknowledged=True,
        expected_snapshot_sha256=initial["snapshot_sha256"])
    before = path.read_bytes()
    assert client.post(route, json={**payload, "expires_at": "2000-01-01"}).status_code == 422
    assert path.read_bytes() == before
    response = client.post(route, json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["alerts"][0]["status"] == status
    assert result["alerts"][0]["requires_human_review"] is True
    assert result["history"] == initial["history"]
    assert result["cursor"] == initial["cursor"]
    assert result["eligibility"] is result["admitted"] is False
    assert client.get("/api/v1/condition-alerts").json()["history"] == []
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()


def test_retained_positive_alerts_remain_isolated_from_normal_view(tmp_path, monkeypatch):
    from test_intraday_monitor import tick
    path = tmp_path / "runtime/intraday-monitor/test-only.json"
    expected = tick(path)
    before = path.read_bytes()
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    result = client.get("/api/v1/condition-alerts?test_only=true")
    assert result.status_code == 200
    assert result.json()["history"] == expected["history"]
    assert len(result.json()["alerts"]) == 1
    assert result.json()["eligibility"] is False
    assert result.json()["monitor_running"] is False
    assert client.get("/api/v1/condition-alerts").json()["history"] == []
    assert path.read_bytes() == before


def test_read_confirmation_cannot_bypass_session_or_select_real_data(tmp_path, monkeypatch):
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    route = "/api/v1/condition-alerts/test-only/foreign/acknowledge"
    payload = dict(test_only=True, acknowledged=True, expected_snapshot_sha256="a" * 64)
    assert client.post(route, json=payload).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.post(route, json=payload).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    for invalid in (
        {**payload, "test_only": False},
        {**payload, "acknowledged": False},
        {**payload, "namespace": "ACTUAL"},
        {**payload, "path": "real.json"},
        {**payload, "expected_snapshot_sha256": 1},
    ):
        assert client.post(route, json=invalid).status_code == 422
    assert not (tmp_path / "runtime").exists()


def test_actual_read_confirmation_persists_but_never_approves_investment(tmp_path, monkeypatch):
    from test_intraday_monitor import tick
    from value_investment_agent.application.hotspot.intraday_monitor import read_intraday_monitor
    path = tmp_path / "runtime/intraday-monitor/test-only.json"
    initial = tick(path)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    current = client.get("/api/v1/condition-alerts?test_only=true").json()
    alert = current["alerts"][0]
    route = f"/api/v1/condition-alerts/test-only/{alert['alert_id']}/acknowledge"
    payload = dict(test_only=True, acknowledged=True,
        expected_snapshot_sha256=current["snapshot_sha256"])
    response = client.post(route, json=payload)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["alerts"][0]["status"] == "ACKNOWLEDGED"
    assert result["history"] == initial["history"]
    assert result["eligibility"] is result["admitted"] is False
    assert result["action"] == "no_order" and result["monitor_running"] is False
    assert read_intraday_monitor(path)["alerts"][0]["status"] == "ACKNOWLEDGED"
    assert client.get("/api/v1/condition-alerts").json()["history"] == []
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()
    before = path.read_bytes()
    invalid = {**payload, "expected_snapshot_sha256": "f" * 64}
    assert client.post(route, json=invalid).status_code == 409
    assert path.read_bytes() == before


def test_public_observation_controls_are_authenticated_and_server_scoped(tmp_path, monkeypatch):
    from value_investment_agent.presentation.web_api import condition_alert_routes as routes
    calls = []
    class Observation:
        def __init__(self, *args, **kwargs):
            pass
        def read(self):
            return dict(status="NOT_STARTED", monitor_running=False, samples=[],
                action="no_order", eligibility=False, m5_admitted=False)
        def start(self, symbol, *, plan_binding):
            assert plan_binding == {"symbol": symbol, "test_binding": "server-owned"}
            calls.append(("start", symbol))
            return {**self.read(), "monitor_running": True}
        def stop(self, *, expected_session_id):
            if expected_session_id != "current-session":
                raise ValueError("Session changed")
            calls.append(("stop",))
            return self.read()
        def close(self):
            pass
    monkeypatch.setattr(routes, "PublicObservationSession", Observation)
    monkeypatch.setattr(routes, "bind_quote_plan", lambda plan, *, symbol, now:
        {"symbol": symbol, "test_binding": "server-owned"})
    monkeypatch.setattr(routes, "load_price_conditions", lambda *args, **kwargs: {"items": [
        dict(symbol="600150", company_name="公开候选", price_action_plan={}),
        dict(symbol="000333", company_name="历史候选", price_action_plan={
            "candidate_lifecycle": "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"})]})
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    endpoint = "/api/v1/condition-alerts/public-observation/"
    payload = dict(acknowledged=True, symbol="600150")
    assert client.post(endpoint + "start", json=payload).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.post(endpoint + "start", json=payload).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    for invalid in ({**payload, "namespace": "ACTUAL"}, {**payload, "path": "foreign"},
                    {**payload, "plan_binding": {"forged": True}},
                    {**payload, "acknowledged": False}, {**payload, "symbol": "000333"},
                    {**payload, "symbol": "600519"}, {**payload, "symbol": []}):
        assert client.post(endpoint + "start", json=invalid).status_code in {409, 422}
    assert not calls
    view = client.get("/api/v1/condition-alerts").json()
    assert view["public_observation"]["choices"] == [dict(symbol="600150", company_name="公开候选")]
    started = client.post(endpoint + "start", json=payload)
    assert started.status_code == 200
    assert started.json()["m5_admitted"] is False
    assert client.post(endpoint + "stop", json={"acknowledged": True}).status_code == 422
    assert client.post(endpoint + "stop", json={"acknowledged": True, "expected_session_id": "stale"}).status_code == 409
    assert client.post(endpoint + "stop", json={"acknowledged": True, "expected_session_id": "current-session"}).status_code == 200
    assert calls == [("start", "600150"), ("stop",)]
    assert not (tmp_path / "runtime").exists()
