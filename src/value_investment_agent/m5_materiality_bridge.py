"""Bridge human materiality decisions into the M5 change-event pipeline.

The existing materiality contract preserves the final human verdict. This
module maps only actionable verdicts into M5 events and explicit dependency
kinds. Non-material, already-incorporated and duplicate verdicts remain
silent so title-based candidates cannot mutate valuation facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Mapping, Sequence

from .event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_DUPLICATE,
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    DECISION_SUPPORTING,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    EVENT_NAMESPACES,
    EVENT_TYPE_MATERIAL_ANNOUNCEMENT,
    HUMAN_MATERIALITY_EVIDENCE_TYPE,
    MATERIALITY_BRIDGE_SOURCE_ID,
    MATERIALITY_PENDING_STATUS,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    ChangeEventInput,
    _required_bool,
    _required_text,
    _optional_text,
    change_event_input_from_payload,
)
from .m5_event_dependencies import (
    DEPENDENCY_KINDS,
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_DISTRIBUTION_HISTORY,
    KIND_DIVIDEND_SUSTAINABILITY,
    KIND_ENTRY_CONSISTENCY,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_PORTFOLIO_RISK,
    KIND_POSITION_GUIDANCE,
    KIND_THESIS,
    KIND_VALUATION_INPUTS,
    KIND_VALUATION_RESULT,
)


MATERIALITY_BRIDGE_SCHEMA = "m5-materiality-bridge-v1"
SEVERITY_SILENT = "SILENT"
CONFIDENCE_SILENT = "SILENT"

SILENT_MATERIALITY_DECISIONS = frozenset(
    {
        DECISION_NOT_MATERIAL,
        DECISION_SUPPORTING,
        DECISION_ALREADY_INCORPORATED,
        DECISION_DUPLICATE,
    }
)
ACTIONABLE_MATERIALITY_DECISIONS = frozenset(
    {
        DECISION_REQUIRES_RECALCULATION,
        DECISION_REQUIRES_DECOMPOSITION,
        DECISION_RISK_MONITOR,
    }
)

_NORMALIZE_TAG = re.compile(r"[^0-9a-z_]+")

_DOMAIN_KINDS: dict[str, frozenset[str]] = {
    "balance_sheet_risk": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "income_statement_risk": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "cash_flow_risk": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "lease": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "minority_interest": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "investment": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "goodwill": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "debt": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "tax": frozenset({KIND_FACTS, KIND_VALUATION_INPUTS}),
    "dividend": frozenset({KIND_DISTRIBUTION_HISTORY, KIND_DIVIDEND_SUSTAINABILITY}),
    "distribution": frozenset({KIND_DISTRIBUTION_HISTORY, KIND_DIVIDEND_SUSTAINABILITY}),
    "buyback": frozenset(
        {KIND_DISTRIBUTION_HISTORY, KIND_VALUATION_INPUTS, KIND_THESIS}
    ),
    "business_model": frozenset({KIND_THESIS, KIND_VALUATION_INPUTS}),
    "competitive_position": frozenset({KIND_THESIS}),
    "portfolio_risk": frozenset({KIND_PORTFOLIO_RISK}),
    "concentration": frozenset({KIND_PORTFOLIO_RISK}),
    "position": frozenset({KIND_POSITION_GUIDANCE}),
    "model": frozenset({KIND_MODEL_VALIDITY}),
    "entry": frozenset({KIND_ENTRY_CONSISTENCY}),
}

_ARTIFACT_KINDS: dict[str, str] = {
    "valuation_result": KIND_VALUATION_RESULT,
    "model_validity": KIND_MODEL_VALIDITY,
    "research_thesis": KIND_THESIS,
    "entry": KIND_ENTRY_CONSISTENCY,
    "decision_review": KIND_DECISION_REVIEW,
}


def _tag(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _NORMALIZE_TAG.sub("", text)


def _unique(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(items)))


def _mapped_domain_kinds(decision: EventMaterialityDecision) -> tuple[set[str], list[str]]:
    kinds: set[str] = set()
    unmapped: list[str] = []
    for value in decision.affected_domains:
        tag = _tag(value)
        mapped = _DOMAIN_KINDS.get(tag)
        if mapped is None:
            unmapped.append(str(value))
            continue
        kinds.update(mapped)
    return kinds, unmapped


def _artifact_kinds(decision: EventMaterialityDecision) -> tuple[set[str], list[str]]:
    kinds: set[str] = set()
    unmapped: list[str] = []
    for value in decision.affected_artifacts:
        mapped = _ARTIFACT_KINDS.get(_tag(value))
        if mapped is None:
            unmapped.append(str(value))
            continue
        kinds.add(mapped)
    return kinds, unmapped


def materiality_direct_kinds(
    decision: EventMaterialityDecision,
) -> tuple[str, ...]:
    """Return only the dependency kinds affected by a human materiality verdict."""

    if decision.human_decision in SILENT_MATERIALITY_DECISIONS:
        return ()
    if decision.human_decision == DECISION_REQUIRES_DECOMPOSITION:
        return (KIND_DECISION_REVIEW, KIND_CURRENT_STATUS)
    if decision.human_decision == DECISION_RISK_MONITOR:
        return (KIND_DECISION_REVIEW,)
    if decision.human_decision != DECISION_REQUIRES_RECALCULATION:
        raise ValueError("Unknown materiality decision cannot be mapped")

    kinds: set[str] = {
        KIND_MODEL_VALIDITY,
        KIND_VALUATION_INPUTS,
        KIND_DECISION_REVIEW,
    }
    if decision.affected_fact_fields:
        kinds.add(KIND_FACTS)
    if decision.affected_assumptions:
        kinds.add(KIND_VALUATION_INPUTS)
    domain_kinds, _ = _mapped_domain_kinds(decision)
    kinds.update(domain_kinds)
    artifact_kinds, _ = _artifact_kinds(decision)
    kinds.update(artifact_kinds)
    return _unique(kinds)


def materiality_event_from_decision(
    decision: EventMaterialityDecision,
    *,
    namespace: str,
) -> ChangeEventInput | None:
    """Convert one human materiality decision into an M5 event or silence."""

    if namespace not in EVENT_NAMESPACES:
        raise ValueError("Unknown materiality bridge namespace")
    if decision.reviewed_at is None:
        raise ValueError("Only reviewed materiality decisions can enter M5")
    if decision.reviewed_at < decision.published_at:
        raise ValueError("Materiality review cannot precede source publication")
    if decision.action != ACTION_NO_ORDER:
        raise ValueError("Materiality bridge must remain no_order")
    if decision.human_decision in SILENT_MATERIALITY_DECISIONS:
        return None
    if decision.human_decision not in ACTIONABLE_MATERIALITY_DECISIONS:
        raise ValueError("Unknown materiality decision cannot enter M5")

    direct_kinds = materiality_direct_kinds(decision)
    severity = SEVERITY_MEDIUM if decision.human_decision == DECISION_RISK_MONITOR else SEVERITY_HIGH
    confidence = CONFIDENCE_MEDIUM if decision.human_decision == DECISION_RISK_MONITOR else CONFIDENCE_HIGH
    _, unmapped_domains = _mapped_domain_kinds(decision)
    _, unmapped_artifacts = _artifact_kinds(decision)
    source_ref = dict(decision.source_ref)
    source_ref["sha256"] = decision.source_sha256
    evidence_refs = [source_ref]
    evidence_refs.append(
        {
            "id": decision.event_decision_id,
            "type": HUMAN_MATERIALITY_EVIDENCE_TYPE,
            "source_sha256": decision.source_sha256,
        }
    )
    current_state: dict[str, Any] = {
        "materiality_status": decision.human_decision,
        "source_sha256": decision.source_sha256,
        "source_ref_id": source_ref["id"],
        "source_ref_sha256": decision.source_sha256,
        "supersedes_event_id": decision.supersedes_event_id,
        "event_cluster_id": decision.event_cluster_id,
        "affected_domains": list(decision.affected_domains),
        "affected_fact_fields": list(decision.affected_fact_fields),
        "affected_assumptions": list(decision.affected_assumptions),
        "affected_artifacts": list(decision.affected_artifacts),
        "requires_recalculation": decision.requires_recalculation,
        "requires_model_stale": decision.requires_model_stale,
        "direct_dependency_kinds": list(direct_kinds),
        "unmapped_domains": unmapped_domains,
        "unmapped_artifacts": unmapped_artifacts,
    }
    return ChangeEventInput(
        source_id=MATERIALITY_BRIDGE_SOURCE_ID,
        source_event_id=f"materiality-review:{decision.event_decision_id}",
        symbol=decision.symbol,
        event_type=EVENT_TYPE_MATERIAL_ANNOUNCEMENT,
        detected_at=decision.reviewed_at,
        available_at=decision.published_at,
        effective_at=decision.published_at,
        previous_state={"materiality_status": MATERIALITY_PENDING_STATUS},
        current_state=current_state,
        severity=severity,
        reason=(
            f"human_event_materiality={decision.human_decision}; "
            f"candidate_reason={decision.machine_candidate_reason}"
        ),
        evidence_refs=tuple(evidence_refs),
        confidence=confidence,
        requires_human_review=True,
        namespace=namespace,
        action=ACTION_NO_ORDER,
    )


@dataclass(frozen=True)
class MaterialityDecisionPlan:
    decision_id: str
    symbol: str
    human_decision: str
    silent: bool
    event: ChangeEventInput | None
    direct_kinds: tuple[str, ...]
    severity: str
    confidence: str
    reason: str
    supersedes_event_id: str | None = None
    event_cluster_id: str | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.symbol.strip():
            raise ValueError("Materiality decision plan requires id and symbol")
        if self.human_decision not in {
            *SILENT_MATERIALITY_DECISIONS,
            *ACTIONABLE_MATERIALITY_DECISIONS,
        }:
            raise ValueError("Unknown materiality decision in plan")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Materiality decision plan must remain no_order")
        if self.silent and (self.event is not None or self.direct_kinds):
            raise ValueError("Silent materiality decisions cannot create M5 effects")
        if self.silent and (self.severity != SEVERITY_SILENT or self.confidence != CONFIDENCE_SILENT):
            raise ValueError("Silent materiality decisions must carry silent metadata")
        if not self.silent and (
            self.event is None or not self.direct_kinds
        ):
            raise ValueError("Actionable materiality decisions require M5 effects")
        if self.event is not None and self.event.symbol != self.symbol:
            raise ValueError("Materiality event symbol does not match the plan")
        object.__setattr__(
            self,
            "supersedes_event_id",
            _optional_text(self.supersedes_event_id, "supersedes_event_id"),
        )
        object.__setattr__(
            self,
            "event_cluster_id",
            _optional_text(self.event_cluster_id, "event_cluster_id"),
        )
        if self.event is not None:
            if (
                self.event.current_state.get("supersedes_event_id")
                != self.supersedes_event_id
            ):
                raise ValueError(
                    "Materiality plan supersedes target does not match its event"
                )
            if (
                self.event.current_state.get("event_cluster_id")
                != self.event_cluster_id
            ):
                raise ValueError(
                    "Materiality plan event cluster does not match its event"
                )

    def as_policy(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "human_decision": self.human_decision,
            "silent": self.silent,
            "supersedes_event_id": self.supersedes_event_id,
            "event_cluster_id": self.event_cluster_id,
            "event": self.event.as_policy() if self.event else None,
            "direct_kinds": list(self.direct_kinds),
            "severity": self.severity,
            "confidence": self.confidence,
            "reason": self.reason,
            "action": self.action,
        }


def materiality_decision_plan_from_payload(
    payload: Mapping[str, Any],
) -> MaterialityDecisionPlan:
    """Parse one serialized materiality plan fail-closed."""

    if not isinstance(payload, Mapping):
        raise ValueError("Materiality decision plan must be an object")
    data = dict(payload)
    event_payload = data.get("event")
    plan = MaterialityDecisionPlan(
        decision_id=_required_text(data["decision_id"], "decision_id"),
        symbol=_required_text(data["symbol"], "symbol"),
        human_decision=_required_text(data["human_decision"], "human_decision"),
        silent=_required_bool(data["silent"], "silent"),
        event=(
            None
            if event_payload is None
            else change_event_input_from_payload(event_payload)
        ),
        direct_kinds=tuple(str(item) for item in data.get("direct_kinds") or ()),
        severity=_required_text(data["severity"], "severity"),
        confidence=_required_text(data["confidence"], "confidence"),
        reason=_required_text(data["reason"], "reason"),
        supersedes_event_id=_optional_text(
            data.get("supersedes_event_id"),
            "supersedes_event_id",
        ),
        event_cluster_id=_optional_text(
            data.get("event_cluster_id"),
            "event_cluster_id",
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
    if set(data) != set(plan.as_policy()):
        raise ValueError("Materiality decision plan keys do not match the schema")
    if plan.silent != (plan.human_decision in SILENT_MATERIALITY_DECISIONS):
        raise ValueError(
            "Materiality plan silence does not match its human decision"
        )
    if plan.event is not None:
        declared = tuple(
            str(item)
            for item in plan.event.current_state.get("direct_dependency_kinds")
            or ()
        )
        if declared != tuple(plan.direct_kinds):
            raise ValueError(
                "Materiality plan dependency kinds do not match its event payload"
            )
    return plan


@dataclass(frozen=True)
class MaterialityBridgeBatch:
    review_id: str
    symbol: str
    schema_version: str
    namespace: str
    coverage_through: str
    plans: tuple[MaterialityDecisionPlan, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != MATERIALITY_BRIDGE_SCHEMA:
            raise ValueError("Unknown materiality bridge schema")
        if not self.review_id.strip() or not self.symbol.strip():
            raise ValueError("Materiality bridge batch requires review id and symbol")
        if self.namespace not in EVENT_NAMESPACES:
            raise ValueError("Unknown materiality bridge namespace")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Materiality bridge batch must remain no_order")
        if any(item.symbol != self.symbol for item in self.plans):
            raise ValueError("Every materiality plan must match the batch symbol")
        if any(item.event is not None and item.event.namespace != self.namespace for item in self.plans):
            raise ValueError("Materiality event namespace does not match the batch")

    @property
    def events(self) -> tuple[ChangeEventInput, ...]:
        return tuple(item.event for item in self.plans if item.event is not None)

    @property
    def observed_times(self) -> tuple[datetime, ...]:
        return tuple(item.event.detected_at for item in self.plans if item.event is not None)

    @property
    def direct_kinds_by_source_event_id(self) -> dict[str, tuple[str, ...]]:
        return {
            item.event.source_event_id: item.direct_kinds
            for item in self.plans
            if item.event is not None
        }

    @property
    def silent_count(self) -> int:
        return sum(item.silent for item in self.plans)

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "review_id": self.review_id,
            "symbol": self.symbol,
            "namespace": self.namespace,
            "coverage_through": self.coverage_through,
            "plans": [item.as_policy() for item in self.plans],
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> "MaterialityBridgeBatch":
        """Parse a serialized bridge batch fail-closed.

        The payload must round-trip to its canonical form, so a hand-edited
        bridge artifact cannot silently change a human materiality verdict.
        """

        if not isinstance(payload, Mapping):
            raise ValueError("Materiality bridge batch must be an object")
        data = dict(payload)
        if data.get("schema_version") != MATERIALITY_BRIDGE_SCHEMA:
            raise ValueError("Unknown materiality bridge schema")
        coverage_through = _required_text(
            data["coverage_through"],
            "coverage_through",
        )
        datetime.fromisoformat(coverage_through)
        batch = cls(
            review_id=_required_text(data["review_id"], "review_id"),
            symbol=_required_text(data["symbol"], "symbol"),
            schema_version=MATERIALITY_BRIDGE_SCHEMA,
            namespace=_required_text(data["namespace"], "namespace"),
            coverage_through=coverage_through,
            plans=tuple(
                materiality_decision_plan_from_payload(item)
                for item in data.get("plans") or ()
            ),
            action=str(data.get("action", ACTION_NO_ORDER)),
        )
        expected = batch.as_policy()
        if set(data) != set(expected):
            missing = sorted(set(expected) - set(data))
            extra = sorted(set(data) - set(expected))
            raise ValueError(
                "Materiality bridge batch keys do not match the schema: "
                f"missing={missing} extra={extra}"
            )
        if data != expected:
            raise ValueError(
                "Materiality bridge batch does not round-trip to its "
                "canonical form"
            )
        return batch


def build_materiality_bridge_batch(
    review: EventMaterialityReview,
    *,
    namespace: str,
) -> MaterialityBridgeBatch:
    """Convert a complete materiality review into explicit, silent-safe M5 plans."""

    plans = tuple(
        MaterialityDecisionPlan(
            decision_id=item.event_decision_id,
            symbol=item.symbol,
            human_decision=item.human_decision,
            silent=item.human_decision in SILENT_MATERIALITY_DECISIONS,
            event=materiality_event_from_decision(
                item,
                namespace=namespace,
            ),
            direct_kinds=materiality_direct_kinds(item),
            severity=(
                SEVERITY_SILENT
                if item.human_decision in SILENT_MATERIALITY_DECISIONS
                else SEVERITY_MEDIUM
                if item.human_decision == DECISION_RISK_MONITOR
                else SEVERITY_HIGH
            ),
            confidence=(
                CONFIDENCE_SILENT
                if item.human_decision in SILENT_MATERIALITY_DECISIONS
                else CONFIDENCE_MEDIUM
                if item.human_decision == DECISION_RISK_MONITOR
                else CONFIDENCE_HIGH
            ),
            reason=(
                f"human_event_materiality={item.human_decision}; "
                f"candidate_reason={item.machine_candidate_reason}"
            ),
            supersedes_event_id=item.supersedes_event_id,
            event_cluster_id=item.event_cluster_id,
        )
        for item in review.decisions
    )
    return MaterialityBridgeBatch(
        review_id=review.review_id,
        symbol=review.symbol,
        schema_version=MATERIALITY_BRIDGE_SCHEMA,
        namespace=namespace,
        coverage_through=review.coverage_watermark.isoformat(),
        plans=plans,
    )
