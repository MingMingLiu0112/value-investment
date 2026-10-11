"""Non-admitting review checklist derived from replay-verified findings.

No semantic verdict is inferred from hashes, source coverage or model wording.
This adapter records review work still needed; it cannot record approvals.
"""
from __future__ import annotations

from .snapshot import ResearchSnapshot


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
