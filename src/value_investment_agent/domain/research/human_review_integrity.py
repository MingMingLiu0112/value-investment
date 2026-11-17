"""Fail-closed import screening for human research approval receipts.

Historical M1 bundles contain records whose ids look like G3 human approvals but
were emitted by a one-off script with a frozen timestamp and no reviewer
identity. They remain immutable audit evidence; they must never satisfy a G3
gate. This module turns that rule into executable code.

Parsing a historical payload stays possible for audit. What is blocked is the
transition from "a payload exists" to "an approved research decision".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from .human_research_approval import (
    APPROVED_DECISIONS,
    HUMAN_APPROVAL_SCHEMA,
    REVIEWER_HUMAN_RESEARCH_LEAD,
)

INTEGRITY_SCHEMA = "human-review-import-integrity-v1"
ACTION_NO_ORDER = "no_order"

LEGACY_GENERATOR_ID_MARKER = "-g3-human-approval-20260923."
LEGACY_GENERATOR_REVIEWED_AT = "2026-09-23T05:30:00+00:00"

REASON_SCHEMA_UNRECOGNIZED = "unrecognized_approval_schema"
REASON_REVIEWER_IDENTITY_MISSING = "reviewer_identity_missing"
REASON_MACHINE_GENERATED_LEGACY = "machine_generated_legacy_approval"
REASON_FIXED_SCRIPT_TIMESTAMP = "fixed_script_review_timestamp"
REASON_IDENTICAL_TIMESTAMP_CLUSTER = "identical_script_timestamp_cluster"


class ApprovalImportRejected(ValueError):
    """Raised when a payload cannot be imported as a real human review."""

    def __init__(self, reasons: Iterable[str], *, source: str | None = None) -> None:
        self.reasons = tuple(dict.fromkeys(reasons))
        self.source = source
        label = f" ({source})" if source else ""
        super().__init__(
            "human approval import rejected" + label + ": " + ", ".join(self.reasons)
        )


@dataclass(frozen=True)
class ApprovalImportVerdict:
    """Deterministic verdict for one approval-shaped payload."""

    importable: bool
    reasons: tuple[str, ...]
    action: str = ACTION_NO_ORDER

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": INTEGRITY_SCHEMA,
            "action": self.action,
            "importable": self.importable,
            "reasons": list(self.reasons),
        }


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.utcoffset() is None:
        return None
    return parsed


def _same_instant(left: Any, right: str) -> bool:
    first, second = _instant(left), _instant(right)
    return first is not None and second is not None and first == second


def screen_human_approval_payload(
    payload: Mapping[str, Any],
) -> ApprovalImportVerdict:
    """Classify whether one payload may be consumed as a real G3 review.

    A payload is importable only when it is a recognizable approval whose
    human reviewer identity is explicit and that is not a known script output.
    """
    reasons: list[str] = []
    if not isinstance(payload, Mapping):
        return ApprovalImportVerdict(False, (REASON_SCHEMA_UNRECOGNIZED,))
    if payload.get("schema_version") != HUMAN_APPROVAL_SCHEMA:
        reasons.append(REASON_SCHEMA_UNRECOGNIZED)

    reviewer_type = str(payload.get("reviewer_type") or "")
    reviewer_id = str(payload.get("reviewer_id") or "").strip()
    if reviewer_type == REVIEWER_HUMAN_RESEARCH_LEAD and not reviewer_id:
        reasons.append(REASON_REVIEWER_IDENTITY_MISSING)

    approval_id = str(payload.get("approval_id") or "")
    if LEGACY_GENERATOR_ID_MARKER in approval_id:
        if _same_instant(payload.get("reviewed_at"), LEGACY_GENERATOR_REVIEWED_AT):
            reasons.append(REASON_MACHINE_GENERATED_LEGACY)
            reasons.append(REASON_FIXED_SCRIPT_TIMESTAMP)
        elif not reviewer_id:
            reasons.append(REASON_MACHINE_GENERATED_LEGACY)

    return ApprovalImportVerdict(
        importable=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def screen_approval_bundle(
    payloads: Iterable[Mapping[str, Any]],
) -> tuple[ApprovalImportVerdict, ...]:
    """Screen a bundle and flag suspicious identical-timestamp clusters.

    The legacy generator stamped every record with the same instant. A bundle
    where several identity-less approvals share one exact timestamp is not
    credible as independent human review even if ids differ.
    """
    items = list(payloads)
    verdicts = [screen_human_approval_payload(item) for item in items]
    clusters: dict[datetime, int] = {}
    instants: list[datetime | None] = []
    for payload in items:
        instant = _instant(payload.get("reviewed_at")) if isinstance(payload, Mapping) else None
        instants.append(instant)
        reviewer_id = (
            str(payload.get("reviewer_id") or "").strip()
            if isinstance(payload, Mapping)
            else ""
        )
        if instant is not None and not reviewer_id:
            clusters[instant] = clusters.get(instant, 0) + 1
    screened: list[ApprovalImportVerdict] = []
    for verdict, instant in zip(verdicts, instants):
        reasons = list(verdict.reasons)
        if instant is not None and clusters.get(instant, 0) > 1:
            reasons.append(REASON_IDENTICAL_TIMESTAMP_CLUSTER)
        screened.append(
            ApprovalImportVerdict(
                importable=not reasons,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(screened)


def require_importable_approval(
    payload: Mapping[str, Any], *, source: str | None = None
) -> ApprovalImportVerdict:
    """Raise unless the payload may be consumed as a real G3 review."""
    verdict = screen_human_approval_payload(payload)
    if not verdict.importable:
        raise ApprovalImportRejected(verdict.reasons, source=source)
    return verdict


def gate_demotes_approved(verdict: ApprovalImportVerdict) -> bool:
    """True when a non-importable payload must not remain 'approved'."""
    return not verdict.importable and any(
        reason
        in {
            REASON_REVIEWER_IDENTITY_MISSING,
            REASON_MACHINE_GENERATED_LEGACY,
            REASON_FIXED_SCRIPT_TIMESTAMP,
            REASON_IDENTICAL_TIMESTAMP_CLUSTER,
        }
        for reason in verdict.reasons
    )


def is_approved_decision(payload: Mapping[str, Any]) -> bool:
    return payload.get("decision") in APPROVED_DECISIONS