"""Fail-closed CI binding for synthetic restore mechanism evidence."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent import m6_ci_evidence as ci
from value_investment_agent import m6_operational_readiness as readiness


HEAD = "a" * 40


def _responses():
    run_id = 123
    return {
        "runs": {"workflow_runs": [{
            "id": run_id, "head_sha": HEAD, "repository": {"id": ci._REPOSITORY_ID},
            "path": ci._WORKFLOW, "event": "push", "head_branch": "main",
            "status": "completed", "run_attempt": 1, "conclusion": "success",
            "html_url": "https://github.com/MingMingLiu0112/value-investment/actions/runs/123",
        }]},
        "jobs": {"jobs": [{
            "id": 456, "run_id": run_id, "run_attempt": 1,
            "name": "postgres-integration", "status": "completed", "conclusion": "success",
            "steps": [{"name": name, "status": "completed", "conclusion": "success"}
                      for name in ("Verify disposable PostgreSQL research repository",
                                   "Retain synthetic isolated restore evidence")],
        }]},
        "artifacts": {"artifacts": [{
            "id": 789, "name": "m6-synthetic-restore-evidence",
            "workflow_run": {"id": run_id, "repository_id": ci._REPOSITORY_ID,
                             "head_sha": HEAD},
            "expired": False, "size_in_bytes": 100,
            "digest": "sha256:" + "b" * 64,
        }]},
    }


@pytest.fixture
def ci_root(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / ci._WORKFLOW
    target = tmp_path / ci._WORKFLOW
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    monkeypatch.setattr(ci, "_head", lambda _: HEAD)
    monkeypatch.setattr(ci.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(stdout=""))
    return tmp_path


def _mock_api(monkeypatch, responses):
    def get(url):
        if url.endswith("/artifacts?per_page=100"):
            return responses["artifacts"]
        if url.endswith("/jobs?per_page=100"):
            return responses["jobs"]
        return responses["runs"]
    monkeypatch.setattr(ci, "_get_json", get)


def test_current_commit_restore_ci_is_only_engineering_evidence(ci_root, monkeypatch):
    _mock_api(monkeypatch, _responses())
    evidence = ci.verify_restore_ci(ci_root)
    assert evidence["commit_sha"] == HEAD
    assert evidence["artifact_digest"] == "sha256:" + "b" * 64
    assert evidence["run_attempt"] == 1


@pytest.mark.parametrize("mutation", [
    lambda r: r["runs"]["workflow_runs"][0].update(head_sha="c" * 40),
    lambda r: r["runs"]["workflow_runs"][0].update(event="pull_request"),
    lambda r: r["runs"]["workflow_runs"][0].update(run_attempt=2),
    lambda r: r["runs"]["workflow_runs"][0].update(repository={"id": 1}),
    lambda r: r["jobs"]["jobs"][0]["steps"][0].update(conclusion="skipped"),
    lambda r: r["artifacts"]["artifacts"][0].update(expired=True),
    lambda r: r["artifacts"]["artifacts"][0]["workflow_run"].update(id=999),
])
def test_mismatch_fails_closed(ci_root, monkeypatch, mutation):
    responses = _responses()
    mutation(responses)
    _mock_api(monkeypatch, responses)
    with pytest.raises(ValueError):
        ci.verify_restore_ci(ci_root)


def test_dirty_checkout_cannot_bind_ci(ci_root, monkeypatch):
    monkeypatch.setattr(ci.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(stdout=" M docs/execution-status.md"))
    with pytest.raises(ValueError, match="clean worktree"):
        ci.verify_restore_ci(ci_root)


def test_workflow_without_restore_test_cannot_bind_ci(ci_root, monkeypatch):
    workflow = ci_root / ci._WORKFLOW
    workflow.write_text(workflow.read_text(encoding="utf-8").replace(
        "tests/test_m6_restore_integration.py", "tests/test_backup.py"),
        encoding="utf-8")
    _mock_api(monkeypatch, _responses())
    with pytest.raises(ValueError, match="does not run"):
        ci.verify_restore_ci(ci_root)


def test_preflight_ci_only_advances_mechanism(monkeypatch):
    root = Path(__file__).parents[1]
    evidence = {"workflow_path": ci._WORKFLOW, "workflow_sha256": "c" * 64,
                "artifact_id": 789, "artifact_digest": "sha256:" + "b" * 64,
                "verified_at": "2026-09-25T00:00:00+00:00"}
    monkeypatch.setattr(ci, "verify_restore_ci", lambda _: evidence)
    monkeypatch.setattr(readiness, "audit_repository", lambda *args, **kwargs: {
        "status": "DONE", "checks": [], "blockers": [], "evidence": {},
    })
    receipt = readiness.build_preflight_receipt(
        root, root / "config/m6-operational-preflight-v1.json", verify_ci=True)
    criteria = receipt["criteria"]
    assert criteria["m6c3_isolated_restore_mechanism"]["status"] == "DONE"
    assert criteria["m6c4_real_restore_rpo_rto"]["status"] == "NOT_STARTED"
    assert criteria["m6c5_real_sessions_and_events"]["evidence"]["real_events"] == 0
    assert receipt["operational_acceptance_status"] == "NOT_STARTED"
