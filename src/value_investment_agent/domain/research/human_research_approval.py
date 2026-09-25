"""Versioned human G3 approval for one exact valuation and dependency snapshot.

An approval never approves a ticker. It approves the tuple:

    valuation result hash
    + research case hash
    + facts artifact hash
    + assumption-set hash

Any dependency change supersedes the receipt instead of silently inheriting the
human decision. The contract deliberately has no execution semantics other than
``action = no_order``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Mapping

from .research_run_contract import (
    canonical_contract_payload,
    valuation_result_sha256,
)


HUMAN_APPROVAL_SCHEMA = "post-m1-human-research-approval-v1"
ACTION_NO_ORDER = "no_order"

DECISION_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
DECISION_REJECTED_NEEDS_REWORK = "REJECTED_NEEDS_REWORK"
DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE = (
    "APPROVED_CONDITIONAL_LOW_CONFIDENCE"
)
DECISION_APPROVED_RESEARCH_ONLY = "APPROVED_RESEARCH_ONLY"
DECISION_SUPERSEDED = "SUPERSEDED"

HUMAN_APPROVAL_DECISIONS = {
    DECISION_PENDING_HUMAN_REVIEW,
    DECISION_REJECTED_NEEDS_REWORK,
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_APPROVED_RESEARCH_ONLY,
    DECISION_SUPERSEDED,
}

APPROVED_DECISIONS = {
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_APPROVED_RESEARCH_ONLY,
}

PRIORITY_NORMAL = "NORMAL"
PRIORITY_HIGH = "HIGH"
PRIORITIES = {PRIORITY_NORMAL, PRIORITY_HIGH}

REVIEWER_HUMAN_RESEARCH_LEAD = "human_research_lead"

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Serialized timestamps must include timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Serialized decimals must be finite")
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (
            value != value or value in (float("inf"), float("-inf"))
        ):
            raise ValueError("Serialized floats must be finite")
        return value
    raise ValueError(f"Unsupported approval value: {type(value).__name__}")


def _require_hash(value: str | None, field: str) -> str:
    if value is None or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be SHA-256 hex")
    return value.lower()


def _require_refs(refs: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Approval evidence references require ids")
    return normalized


def artifact_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash an artifact payload with the same canonical codec as contracts."""
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("Artifact fingerprint requires a nonempty object")
    return hashlib.sha256(
        canonical_contract_payload(dict(payload)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class HumanResearchApprovalReceipt:
    """Immutable, append-only human review receipt for one valuation envelope."""

    approval_id: str
    symbol: str
    security_id: str
    profile_id: str

    valuation_artifact_id: str
    valuation_artifact_sha256: str
    valuation_model_id: str
    valuation_model_version: str

    research_case_id: str
    research_case_sha256: str
    assumption_set_id: str
    assumption_set_sha256: str
    facts_artifact_id: str
    facts_artifact_sha256: str

    reviewed_at: datetime
    review_as_of: date

    reviewer_type: str
    decision: str
    price_assessment_eligible: bool
    review_priority: str = PRIORITY_NORMAL

    conditions: tuple[str, ...] = ()
    remaining_blockers: tuple[str, ...] = ()
    required_followups: tuple[str, ...] = ()
    reopen_triggers: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()

    decision_version: str = "20260923.1"
    created_at: datetime | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        for field in (
            "approval_id",
            "symbol",
            "security_id",
            "profile_id",
            "valuation_artifact_id",
            "valuation_model_id",
            "valuation_model_version",
            "research_case_id",
            "assumption_set_id",
            "facts_artifact_id",
            "reviewer_type",
            "decision_version",
        ):
            if not getattr(self, field).strip():
                raise ValueError(f"Human approval {field} is required")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Human approval symbol must contain six digits")
        if self.reviewer_type != REVIEWER_HUMAN_RESEARCH_LEAD:
            raise ValueError("Only a human research lead can issue this receipt")
        if self.decision not in HUMAN_APPROVAL_DECISIONS:
            raise ValueError("Unknown human approval decision")
        if self.review_priority not in PRIORITIES:
            raise ValueError("Unknown human approval review priority")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Human research approval must remain no_order")
        for field in (
            "valuation_artifact_sha256",
            "research_case_sha256",
            "assumption_set_sha256",
            "facts_artifact_sha256",
        ):
            object.__setattr__(
                self,
                field,
                _require_hash(getattr(self, field), field),
            )
        if not isinstance(self.review_as_of, date) or isinstance(
            self.review_as_of, datetime
        ):
            raise ValueError("Approval review_as_of must be a date")
        for field in ("reviewed_at", "created_at"):
            value = getattr(self, field)
            if value is not None and (
                not isinstance(value, datetime) or value.utcoffset() is None
            ):
                raise ValueError(f"Approval {field} must include timezone")
        if self.reviewed_at.date() != self.review_as_of:
            raise ValueError("Approval review timestamp must match review_as_of")
        if self.created_at is not None and self.created_at < self.reviewed_at:
            raise ValueError("Approval creation cannot precede review")
        object.__setattr__(
            self,
            "conditions",
            tuple(str(item) for item in self.conditions),
        )
        object.__setattr__(
            self,
            "remaining_blockers",
            tuple(str(item) for item in self.remaining_blockers),
        )
        object.__setattr__(
            self,
            "required_followups",
            tuple(str(item) for item in self.required_followups),
        )
        object.__setattr__(
            self,
            "reopen_triggers",
            tuple(str(item) for item in self.reopen_triggers),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _require_refs(tuple(self.evidence_refs)),
        )
        if self.decision in {
            DECISION_REJECTED_NEEDS_REWORK,
            DECISION_PENDING_HUMAN_REVIEW,
            DECISION_SUPERSEDED,
        } and self.price_assessment_eligible:
            raise ValueError(
                "Rejected, pending and superseded approvals cannot enable price assessment"
            )
        if (
            self.decision == DECISION_REJECTED_NEEDS_REWORK
            and not self.remaining_blockers
        ):
            raise ValueError("A rejected approval must name its remaining blockers")
        if self.decision == DECISION_SUPERSEDED and not self.remaining_blockers:
            raise ValueError("A superseded approval must name the changed dependency")
        if (
            self.decision in APPROVED_DECISIONS
            and self.conditions
            and not self.required_followups
        ):
            raise ValueError("Conditional approval requires explicit followups")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": HUMAN_APPROVAL_SCHEMA,
            "approval_id": self.approval_id,
            "symbol": self.symbol,
            "security_id": self.security_id,
            "profile_id": self.profile_id,
            "valuation_artifact_id": self.valuation_artifact_id,
            "valuation_artifact_sha256": self.valuation_artifact_sha256,
            "valuation_model_id": self.valuation_model_id,
            "valuation_model_version": self.valuation_model_version,
            "research_case_id": self.research_case_id,
            "research_case_sha256": self.research_case_sha256,
            "assumption_set_id": self.assumption_set_id,
            "assumption_set_sha256": self.assumption_set_sha256,
            "facts_artifact_id": self.facts_artifact_id,
            "facts_artifact_sha256": self.facts_artifact_sha256,
            "reviewed_at": self.reviewed_at.isoformat(),
            "review_as_of": self.review_as_of.isoformat(),
            "reviewer_type": self.reviewer_type,
            "decision": self.decision,
            "price_assessment_eligible": self.price_assessment_eligible,
            "review_priority": self.review_priority,
            "conditions": list(self.conditions),
            "remaining_blockers": list(self.remaining_blockers),
            "required_followups": list(self.required_followups),
            "reopen_triggers": list(self.reopen_triggers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "decision_version": self.decision_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


@dataclass(frozen=True)
class HumanResearchApprovalDecision:
    """Resolved approval state against a live valuation and dependencies."""

    approval_id: str
    symbol: str
    status: str
    valuation_bound: bool
    dependencies_bound: bool
    price_assessment_eligible: bool
    blockers: tuple[str, ...]
    action: str = ACTION_NO_ORDER

    @property
    def approved(self) -> bool:
        return (
            self.status in APPROVED_DECISIONS
            and self.valuation_bound
            and self.dependencies_bound
            and self.action == ACTION_NO_ORDER
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "symbol": self.symbol,
            "status": self.status,
            "valuation_bound": self.valuation_bound,
            "dependencies_bound": self.dependencies_bound,
            "price_assessment_eligible": self.price_assessment_eligible,
            "blockers": list(self.blockers),
            "action": self.action,
        }


def _payload_hash(payload: Mapping[str, Any] | None) -> str | None:
    return artifact_fingerprint(payload) if payload else None


def resolve_human_research_approval(
    receipt: HumanResearchApprovalReceipt,
    valuation: Any,
    *,
    model_id: str,
    research_case_payload: Mapping[str, Any] | None = None,
    facts_payload: Mapping[str, Any] | None = None,
    assumptions_payload: Mapping[str, Any] | None = None,
) -> HumanResearchApprovalDecision:
    """Fail closed when any exact artifact or dependency fingerprint changes."""
    if not isinstance(receipt, HumanResearchApprovalReceipt):
        raise TypeError("Human approval resolution requires a typed receipt")
    if receipt.symbol != valuation.symbol:
        return HumanResearchApprovalDecision(
            receipt.approval_id,
            valuation.symbol,
            DECISION_SUPERSEDED,
            False,
            False,
            False,
            ("valuation_symbol_mismatch",),
        )

    valuation_bound = (
        receipt.valuation_model_id == model_id
        and receipt.valuation_model_version == valuation.model_version
        and receipt.valuation_artifact_sha256
        == valuation_result_sha256(valuation)
    )
    dependency_checks = {
        "research_case_sha256": (
            receipt.research_case_sha256,
            _payload_hash(research_case_payload),
        ),
        "facts_artifact_sha256": (
            receipt.facts_artifact_sha256,
            _payload_hash(facts_payload),
        ),
        "assumption_set_sha256": (
            receipt.assumption_set_sha256,
            _payload_hash(assumptions_payload),
        ),
    }
    dependency_blockers = tuple(
        f"{field}_changed"
        for field, (expected, actual) in dependency_checks.items()
        if actual is None or expected != actual
    )
    dependencies_bound = not dependency_blockers

    blockers = list(receipt.remaining_blockers)
    if not valuation_bound:
        blockers.append("valuation_artifact_changed")
    blockers.extend(dependency_blockers)
    status = receipt.decision
    if not valuation_bound or not dependencies_bound:
        status = DECISION_SUPERSEDED
    eligible = receipt.price_assessment_eligible and status in APPROVED_DECISIONS
    return HumanResearchApprovalDecision(
        approval_id=receipt.approval_id,
        symbol=receipt.symbol,
        status=status,
        valuation_bound=valuation_bound,
        dependencies_bound=dependencies_bound,
        price_assessment_eligible=eligible,
        blockers=tuple(dict.fromkeys(blockers)),
        action=ACTION_NO_ORDER,
    )


def human_research_approval_from_payload(
    payload: Mapping[str, Any],
) -> HumanResearchApprovalReceipt:
    if not isinstance(payload, Mapping):
        raise ValueError("Human approval payload must be an object")
    data = dict(payload)
    if data.get("schema_version") != HUMAN_APPROVAL_SCHEMA:
        raise ValueError("Unknown human approval schema")

    def date_value(field: str) -> date:
        raw = data.get(field)
        if not isinstance(raw, str):
            raise ValueError(f"{field} must be an ISO date")
        try:
            return date.fromisoformat(raw)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO date") from error

    def datetime_value(field: str) -> datetime | None:
        raw = data.get(field)
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ValueError(f"{field} must be an ISO timestamp")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            raise ValueError(f"{field} must include a timezone")
        return parsed

    return HumanResearchApprovalReceipt(
        approval_id=str(data["approval_id"]),
        symbol=str(data["symbol"]),
        security_id=str(data["security_id"]),
        profile_id=str(data["profile_id"]),
        valuation_artifact_id=str(data["valuation_artifact_id"]),
        valuation_artifact_sha256=str(data["valuation_artifact_sha256"]),
        valuation_model_id=str(data["valuation_model_id"]),
        valuation_model_version=str(data["valuation_model_version"]),
        research_case_id=str(data["research_case_id"]),
        research_case_sha256=str(data["research_case_sha256"]),
        assumption_set_id=str(data["assumption_set_id"]),
        assumption_set_sha256=str(data["assumption_set_sha256"]),
        facts_artifact_id=str(data["facts_artifact_id"]),
        facts_artifact_sha256=str(data["facts_artifact_sha256"]),
        reviewed_at=datetime_value("reviewed_at"),  # type: ignore[arg-type]
        review_as_of=date_value("review_as_of"),
        reviewer_type=str(data["reviewer_type"]),
        decision=str(data["decision"]),
        price_assessment_eligible=bool(data["price_assessment_eligible"]),
        review_priority=str(data.get("review_priority", PRIORITY_NORMAL)),
        conditions=tuple(str(item) for item in data.get("conditions") or ()),
        remaining_blockers=tuple(
            str(item) for item in data.get("remaining_blockers") or ()
        ),
        required_followups=tuple(
            str(item) for item in data.get("required_followups") or ()
        ),
        reopen_triggers=tuple(
            str(item) for item in data.get("reopen_triggers") or ()
        ),
        evidence_refs=tuple(
            dict(item) for item in data.get("evidence_refs") or ()
        ),
        decision_version=str(data.get("decision_version", "20260923.1")),
        created_at=datetime_value("created_at"),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def human_research_approval_to_payload(
    decision: HumanResearchApprovalDecision,
) -> dict[str, Any]:
    return decision.as_policy()
