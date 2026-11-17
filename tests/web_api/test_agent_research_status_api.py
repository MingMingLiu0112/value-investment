"""Authenticated metadata summary reuses real packet/source verification."""
from datetime import datetime, timezone
import json

from test_agent_research_api import registered_client, unlock
from test_agent_context_workflows import batch_result
from test_web_agent_research import daily_registry, sha, state, write
from value_investment_agent.application.research.agent_review.context_workflows import (
    CONTEXT_KINDS, run_daily_context_mock,
)
from value_investment_agent.application.research.agent_review.daily_registration import register_daily_draft_results
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.application.research.agent_review.web_research import (
    REGISTRY_PATH, REGISTRY_WORKFLOWS_SCHEMA,
)


ROUTE = "/api/v1/agent-research-status"
STATUS_FLAGS = dict(approval_unchanged=True, formal_eligibility_unchanged=True,
                    decision_changed=False)


def test_status_auth_metadata_and_failed_job_isolation(tmp_path, monkeypatch):
    _, _, now = daily_registry(tmp_path)
    path = tmp_path / REGISTRY_PATH
    registry = json.loads(path.read_text(encoding="utf-8"))
    event = registry["cases"]["600519"]["workflows"]["event"]
    # A missing legacy packet is isolated from the valid event workflow.
    registry["cases"]["600519"]["workflows"]["legacy"] = dict(
        packet=dict(path="runtime/absent.json", sha256="0" * 64),
        workbench=event["workbench"], scope=event["scope"])
    registry["cases"]["600000"] = dict(workflows={"event": event})
    write(path, registry)
    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    assert client.get(ROUTE).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://not-local.invalid"
    assert client.get(ROUTE).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    before = state(tmp_path)
    response = client.get(ROUTE)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    result = response.json()
    assert set(result) == {"action", "status", "items", "failures", "review_queue",
                           "review_queue_count", *STATUS_FLAGS}
    assert result["action"] == "no_order" and result["status"] == "PARTIAL"
    assert all(result[key] == value for key, value in STATUS_FLAGS.items())
    assert len(result["items"]) == 3 and len(result["failures"]) == 2
    view = next(row for row in result["items"] if row["workflow"] == "event" and row["symbol"] == "600519")
    assert set(view) == {"symbol", "workflow", "status", "mode", "research_cutoff", "packet_sha256",
                         "generated_at", "findings_count", "pending_human_review"}
    assert view["status"] == "VERIFIED" and view["mode"] == "MOCK"
    assert view["packet_sha256"] == event["packet"]["sha256"]
    assert view["findings_count"] == view["pending_human_review"] == 3
    assert isinstance(view["generated_at"], str) and isinstance(view["research_cutoff"], str)
    assert result["review_queue_count"] == len(result["review_queue"]) == 1
    queued = result["review_queue"][0]
    assert set(queued) == {"symbol", "name", "workflow", "status", "verification_status",
        "research_as_of", "available_at", "source_available_at", "source_scope",
        "packet_binding", "registration_binding", "review_reason", "review_reason_text",
        "next_action", "next_action_text", "pending_findings_count", "action",
        "approval_unchanged", "formal_eligibility_unchanged", "decision_changed"}
    assert queued["symbol"] == "600519" and queued["name"] == "Synthetic issuer"
    assert queued["workflow"] == "event" and queued["status"] == "PENDING_HUMAN_REVIEW"
    assert queued["verification_status"] == "VERIFIED"
    assert queued["research_as_of"] == view["research_cutoff"]
    assert queued["available_at"] == view["generated_at"]
    assert queued["source_available_at"] == "2026-10-07"
    assert queued["source_scope"] == dict(
        scope=event["scope"], data_scope=None, mode="MOCK",
        classification="TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE",
        test_only=True, formal_evidence=False, excerpt_origin=None)
    assert queued["packet_binding"] == event["packet"]
    assert queued["registration_binding"]["path"] == REGISTRY_PATH
    assert queued["review_reason"] == "VERIFIED_RESEARCH_FINDINGS_PENDING_HUMAN_REVIEW"
    assert queued["next_action"] == "OPEN_REGISTERED_DRAFT_FOR_HUMAN_REVIEW"
    assert queued["pending_findings_count"] == 3
    assert queued["action"] == "no_order"
    assert all(queued[key] == value for key, value in STATUS_FLAGS.items())
    missing = next(row for row in result["items"] if row["workflow"] == "legacy")
    assert missing["status"] == "UNAVAILABLE" and missing["packet_sha256"] is None
    assert missing["findings_count"] == missing["pending_human_review"] == 0
    # Exact packet/registration paths are required bindings; finding/source text is not exposed.
    assert "Synthetic official-source bytes" not in response.text
    assert '"claim"' not in response.text and '"evidence_refs"' not in response.text
    assert state(tmp_path) == before


