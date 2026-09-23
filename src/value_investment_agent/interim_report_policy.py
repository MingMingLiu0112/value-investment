"""Policy for unaudited statutory interim reports.

An unaudited half-year filing is a legal reporting event. By default it lowers
model confidence but does not by itself block research or make a valuation
invalid. Known conflicts, corrections, scope problems, audit qualifications or
material accounting uncertainty can escalate it back to a hard blocker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
from typing import Any


INTERIM_REPORT_POLICY_SCHEMA = "post-m1-interim-report-policy-v1"
CLASSIFICATION_CONFIDENCE_MODIFIER = "CONFIDENCE_MODIFIER"
CLASSIFICATION_HARD_BLOCKER = "HARD_BLOCKER"
CLASSIFICATIONS = {
    CLASSIFICATION_CONFIDENCE_MODIFIER,
    CLASSIFICATION_HARD_BLOCKER,
}
ACTION_NO_ORDER = "no_order"

_SYMBOL = re.compile(r"^[0-9]{6}$")


def _require_refs(refs: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Interim policy evidence references require ids")
    return normalized


@dataclass(frozen=True)
class InterimReportPolicyDecision:
    """Versioned reclassification of one interim report risk factor."""

    symbol: str
    report_period: date
    source_verified: bool
    has_reported_conflict: bool
    has_subsequent_correction: bool
    has_scope_mismatch: bool
    has_audit_qualification: bool
    has_material_accounting_uncertainty: bool
    classification: str
    previous_classification: str = "HARD_BLOCKER"
    policy_reason: str = "policy correction"
    decision_version: str = "20260923.1"
    evidence_refs: tuple[dict[str, Any], ...] = ()
    blockers: tuple[str, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Interim policy symbol must contain six digits")
        if not isinstance(self.report_period, date):
            raise ValueError("Interim policy report_period must be a date")
        if self.classification not in CLASSIFICATIONS:
            raise ValueError("Unknown interim policy classification")
        if self.previous_classification not in CLASSIFICATIONS:
            raise ValueError("Unknown previous interim policy classification")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Interim report policy must remain no_order")
        if not self.policy_reason.strip():
            raise ValueError("Interim report policy requires a reason")
        if self.classification == CLASSIFICATION_HARD_BLOCKER and not self.blockers:
            raise ValueError("A hard blocker requires an escalation reason")
        object.__setattr__(
            self,
            "evidence_refs",
            _require_refs(tuple(self.evidence_refs)),
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(str(item) for item in self.blockers),
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": INTERIM_REPORT_POLICY_SCHEMA,
            "symbol": self.symbol,
            "report_period": self.report_period.isoformat(),
            "source_verified": self.source_verified,
            "has_reported_conflict": self.has_reported_conflict,
            "has_subsequent_correction": self.has_subsequent_correction,
            "has_scope_mismatch": self.has_scope_mismatch,
            "has_audit_qualification": self.has_audit_qualification,
            "has_material_accounting_uncertainty": (
                self.has_material_accounting_uncertainty
            ),
            "classification": self.classification,
            "previous_classification": self.previous_classification,
            "policy_reason": self.policy_reason,
            "decision_version": self.decision_version,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "blockers": list(self.blockers),
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def classify_unaudited_interim_report(
    *,
    symbol: str,
    report_period: date,
    source_verified: bool,
    has_reported_conflict: bool = False,
    has_subsequent_correction: bool = False,
    has_scope_mismatch: bool = False,
    has_audit_qualification: bool = False,
    has_material_accounting_uncertainty: bool = False,
    previous_classification: str = "HARD_BLOCKER",
    evidence_refs: tuple[dict[str, Any], ...] = (),
) -> InterimReportPolicyDecision:
    """Apply the corrected default without deleting the historical blocker."""
    if not source_verified:
        return InterimReportPolicyDecision(
            symbol=symbol,
            report_period=report_period,
            source_verified=False,
            has_reported_conflict=has_reported_conflict,
            has_subsequent_correction=has_subsequent_correction,
            has_scope_mismatch=has_scope_mismatch,
            has_audit_qualification=has_audit_qualification,
            has_material_accounting_uncertainty=has_material_accounting_uncertainty,
            classification=CLASSIFICATION_HARD_BLOCKER,
            previous_classification=previous_classification,
            policy_reason="unverified statutory source",
            evidence_refs=evidence_refs,
            blockers=("interim_source_not_verified",),
        )

    escalated = (
        has_reported_conflict
        or has_subsequent_correction
        or has_scope_mismatch
        or has_audit_qualification
        or has_material_accounting_uncertainty
    )
    blockers = tuple(
        item
        for item in (
            "reported_data_conflict" if has_reported_conflict else None,
            "subsequent_correction" if has_subsequent_correction else None,
            "scope_mismatch" if has_scope_mismatch else None,
            "audit_qualification_evidence" if has_audit_qualification else None,
            (
                "material_accounting_uncertainty"
                if has_material_accounting_uncertainty
                else None
            ),
        )
        if item is not None
    )
    return InterimReportPolicyDecision(
        symbol=symbol,
        report_period=report_period,
        source_verified=True,
        has_reported_conflict=has_reported_conflict,
        has_subsequent_correction=has_subsequent_correction,
        has_scope_mismatch=has_scope_mismatch,
        has_audit_qualification=has_audit_qualification,
        has_material_accounting_uncertainty=has_material_accounting_uncertainty,
        classification=(
            CLASSIFICATION_HARD_BLOCKER
            if escalated
            else CLASSIFICATION_CONFIDENCE_MODIFIER
        ),
        previous_classification=previous_classification,
        policy_reason="policy correction",
        evidence_refs=evidence_refs,
        blockers=blockers,
    )


def interim_report_policy_from_payload(
    payload: dict[str, Any],
) -> InterimReportPolicyDecision:
    data = dict(payload)
    if data.get("schema_version") != INTERIM_REPORT_POLICY_SCHEMA:
        raise ValueError("Unknown interim report policy schema")
    return InterimReportPolicyDecision(
        symbol=str(data["symbol"]),
        report_period=date.fromisoformat(str(data["report_period"])),
        source_verified=bool(data["source_verified"]),
        has_reported_conflict=bool(data["has_reported_conflict"]),
        has_subsequent_correction=bool(data["has_subsequent_correction"]),
        has_scope_mismatch=bool(data["has_scope_mismatch"]),
        has_audit_qualification=bool(data["has_audit_qualification"]),
        has_material_accounting_uncertainty=bool(
            data["has_material_accounting_uncertainty"]
        ),
        classification=str(data["classification"]),
        previous_classification=str(data["previous_classification"]),
        policy_reason=str(data["policy_reason"]),
        decision_version=str(data.get("decision_version", "20260923.1")),
        evidence_refs=tuple(
            dict(item) for item in data.get("evidence_refs") or ()
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
