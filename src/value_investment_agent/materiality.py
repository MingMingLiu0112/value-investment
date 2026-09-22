"""Explicit materiality assessment for scope items that cannot be perfectly split.

Materiality separates a small, quantified unknown from an unknown that could
still change the valuation conclusion. LOW or IMMATERIAL requires a quantified
exposure or a justified bound. UNKNOWN remains fail-closed and can never be
silently relabeled as unimportant.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import re
from typing import Any


MATERIALITY_IMMATERIAL = "IMMATERIAL"
MATERIALITY_LOW = "LOW"
MATERIALITY_MEDIUM = "MEDIUM"
MATERIALITY_HIGH = "HIGH"
MATERIALITY_UNKNOWN = "UNKNOWN"
MATERIALITY_LEVELS = {
    MATERIALITY_IMMATERIAL,
    MATERIALITY_LOW,
    MATERIALITY_MEDIUM,
    MATERIALITY_HIGH,
    MATERIALITY_UNKNOWN,
}

TREATMENT_IGNORE_WITH_DISCLOSURE = "IGNORE_WITH_DISCLOSURE"
TREATMENT_MODEL_AS_RANGE = "MODEL_AS_RANGE"
TREATMENT_SCENARIO_STRESS = "SCENARIO_STRESS"
TREATMENT_BLOCK_MODEL = "BLOCK_MODEL"
TREATMENT_REQUIRE_MORE_EVIDENCE = "REQUIRE_MORE_EVIDENCE"
MATERIALITY_TREATMENTS = {
    TREATMENT_IGNORE_WITH_DISCLOSURE,
    TREATMENT_MODEL_AS_RANGE,
    TREATMENT_SCENARIO_STRESS,
    TREATMENT_BLOCK_MODEL,
    TREATMENT_REQUIRE_MORE_EVIDENCE,
}


def _validate_refs(refs: list[dict[str, Any]], *, required: bool = False) -> None:
    if not isinstance(refs, list) or any(not ref.get("id") for ref in refs):
        raise ValueError("Materiality evidence references must be named")
    if required and not refs:
        raise ValueError("A quantified low-materiality conclusion requires evidence")


def _validate_decimal(value: Decimal | None, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class ScopeMaterialityAssessment:
    """Materiality judgment for one unresolved scope item."""

    symbol: str
    issue_id: str
    metric: str
    estimated_exposure_ratio: Decimal | None
    downside_impact: Decimal | None
    upside_impact: Decimal | None
    materiality: str
    treatment: str
    rationale: str
    evidence_refs: list[dict[str, Any]]
    blockers: list[str]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Materiality symbol must contain six digits")
        if not self.issue_id.strip() or not self.metric.strip():
            raise ValueError("Materiality issue_id and metric are required")
        if self.materiality not in MATERIALITY_LEVELS:
            raise ValueError("Unknown materiality level")
        if self.treatment not in MATERIALITY_TREATMENTS:
            raise ValueError("Unknown materiality treatment")
        if not self.rationale.strip():
            raise ValueError("Materiality rationale is required")
        object.__setattr__(self, "issue_id", self.issue_id.strip())
        object.__setattr__(self, "metric", self.metric.strip())
        object.__setattr__(self, "rationale", self.rationale.strip())
        object.__setattr__(
            self,
            "estimated_exposure_ratio",
            _validate_decimal(self.estimated_exposure_ratio, "estimated_exposure_ratio"),
        )
        object.__setattr__(
            self, "downside_impact", _validate_decimal(self.downside_impact, "downside_impact")
        )
        object.__setattr__(
            self, "upside_impact", _validate_decimal(self.upside_impact, "upside_impact")
        )
        quantified = (
            self.estimated_exposure_ratio is not None
            or self.downside_impact is not None
            or self.upside_impact is not None
        )
        if self.materiality in {MATERIALITY_IMMATERIAL, MATERIALITY_LOW} and not quantified:
            raise ValueError(
                "IMMATERIAL or LOW materiality requires quantified exposure or a justified bound"
            )
        if self.materiality == MATERIALITY_UNKNOWN and self.treatment not in {
            TREATMENT_REQUIRE_MORE_EVIDENCE,
            TREATMENT_BLOCK_MODEL,
        }:
            raise ValueError("UNKNOWN materiality must fail closed")
        if self.materiality == MATERIALITY_HIGH and self.treatment not in {
            TREATMENT_SCENARIO_STRESS,
            TREATMENT_BLOCK_MODEL,
        }:
            raise ValueError("HIGH materiality requires scenario stress or a model block")
        if self.materiality in {
            MATERIALITY_MEDIUM,
            MATERIALITY_HIGH,
        } and self.treatment == TREATMENT_IGNORE_WITH_DISCLOSURE:
            raise ValueError("MEDIUM or HIGH materiality cannot be ignored")
        _validate_refs(
            self.evidence_refs,
            required=self.materiality in {MATERIALITY_IMMATERIAL, MATERIALITY_LOW},
        )
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("Materiality blockers must be non-empty strings")
        object.__setattr__(self, "evidence_refs", [dict(ref) for ref in self.evidence_refs])
        object.__setattr__(self, "blockers", [blocker.strip() for blocker in self.blockers])

    @property
    def fail_closed(self) -> bool:
        return self.materiality == MATERIALITY_UNKNOWN or self.treatment in {
            TREATMENT_BLOCK_MODEL,
            TREATMENT_REQUIRE_MORE_EVIDENCE,
        }

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "issue_id": self.issue_id,
            "metric": self.metric,
            "estimated_exposure_ratio": (
                str(self.estimated_exposure_ratio)
                if self.estimated_exposure_ratio is not None
                else None
            ),
            "downside_impact": (
                str(self.downside_impact) if self.downside_impact is not None else None
            ),
            "upside_impact": (
                str(self.upside_impact) if self.upside_impact is not None else None
            ),
            "materiality": self.materiality,
            "treatment": self.treatment,
            "rationale": self.rationale,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "blockers": list(self.blockers),
            "fail_closed": self.fail_closed,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, indent=2)


def materiality_applicability_effect(
    materiality: ScopeMaterialityAssessment,
    applicability_status: str,
) -> dict[str, Any]:
    """Materiality is only one input; it never changes model applicability by itself."""

    if not isinstance(materiality, ScopeMaterialityAssessment):
        raise ValueError("Materiality effect requires a typed assessment")
    return {
        "symbol": materiality.symbol,
        "issue_id": materiality.issue_id,
        "materiality": materiality.materiality,
        "treatment": materiality.treatment,
        "applicability_status_before": applicability_status,
        "applicability_status_after": applicability_status,
        "model_unlocked": False,
        "reason": (
            "Materiality informs applicability only through an explicit route decision; "
            "a LOW or IMMATERIAL item cannot convert MODEL_NOT_APPLICABLE to SUPPORTED."
        ),
    }


def materiality_from_payload(payload: dict[str, Any]) -> ScopeMaterialityAssessment:
    """Restore a serialized materiality assessment."""

    return ScopeMaterialityAssessment(
        symbol=str(payload["symbol"]),
        issue_id=str(payload["issue_id"]),
        metric=str(payload["metric"]),
        estimated_exposure_ratio=_payload_decimal(payload.get("estimated_exposure_ratio")),
        downside_impact=_payload_decimal(payload.get("downside_impact")),
        upside_impact=_payload_decimal(payload.get("upside_impact")),
        materiality=str(payload["materiality"]),
        treatment=str(payload["treatment"]),
        rationale=str(payload["rationale"]),
        evidence_refs=list(payload.get("evidence_refs", [])),
        blockers=list(payload.get("blockers", [])),
    )


def _payload_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Materiality decimal values must be finite")
    return number
