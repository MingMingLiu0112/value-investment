"""Transparent, deterministic valuation-confidence rules; no LLM scoring."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


MIN_FORECAST_HORIZON_MEDIUM = 5
MIN_FORECAST_HORIZON_HIGH = 10
MAX_TERMINAL_SHARE_HIGH = Decimal("0.60")
MAX_TERMINAL_SHARE_MEDIUM = Decimal("0.75")
MAX_CROSS_CHECK_DISAGREEMENT_HIGH = Decimal("0.10")
MAX_CROSS_CHECK_DISAGREEMENT_MEDIUM = Decimal("0.20")


__all__ = [
    "ConfidenceAssessment",
    "ConfidenceEvidence",
    "MAX_CROSS_CHECK_DISAGREEMENT_HIGH",
    "MAX_CROSS_CHECK_DISAGREEMENT_MEDIUM",
    "MAX_TERMINAL_SHARE_HIGH",
    "MAX_TERMINAL_SHARE_MEDIUM",
    "MIN_FORECAST_HORIZON_HIGH",
    "MIN_FORECAST_HORIZON_MEDIUM",
    "evaluate_confidence",
]


@dataclass(frozen=True)
class ConfidenceEvidence:
    data_completeness: Decimal
    business_stability: str
    parameter_sensitivity: str
    cyclicality: str
    forecast_horizon_years: int
    terminal_value_share: Decimal | None
    cross_check_disagreement: Decimal | None
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.data_completeness <= Decimal("1"):
            raise ValueError("data completeness must be between zero and one")
        for name in ("business_stability", "parameter_sensitivity", "cyclicality"):
            if getattr(self, name) not in {"high", "medium", "low", "unknown"}:
                raise ValueError(f"{name} must be high, medium, low or unknown")
        if self.forecast_horizon_years <= 0:
            raise ValueError("forecast horizon must be positive")
        for name in ("terminal_value_share", "cross_check_disagreement"):
            value = getattr(self, name)
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError(f"{name} must be a nonnegative finite Decimal")
        if not self.evidence_refs or any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("confidence evidence requires named references")


@dataclass(frozen=True)
class ConfidenceAssessment:
    confidence: str
    reasons: list[str]
    blockers: list[str]

    def as_policy(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
        }


def evaluate_confidence(evidence: ConfidenceEvidence) -> ConfidenceAssessment:
    """Apply explicit policy thresholds; uncertainty or missing checks mean low."""
    if not isinstance(evidence, ConfidenceEvidence):
        raise ValueError("confidence assessment requires ConfidenceEvidence")

    blockers: list[str] = []
    reasons: list[str] = []

    if evidence.data_completeness < Decimal("1"):
        blockers.append("data_completeness_below_one")
    if evidence.business_stability in {"low", "unknown"}:
        blockers.append(f"business_stability_{evidence.business_stability}")
    if evidence.parameter_sensitivity in {"high", "unknown"}:
        blockers.append(f"parameter_sensitivity_{evidence.parameter_sensitivity}")
    if evidence.cyclicality == "unknown":
        blockers.append("cyclicality_unknown")
    if (evidence.cyclicality == "high"
            and evidence.business_stability != "high"):
        blockers.append("high_cyclicality_without_high_business_stability")
    if evidence.forecast_horizon_years < MIN_FORECAST_HORIZON_MEDIUM:
        blockers.append("forecast_horizon_below_medium_policy")

    if evidence.terminal_value_share is None:
        blockers.append("terminal_value_share_not_measured")
    elif evidence.terminal_value_share > MAX_TERMINAL_SHARE_MEDIUM:
        blockers.append("terminal_value_share_above_medium_policy")

    if evidence.cross_check_disagreement is None:
        blockers.append("cross_check_disagreement_not_measured")
    elif evidence.cross_check_disagreement > MAX_CROSS_CHECK_DISAGREEMENT_MEDIUM:
        blockers.append("cross_check_disagreement_above_medium_policy")

    if blockers:
        reasons.append("at least one confidence hard blocker is present")
        return ConfidenceAssessment("低", reasons, list(dict.fromkeys(blockers)))

    high_checks = (
        evidence.business_stability == "high",
        evidence.parameter_sensitivity == "low",
        evidence.cyclicality == "low",
        evidence.forecast_horizon_years >= MIN_FORECAST_HORIZON_HIGH,
        evidence.terminal_value_share is not None
        and evidence.terminal_value_share <= MAX_TERMINAL_SHARE_HIGH,
        evidence.cross_check_disagreement is not None
        and evidence.cross_check_disagreement <= MAX_CROSS_CHECK_DISAGREEMENT_HIGH,
    )
    if all(high_checks):
        reasons.append("all high-confidence evidence checks passed")
        return ConfidenceAssessment("高", reasons, [])

    reasons.append("confidence checks passed medium policy but not all high policy")
    return ConfidenceAssessment("中", reasons, [])
