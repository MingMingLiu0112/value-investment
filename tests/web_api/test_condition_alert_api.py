"""Local authorization and strict TEST_ONLY reminder-view separation."""
from test_held_continuity_api import client_for, unlock


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
