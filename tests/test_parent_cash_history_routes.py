"""The company history projection is read-only and bounded."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes


def test_parent_cash_history_projects_failed_checkpoint_without_execution(tmp_path, monkeypatch):
    store = tmp_path / "tasks"
    task = store / ("rt-" + "a" * 32)
    task.mkdir(parents=True)
    (task / "input.json").write_text("{}", encoding="utf-8")
    calls = []

    class Service:
        base = store

        def __init__(self, root):
            assert root == tmp_path

        def _load(self, task_id):
            calls.append(task_id)
            return ({"spec_binding": {"path": "runtime/spec.json", "sha256": "a" * 64}},
                    {"status": "FAILED", "responses": {"base.operating": {}},
                     "reservations": {"b": {"scenario": "base.policy", "status": "RESERVED", "cost": "0.2"}},
                     "error_code": "PARENT_PROVIDER_TIMEOUT", "reserved_cost": "0.2", "settled_cost": "0"},
                    {"path": "runtime/task.json", "sha256": "b" * 64})

        def _bound(self, binding):
            return {"symbol": "600887", "action": "no_order",
                    "fact_anchors": {"cash": {"period_end": "2025-12-31"}}}

    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV2", Service)
    monkeypatch.setattr(routes, "authorize", lambda *_, **__: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=0)
    result = TestClient(app).get("/api/v1/operating-research/parent-cash-tasks/history?symbol=600887")
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    row = result.json()["items"][0]
    assert row["source_years"] == ["2025"]
    assert row["stage"] == "base.policy"
    assert row["settled_cost_cny"] == "0"
    assert row["e2_consumption"] == "UNVERIFIED"
    assert row["formal"] is False
    assert calls == [task.name]
    assert list(task.iterdir()) == [task / "input.json"]
