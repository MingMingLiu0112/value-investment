"""TEST_ONLY complete saved-response task API; no real model/approval."""
import json
import pytest
from pathlib import Path

from test_web_agent_research import build, state
from web_api.test_held_continuity_api import client_for, unlock


def test_research_task_api_auth_idempotency_and_no_read_side_effect(tmp_path, monkeypatch):
    build(tmp_path)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    body = dict(symbol="600519", workflow="legacy", request_key="test-task-001")
    before = state(tmp_path)
    assert client.post("/api/v1/research-tasks", json=body).status_code == 401
    assert state(tmp_path) == before
    unlock(client, secret)
    created = client.post("/api/v1/research-tasks", json=body)
    assert created.status_code == 202, created.text
    task_id = created.json()["task_id"]
    complete = client.get("/api/v1/research-tasks/" + task_id)
    assert complete.status_code == 200, complete.text
    result = complete.json()
    assert result["status"] == "SUCCEEDED", result
    assert result["workflow"] == "legacy"
    assert result["checkpoint_verified"] is True
    assert result["new_llm_calls"] == 0
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    before = state(tmp_path)
    assert client.get("/api/v1/research-tasks/" + task_id).json() == result
    assert state(tmp_path) == before
    again = client.post("/api/v1/research-tasks", json=body)
    assert again.json()["task_id"] == task_id
    assert again.json()["status"] == "SUCCEEDED"
    assert client.post("/api/v1/research-tasks/" + task_id + "/resume").json()["status"] == "SUCCEEDED"
    assert client.post("/api/v1/research-tasks/" + task_id + "/cancel").json()["status"] == "SUCCEEDED"
    before = state(tmp_path)
    found = client.get("/api/v1/research-tasks?symbol=600519").json()
    assert [row["task_id"] for row in found["items"]] == [task_id]
    assert client.get("/api/v1/research-tasks?symbol=600887").json()["items"] == []
    assert state(tmp_path) == before
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()


def test_task_api_rejects_paths_paid_model_bad_source_and_cross_origin(tmp_path, monkeypatch):
    _, _, _, original, _, _ = build(tmp_path)
    client, secret = client_for(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch)
    unlock(client, secret)
    body = dict(symbol="600519", workflow="legacy", request_key="test-task-002")
    for extra in (dict(path="private.json"), dict(mode="live"), dict(model="external")):
        assert client.post("/api/v1/research-tasks", json={**body, **extra}).status_code == 422
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.post("/api/v1/research-tasks", json=body).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    original.write_text("changed original", encoding="utf-8")
    assert client.post("/api/v1/research-tasks", json=body).status_code == 422
    assert not (tmp_path / "runtime/research-task-execution-v1").exists()
    assert client.get("/api/v1/research-tasks/../../private").status_code == 404


def test_task_api_lock_contention_is_retryable_not_missing(tmp_path, monkeypatch):
    from value_investment_agent.application.research.agent_review.task_execution_v1 import ResearchTaskService
    from value_investment_agent.application.portfolio.private_journal_lock import LockTimeout
    build(tmp_path)
    client,secret=client_for(tmp_path,tmp_path/"TEST_ONLY.jsonl",monkeypatch)
    unlock(client,secret)
    def busy(*args,**kwargs):
        raise LockTimeout("TEST_ONLY concurrent owner")
    monkeypatch.setattr(ResearchTaskService,"read",busy)
    response=client.get("/api/v1/research-tasks/rt-"+"a"*32)
    assert response.status_code==409 and response.json()["status"]=="TASK_BUSY"
    monkeypatch.setattr(ResearchTaskService,"create",busy)
    response=client.post("/api/v1/research-tasks",json=dict(symbol="600519",workflow="legacy",request_key="test-busy-001"))
    assert response.status_code==409 and response.json()["status"]=="TASK_BUSY"


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_requested_workflow_is_persisted_and_idempotent(tmp_path, monkeypatch, workflow):
    from test_web_agent_research import daily_registry
    daily_registry(tmp_path,workflow)
    client,secret=client_for(tmp_path,tmp_path/"TEST_ONLY.jsonl",monkeypatch)
    unlock(client,secret)
    body=dict(symbol="600519",workflow=workflow,request_key="workflow-test-"+workflow)
    result=client.post("/api/v1/research-tasks",json=body)
    assert result.status_code==202,result.text
    task_id=result.json()["task_id"]
    persisted=client.get("/api/v1/research-tasks/"+task_id).json()
    assert persisted["workflow"]==workflow
    assert client.post("/api/v1/research-tasks",json=body).json()["task_id"]==task_id
