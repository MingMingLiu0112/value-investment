"""TEST_ONLY real existing Mock/replay contracts; no provider or verifier mocks."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from test_llm_agent_research import _inputs, _replies
from value_investment_agent.application.research.agent_review.llm_pilot import run_llm_research_pilot, MOCK_SCOPE
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.application.research.agent_review.supervisor import run_agent_research_pilot
from value_investment_agent.application.research.agent_review.web_research import (
    read_web_agent_research, REGISTRY_PATH, REGISTRY_SCHEMA, OFFLINE_SCOPE,
)
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def state(root):
    return {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def register(root, packet_path, workbench, scope):
    value = {"schema_version": REGISTRY_SCHEMA, "action": "no_order", "cases": {
        "600519": {"packet": {"path": packet_path.relative_to(root).as_posix(), "sha256": sha(packet_path)},
                   "workbench": {"path": workbench.relative_to(root).as_posix(), "sha256": sha(workbench)},
                   "scope": scope}}}
    write(root / REGISTRY_PATH, value)
    return value


def build(root, *, context=False, offline=False):
    workbench, digest, original = _inputs(root)
    packet_path = root / "runtime/agent/packet.json"
    kwargs = dict(root=root, symbol="600519", workbench=workbench,
                  workbench_sha256=digest, output=packet_path)
    if context:
        text = original.read_text(encoding="utf-8")
        kwargs["source_requests"] = (ExcerptRequest("filing-1", "runtime/official.txt", sha(original),
            "2026-10-07T12:00:00+08:00", text, text_start=0, text_end=len(text)),)
    if offline:
        packet = run_agent_research_pilot(**kwargs)
    else:
        packet = run_llm_research_pilot(**kwargs, provider=MockLLMProvider(_replies()), mode="mock")
    registry = register(root, packet_path, workbench, packet["scope"])
    now = datetime.fromisoformat(packet["generated_at"]) + timedelta(minutes=1)
    return packet, packet_path, workbench, original, registry, now


def read(root, now):
    return read_web_agent_research(root, symbol="600519", now=now)


@pytest.mark.parametrize("context,offline", [(False, False), (True, False), (False, True), (True, True)])
def test_existing_real_contract_projects_three_roles_without_writes(tmp_path, context, offline):
    packet, path, wb, original, registry, now = build(tmp_path, context=context, offline=offline)
    before = state(tmp_path)
    result = read(tmp_path, now)
    assert result["status"] == "VERIFIED", result
    assert result["mode"] == ("OFFLINE_REPLAY" if offline else "MOCK")
    assert result["scope"] == packet["scope"]
    assert {row["role"] for row in result["findings"]} == {"FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"}
    assert result["bindings"]["packet"] == registry["cases"]["600519"]["packet"]
    assert result["bindings"]["workbench"]["sha256"] == sha(wb)
    assert result["sources"][0]["sha256"] == sha(original)
    assert result["research_as_of"] == "2026-10-08"
    assert result["formal_fact_count"] == result["approval_count"] == 0
    assert result["decision_changed"] is result["eligibility"] is result["admitted"] is False
    assert result["action"] == "no_order"
    assert all(row["status"] == "PENDING_HUMAN_REVIEW" for row in result["findings"])
    assert all("semantic_review" in row for row in result["findings"])
    if context:
        assert result["findings"][0]["source_context"]["context_assurance"] == "EXACT_SOURCE_EXCERPTS_VERIFIED"
        assert result["findings"][0]["source_context"]["excerpt_locators"][0]["sha256"] == sha(original)
    result["findings"][0]["claim"] = "mutated return"
    assert read(tmp_path, now)["findings"][0]["claim"] != "mutated return"
    assert state(tmp_path) == before


def test_missing_registry_does_not_guess_latest_or_read_daily_private_data(tmp_path):
    now = datetime.now(timezone.utc)
    write(tmp_path / "runtime/newest-agent/packet.json", {"not": "registered"})
    write(tmp_path / "config/daily-trade-assistant-v1.json", {"cases": {"600519": {"mock_responses": "anything"}}})
    before = state(tmp_path)
    result = read(tmp_path, now)
    assert result["status"] == "NOT_CONNECTED" and not result["findings"]
    assert state(tmp_path) == before


def test_missing_symbol_has_safe_default(tmp_path):
    write(tmp_path / REGISTRY_PATH, {"schema_version": REGISTRY_SCHEMA, "action": "no_order", "cases": {}})
    assert read(tmp_path, datetime.now(timezone.utc))["reason"] == "SYMBOL_NOT_REGISTERED"


def daily_registry(root, workflow="event"):
    from test_daily_agent_research import setup, financial_setup
    from value_investment_agent.application.research.agent_review.daily_research import (
        run_daily_event_mock, run_daily_financial_mock,
    )
    from value_investment_agent.application.research.agent_review.web_research import REGISTRY_WORKFLOWS_SCHEMA
    args = (setup if workflow == "event" else financial_setup)(root)
    result = (run_daily_event_mock if workflow == "event" else run_daily_financial_mock)(**args)
    value = {"schema_version": REGISTRY_WORKFLOWS_SCHEMA, "action": "no_order", "cases": {
        "600519": {"workflows": {workflow: {"packet": result["packet"],
            "workbench": result["workflow_binding"]["workbench"],
            "scope": MOCK_SCOPE, "workflow_binding": result["workflow_binding"]}}}}}
    write(root / REGISTRY_PATH, value)
    packet = json.loads(args["output"].read_text(encoding="utf-8"))
    return args, value, datetime.fromisoformat(packet["generated_at"]) + timedelta(minutes=1)


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_daily_workflow_selection_reverifies_pins_and_preserves_missing_workflows(tmp_path, workflow):
    _, registry, now = daily_registry(tmp_path, workflow)
    before = state(tmp_path)
    result = read_web_agent_research(tmp_path, symbol="600519", now=now, workflow=workflow)
    assert result["status"] == "VERIFIED", result
    assert result["workflow"] == workflow and result["available_workflows"] == [workflow]
    assert len(result["findings"]) == 3 and result["approval_count"] == 0
    missing = read_web_agent_research(tmp_path, symbol="600519", now=now, workflow="legacy")
    assert missing["reason"] == "WORKFLOW_NOT_REGISTERED" and not missing["findings"]
    assert read(tmp_path, now) == result
    assert state(tmp_path) == before
    registry["cases"]["600519"]["workflows"][workflow]["workflow_binding"]["version"] = 99
    write(tmp_path / REGISTRY_PATH, registry)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_generic_packet_cannot_be_relabelled_daily_event(tmp_path):
    packet, _, _, _, registry, now = build(tmp_path)
    from value_investment_agent.application.research.agent_review.web_research import REGISTRY_WORKFLOWS_SCHEMA
    entry = registry["cases"]["600519"]
    entry["workflow_binding"] = {"workflow": "announcement_event", "version": 2,
        "workbench": entry["workbench"], "research_input_fingerprint": packet["research_input_fingerprint"]}
    registry["schema_version"] = REGISTRY_WORKFLOWS_SCHEMA
    registry["cases"]["600519"] = {"workflows": {"event": entry}}
    write(tmp_path / REGISTRY_PATH, registry)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_daily_financial_transcription_replacement_is_not_a_verified_draft(tmp_path):
    args, _, now = daily_registry(tmp_path, "financial")
    args["transcription"].write_bytes(b"changed")
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("target", ["packet", "workbench", "original"])
def test_changed_or_absent_registered_bytes_fail_closed(tmp_path, target):
    _, path, wb, original, _, now = build(tmp_path)
    file = {"packet": path, "workbench": wb, "original": original}[target]
    file.write_text("changed bytes", encoding="utf-8")
    before = state(tmp_path)
    result = read(tmp_path, now)
    assert result["status"] == "UNAVAILABLE" and result["findings"] == [] and result["sources"] == []
    assert state(tmp_path) == before
    file.unlink()
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("change", ["symbol", "scope", "workbench_path", "workbench_hash", "action",
    "approval", "decision", "claim", "future_generated", "naive_generated", "future_as_of", "context", "quality"])
def test_rehashed_packet_still_requires_real_verifier(tmp_path, change):
    packet, path, wb, _, registry, now = build(tmp_path, context=True)
    if change == "symbol":
        packet["symbol"] = "000333"
    elif change == "scope":
        packet["scope"] = "LIVE_LLM_RESEARCH_NOT_ADMITTED"
    elif change == "workbench_path":
        packet["workbench_path"] = "runtime/other-workbench.json"
    elif change == "workbench_hash":
        packet["workbench_sha256"] = "a" * 64
    elif change == "action":
        packet["action"] = "order"
    elif change == "approval":
        packet["approval_count"] = 1
    elif change == "decision":
        packet["decision_changed"] = True
    elif change == "claim":
        packet["findings"][0]["claim"] = "Forged economic conclusion"
    elif change == "future_generated":
        packet["generated_at"] = (now + timedelta(seconds=1)).isoformat()
    elif change == "naive_generated":
        packet["generated_at"] = now.replace(tzinfo=None).isoformat()
    elif change == "future_as_of":
        packet["research_as_of"] = (now + timedelta(days=1)).date().isoformat()
    elif change == "context":
        packet["source_context"]["excerpts"][0]["excerpt"] = "Forged source excerpt"
    else:
        packet["findings"][0]["confidence"] = "HIGH"
    write(path, packet)
    registry["cases"]["600519"]["packet"]["sha256"] = sha(path)
    write(tmp_path / REGISTRY_PATH, registry)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("change", ["unknown_schema", "extra", "bad_hash", "unknown_scope", "absolute", "traversal", "private", "unknown_entry"])
def test_registry_contract_strict_and_no_private_reads(tmp_path, change, monkeypatch):
    _, _, _, _, registry, now = build(tmp_path)
    entry = registry["cases"]["600519"]
    if change == "unknown_schema":
        registry["schema_version"] = "unknown"
    elif change == "extra":
        registry["user_approved"] = True
    elif change == "bad_hash":
        entry["packet"]["sha256"] = "invalid"
    elif change == "unknown_scope":
        entry["scope"] = "APPROVED"
    elif change == "absolute":
        entry["packet"]["path"] = str((tmp_path / "runtime/agent/packet.json").resolve())
    elif change == "traversal":
        entry["packet"]["path"] = "runtime/../runtime/agent/packet.json"
    elif change == "private":
        entry["packet"]["path"] = "runtime/private-portfolio/ledger.json"
    else:
        entry["approved"] = True
    write(tmp_path / REGISTRY_PATH, registry)
    original_open = Path.open
    def guarded(path, *args, **kwargs):
        assert "private-portfolio" not in str(path)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_changed_registered_workbench_cannot_substitute_packet_workbench(tmp_path):
    _, _, wb, _, registry, now = build(tmp_path)
    other = wb.with_name("other.json")
    other.write_bytes(wb.read_bytes())
    registry["cases"]["600519"]["workbench"]["path"] = "runtime/other.json"
    write(tmp_path / REGISTRY_PATH, registry)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_duplicate_registry_json_keys_rejected(tmp_path):
    file = tmp_path / REGISTRY_PATH
    file.parent.mkdir()
    file.write_text('{"schema_version":"a","schema_version":"b","action":"no_order","cases":{}}')
    assert read(tmp_path, datetime.now(timezone.utc))["status"] == "UNAVAILABLE"


def test_registry_race_during_projection_rejected(tmp_path, monkeypatch):
    import value_investment_agent.application.research.agent_review.web_research as module
    _, _, _, _, registry, now = build(tmp_path)
    original = module.project_verified_agent_packet
    def swap(*args, **kwargs):
        original(*args, **kwargs)
        registry["cases"] = {}
        write(tmp_path / REGISTRY_PATH, registry)
    monkeypatch.setattr(module, "project_verified_agent_packet", swap)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_file_budget_rejected_before_read(tmp_path, monkeypatch):
    _, path, _, _, _, now = build(tmp_path)
    with path.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    original_open = Path.open
    def guarded(file, *args, **kwargs):
        assert file != path, "Oversized packet must be rejected by stat"
        return original_open(file, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("symbol", ["../600519", "６００５１９", "600519 ", None])
def test_bad_symbol_raises_without_writes(tmp_path, symbol):
    with pytest.raises(ValueError):
        read_web_agent_research(tmp_path, symbol=symbol, now=datetime.now(timezone.utc))
    assert not list(tmp_path.iterdir())


def test_naive_clock_raises(tmp_path):
    with pytest.raises(ValueError):
        read(tmp_path, datetime(2026, 10, 18))


def test_missing_registered_packet_is_not_disconnected(tmp_path):
    _, path, _, _, _, now = build(tmp_path)
    path.unlink()
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"


def test_existing_windows_source_separators_preserved_without_rewriting(tmp_path):
    _, path, wb, _, registry, _ = build(tmp_path)
    value = json.loads(wb.read_text())
    value["source_verification"]["sources"][0]["path"] = "runtime\\official.txt"
    write(wb, value)
    # Rebuild through the actual pilot because workbench bytes bind its input.
    other = path.with_name("windows-packet.json")
    packet = run_llm_research_pilot(root=tmp_path, symbol="600519", workbench=wb,
        workbench_sha256=sha(wb), output=other, mode="mock", provider=MockLLMProvider(_replies()))
    register(tmp_path, other, wb, packet["scope"])
    before = state(tmp_path)
    result = read(tmp_path, datetime.fromisoformat(packet["generated_at"]) + timedelta(seconds=1))
    assert result["status"] == "VERIFIED"
    assert state(tmp_path) == before


def test_counterevidence_links_keep_existing_quality_checks(tmp_path):
    from value_investment_agent.application.decision.artifact_bundle import (
        ReadOnlyArtifactBundleRepository, export_artifact_bundle,
    )
    from value_investment_agent.research_artifacts import ResearchArtifactEnvelope, StoredResearchArtifact
    from value_investment_agent.research_artifact_codecs import ResearchCaseCodec
    wb, _, _ = _inputs(tmp_path)
    raw = json.loads(wb.read_text())
    stored = ReadOnlyArtifactBundleRepository(raw["artifact_bundle"]).load_by_id("case-1")
    case = ResearchCaseCodec().from_payload(stored.envelope.payload_object())
    counter = tmp_path / "runtime/counter.txt"
    counter.write_text("TEST_ONLY counterevidence original", encoding="utf-8")
    ref = {"id": "counter-1", "path": "runtime/counter.txt", "sha256": sha(counter),
           "available_at": "2026-10-07T12:00:00+08:00", "source_url": "https://www.cninfo.com.cn/test-only.pdf"}
    case = replace(case, evidence_refs=[*case.evidence_refs, ref])
    updated = StoredResearchArtifact(artifact_id=stored.artifact_id,
        envelope=ResearchArtifactEnvelope.build(identity=stored.envelope.identity,
            payload=ResearchCaseCodec().to_payload(case), run_id=stored.envelope.run_id),
        created_at=stored.created_at)
    raw["artifact_bundle"] = export_artifact_bundle([updated])
    raw["source_verification"]["sources"].append({"path": ref["path"], "sha256": ref["sha256"]})
    write(wb, raw)
    replies = {role: json.loads(text) for role, text in _replies().items()}
    replies["COUNTER_EVIDENCE"]["findings"][0]["counter_evidence_refs"] = ["counter-1"]
    path = tmp_path / "runtime/agent/packet.json"
    packet = run_llm_research_pilot(root=tmp_path, symbol="600519", workbench=wb,
        workbench_sha256=sha(wb), output=path, mode="mock",
        provider=MockLLMProvider({role: json.dumps(value) for role, value in replies.items()}))
    register(tmp_path, path, wb, packet["scope"])
    result = read(tmp_path, datetime.fromisoformat(packet["generated_at"]) + timedelta(seconds=1))
    assert result["status"] == "VERIFIED"
    row = next(row for row in result["findings"] if row["role"] == "COUNTER_EVIDENCE")
    assert row["counter_evidence_refs"] == ["counter-1"]
    source = next(source for source in result["sources"] if source["evidence_id"] == "counter-1")
    assert source["source_url"] == ref["source_url"] and source["sha256"] == sha(counter)


@pytest.mark.parametrize("path", [".", "runtime/../../private/ledger.json", "runtime/.env"])
def test_private_or_nonartifact_source_preflight_does_not_open_source(tmp_path, path, monkeypatch):
    _, _, wb, _, registry, now = build(tmp_path)
    value = json.loads(wb.read_text())
    value["source_verification"]["sources"].append({"path": path, "sha256": "a" * 64})
    write(wb, value)
    # A consistent packet/workbench binding still cannot authorize a private read.
    packet_path = tmp_path / registry["cases"]["600519"]["packet"]["path"]
    packet = json.loads(packet_path.read_text())
    packet["workbench_sha256"] = sha(wb)
    write(packet_path, packet)
    registry["cases"]["600519"]["workbench"]["sha256"] = sha(wb)
    registry["cases"]["600519"]["packet"]["sha256"] = sha(packet_path)
    write(tmp_path / REGISTRY_PATH, registry)
    original_open = Path.open
    def guarded(file, *args, **kwargs):
        assert "private" not in file.parts and file.name != ".env"
        return original_open(file, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert read(tmp_path, now)["status"] == "UNAVAILABLE"
