"""Bounded, read-only three-role research orchestration."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from ....domain.agent_research.contracts import AgentFinding, AgentRole, FindingStatus
from ...product.common import require_inside, sha256_file, write_new_json
from .snapshot import ResearchSnapshot, load_research_snapshot
from .source_context import (
    ExcerptRequest, load_source_context, offline_context_input_sha256,
    finding_source_context,
)


@dataclass(frozen=True)
class AgentProposal:
    claim: str
    finding_type: str
    evidence_refs: tuple[str, ...]
    affected_dimension: str
    follow_up: str


class ResearchModel(Protocol):
    model_id: str
    prompt_version: str

    def propose(self, role: AgentRole, snapshot: ResearchSnapshot) -> AgentProposal | None: ...


class OfflineCaseReplayModel:
    """Deterministic pilot only: re-exposes existing case statements, not new AI research."""

    model_id = "OFFLINE_CASE_REPLAY_ONLY"
    prompt_version = "agent-research-pilot-v1"

    def propose(self, role: AgentRole, snapshot: ResearchSnapshot) -> AgentProposal | None:
        choices = {
            AgentRole.FUNDAMENTAL: (snapshot.positives, "business_quality", "INTERPRETATION"),
            AgentRole.COUNTER_EVIDENCE: (snapshot.counter_evidence, "counter_evidence", "INTERPRETATION"),
            AgentRole.EVENT: (snapshot.thesis_breakers, "event_monitoring", "RESEARCH_QUESTION"),
        }
        statements, dimension, finding_type = choices[role]
        references = snapshot.evidence_by_id()
        for item in statements:
            refs = tuple(item.get("evidence_refs") or ())
            if (item.get("text") and refs and all(
                    references[ref].get("available_at") is not None for ref in refs)):
                return AgentProposal(
                    claim=str(item["text"]), finding_type=finding_type,
                    evidence_refs=refs,
                    affected_dimension=dimension,
                    follow_up="核对原件与当前研究范围后由研究负责人复核。",
                )
        return None


def _finding(role: AgentRole, proposal: AgentProposal, snapshot: ResearchSnapshot,
             model: ResearchModel, now: datetime) -> AgentFinding:
    references = snapshot.evidence_by_id()
    if not proposal.evidence_refs or not set(proposal.evidence_refs).issubset(references):
        raise ValueError("Agent proposal cites unknown evidence")
    if any(references[ref].get("available_at") is None for ref in proposal.evidence_refs):
        raise ValueError("Agent proposal cites evidence without a PIT availability bound")
    if len(proposal.evidence_refs) > 8 or len(proposal.claim) > 1200:
        raise ValueError("Agent proposal exceeds bounded scope")
    latest = max(datetime.fromisoformat(references[ref]["available_at"])
                 for ref in proposal.evidence_refs)
    if latest.astimezone(ZoneInfo("Asia/Shanghai")).date() > snapshot.as_of:
        raise ValueError("Agent proposal cites future evidence")
    digest = hashlib.sha256((snapshot.input_fingerprint + role.value
                             + proposal.claim + "|".join(proposal.evidence_refs)).encode("utf-8")).hexdigest()
    return AgentFinding(
        finding_id=f"agent-{digest[:24]}", symbol=snapshot.symbol,
        research_as_of=snapshot.as_of, agent_role=role,
        claim=proposal.claim, finding_type=proposal.finding_type,
        supporting_evidence_refs=proposal.evidence_refs, counter_evidence_refs=(),
        source_available_at=latest, research_input_fingerprint=snapshot.input_fingerprint,
        model_id=model.model_id, prompt_version=model.prompt_version,
        confidence="LOW", verification_status=FindingStatus.PENDING_HUMAN_REVIEW,
        affected_research_dimensions=(proposal.affected_dimension,),
        proposed_follow_up=proposal.follow_up, created_at=now,
    )


def expected_offline_findings(snapshot: ResearchSnapshot, generated_at: datetime) -> list[dict[str, object]]:
    model = OfflineCaseReplayModel()
    findings = []
    for role in AgentRole:
        proposal = model.propose(role, snapshot)
        if proposal is not None:
            findings.append(_finding(role, proposal, snapshot, model, generated_at).as_dict())
    return findings


def run_agent_research_pilot(*, root: Path, workbench: Path, workbench_sha256: str,
                             symbol: str, output: Path,
                             model: ResearchModel | None = None,
                             source_requests: tuple[ExcerptRequest, ...] | None = None) -> dict[str, object]:
    """Reverify official bytes, run bounded roles, and save a non-admitted packet."""
    root = root.resolve()
    target = require_inside(root / "runtime", output, "agent pilot output")
    snapshot = load_research_snapshot(
        root=root, workbench=workbench, expected_sha256=workbench_sha256, symbol=symbol,
    )
    runner = model or OfflineCaseReplayModel()
    context = None if source_requests is None else load_source_context(root=root,
        snapshot=snapshot, requests=source_requests, enabled=True).as_dict()
    if context is not None:
        snapshot = replace(snapshot, source_context=context)
    now = datetime.now(timezone.utc)
    findings = []
    for role in AgentRole:
        proposal = runner.propose(role, snapshot)
        if proposal is not None:
            findings.append(_finding(role, proposal, snapshot, runner, now).as_dict())
    if len(findings) > len(AgentRole):
        raise ValueError("Agent pilot exceeded role budget")
    packet: dict[str, object] = {
        "schema_version": "agent-research-pilot-v1", "scope": "OFFLINE_REPLAY_NOT_NEW_LLM_RESEARCH",
        "symbol": symbol, "research_as_of": snapshot.as_of.isoformat(),
        "generated_at": now.isoformat(), "workbench_path": str(workbench.resolve().relative_to(root)).replace("\\", "/"),
        "workbench_sha256": snapshot.workbench_sha256,
        "research_input_fingerprint": snapshot.input_fingerprint,
        "model_id": runner.model_id, "prompt_version": runner.prompt_version,
        "findings": findings, "formal_fact_count": 0, "approval_count": 0,
        "decision_changed": False, "action": "no_order",
    }
    if context is not None:
        packet["schema_version"] = "agent-research-pilot-source-v2"
        packet["source_context"] = context
        packet["context_input_sha256"] = offline_context_input_sha256(snapshot, context)
        packet["finding_source_context"] = finding_source_context(
            findings, context, packet["context_input_sha256"])
    if target.exists():
        current = json.loads(target.read_text(encoding="utf-8"))
        try:
            prior_time = datetime.fromisoformat(current["generated_at"])
            if prior_time.utcoffset() is None:
                raise ValueError("Naive timestamp")
            expected = dict(packet, generated_at=prior_time.isoformat())
            if isinstance(runner, OfflineCaseReplayModel):
                expected["findings"] = expected_offline_findings(snapshot, prior_time)
                if context is not None:
                    expected["finding_source_context"] = finding_source_context(
                        expected["findings"], context, packet["context_input_sha256"])
            else:
                raise ValueError("Custom model output cannot be revalidated")
            if current != expected:
                raise ValueError("Existing output differs from verified replay")
        except (KeyError, TypeError, ValueError) as exc:
            raise FileExistsError("Existing agent pilot output is not an identical verified replay") from exc
        return current
    write_new_json(target, packet)
    return packet
