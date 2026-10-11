"""Non-admitting review checklist derived from replay-verified findings.

No semantic verdict is inferred from hashes, source coverage or model wording.
This adapter records review work still needed; it cannot record approvals.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from ...product.common import load_json_object, require_inside, sha256_file
from .snapshot import ResearchSnapshot


INDEPENDENT_SCOPE = "INDEPENDENT_SEMANTIC_REVIEW_NOT_ADMITTED"
VERDICTS = {
    "facts": {"NO_NEW_FACT_CLAIM", "MATCHES_EXCERPTS", "CONTRADICTED", "INSUFFICIENT_SUPPORT"},
    "inference": {"REASONABLE_WITH_LIMITS", "REASONABLE_RESEARCH_QUESTION",
                  "INSUFFICIENT_EXCERPT_SUPPORT", "UNREASONABLE"},
    "counterevidence": {"LIMITED_COUNTEREVIDENCE", "COUNTEREVIDENCE_ADDRESSED",
                        "MATERIAL_COUNTEREVIDENCE_OMITTED"},
}


def semantic_binding_sha256(value: dict) -> str:
    """Canonical UTF-8 object digest, including every finding/excerpt field."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def load_independent_semantic_review(*, root: Path, path: Path, expected_sha256: str,
                                     packet_path: Path, packet_sha256: str,
                                     packet: dict, context: dict | None) -> dict[str, dict]:
    """Consume bounded external judgments only after packet/original revalidation.

    Hashes bind the reviewer's judgments to evidence; they do not prove those
    judgments or confer human approval. Unknown fields are rejected, not merged.
    """
    source = require_inside(root / "config/research-reviews", path, "independent review")
    try:
        actual_sha256 = sha256_file(source)
    except OSError as exc:
        raise ValueError("Independent review file is unavailable") from exc
    if actual_sha256 != expected_sha256:
        raise ValueError("Independent review hash mismatch")
    review = load_json_object(source, "independent semantic review")
    keys = {"schema_version", "scope", "reviewer", "reviewed_at", "symbol",
            "research_as_of", "packet_path", "packet_sha256", "context_sha256",
            "findings", "action", "formal_fact_count", "approval_count", "decision_changed"}
    if set(review) != keys or (
            review["schema_version"] != "agent-independent-semantic-review-v1"
            or review["scope"] != INDEPENDENT_SCOPE or review["action"] != "no_order"
            or type(review["formal_fact_count"]) is not int or review["formal_fact_count"] != 0
            or type(review["approval_count"]) is not int or review["approval_count"] != 0
            or review["decision_changed"] is not False):
        raise ValueError("Independent review cannot escalate scope")
    if not isinstance(review["reviewer"], str) or not review["reviewer"].strip():
        raise ValueError("Independent review requires reviewer identity")
    try:
        reviewed = datetime.fromisoformat(review["reviewed_at"])
        generated = datetime.fromisoformat(packet["generated_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid independent review date") from exc
    if reviewed.utcoffset() is None or generated.utcoffset() is None or reviewed < generated:
        raise ValueError("Independent review predates packet or lacks timezone")
    if (review["symbol"] != packet["symbol"]
            or review["research_as_of"] != packet["research_as_of"]
            or review["packet_path"] != packet_path.resolve().relative_to(root.resolve()).as_posix()
            or review["packet_sha256"] != packet_sha256
            or sha256_file(packet_path) != packet_sha256
            or context is None or review["context_sha256"] != context["context_sha256"]):
        raise ValueError("Independent review packet/context identity mismatch")
    rows = review["findings"]
    if not isinstance(rows, list) or len(rows) != len(packet["findings"]):
        raise ValueError("Independent review must cover every finding exactly once")
    result = {}
    row_keys = {"finding_id", "agent_role", "finding_sha256", "finding_context_sha256",
                "excerpt_bindings", "facts", "inference", "counterevidence"}
    sidecars = {item["finding_id"]: item for item in packet["finding_source_context"]}
    findings = {item["finding_id"]: item for item in packet["findings"]}
    if len(findings) != len(rows) or len(sidecars) != len(rows):
        raise ValueError("Duplicate packet finding identity")
    for row in rows:
        if not isinstance(row, dict) or set(row) != row_keys:
            raise ValueError("Independent finding review has invalid scope/schema")
        finding_id = row["finding_id"]
        if not isinstance(finding_id, str) or finding_id not in findings or finding_id in result:
            raise ValueError("Unknown or duplicate independent finding identity")
        finding = findings[finding_id]
        cited = set(finding["supporting_evidence_refs"] + finding["counter_evidence_refs"])
        excerpts = [item for item in context["excerpts"] if item["source_id"] in cited]
        bindings = [{"source_id": item["source_id"], "path": item["path"],
                     "source_sha256": item["sha256"],
                     "excerpt_sha256": semantic_binding_sha256(item)} for item in excerpts]
        if (row["agent_role"] != finding["agent_role"]
                or row["finding_sha256"] != semantic_binding_sha256(finding)
                or row["finding_context_sha256"] != sidecars[finding_id]["finding_context_sha256"]
                or {item["source_id"] for item in excerpts} != cited
                or row["excerpt_bindings"] != bindings):
            raise ValueError("Independent finding/source/excerpt binding mismatch")
        axes = {}
        for axis, allowed in VERDICTS.items():
            item = row[axis]
            if (not isinstance(item, dict) or set(item) != {"verdict", "rationale"}
                    or not isinstance(item["verdict"], str) or item["verdict"] not in allowed
                    or not isinstance(item["rationale"], str)
                    or not 1 <= len(item["rationale"].strip()) <= 4000):
                raise ValueError("Unknown independent verdict or invalid rationale")
            axes[axis] = dict(item)
        result[finding_id] = {
            "status": "COMPLETED_NON_ADMITTING", "scope": INDEPENDENT_SCOPE,
            "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
            "review_path": source.relative_to(root.resolve()).as_posix(),
            "review_sha256": expected_sha256,
            "finding_sha256": row["finding_sha256"],
            "finding_context_sha256": row["finding_context_sha256"],
            "excerpt_bindings": bindings, **axes,
            "action": "no_order", "formal_fact_count": 0, "approval_count": 0,
            "decision_changed": False,
        }
    if sha256_file(source) != expected_sha256 or sha256_file(packet_path) != packet_sha256:
        raise ValueError("Independent review or packet changed during validation")
    return result


def semantic_review_checklist(finding: dict, snapshot: ResearchSnapshot,
                              context: dict | None) -> dict:
    """Call only after the finding and optional original context are revalidated."""
    cited = set(finding["supporting_evidence_refs"] + finding["counter_evidence_refs"])
    covered = set() if context is None else {
        item["source_id"] for item in context["excerpts"]
    }
    loaded, missing = sorted(cited & covered), sorted(cited - covered)
    counter_refs = list(finding["counter_evidence_refs"])
    recorded_countercase = [
        {"text": item["text"], "evidence_refs": list(item.get("evidence_refs") or ())}
        for item in snapshot.counter_evidence if item.get("text")
    ]
    return {
        "schema_version": "agent-semantic-review-checklist-v1",
        "finding_id": finding["finding_id"],
        "status": "PENDING_SEMANTIC_REVIEW",
        "semantic_assurance": "CLAIM_SEMANTICS_NOT_VERIFIED",
        "original_match": {
            "status": "MATCHED_EXCERPTS_ONLY" if loaded and not missing else "PENDING",
            "covered_evidence_refs": loaded,
            "uncovered_evidence_refs": missing,
            "reason": "Located excerpts match originals; claim support still needs review."
                      if loaded and not missing else
                      "Cited originals lack full excerpt coverage; claim support is unverified.",
        },
        "factual_verification": {
            "status": "PENDING",
            "reason": "Source integrity does not verify financial figures or their meaning.",
            "checks": [
                "Compare each claimed fact with the cited original and reconcile figures.",
                "Check units, currency, periods and accounting-basis comparability.",
                "Check listed-company, parent, subsidiary and minority-interest scope.",
                "Confirm fact availability at the research cutoff; future evidence is rejected.",
            ],
        },
        "inference_reasonableness": {
            "status": "PENDING",
            "reason": "Economic reasoning has not been independently evaluated.",
            "checks": [
                "Test earnings persistence and optimistic assumptions against adverse cases.",
                "Reconcile profit with cash conversion and sustainable distributions.",
                "Check material operating risks and omitted facts against the thesis.",
                "Resolve entity-scope conflicts before relying on any cash-flow inference.",
            ],
        },
        "counterevidence": {
            "status": "PENDING",
            "reason": "Cited counterevidence needs assessment; references do not resolve conflicts."
                      if counter_refs else
                      "Finding cites no counterevidence; absence of citations is not absence of risk.",
            "cited_evidence_refs": counter_refs,
            "recorded_countercase": recorded_countercase[:3],
            "recorded_countercase_count": len(recorded_countercase),
        },
        "independent_review": {
            "status": "PENDING",
            "reason": "Three model roles are not evidence of completed independent review.",
        },
        "human_confirmation": {
            "status": "PENDING",
            "reason": "No human confirmation is recorded by this checklist.",
        },
        "proposed_follow_up": finding["proposed_follow_up"],
        "action": "no_order", "formal_fact_count": 0,
        "approval_count": 0, "decision_changed": False,
    }
