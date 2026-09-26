"""Machine-readable M6 start-criteria matrix.

The matrix separates the source of a missing prerequisite from whether that
prerequisite blocks the first technical Shadow start. It is descriptive only:
it neither grants production authorization nor advances M6 operational state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "m6-start-criteria-matrix-v1"
M6_OPERATIONAL = "NOT_STARTED"
ACTION_NO_ORDER = "no_order"
DECISION_BLOCKED = "BLOCKED_PENDING_HARD_START_GATES"
DECISION_READY = "SHADOW_START_READY"
DECISIONS = frozenset({DECISION_BLOCKED, DECISION_READY})

CLASSIFICATIONS = frozenset(
    {
        "MACHINE_READY",
        "USER_INPUT_REQUIRED",
        "USER_AUTHORIZATION_REQUIRED",
        "NATURAL_TIME_REQUIRED",
        "RESEARCH_EVIDENCE_REQUIRED",
    }
)
SHADOW_START_GATES = frozenset(
    {
        "HARD_START_GATE",
        "SOFT_PRODUCT_GAP",
        "NATURAL_TIME_GATE",
        "NOT_RELEVANT_TO_SHADOW_START",
    }
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


@dataclass(frozen=True)
class StartCriterion:
    criterion_id: str
    requirement: str
    classification: str
    shadow_start_gate: str
    current_satisfied: bool | None
    current_state: str
    rationale: str
    evidence_refs: tuple[str, ...]
    reopen_condition: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "criterion_id",
            _required_text(self.criterion_id, "criterion_id"),
        )
        object.__setattr__(
            self,
            "requirement",
            _required_text(self.requirement, "requirement"),
        )
        if self.classification not in CLASSIFICATIONS:
            raise ValueError(f"Unknown M6 criterion classification: {self.classification}")
        if self.shadow_start_gate not in SHADOW_START_GATES:
            raise ValueError(f"Unknown M6 Shadow gate: {self.shadow_start_gate}")
        if self.current_satisfied is not None and not isinstance(
            self.current_satisfied, bool
        ):
            raise ValueError("current_satisfied must be boolean or null")
        if self.shadow_start_gate == "HARD_START_GATE" and self.current_satisfied is None:
            raise ValueError("hard start criteria require a boolean current_satisfied")
        if self.shadow_start_gate == "NATURAL_TIME_GATE" and self.current_satisfied is not False:
            raise ValueError("natural-time gates cannot already be satisfied at start")
        object.__setattr__(
            self,
            "current_state",
            _required_text(self.current_state, "current_state"),
        )
        object.__setattr__(self, "rationale", _required_text(self.rationale, "rationale"))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if any(not isinstance(item, str) or not item for item in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty paths")
        if self.current_satisfied is False and not self.reopen_condition:
            raise ValueError("unsatisfied criteria require a reopen_condition")

    def as_policy(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "requirement": self.requirement,
            "classification": self.classification,
            "shadow_start_gate": self.shadow_start_gate,
            "current_satisfied": self.current_satisfied,
            "current_state": self.current_state,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "reopen_condition": self.reopen_condition,
        }


@dataclass(frozen=True)
class M6StartCriteriaMatrix:
    reviewed_at: date
    criteria: tuple[StartCriterion, ...]
    schema_version: str = SCHEMA_VERSION
    action: str = ACTION_NO_ORDER
    m6_operational: str = M6_OPERATIONAL
    production_authorization_requested: bool = False
    production_authorization_granted: bool = False
    shadow_start_allowed: bool = False
    decision: str = DECISION_BLOCKED

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported M6 start-criteria matrix schema")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M6 start-criteria matrix must remain no_order")
        if self.m6_operational != M6_OPERATIONAL:
            raise ValueError("M6 operational status must remain NOT_STARTED")
        if self.production_authorization_requested:
            raise ValueError("the matrix must not request production authorization")
        if self.production_authorization_granted:
            raise ValueError("the matrix cannot grant production authorization")
        object.__setattr__(self, "criteria", tuple(self.criteria))
        if not self.criteria:
            raise ValueError("the matrix must contain criteria")
        if len({item.criterion_id for item in self.criteria}) != len(self.criteria):
            raise ValueError("M6 criterion ids must be unique")
        hard_gates = [item for item in self.criteria if item.shadow_start_gate == "HARD_START_GATE"]
        if not hard_gates:
            raise ValueError("the matrix must identify hard Shadow start gates")
        if self.shadow_start_allowed and any(
            item.current_satisfied is not True for item in hard_gates
        ):
            raise ValueError("Shadow cannot start while hard gates are unsatisfied")
        if not self.shadow_start_allowed and not any(
            item.current_satisfied is not True for item in hard_gates
        ):
            raise ValueError("blocked Shadow start requires an unsatisfied hard gate")
        if self.decision not in DECISIONS:
            raise ValueError("unsupported M6 start decision")
        if self.shadow_start_allowed and self.decision != DECISION_READY:
            raise ValueError(
                "a startable matrix must report SHADOW_START_READY"
            )
        if not self.shadow_start_allowed and self.decision != DECISION_BLOCKED:
            raise ValueError(
                "a blocked matrix must report BLOCKED_PENDING_HARD_START_GATES"
            )

    def as_policy(self) -> dict[str, Any]:
        hard_gates = [
            item for item in self.criteria if item.shadow_start_gate == "HARD_START_GATE"
        ]
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "reviewed_at": self.reviewed_at.isoformat(),
            "M6_OPERATIONAL": self.m6_operational,
            "production_authorization_requested": self.production_authorization_requested,
            "production_authorization_granted": self.production_authorization_granted,
            "shadow_start_allowed": self.shadow_start_allowed,
            "decision": self.decision,
            "criteria": [item.as_policy() for item in self.criteria],
            "summary": {
                "hard_start_gates": len(hard_gates),
                "hard_start_gates_satisfied": sum(
                    item.current_satisfied is True for item in hard_gates
                ),
                "natural_time_gates": sum(
                    item.shadow_start_gate == "NATURAL_TIME_GATE"
                    for item in self.criteria
                ),
                "soft_product_gaps": sum(
                    item.shadow_start_gate == "SOFT_PRODUCT_GAP"
                    for item in self.criteria
                ),
            },
        }


def m6_start_criteria_matrix_from_payload(
    payload: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> M6StartCriteriaMatrix:
    if not isinstance(payload, Mapping):
        raise ValueError("M6 start-criteria matrix must be a JSON object")
    classification_legend = payload.get("classification_legend")
    gate_legend = payload.get("shadow_start_gate_legend")
    if not isinstance(classification_legend, Mapping) or set(
        classification_legend
    ) != CLASSIFICATIONS:
        raise ValueError("classification_legend must define the exact classification set")
    if not isinstance(gate_legend, Mapping) or set(gate_legend) != SHADOW_START_GATES:
        raise ValueError("shadow_start_gate_legend must define the exact gate set")
    for flag in (
        "production_authorization_requested",
        "production_authorization_granted",
        "shadow_start_allowed",
    ):
        if not isinstance(payload.get(flag), bool):
            raise ValueError(f"{flag} must be boolean")
    raw_criteria = payload.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ValueError("criteria must be a non-empty list")
    criteria: list[StartCriterion] = []
    for index, item in enumerate(raw_criteria):
        if not isinstance(item, Mapping):
            raise ValueError(f"criterion {index} must be an object")
        evidence_refs = item.get("evidence_refs") or []
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ValueError(f"criterion {index} evidence_refs must be a non-empty list")
        criterion = StartCriterion(
            criterion_id=str(item.get("criterion_id") or ""),
            requirement=str(item.get("requirement") or ""),
            classification=str(item.get("classification") or ""),
            shadow_start_gate=str(item.get("shadow_start_gate") or ""),
            current_satisfied=item.get("current_satisfied"),
            current_state=str(item.get("current_state") or ""),
            rationale=str(item.get("rationale") or ""),
            evidence_refs=tuple(str(path) for path in evidence_refs),
            reopen_condition=(
                None
                if item.get("reopen_condition") is None
                else str(item.get("reopen_condition"))
            ),
        )
        if root is not None:
            resolved_root = root.resolve()
            for ref in criterion.evidence_refs:
                evidence_path = (resolved_root / ref).resolve()
                if not evidence_path.is_relative_to(resolved_root) or not evidence_path.is_file():
                    raise ValueError(f"missing M6 evidence reference: {ref}")
        criteria.append(criterion)
    reviewed_at = date.fromisoformat(str(payload.get("reviewed_at")))
    return M6StartCriteriaMatrix(
        reviewed_at=reviewed_at,
        criteria=tuple(criteria),
        schema_version=str(payload.get("schema_version") or ""),
        action=str(payload.get("action") or ""),
        m6_operational=str(payload.get("M6_OPERATIONAL") or ""),
        production_authorization_requested=payload[
            "production_authorization_requested"
        ],
        production_authorization_granted=payload["production_authorization_granted"],
        shadow_start_allowed=payload["shadow_start_allowed"],
        decision=str(payload.get("decision") or ""),
    )


def load_m6_start_criteria_matrix(
    path: Path,
    *,
    root: Path | None = None,
) -> M6StartCriteriaMatrix:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("M6 start-criteria matrix must be a JSON object")
    return m6_start_criteria_matrix_from_payload(payload, root=root)
