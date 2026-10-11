from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from test_llm_agent_research import _inputs
from value_investment_agent.application.product import agent_research_surface
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review import llm_pilot
from value_investment_agent.application.research.agent_review.semantic_review import semantic_review_checklist
from value_investment_agent.application.research.agent_review.snapshot import load_research_snapshot
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.domain.agent_research.contracts import AgentRole
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider


@pytest.fixture
def mock_case(tmp_path):
    workbench, digest, original = _inputs(tmp_path)
    snapshot = load_research_snapshot(root=tmp_path, workbench=workbench,
                                     expected_sha256=digest, symbol="600519")
    fixture = Path(__file__).parent / "fixtures/agent_research_mock_600519.json"
    replies = json.loads(fixture.read_text(encoding="utf-8"))
    ids = sorted({ref for reply in replies.values() for item in reply["findings"]
                  for ref in item["supporting_evidence_refs"]})
    snapshot = replace(snapshot, evidence=tuple(
        {**snapshot.evidence[0], "id": ref} for ref in ids), counter_evidence=({
            "text": "Parent distributions and subsidiary cash have different entity scopes; reconcile before relying on the thesis.",
            "evidence_refs": ids,
        },))
    return workbench, digest, original, snapshot, replies


def findings(snapshot, replies):
    return [item for role in AgentRole for item in llm_pilot.validate_role_response(
        json.dumps(replies[role.value]), role=role, snapshot=snapshot,
        model_id="mock", created_at=datetime.now(timezone.utc))]


def test_actual_mock_fixture_keeps_entity_countercase_pending(mock_case):
    _, _, _, snapshot, replies = mock_case
    for finding in findings(snapshot, replies):
        review = semantic_review_checklist(finding, snapshot, None)
        assert review["status"] == "PENDING_SEMANTIC_REVIEW"
        assert review["original_match"]["status"] == "PENDING"
        for key in ("factual_verification", "inference_reasonableness", "counterevidence",
                    "independent_review", "human_confirmation"):
            assert review[key]["status"] == "PENDING"
            assert review[key]["reason"]
        assert "entity scopes" in review["counterevidence"]["recorded_countercase"][0]["text"]
        assert review["counterevidence"]["cited_evidence_refs"] == []
        assert review["approval_count"] == review["formal_fact_count"] == 0
        assert review["decision_changed"] is False and review["action"] == "no_order"


def test_source_word_overlap_cannot_verify_opposing_claims(mock_case):
    _, _, original, snapshot, replies = mock_case
    finding = findings(snapshot, replies)[0]
    context = {"excerpts": [{"source_id": ref["id"],
                              "excerpt": original.read_text(encoding="utf-8")}
                             for ref in snapshot.evidence]}
    for claim in ("Synthetic official-source bytes prove sustainable dividends.",
                  "Synthetic official-source bytes disprove sustainable dividends."):
        review = semantic_review_checklist({**finding, "claim": claim}, snapshot, context)
        assert review["original_match"]["status"] == "MATCHED_EXCERPTS_ONLY"
        assert review["factual_verification"]["status"] == "PENDING"
        assert review["inference_reasonableness"]["status"] == "PENDING"
        assert review["semantic_assurance"] == "CLAIM_SEMANTICS_NOT_VERIFIED"


def test_review_is_consumed_by_existing_verified_agent_surface(mock_case, tmp_path, monkeypatch):
    workbench, digest, original, snapshot, replies = mock_case
    monkeypatch.setattr(llm_pilot, "load_research_snapshot", lambda **_: snapshot)
    monkeypatch.setattr(agent_research_surface, "load_research_snapshot", lambda **_: snapshot)
    text = original.read_text(encoding="utf-8")
    requests = tuple(ExcerptRequest(ref["id"], ref["path"], ref["sha256"],
                                   ref["available_at"], text, text_start=0, text_end=len(text))
                     for ref in snapshot.evidence)
    output = tmp_path / "runtime/mock-semantic.json"
    packet = llm_pilot.run_llm_research_pilot(
        root=tmp_path, workbench=workbench, workbench_sha256=digest, symbol="600519",
        output=output, provider=MockLLMProvider({key: json.dumps(value) for key, value
                                               in replies.items()}),
        mode="mock", source_requests=requests)
    payload = {"as_of": snapshot.as_of.isoformat(),
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "audit": {"evidence": []},
               "companies": [{"symbol": "600519", "decision_status": "WAIT"}]}
    agent_research_surface.project_verified_agent_packet(
        payload, root=tmp_path, path=output, expected_sha256=sha256_file(output))
    company = payload["companies"][0]
    assert company["decision_status"] == "WAIT"
    for view, finding in zip(company["agent_research"], packet["findings"], strict=True):
        assert view["claim"] == finding["claim"]
        assert view["status"] == "PENDING_HUMAN_REVIEW"
        assert view["semantic_review"]["finding_id"] == finding["finding_id"]
        assert view["semantic_review"]["original_match"]["status"] == "MATCHED_EXCERPTS_ONLY"
        assert view["semantic_review"]["human_confirmation"]["status"] == "PENDING"
    assert packet["approval_count"] == 0 and packet["decision_changed"] is False
    original.write_text("Changed official source", encoding="utf-8")
    fresh = deepcopy(payload)
    fresh["companies"][0].pop("agent_research")
    with pytest.raises(ValueError, match="hash mismatch"):
        agent_research_surface.project_verified_agent_packet(
            fresh, root=tmp_path, path=output, expected_sha256=sha256_file(output))
    assert "agent_research" not in fresh["companies"][0]
    assert fresh["companies"][0]["decision_status"] == "WAIT"


def test_actual_mock_future_evidence_is_rejected_with_reason(mock_case):
    _, _, _, snapshot, replies = mock_case
    future = replace(snapshot, evidence=tuple(
        {**ref, "available_at": "2026-10-09T12:00:00+08:00"} for ref in snapshot.evidence))
    with pytest.raises(ValueError, match="future evidence"):
        findings(future, replies)


def test_actual_mock_source_identity_mismatch_is_rejected(mock_case):
    _, _, _, snapshot, replies = mock_case
    changed = deepcopy(replies)
    changed["FUNDAMENTAL"]["findings"][0]["supporting_evidence_refs"] = ["other-entity-filing"]
    with pytest.raises(ValueError, match="invalid or out-of-scope evidence"):
        findings(snapshot, changed)


def test_partial_original_coverage_and_cited_counterevidence_stay_distinct(mock_case):
    _, _, _, snapshot, replies = mock_case
    changed = deepcopy(replies)
    row = changed["FUNDAMENTAL"]["findings"][0]
    row["counter_evidence_refs"] = [row["supporting_evidence_refs"].pop()]
    finding = findings(snapshot, changed)[0]
    context = {"excerpts": [{"source_id": row["supporting_evidence_refs"][0]}]}
    review = semantic_review_checklist(finding, snapshot, context)
    assert review["original_match"]["status"] == "PENDING"
    assert review["original_match"]["uncovered_evidence_refs"] == row["counter_evidence_refs"]
    assert review["counterevidence"]["cited_evidence_refs"] == row["counter_evidence_refs"]
    assert review["counterevidence"]["status"] == "PENDING"
    assert "resolve conflicts" in review["counterevidence"]["reason"]
