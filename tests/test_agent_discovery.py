"""Retained public market originals through discovery, four Mock jobs and HTTP."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from test_daily_agent_research_cli import cli
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review.discovery import discover_daily_mock_inputs
from value_investment_agent.application.research.agent_review.daily_batch import run_daily_mock_batch
from value_investment_agent.application.research.agent_review.daily_registration import register_daily_draft_results
from value_investment_agent.application.research.agent_review.web_research import read_web_agent_research


PROJECT = Path(__file__).resolve().parents[1]
# Replay the retained 2026-10-16 cases before their next-session expiry. The
# production clock remains live; later dates must reject those cases.
REPLAY_AT = datetime.fromisoformat("2026-10-19T02:00:00+00:00")


def copy_registered_public_inputs(root):
    """Only explicit public bindings, never a recursive copy of runtime/private data."""
    seen = set()
    def copy(name, digest=None):
        name = str(name).replace("\\", "/")
        assert name.startswith(("runtime/", "config/", "artifacts/", "docs/"))
        assert not any(word in name.lower() for word in ("private", "secret", "credential", "journal"))
        if name in seen:
            return
        # Freeze the public fixture's metadata independently of daily updates.
        fixture = {"config/current-price-conditions.json": "agent-discovery-price-registry-v1.json",
                   "config/current-agent-research.json": "agent-discovery-research-registry-v1.json"}.get(name)
        source = PROJECT / "tests/fixtures" / fixture if fixture else PROJECT / name
        raw = source.read_bytes()
        if digest is not None:
            assert hashlib.sha256(raw).hexdigest() == digest
        seen.add(name)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if source.suffix == ".json":
            walk(json.loads(raw))
    def walk(value):
        if isinstance(value, dict):
            for key, digest_key in (("path", "sha256"), ("case_path", "case_sha256"),
                                    ("bundle_path", "bundle_sha256"), ("packet_path", "packet_sha256")):
                if isinstance(value.get(key), str) and digest_key in value:
                    copy(value[key], value[digest_key])
            if isinstance(value.get("canonical_payload"), str):
                walk(json.loads(value["canonical_payload"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    copy("config/current-price-conditions.json")
    copy("config/current-agent-research.json")
    # Public packet discovery is optional; retained current registry replay is
    # sufficient and avoids copying unrelated public workbench dependencies.
    return seen


def confirmed_test_only_input(root):
    path = root / "runtime/agent-research-test-only-inputs/confirmed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = dict(schema_version="agent-test-only-retrospective-input-v1", action="no_order",
        symbol="600519", account_scope="TEST_ONLY", confirmed=True, records=[
            dict(kind="original_plan", text="TEST_ONLY original plan: wait for confirmed close; no orders.",
                 available_at="2026-10-12T16:00:00+08:00"),
            dict(kind="manual_fill", text="TEST_ONLY manual fill: 100 shares recorded by isolated scenario.",
                 available_at="2026-10-13T10:00:00+08:00"),
            dict(kind="confirmed_holding", text="TEST_ONLY confirmed holding: 100 shares in isolated scenario.",
                 available_at="2026-10-13T16:00:00+08:00"),
            dict(kind="subsequent_information", text="TEST_ONLY subsequent information: review risk; no inferred past knowledge.",
                 available_at="2026-10-14T16:00:00+08:00")])
    path.write_text(json.dumps(value), encoding="utf-8")
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def discover(root, retrospective=None):
    return discover_daily_mock_inputs(root=root, output_directory=Path("runtime/agent-research-discovery"),
        now=REPLAY_AT, max_hotspots=1, retrospective=retrospective)


def batch(root, found):
    return run_daily_mock_batch(root=root, plan=Path(found["batch_plan"]["path"]),
                               plan_sha256=found["batch_plan"]["sha256"])


def test_expired_retained_hotspots_do_not_block_other_workflows(tmp_path):
    copy_registered_public_inputs(tmp_path)
    found = discover_daily_mock_inputs(root=tmp_path,
        output_directory=Path("runtime/agent-research-discovery"),
        now=datetime.fromisoformat("2026-10-20T02:00:00+00:00"), max_hotspots=1)
    assert found["status"] == "PARTIAL"
    assert any(row["workflow"] == "hotspot" and row["status"] == "FAILED_INPUT"
               for row in found["items"])
    assert any(row["workflow"] in {"event", "financial"} and row["status"] in {"EXPORTED", "UNCHANGED"}
               for row in found["items"])
    assert found["approval_count"] == 0


def test_real_public_four_workflows_discover_register_http_and_unchanged(tmp_path, monkeypatch):
    import socket
    import threading
    import time
    import httpx
    import uvicorn
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider
    from value_investment_agent.application.research.agent_review import llm_pilot

    class ReplayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return REPLAY_AT.astimezone(tz) if tz is not None else REPLAY_AT.replace(tzinfo=None)

    monkeypatch.setattr(llm_pilot, "datetime", ReplayClock)

    def forbidden(*args, **kwargs):
        pytest.fail("Discovery and Mock workflows must not perform network provider calls")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("value_investment_agent.infrastructure.agent_runtime.provider.build_opener", forbidden)
    copy_registered_public_inputs(tmp_path)
    before_registry = (tmp_path / "config/current-agent-research.json").read_bytes()
    pin = confirmed_test_only_input(tmp_path)
    found = discover(tmp_path, pin)
    assert found["status"] == "READY", found
    assert {row["workflow"] for row in found["items"]} == {"hotspot", "financial", "event", "retrospective"}
    result = batch(tmp_path, found)
    assert result["status"] == "SUCCESS", result
    assert len(result["items"]) == 4
    assert (tmp_path / "config/current-agent-research.json").read_bytes() == before_registry
    now = datetime.now(timezone.utc)
    registration = register_daily_draft_results(root=tmp_path, batch_result=result, now=now)
    assert registration["status"] == "UPDATED", registration
    for item in result["items"]:
        view = read_web_agent_research(tmp_path, symbol=item["symbol"], workflow=item["workflow"], now=now)
        assert view["status"] == "VERIFIED", view
        assert view["approval_count"] == view["formal_fact_count"] == 0
        if item["workflow"] == "hotspot":
            assert view["data_scope"] == "PUBLIC_RESEARCH"
            context = json.loads((tmp_path / item["result"]["workflow_binding"]["context"]["path"]).read_text())
            assert "classification_effective_date" in context["records"][0]["excerpt"]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in
              (tmp_path / "runtime/agent-research-discovery").rglob("*") if p.is_file()}
    monkeypatch.setattr(MockLLMProvider, "complete", lambda *a: pytest.fail("Unchanged sources must skip provider calls"))
    repeated = discover(tmp_path, pin)
    stable = discover(tmp_path, pin)
    assert repeated["batch_plan"] == stable["batch_plan"] == found["batch_plan"]
    assert all(row["status"] == "UNCHANGED" for row in stable["items"])
    assert batch(tmp_path, found) == result
    changed = [str(p) for p, prior in before.items() if (p.read_bytes(), p.stat().st_mtime_ns) != prior]
    assert not changed, changed
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    secret = "TEST_ONLY-discovery-" + "x" * 48
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path, port=port, bootstrap_secret=secret),
        log_level="error", lifespan="off", ws="none"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                          timeout=30.0) as client:
            token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
            client.headers["x-local-session"] = token
            for item in result["items"]:
                response = client.get(f"/api/v1/agent-research/{item['symbol']}?workflow={item['workflow']}")
                assert response.status_code == 200
                assert response.json()["status"] == "VERIFIED"
                assert not response.json()["eligibility"]
            summary = client.get("/api/v1/agent-research-status").json()
            assert summary["status"] == "VERIFIED", summary
            assert {"hotspot", "event", "financial", "retrospective"} <= {
                row["workflow"] for row in summary["items"]}
            assert all(row["pending_human_review"] == 3 for row in summary["items"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
    registry = json.loads((tmp_path / "config/current-price-conditions.json").read_text(encoding="utf-8"))
    broken = tmp_path / registry["items"][0]["case_path"]
    broken.write_bytes(broken.read_bytes() + b" ")
    partial = discover(tmp_path, pin)
    assert partial["status"] == "PARTIAL"
    assert any(row["workflow"] == "hotspot" and row["status"] == "FAILED_INPUT" for row in partial["items"])
    remaining = json.loads((tmp_path / partial["batch_plan"]["path"]).read_text(encoding="utf-8"))
    assert {"event", "financial", "retrospective"} <= {row["workflow"] for row in remaining["jobs"]}


def test_discovery_isolates_missing_sources_and_rejects_real_private_input(tmp_path):
    pin = confirmed_test_only_input(tmp_path)
    result = discover(tmp_path, pin)
    assert result["status"] == "PARTIAL"
    assert batch(tmp_path, result)["items"][0]["status"] == "DRAFT_READY"
    rejected = discover(tmp_path, dict(path="runtime/private/account.json", sha256="0" * 64))
    assert rejected["status"] == "BLOCKED"
    assert any(row["workflow"] == "retrospective" and row["status"] == "FAILED_INPUT" for row in rejected["items"])


def test_discovery_cli_exports_without_registration(cli, tmp_path, monkeypatch, capsys):
    import sys
    pin = confirmed_test_only_input(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pilot", "--mode", "mock", "--discover-contexts",
        "--test-only-retrospective", pin["path"], "--test-only-retrospective-sha256", pin["sha256"]])
    assert cli.main() == 3
    result = json.loads(capsys.readouterr().out)
    assert result["batch_plan"] and not result["registered_or_published"]
    assert not (tmp_path / "config/current-agent-research.json").exists()


@pytest.mark.parametrize("case", ["unconfirmed", "real_account", "future", "missing_record"])
def test_retrospective_export_rejects_invalid_confirmation_scope_and_time(tmp_path, case):
    pin = confirmed_test_only_input(tmp_path)
    path = tmp_path / pin["path"]
    value = json.loads(path.read_text())
    if case == "unconfirmed":
        value["confirmed"] = False
    elif case == "real_account":
        value["account_scope"] = "REAL"
    elif case == "future":
        value["records"][0]["available_at"] = "2099-01-01T00:00:00+08:00"
    else:
        value["records"].pop()
    path.write_text(json.dumps(value), encoding="utf-8")
    pin["sha256"] = sha256_file(path)
    found = discover(tmp_path, pin)
    assert found["status"] == "BLOCKED" and found["batch_plan"] is None
    assert not (tmp_path / "config/current-agent-research.json").exists()


def test_export_boundary_and_work_budget_fail_before_writes(tmp_path):
    for directory, limit in ((Path("config"), 1), (Path("runtime/agent-research-discovery"), 11)):
        with pytest.raises(ValueError):
            discover_daily_mock_inputs(root=tmp_path, output_directory=directory,
                now=datetime.now(timezone.utc), max_hotspots=limit)
    assert not (tmp_path / "runtime").exists()
