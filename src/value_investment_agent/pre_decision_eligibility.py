"""Gate that must pass before any positive decision-stage review is allowed.

Passing this gate never creates a BUY, ADD, position or order. It only proves
that the reviewed valuation, human approval, current event review, model
validity and price bridge are simultaneously legal research inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
from typing import Any, Mapping

from .event_materiality import EventMaterialityReview
from .human_research_approval import (
    HumanResearchApprovalReceipt,
    resolve_human_research_approval,
)
from .model_validity import ModelValidity
from .price_attractiveness import (
    STATUS_NOT_ASSESSABLE,
    PriceAttractivenessAssessment,
)
from .price_bridge import PriceBridgeResult
from .research_gate import ResearchGate
from .valuation_models.base import ValuationResult


PREDECISION_SCHEMA = "post-m1-predecision-eligibility-v1"
ACTION_NO_ORDER = "no_order"
STATUS_ELIGIBLE = "ELIGIBLE_FOR_DECISION_REVIEW"
STATUS_NOT_ELIGIBLE = "NOT_ELIGIBLE"

_SYMBOL = re.compile(r"^[0-9]{6}$")


def _merge_refs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Predecision evidence references require ids")
            current = merged.get(ref_id)
            if current is None:
                merged[ref_id] = ref
                continue
            for key, value in ref.items():
                if key in current and current[key] != value:
                    raise ValueError(f"Predecision evidence id conflict: {ref_id}")
                current[key] = value
    return list(merged.values())


@dataclass(frozen=True)
class PreDecisionEligibility:
    """Fail-closed prerequisite check for future M3 positive reviews."""

    symbol: str
    decision_as_of: date
    status: str
    approval_status: str
    model_validity_status: str
    price_bridge_status: str
    event_review_watermark: date | None
    blockers: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Predecision symbol must contain six digits")
        if self.status not in {STATUS_ELIGIBLE, STATUS_NOT_ELIGIBLE}:
            raise ValueError("Unknown predecision status")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Predecision check must remain no_order")
        if self.status == STATUS_ELIGIBLE and self.blockers:
            raise ValueError("An eligible predecision check cannot have blockers")
        if self.status == STATUS_NOT_ELIGIBLE and not self.blockers:
            raise ValueError("A blocked predecision check requires a blocker")
        refs = tuple(dict(ref) for ref in self.evidence_refs)
        if any(not ref.get("id") for ref in refs):
            raise ValueError("Predecision evidence requires named references")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "evidence_refs", refs)

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": PREDECISION_SCHEMA,
            "symbol": self.symbol,
            "decision_as_of": self.decision_as_of.isoformat(),
            "status": self.status,
            "approval_status": self.approval_status,
            "model_validity_status": self.model_validity_status,
            "price_bridge_status": self.price_bridge_status,
            "event_review_watermark": (
                self.event_review_watermark.isoformat()
                if self.event_review_watermark is not None
                else None
            ),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def evaluate_pre_decision_eligibility(
    *,
    gate: ResearchGate,
    valuation: ValuationResult,
    approval: HumanResearchApprovalReceipt,
    model_validity: ModelValidity,
    price_bridge: PriceBridgeResult,
    event_materiality: EventMaterialityReview,
    decision_as_of: date,
    model_id: str,
    research_case_payload: Mapping[str, Any],
    facts_payload: Mapping[str, Any],
    assumptions_payload: Mapping[str, Any],
    price_attractiveness: PriceAttractivenessAssessment | None = None,
) -> PreDecisionEligibility:
    """Apply the decision-layer prerequisites without producing any decision."""
    if not (gate.symbol == valuation.symbol == price_bridge.symbol == model_validity.symbol):
        raise ValueError("Predecision inputs must share one symbol")
    if event_materiality.symbol != valuation.symbol:
        raise ValueError("Event materiality review must match the valuation symbol")

    approval_decision = resolve_human_research_approval(
        approval,
        valuation,
        model_id=model_id,
        research_case_payload=research_case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
    )
    blockers: list[str] = []
    if not gate.valuation_ready:
        blockers.append("research_gate_not_ready")
    if not approval_decision.approved:
        blockers.append("human_research_approval_not_valid")
    if not approval_decision.price_assessment_eligible:
        blockers.append("human_approval_price_assessment_not_eligible")
    if event_materiality.has_unresolved_recalculation:
        blockers.append("unresolved_event_recalculation")
    if event_materiality.has_unresolved_decomposition:
        blockers.append("unresolved_event_decomposition")
    if not event_materiality.covers(decision_as_of):
        blockers.append("event_review_watermark_not_current")
    if model_validity.status not in {"VALID"}:
        blockers.append(f"model_validity_{model_validity.status.lower()}")
    if price_bridge.bridge_status != "READY":
        blockers.append(f"price_bridge_{price_bridge.bridge_status.lower()}")
    if (
        price_attractiveness is not None
        and price_attractiveness.status == STATUS_NOT_ASSESSABLE
    ):
        blockers.append("price_attractiveness_not_assessable")
    blockers.extend(approval_decision.blockers)
    blockers.extend(event_materiality.review_blockers)

    status = STATUS_ELIGIBLE if not blockers else STATUS_NOT_ELIGIBLE
    evidence_refs = _merge_refs(
        list(approval.evidence_refs),
        list(event_materiality.evidence_refs),
        list(price_bridge.evidence_refs),
    )
    return PreDecisionEligibility(
        symbol=valuation.symbol,
        decision_as_of=decision_as_of,
        status=status,
        approval_status=approval_decision.status,
        model_validity_status=model_validity.status,
        price_bridge_status=price_bridge.bridge_status,
        event_review_watermark=event_materiality.coverage_watermark,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=tuple(evidence_refs),
    )


def pre_decision_eligibility_from_payload(
    payload: Mapping[str, Any],
) -> PreDecisionEligibility:
    data = dict(payload)
    if data.get("schema_version") != PREDECISION_SCHEMA:
        raise ValueError("Unknown predecision schema")
    watermark = data.get("event_review_watermark")
    return PreDecisionEligibility(
        symbol=str(data["symbol"]),
        decision_as_of=date.fromisoformat(str(data["decision_as_of"])),
        status=str(data["status"]),
        approval_status=str(data["approval_status"]),
        model_validity_status=str(data["model_validity_status"]),
        price_bridge_status=str(data["price_bridge_status"]),
        event_review_watermark=(
            date.fromisoformat(str(watermark)) if watermark is not None else None
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
