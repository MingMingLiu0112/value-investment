import json

from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import create_app


def test_update_status_is_read_only_and_does_not_claim_missing_run(tmp_path):
    client = TestClient(create_app(tmp_path))
    result = client.get("/api/v1/daily-update-status")
    assert result.status_code == 200
    assert result.json() == {
        "action": "no_order", "status": "NOT_RECORDED", "last_run": None,
    }
    assert not (tmp_path / ".tmp/daily-workbench-latest-run.json").exists()


def test_failed_update_retains_failure_and_previous_publication(tmp_path):
    target = tmp_path / ".tmp/daily-workbench-latest-run.json"
    target.parent.mkdir()
    target.write_text(json.dumps({
        "schema_version": "daily-workbench-run-v1", "action": "no_order",
        "mode": "SAFE_REFRESH", "status": "BLOCKED", "published": False,
        "exit_code": 1, "publication_id": None,
        "retained_publication_id": "previous-publication", "notes": [],
        "started_at": "2026-10-14T08:00:00+00:00",
        "finished_at": "2026-10-14T08:01:00+00:00",
    }), encoding="utf-8")
    original = target.read_bytes()
    result = TestClient(create_app(tmp_path)).get("/api/v1/daily-update-status").json()
    assert result["last_run"]["status"] == "BLOCKED"
    assert result["last_run"]["published"] is False
    assert result["last_run"]["retained_publication_id"] == "previous-publication"
    assert target.read_bytes() == original
