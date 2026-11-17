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


def test_numbered_parent_cash_task_api_runs_only_on_explicit_post(tmp_path, monkeypatch):
    calls = []
    task_id = "rt-" + "b" * 32

    class NumberedService:
        def __init__(self, root):
            assert root == tmp_path

        def create(self, *, spec_binding, request_key):
            calls.append(("create", spec_binding, request_key))
            return {"task_id": task_id, "status": "QUEUED", "action": "no_order",
                    "formal_eligibility": False}

        def run(self, value):
            calls.append(("run", value))

        def read(self, value):
            calls.append(("read", value))
            return {"task_id": value, "status": "SUCCEEDED", "action": "no_order",
                    "formal_eligibility": False, "main_range_adopted": False}

        def cancel(self, value):
            calls.append(("cancel", value))
            return {"task_id": value, "status": "CANCELLED", "action": "no_order"}

        def resume(self, value):
            calls.append(("resume", value))
            return {"task_id": value, "status": "QUEUED", "action": "no_order"}

    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", NumberedService)
    monkeypatch.setattr(routes, "authorize", lambda *_, **__: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=0)
    client = TestClient(app)
    path = "/api/v1/operating-research/parent-cash-tasks/v3"
    assert client.get(f"{path}/{task_id}").json()["status"] == "SUCCEEDED"
    assert calls == [("read", task_id)]
    assert client.post(path, json={"request_key": "test-request-01",
        "spec_binding": {"path": "runtime/spec.json", "sha256": "a" * 64}}).status_code == 202
    assert calls[-2:] == [("create", {"path": "runtime/spec.json", "sha256": "a" * 64},
                            "test-request-01"), ("run", task_id)]
    assert client.post(f"{path}/{task_id}/cancel").json()["status"] == "CANCELLED"
    assert client.post(f"{path}/{task_id}/resume").json()["status"] == "QUEUED"
    assert calls[-2:] == [("resume", task_id), ("run", task_id)]
    assert client.post(path, json={"request_key": "x", "extra": 1}).status_code == 422
    assert client.get(f"{path}/invalid").status_code == 422


def test_numbered_history_is_visible_without_old_task_store(tmp_path, monkeypatch):
    directory = tmp_path / "new" / ("rt-" + "c" * 32)
    directory.mkdir(parents=True)
    (directory / "input.json").write_text("{}", encoding="utf-8")

    class OldService:
        base = tmp_path / "absent-old"

        def __init__(self, root):
            assert root == tmp_path

    class NumberedService:
        base = tmp_path / "new"

        def __init__(self, root):
            assert root == tmp_path

        def _load(self, task_id):
            assert task_id == directory.name
            return ({"spec_binding": {"path": "runtime/source.json", "sha256": "a" * 64}},
                    {"status": "SUCCEEDED", "responses": {"base.operating": {}},
                     "reservations": {}, "reserved_cost": "0", "settled_cost": "0.1"},
                    {"path": "runtime/task.json", "sha256": "b" * 64})

        def _bound(self, binding):
            return {"symbol": "000568", "action": "no_order",
                    "fact_anchors": {"cash": {"period_end": "2025-12-31"}}}

    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV2", OldService)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", NumberedService)
    monkeypatch.setattr(routes, "authorize", lambda *_, **__: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=0)
    response = TestClient(app).get(
        "/api/v1/operating-research/parent-cash-tasks/history?symbol=000568")
    assert response.status_code == 200
    row = response.json()["items"][0]
    assert row["task_contract"] == "parent-cash-task-v3"
    assert row["candidate_status"] == "COMPILED_CONDITIONAL_NOT_MAIN"
    assert row["e2_consumption"] == "UNVERIFIED"
    assert row["action"] == "no_order"


def test_sibling_execution_root_keeps_code_checkout_v3_history_read_only(tmp_path, monkeypatch):
    code_root = tmp_path / "code"
    task_root = tmp_path / "tasks"
    code_root.mkdir()
    task_root.mkdir()
    task_id = "rt-" + "d" * 32
    archive = code_root / "numbered" / task_id
    archive.mkdir(parents=True)
    (archive / "input.json").write_text("{}", encoding="utf-8")
    calls = []

    class OldService:
        def __init__(self, root):
            self.base = root / "absent-old"

    class NumberedService:
        def __init__(self, root):
            self.base = root / "numbered"
            self.root = root

        def read(self, value):
            calls.append(("read", self.root, value))
            return {"task_id": value, "status": "FAILED", "action": "no_order"}

        def _load(self, value):
            calls.append(("load", self.root, value))
            return ({"spec_binding": {"path": "runtime/source.json", "sha256": "a" * 64}},
                    {"status": "FAILED", "responses": {}, "reservations": {},
                     "error_code": "TERMINAL_DEBT_UNSUPPORTED", "reserved_cost": "0.1",
                     "settled_cost": "0.1"},
                    {"path": "runtime/archived-state.json", "sha256": "b" * 64})

        def _bound(self, binding):
            return {"symbol": "000568", "action": "no_order", "fact_anchors": {}}

    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: task_root)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV2", OldService)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", NumberedService)
    monkeypatch.setattr(routes, "authorize", lambda *_, **__: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=code_root, sessions=None, port=0)
    client = TestClient(app)
    history = client.get("/api/v1/operating-research/parent-cash-tasks/history?symbol=000568")
    assert history.status_code == 200
    assert history.json()["items"][0]["read_only_archive"] is True
    detail = client.get(f"/api/v1/operating-research/parent-cash-tasks/v3/{task_id}")
    assert detail.json()["status"] == "FAILED"
    assert ("read", code_root, task_id) in calls
    assert ("read", task_root, task_id) not in calls
    assert client.post(f"/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/cancel").status_code == 422
