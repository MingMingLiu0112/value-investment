import json
import pytest
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

    monkeypatch.setattr(routes, "run_and_seal_parent_cash_task", lambda service, task: service.run(task))
    monkeypatch.setattr(routes, "preflight_parent_cash_task", lambda service, binding: None)

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

def test_h1_sensitivity_requires_local_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: tmp_path)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=8001)
    client = TestClient(app)
    endpoint = "/api/v1/operating-research/parent-cash-tasks/v3/rt-" + "1" * 32 + "/h1-sensitivity"
    denied = client.get(endpoint, params={"symbol": "000568"})
    assert denied.status_code in (401, 403)
    assert denied.json()["action"] == "no_order"
    monkeypatch.setattr(routes, "authorize", lambda *_, **__: None)
    missing = client.get(endpoint, params={"symbol": "000568"})
    assert missing.status_code == 404
    assert missing.json()["status"] == "PARENT_TASK_H1_SENSITIVITY_NOT_REGISTERED"



@pytest.mark.parametrize("failure", [None, "invalid_json", "unsettled", "operating_series", "financing", "base_terminal"])
def test_company_launch_requires_binding_and_reuses_request_key(tmp_path, monkeypatch, failure):
    from hashlib import sha256

    binding = {"path": "runtime/spec.json", "sha256": "a" * 64}
    task_id = "rt-" + "b" * 32
    calls = []

    class Service:
        def __init__(self, root):
            self.root = self.base = root
            if failure:
                key = "value-web-" + binding["sha256"]
                former_id = "rt-" + sha256(("parent-cash-task-v3:" + key).encode()).hexdigest()[:32]
                (root / former_id).mkdir(exist_ok=True)
                (root / former_id / "input.json").touch()

        def read(self, _):
            if failure in {"financing", "base_terminal"}:
                return dict(status="FAILED",
                            error_code="BEAR_POLICY_PARENT_FINANCING_ABOVE_DISCLOSED_PROCEEDS:2026")
            return dict(status="FAILED", error_code=(
                "BEAR_OPERATING_PARENT_V3_YEARS_OR_SERIES_INVALID" if failure == "operating_series"
                else "BEAR_POLICY_PARENT_V3_INVALID_JSON"),
                        completed_stages=["bear.operating"],
                        reservations={"policy": {"status": "RESERVED"}} if failure == "unsettled" else {})

        def create(self, *, spec_binding, request_key, **options):
            assert 8 <= len(request_key) <= 80
            calls.append((spec_binding, request_key, options))
            if failure == "base_terminal" and request_key.startswith(("value-fin1-", "value-fin2-")):
                return {"status": "FAILED", "task_id": task_id,
                        "error_code": "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION",
                        "action": "no_order"}
            return {"status": "QUEUED", "task_id": task_id, "action": "no_order"}

    monkeypatch.setattr(routes, "ParentCashTaskServiceV2", Service)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", Service)
    monkeypatch.setattr(routes, "authorize", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda project: project)
    monkeypatch.setattr(routes, "registered_cash_task_spec",
                        lambda service, symbol: binding if symbol == "600323" else None)
    monkeypatch.setattr(routes, "run_and_seal_parent_cash_task",
                        lambda service, identifier: calls.append(identifier))
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=tmp_path, sessions=None, port=8001)
    client = TestClient(app)
    path = "/api/v1/operating-research/parent-cash-tasks/by-company"
    assert client.post(path, json={"symbol": "600066"}).status_code == 409
    assert client.post(path, json={"symbol": "600323", "spec_binding": binding}).status_code == 422
    assert not calls
    for _ in range(2):
        response = client.post(path, json={"symbol": "600323"})
        assert response.status_code == 202 and response.json()["task_id"] == task_id
    key = "value-web-" + binding["sha256"]
    options = {}
    if failure in {"invalid_json", "operating_series", "financing", "base_terminal"}:
        former_id = "rt-" + sha256(("parent-cash-task-v3:" + key).encode()).hexdigest()[:32]
        key = {"invalid_json": "value-policy1-", "operating_series": "value-op1-",
               "financing": "value-fin1-", "base_terminal": "value-fin1-"}[failure] + binding["sha256"]
        options = dict(seed_task_id=former_id,
                       replay_from_stage="bear.operating" if failure == "operating_series" else "bear.policy")
    expected = [(binding, key, options)]
    if failure == "base_terminal":
        expected.append((binding, "value-fin2-" + binding["sha256"],
                         dict(seed_task_id=task_id, replay_from_stage="base.terminal")))
        expected.append((binding, "value-fin3-" + binding["sha256"],
                         dict(seed_task_id=task_id, replay_from_stage="base.operating")))
    assert calls == (expected + [task_id]) * 2

    if failure is None:
        calls.clear()
        body = {"symbol": "600323", "continue_from_task_id": task_id}
        assert client.post(path, json=body).status_code == 422
        assert not calls
        monkeypatch.setattr(Service, "read", lambda *_: dict(
            status="FAILED", spec_binding=binding,
            error_code="BASE_POLICY_PARENT_PROVIDER_OR_SETTLEMENT_AMBIGUOUS",
            completed_stages=["base.operating"],
        ))
        for _ in range(2):
            assert client.post(path, json=body).status_code == 202
        key = "value-policy-recovery-" + sha256(task_id.encode()).hexdigest()[:56]
        assert calls == [(binding, key, dict(seed_task_id=task_id,
                          replay_from_stage="base.policy")), task_id] * 2


def test_current_parent_cash_spec_keeps_historical_case_binding(tmp_path):
    from types import SimpleNamespace
    from value_investment_agent.application.research.parent_cash_task_completion_v1 import (
        _case_binding, registered_cash_task_spec,
    )

    config = tmp_path / "config"
    config.mkdir()
    path = config / "parent-cash-task-case-bindings-v1.json"
    old = {"path": "old.json", "sha256": "1" * 64}
    current = {"path": "new.json", "sha256": "2" * 64}
    case = {"path": "case.json", "sha256": "3" * 64}
    payload = {"schema_version": "parent-cash-task-case-bindings-v1", "specs": {
        binding["sha256"]: {"symbol": "600887", "spec_binding": binding,
                             "case_package_binding": case}
        for binding in (old, current)
    }}
    documents = {
        "new.json": {"symbol": "600887", "action": "no_order", "model_applicable": True},
        "case.json": {"symbol": "600887", "profile_id": "quality_compounder",
                      "schema_version": "m1-valuation-package-v2",
                      "research_case": {"symbol": "600887"}},
    }
    service = SimpleNamespace(root=tmp_path, _bound=lambda binding: documents[binding["path"]])
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="PARENT_TASK_AMBIGUOUS_COMPANY_BINDING"):
        registered_cash_task_spec(service, "600887")
    payload["active_spec_by_symbol"] = {"600887": current["sha256"]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert registered_cash_task_spec(service, "600887") == current
    assert _case_binding(tmp_path, old) == case
    payload["active_spec_by_symbol"]["600887"] = "4" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="PARENT_TASK_ACTIVE_SPEC_INVALID"):
        registered_cash_task_spec(service, "600887")