def test_status_missing_registry_and_tampered_packet(tmp_path, monkeypatch):
    _, _, now = daily_registry(tmp_path)
    registry = json.loads((tmp_path / REGISTRY_PATH).read_text(encoding="utf-8"))
    event = registry["cases"]["600519"]["workflows"]["event"]
    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    unlock(client, secret)
    assert client.get(ROUTE).json()["status"] == "VERIFIED"
    packet = tmp_path / event["packet"]["path"]
    packet.write_bytes(packet.read_bytes() + b" ")
    result = client.get(ROUTE).json()
    assert result["status"] == "UNAVAILABLE" and result["failures"]
    assert result["items"][0]["generated_at"] is None
    assert result["review_queue"] == [] and result["review_queue_count"] == 0
    assert result["action"] == "no_order" and all(
        result[key] == value for key, value in STATUS_FLAGS.items())
    (tmp_path / REGISTRY_PATH).unlink()
    assert client.get(ROUTE).json() == dict(
        action="no_order", status="NOT_CONNECTED", items=[], failures=[],
        review_queue=[], review_queue_count=0, **STATUS_FLAGS)
    write(tmp_path / REGISTRY_PATH, dict(schema_version="web-agent-research-registry-v2", action="no_order",
        cases={f"{index:06d}": {"workflows": {"event": event}} for index in range(101)}))
    bounded = client.get(ROUTE).json()
    assert bounded["status"] == "UNAVAILABLE" and not bounded["items"]
    assert bounded["review_queue"] == [] and bounded["review_queue_count"] == 0
    assert bounded["failures"][0]["reason"] == "REGISTRY_VERIFICATION_FAILED"


def test_status_authenticated_empty_queue_keeps_no_admission(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    write(tmp_path / REGISTRY_PATH, dict(schema_version=REGISTRY_WORKFLOWS_SCHEMA,
                                        action="no_order", cases={}))
    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    assert client.get(ROUTE).status_code == 401
    unlock(client, secret)
    before = state(tmp_path)
    response = client.get(ROUTE)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == dict(
        action="no_order", status="NOT_CONNECTED", items=[], failures=[],
        review_queue=[], review_queue_count=0, **STATUS_FLAGS)
    assert state(tmp_path) == before


def test_status_queue_preserves_mock_and_hotspot_derived_scope_labels(tmp_path, monkeypatch):
    _, registry, _ = daily_registry(tmp_path)
    event = registry["cases"]["600519"]["workflows"]["event"]
    workbench = tmp_path / event["workbench"]["path"]
    original = tmp_path / "runtime/official.txt"
    text = original.read_text(encoding="utf-8")
    source = ExcerptRequest("filing-1", "runtime/official.txt", sha(original),
        "2026-10-07T12:00:00+08:00", text, text_start=0, text_end=len(text))
    context_path = tmp_path / "runtime/hotspot-context.json"
    context = dict(schema_version="agent-source-workflow-context-v1", action="no_order",
        symbol="600519", workflow="hotspot", scope="PUBLIC_RESEARCH", records=[
            dict(kind=kind, source_id=source.source_id, excerpt=source.excerpt,
                 available_at=source.available_at) for kind in sorted(CONTEXT_KINDS["hotspot"])])
    write(context_path, context)
    args = dict(root=tmp_path, workbench=workbench,
        workbench_sha256=event["workbench"]["sha256"], symbol="600519",
        output=tmp_path / "runtime/daily-agent/hotspot-packet.json",
        source_requests=(source,), workflow="hotspot", context_path=context_path,
        context_sha256=sha(context_path))
    hotspot = run_daily_context_mock(**args)
    now = datetime.now(timezone.utc)
    registration = register_daily_draft_results(
        root=tmp_path, batch_result=batch_result(hotspot, "hotspot"), now=now)
    assert registration["status"] == "UPDATED"

    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    unlock(client, secret)
    before = state(tmp_path)
    result = client.get(ROUTE).json()
    assert result["action"] == "no_order" and all(
        result[key] == value for key, value in STATUS_FLAGS.items())
    assert result["review_queue_count"] == len(result["review_queue"]) == 2
    by_workflow = {item["workflow"]: item for item in result["review_queue"]}
    event_scope = by_workflow["event"]["source_scope"]
    assert event_scope["test_only"] is True and event_scope["formal_evidence"] is False
    assert event_scope["classification"] == "TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE"
    assert event_scope["excerpt_origin"] is None
    hotspot_scope = by_workflow["hotspot"]["source_scope"]
    assert hotspot_scope["data_scope"] == "PUBLIC_RESEARCH"
    assert hotspot_scope["mode"] == "MOCK" and hotspot_scope["test_only"] is True
    assert hotspot_scope["formal_evidence"] is False
    assert hotspot_scope["excerpt_origin"] == "DERIVED_FROM_VERIFIED_PLAN"
    assert all(item["action"] == "no_order" for item in result["review_queue"])
    assert all(item["approval_unchanged"] is True for item in result["review_queue"])
    assert all(item["formal_eligibility_unchanged"] is True for item in result["review_queue"])
    assert state(tmp_path) == before
