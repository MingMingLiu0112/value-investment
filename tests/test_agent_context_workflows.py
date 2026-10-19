"""TEST_ONLY end-to-end context workflows through real verification and registration."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_daily_agent_research import setup
from test_daily_agent_research_cli import cli
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review.context_workflows import (
    CONTEXT_KINDS, run_daily_context_mock,
)
from value_investment_agent.application.research.agent_review.daily_batch import run_daily_mock_batch
from value_investment_agent.application.research.agent_review.daily_registration import register_daily_draft_results
from value_investment_agent.application.research.agent_review.llm_pilot import _agent_output_lock_path
from value_investment_agent.application.research.agent_review.web_research import read_web_agent_research


def context_inputs(root, workflow):
    args = setup(root)
    args.pop("responses")
    source = args["source_requests"][0]
    value = dict(schema_version="agent-source-workflow-context-v1", action="no_order",
        symbol=args["symbol"], workflow=workflow, scope="TEST_ONLY", records=[
            dict(kind=kind, source_id=source.source_id, excerpt=source.excerpt,
                 available_at=source.available_at) for kind in sorted(CONTEXT_KINDS[workflow])])
    path = root / "runtime/context.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    args.update(workflow=workflow, context_path=path, context_sha256=sha256_file(path))
    return args, value


def batch_result(result, workflow):
    return dict(schema_version="daily-agent-mock-batch-result-v1", mode="MOCK", action="no_order",
        approval_count=0, decision_changed=False, items=[dict(symbol="600519",
            workflow=workflow, status="DRAFT_READY", result=result)])


@pytest.mark.parametrize("workflow", ["hotspot", "retrospective"])
def test_full_chain_register_reopen_and_reject_changed_context(tmp_path, workflow, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("Mock must not open a network provider")
    monkeypatch.setattr("value_investment_agent.infrastructure.agent_runtime.provider.build_opener", forbidden)
    args, value = context_inputs(tmp_path, workflow)
    result = run_daily_context_mock(**args)
    assert len(result["findings"]) == 3
    assert result["data_scope"] == "TEST_ONLY"
    assert run_daily_context_mock(**args) == result
    now = datetime.now(timezone.utc)
    batch = batch_result(result, workflow)
    registration = register_daily_draft_results(root=tmp_path, batch_result=batch, now=now)
    assert registration["status"] == "UPDATED", registration
    assert register_daily_draft_results(root=tmp_path, batch_result=batch, now=now)["status"] == "UNCHANGED"
    view = read_web_agent_research(tmp_path, symbol="600519", workflow=workflow, now=now)
    assert view["status"] == "VERIFIED", view
    assert view["data_scope"] == "TEST_ONLY" and not view["eligibility"]
    assert view["approval_count"] == view["formal_fact_count"] == 0
    value["records"][0]["excerpt"] = "Not present in admitted source"
    args["context_path"].write_text(json.dumps(value), encoding="utf-8")
    assert read_web_agent_research(tmp_path, symbol="600519", workflow=workflow, now=now)["status"] == "UNAVAILABLE"
    args["context_sha256"] = sha256_file(args["context_path"])
    with pytest.raises(ValueError, match="exact admitted excerpt"):
        run_daily_context_mock(**args)


@pytest.mark.parametrize("change", ["scope", "future", "citation", "missing", "unknown"])
def test_reject_scope_time_and_citation_without_writing(tmp_path, change):
    args, value = context_inputs(tmp_path, "retrospective")
    if change == "scope":
        value["scope"] = "PRIVATE"
    elif change == "future":
        value["records"][0]["available_at"] = "2099-01-01T00:00:00+08:00"
    elif change == "citation":
        value["records"][0]["source_id"] = "unknown"
    elif change == "missing":
        value["records"].pop()
    else:
        value["account_number"] = "TEST_ONLY"
    args["context_path"].write_text(json.dumps(value), encoding="utf-8")
    args["context_sha256"] = sha256_file(args["context_path"])
    with pytest.raises(ValueError):
        run_daily_context_mock(**args)
    assert not args["output"].exists()


def test_batch_context_failure_does_not_block_other_job(tmp_path):
    args, _ = context_inputs(tmp_path, "hotspot")
    requests = tmp_path / "runtime/requests.json"
    requests.write_text(json.dumps(dict(schema_version="agent-excerpt-requests-v1", action="no_order",
        symbol="600519", requests=[asdict(row) for row in args["source_requests"]])), encoding="utf-8")
    def pin(path):
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path))
    good = dict(symbol="600519", workflow="hotspot", workbench=pin(args["workbench"]),
        context=pin(args["context_path"]), source_requests=pin(requests), output="runtime/hotspot.json")
    bad = dict(good, workflow="retrospective", output="runtime/retro.json")
    plan = tmp_path / "runtime/plan.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1", action="no_order",
        mode="MOCK", jobs=[bad, good])), encoding="utf-8")
    result = run_daily_mock_batch(root=tmp_path, plan=plan, plan_sha256=sha256_file(plan))
    assert result["status"] == "PARTIAL"
    assert [item["status"] for item in result["items"]] == ["FAILED", "DRAFT_READY"]


def test_private_context_is_rejected_before_open(tmp_path, monkeypatch):
    args, _ = context_inputs(tmp_path, "retrospective")
    secret_path = tmp_path / "runtime/private-account.json"
    original_open = Path.open
    def guarded_open(path, *a, **kw):
        if path == secret_path:
            pytest.fail("Private context must not be opened")
        return original_open(path, *a, **kw)
    monkeypatch.setattr(Path, "open", guarded_open)
    args["context_path"] = secret_path
    with pytest.raises(ValueError, match="public research artifact"):
        run_daily_context_mock(**args)


def test_busy_job_lock_does_not_abort_following_job(tmp_path):
    args, _ = context_inputs(tmp_path, "hotspot")
    request_path = tmp_path / "runtime/requests.json"
    request_path.write_text(json.dumps(dict(schema_version="agent-excerpt-requests-v1", action="no_order",
        symbol="600519", requests=[asdict(row) for row in args["source_requests"]])), encoding="utf-8")
    def pin(path):
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path))
    job = dict(symbol="600519", workflow="hotspot", workbench=pin(args["workbench"]),
        context=pin(args["context_path"]), source_requests=pin(request_path), output="runtime/busy.json")
    lock = _agent_output_lock_path(tmp_path / "runtime/busy.json")
    source_root = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    child_code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from value_investment_agent.application.portfolio.private_journal_lock import InterProcessLock\n"
        "lock = InterProcessLock(Path(sys.argv[1]), timeout_seconds=1)\n"
        "lock.acquire()\n"
        "print('LOCKED', flush=True)\n"
        "sys.stdin.read()\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", child_code, str(lock)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=env,
    )
    plan = tmp_path / "runtime/plan.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1", action="no_order", mode="MOCK",
        jobs=[job, dict(job, output="runtime/next.json")])), encoding="utf-8")
    try:
        assert holder.stdout.readline().strip() == "LOCKED"
        result = run_daily_mock_batch(root=tmp_path, plan=plan, plan_sha256=sha256_file(plan))
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=10)
    assert result["status"] == "PARTIAL"
    assert [row["status"] for row in result["items"]] == ["FAILED", "DRAFT_READY"]
    assert result["items"][0]["error_type"] == "RuntimeError"
    assert lock.is_file()


def test_retrospective_rejects_later_plan_as_original_knowledge(tmp_path):
    from dataclasses import replace
    from value_investment_agent.application.research.agent_review.context_workflows import verify_workflow_context
    from value_investment_agent.application.research.agent_review.snapshot import load_research_snapshot

    args, value = context_inputs(tmp_path, "retrospective")
    snapshot = load_research_snapshot(root=tmp_path, workbench=args["workbench"],
        expected_sha256=args["workbench_sha256"], symbol="600519")
    evidence, excerpts = [], []
    for row in value["records"]:
        row["source_id"] = row["kind"]
        row["available_at"] = ("2026-10-08T12:00:00+08:00" if row["kind"] == "original_plan"
                               else "2026-10-07T12:00:00+08:00")
        evidence.append(dict(snapshot.evidence[0], id=row["source_id"], available_at=row["available_at"]))
        excerpts.append(dict(source_id=row["source_id"], excerpt=row["excerpt"]))
    args["context_path"].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="PIT order"):
        verify_workflow_context(root=tmp_path, snapshot=replace(snapshot, evidence=tuple(evidence)),
            workflow="retrospective", context_path=args["context_path"],
            context_sha256=sha256_file(args["context_path"]), excerpts=excerpts)


@pytest.mark.parametrize("workflow", ["hotspot", "retrospective"])
def test_context_cli_calls_real_chain(cli, tmp_path, monkeypatch, capsys, workflow):
    import sys

    args, _ = context_inputs(tmp_path, workflow)
    request_path = tmp_path / "runtime/requests.json"
    request_path.write_text(json.dumps(dict(schema_version="agent-excerpt-requests-v1", action="no_order",
        symbol="600519", requests=[asdict(row) for row in args["source_requests"]])), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["pilot", "--mode", "mock", "--workflow", workflow,
        "--symbol", "600519", "--workbench", str(args["workbench"]),
        "--workbench-sha256", args["workbench_sha256"], "--output", str(args["output"]),
        "--context", str(args["context_path"]), "--context-sha256", args["context_sha256"],
        "--source-requests", str(request_path), "--source-requests-sha256", sha256_file(request_path)])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["findings"]) == 3
    assert result["live_status"] == "LIVE_LLM_NOT_AUTHORIZED"


def test_api_context_workflow_replays_without_provider(tmp_path, monkeypatch):
    from test_agent_research_api import registered_client, unlock, ROUTE

    args, _ = context_inputs(tmp_path, "retrospective")
    result = run_daily_context_mock(**args)
    now = datetime.now(timezone.utc)
    register_daily_draft_results(root=tmp_path, batch_result=batch_result(result, "retrospective"), now=now)
    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    assert client.get(ROUTE + "?workflow=retrospective").status_code == 401
    unlock(client, secret)
    response = client.get(ROUTE + "?workflow=retrospective")
    assert response.status_code == 200 and response.json()["status"] == "VERIFIED"
    assert response.json()["data_scope"] == "TEST_ONLY"
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()


def test_real_http_restart_replays_draft_and_keeps_session_boundary(tmp_path):
    import socket
    import threading
    import time

    import httpx
    import uvicorn
    from value_investment_agent.presentation.web_api.app import create_app

    args, _ = context_inputs(tmp_path, "hotspot")
    result = run_daily_context_mock(**args)
    register_daily_draft_results(root=tmp_path, batch_result=batch_result(result, "hotspot"),
        now=datetime.now(timezone.utc))
    for _ in range(2):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        secret = "TEST_ONLY-http-" + "x" * 48
        server = uvicorn.Server(uvicorn.Config(create_app(tmp_path, port=port, bootstrap_secret=secret),
            log_level="error", lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                route = "/api/v1/agent-research/600519?workflow=hotspot"
                assert client.get(route).status_code == 401
                token = client.post("/api/v1/private/session/unlock",
                    json={"bootstrap_token": secret}).json()["token"]
                client.headers["x-local-session"] = token
                response = client.get(route)
                assert response.status_code == 200
                assert response.json()["status"] == "VERIFIED"
                assert response.json()["action"] == "no_order"
                assert response.headers["cache-control"] == "no-store"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            assert not thread.is_alive()


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_retained_public_source_to_fresh_draft_and_registered_view(tmp_path, workflow):
    """Copy only registered public bytes; never change actual runtime pointers."""
    from value_investment_agent.application.research.agent_review.daily_research import (
        run_daily_event_mock, run_daily_financial_mock,
    )
    from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest

    project = Path(__file__).resolve().parents[1]
    registry = json.loads((project / "config/current-agent-research.json").read_text(encoding="utf-8"))
    entry = registry["cases"]["600519"]["workflows"][workflow]
    def copy(ref):
        source = project / ref["path"]
        assert sha256_file(source) == ref["sha256"]
        target = tmp_path / ref["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target
    wb = copy(entry["workbench"])
    payload = json.loads(wb.read_text(encoding="utf-8"))
    originals = list(payload["source_verification"]["sources"])
    for artifact in payload["artifact_bundle"]["artifacts"]:
        if artifact["identity"]["artifact_type"] == "research_case":
            originals += json.loads(artifact["canonical_payload"])["evidence_refs"]
    for ref in originals:
        copy(ref)
    packet = json.loads((project / entry["packet"]["path"]).read_text(encoding="utf-8"))
    requests = tuple(ExcerptRequest(**row) for row in packet["source_context"]["excerpts"])
    args = dict(root=tmp_path, workbench=wb, workbench_sha256=entry["workbench"]["sha256"],
        symbol="600519", output=tmp_path / "runtime/fresh-draft.json", source_requests=requests)
    if workflow == "event":
        result = run_daily_event_mock(**args, responses=packet["raw_responses"])
    else:
        extra = {}
        for key in ("transcription", "metric_workbench"):
            ref = entry["workflow_binding"][key]
            extra[key] = copy(ref)
            extra[key + "_sha256"] = ref["sha256"]
        result = run_daily_financial_mock(**args, **extra)
    assert len(result["findings"]) == 3
    now = datetime.now(timezone.utc)
    assert register_daily_draft_results(root=tmp_path, batch_result=batch_result(result, workflow),
        now=now)["status"] == "UPDATED"
    view = read_web_agent_research(tmp_path, symbol="600519", workflow=workflow, now=now)
    assert view["status"] == "VERIFIED", view
    assert view["mode"] == "MOCK" and view["approval_count"] == 0
    assert any("cninfo" in row["evidence_id"] for row in view["sources"])
