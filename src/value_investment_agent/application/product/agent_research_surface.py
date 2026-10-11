"""Project only replay-verified, unadmitted research lines into product data."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..research.agent_review.snapshot import load_research_snapshot
from ..research.agent_review.source_context import (
    verify_packet_source_context, offline_context_input_sha256,
    verify_finding_source_context,
)
from ..research.agent_review.supervisor import OfflineCaseReplayModel, expected_offline_findings
from ..research.agent_review.llm_pilot import LIVE_SCOPE, MOCK_SCOPE, verify_llm_packet
from ...domain.agent_research.contracts import AgentRole
from .common import load_json_object, require_inside, sha256_file


def project_verified_agent_packet(payload: dict[str, Any], *, root: Path,
                                  path: Path, expected_sha256: str) -> None:
    root = root.resolve()
    source = require_inside(root / "runtime", path, "agent research packet")
    if sha256_file(source) != expected_sha256:
        raise ValueError("Agent research packet hash mismatch")
    packet = load_json_object(source, "agent research packet")
    scope = packet.get("scope")
    if (scope not in {"OFFLINE_REPLAY_NOT_NEW_LLM_RESEARCH", MOCK_SCOPE, LIVE_SCOPE}
            or packet.get("action") != "no_order"
            or packet.get("formal_fact_count") != 0
            or packet.get("approval_count") != 0
            or packet.get("decision_changed") is not False):
        raise ValueError("Agent research packet cannot upgrade investment state")
    if scope == "OFFLINE_REPLAY_NOT_NEW_LLM_RESEARCH":
        model = OfflineCaseReplayModel()
        if (packet.get("schema_version") not in {"agent-research-pilot-v1", "agent-research-pilot-source-v2"}
                or packet.get("model_id") != model.model_id
                or packet.get("prompt_version") != model.prompt_version):
            raise ValueError("Unknown offline research replay version")
    snapshot = load_research_snapshot(
        root=root, workbench=root / packet["workbench_path"],
        expected_sha256=packet["workbench_sha256"], symbol=packet["symbol"],
    )
    context = verify_packet_source_context(root=root, snapshot=snapshot, packet=packet)
    if (packet.get("research_input_fingerprint") != snapshot.input_fingerprint
            or packet.get("research_as_of") != snapshot.as_of.isoformat()
            or payload.get("as_of") != snapshot.as_of.isoformat()):
        raise ValueError("Agent research and product dates/dependencies differ")
    product_generated = datetime.fromisoformat(payload["generated_at"])
    packet_generated = datetime.fromisoformat(packet["generated_at"])
    if (product_generated.utcoffset() is None or packet_generated.utcoffset() is None
            or packet_generated > product_generated):
        raise ValueError("Agent research packet is newer than the product")
    findings = packet.get("findings")
    if not isinstance(findings, list) or not 3 <= len(findings) <= 6:
        raise ValueError("Agent pilot requires three bounded roles")
    if scope == "OFFLINE_REPLAY_NOT_NEW_LLM_RESEARCH":
        if [item.get("agent_role") for item in findings] != [role.value for role in AgentRole]:
            raise ValueError("Offline research roles are missing or reordered")
        if findings != expected_offline_findings(snapshot, packet_generated):
            raise ValueError("Offline findings differ from verified replay")
        if context is not None:
            verify_finding_source_context(packet, context, offline_context_input_sha256(snapshot, context))
    else:
        verify_llm_packet(packet, snapshot, root=root)
    views = []
    for item in findings:
        views.append({
            "role": item["agent_role"], "claim": item["claim"],
            "evidence_refs": item["supporting_evidence_refs"],
            "counter_evidence_refs": item["counter_evidence_refs"],
            "status": "PENDING_HUMAN_REVIEW",
            "scope": scope, "finding_type": item["finding_type"],
            "research_as_of": snapshot.as_of.isoformat(),
        })
        if context is not None:
            views[-1]["source_context"] = {
                **packet["finding_source_context"][len(views) - 1],
                "context_assurance": context["context_assurance"],
                "uncovered_evidence": context["uncovered_evidence"],
                "source_text_policy": context["source_text_policy"],
                "excerpt_locators": [
                    {key: excerpt[key] for key in ("source_id", "path", "sha256", "available_at",
                                                   "page", "text_start", "text_end")}
                    for excerpt in context["excerpts"]
                    if excerpt["source_id"] in set(item["supporting_evidence_refs"]
                                                  + item["counter_evidence_refs"])],
            }
    matches = [item for item in payload.get("companies", [])
               if item.get("symbol") == snapshot.symbol]
    if len(matches) != 1 or matches[0].get("agent_research"):
        raise ValueError("Agent research requires one unmodified product company")
    audit = payload.get("audit")
    if not isinstance(audit, dict) or not isinstance(audit.get("evidence"), list):
        raise ValueError("Agent research requires a product evidence audit")
    existing = {record["evidence_id"]: record for record in audit["evidence"]}
    for ref_id in sorted({ref for finding in findings for ref in (
            finding["supporting_evidence_refs"] + finding["counter_evidence_refs"])}):
        ref = snapshot.evidence_by_id()[ref_id]
        audit_record = {
            "evidence_id": ref_id,
            "title": str(ref.get("title") or ref_id),
            "artifact_type": "AGENT_RESEARCH_SOURCE",
            "path": ref["path"], "sha256": ref["sha256"],
            "available_at": datetime.fromisoformat(ref["available_at"]).astimezone(
                ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "action": "no_order",
        }
        url = ref.get("url") or ref.get("source_url")
        if url is not None:
            audit_record["source_url"] = url
        prior = existing.get(ref_id)
        if prior is not None:
            if any(prior.get(key) != audit_record[key] for key in ("path", "sha256", "available_at", "action")):
                raise ValueError("Agent source conflicts with product evidence audit")
        else:
            audit["evidence"].append(audit_record)
    matches[0]["agent_research"] = views
    if sha256_file(source) != expected_sha256:
        raise ValueError("Agent packet changed during projection")
