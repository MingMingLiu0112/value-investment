"""TEST_ONLY binding checks; no provider, private account, or paid call."""
import subprocess

import pytest
from web_api.test_held_continuity_api import client_for, unlock
from value_investment_agent.presentation.web_api import live_operating_research_routes as routes


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def sibling_roots(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "--allow-empty", "-m", "TEST_ONLY", cwd=repo)
    (repo / ".tmp").mkdir()
    code = repo / ".tmp" / "code"
    research = repo / ".tmp" / "research"
    _git("worktree", "add", "--detach", str(code), cwd=repo)
    _git("worktree", "add", "--detach", str(research), cwd=repo)
    return code, research


def test_alternate_root_is_used_for_task_history_model_status_and_e2(
        sibling_roots, monkeypatch):
    code, research = sibling_roots
    (research / "TEST_ONLY-task.json").write_text('{"task_id":"TEST_ONLY"}', encoding="utf-8")
    monkeypatch.setenv(routes.RESEARCH_TASK_ROOT_ENV, str(research))
    roots = []

    class ReadOnlyService:
        test_provider = object()
        def __init__(self, root):
            roots.append(root)
            self.root = root
        def list_for_symbol(self, symbol):
            assert symbol == "600519"
            return []
        def read(self, task_id):
            assert (self.root / "TEST_ONLY-task.json").is_file()
            return {"task_id": task_id, "status": "WAITING_EVIDENCE", "action": "no_order"}

    monkeypatch.setattr(routes, "LiveOperatingTaskService", ReadOnlyService)
    monkeypatch.setattr(routes, "model_status", lambda root: {
        "status": "MODEL_AUTHORIZATION_REQUIRED", "action": "no_order",
        "credential_present": False, "real_calls_started": False,
        "TEST_ONLY_budget_root": str(root),
    })
    client, secret = client_for(code, code / "TEST_ONLY-journal.jsonl", monkeypatch)
    status = client.get("/api/v1/operating-research/model-status").json()
    assert status["research_task_root"] == str(research)
    assert status["code_root"] == str(code)
    assert status["TEST_ONLY_budget_root"] == str(research)
    assert status["research_task_root_binding"] == "CONFIGURED_SIBLING_WORKTREE"
    unlock(client, secret)
    task = client.get("/api/v1/operating-research/tasks/TEST_ONLY").json()
    assert task["task_id"] == "TEST_ONLY" and task["action"] == "no_order"
    assert roots == [research]


@pytest.mark.parametrize("bad", ["relative", "missing", "repo", "outside"])
def test_invalid_or_missing_binding_fails_closed(sibling_roots, tmp_path, monkeypatch, bad):
    code, research = sibling_roots
    outside = tmp_path / "outside"
    outside.mkdir()
    value = {"relative": "../research", "missing": str(research / "missing"),
             "repo": str(code.parents[1]), "outside": str(outside)}[bad]
    monkeypatch.setenv(routes.RESEARCH_TASK_ROOT_ENV, value)
    with pytest.raises(ValueError, match="INVALID_LOCAL_RESEARCH_TASK_ROOT"):
        client_for(code, code / "TEST_ONLY-journal.jsonl", monkeypatch)


def test_missing_source_is_not_replaced_by_code_root(sibling_roots, monkeypatch):
    code, research = sibling_roots
    (code / "config").mkdir()
    (code / "config" / "TEST_ONLY-source.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(routes.RESEARCH_TASK_ROOT_ENV, str(research))

    class SourceBoundService:
        test_provider = object()
        def __init__(self, root):
            self.root = root
        def list_for_symbol(self, symbol):
            return []
        def create(self, **kwargs):
            if not (self.root / "config" / "TEST_ONLY-source.json").is_file():
                raise ValueError("SOURCE_NOT_IN_RESEARCH_ROOT")
            raise AssertionError("code-root source must not be used")

    monkeypatch.setattr(routes, "LiveOperatingTaskService", SourceBoundService)
    client, secret = client_for(code, code / "TEST_ONLY-journal.jsonl", monkeypatch)
    unlock(client, secret)
    result = client.post("/api/v1/operating-research/tasks",
                         json={"symbol": "600519", "request_key": "TEST_ONLY"})
    assert result.status_code == 422
    assert result.json()["status"] == "LIVE_TASK_REJECTED_SOURCE_CONFIG_OR_BUDGET"
    assert not (research / "config" / "TEST_ONLY-source.json").exists()


def test_e2_reader_receives_the_same_alternate_root(sibling_roots, monkeypatch):
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2

    code, research = sibling_roots
    monkeypatch.setenv(routes.RESEARCH_TASK_ROOT_ENV, str(research))
    observed = []

    def read(*, root, task_id, now, service):
        observed.append((root, service.root, task_id))
        return {"status": "UNASSESSABLE", "reason": "TEST_ONLY_MISSING_ECONOMIC_SOURCE",
                "action": "no_order", "formal_eligibility": False}

    monkeypatch.setattr(e2, "read_d2_cash_policy_e2_input", read)
    client, secret = client_for(code, code / "TEST_ONLY-journal.jsonl", monkeypatch)
    unlock(client, secret)
    result = client.get("/api/v1/operating-research/cash-policy-tasks/TEST_ONLY/e2-input")
    assert result.status_code == 200
    assert result.json()["status"] == "UNASSESSABLE"
    assert observed == [(research, research, "TEST_ONLY")]
