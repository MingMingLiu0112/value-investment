"""Explicit, evidence-backed valuation assumptions kept separate from facts.

Valuation mathematics receives verified facts and reviewed assumptions. An
assumption is a forward-looking research judgment with a bear/base/bull range,
a stated economic basis, rationale, evidence, confidence and sensitivity. It
must never be silently embedded inside a valuation model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
import re
from typing import Any


STATUS_READY = "READY"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_READY = "NOT_READY"
STATUS_INVALID = "INVALID"
ASSUMPTION_SET_STATUSES = {
    STATUS_READY,
    STATUS_PARTIAL,
    STATUS_NOT_READY,
    STATUS_INVALID,
}

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = {CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH}

SENSITIVITY_LOW = "low"
SENSITIVITY_MEDIUM = "medium"
SENSITIVITY_HIGH = "high"
SENSITIVITY_LEVELS = {SENSITIVITY_LOW, SENSITIVITY_MEDIUM, SENSITIVITY_HIGH}

ORDER_ASCENDING = "ascending"
ORDER_DESCENDING = "descending"
SCENARIO_ORDERINGS = {ORDER_ASCENDING, ORDER_DESCENDING}


def _validate_refs(refs: list[dict[str, Any]]) -> None:
    if not isinstance(refs, list) or any(not ref.get("id") for ref in refs):
        raise ValueError("Valuation assumptions require named evidence references")


def _normalize_scenario_value(value: Decimal | str | None, field: str) -> Decimal | str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{field} must be a finite Decimal")
        return value
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{field} cannot be empty")
        return value.strip()
    raise ValueError(f"{field} must be a Decimal, string or None")


def _scenario_values_are_ordered(
    values: tuple[Decimal | str | None, ...],
    ordering: str,
) -> bool:
    if any(not isinstance(value, Decimal) for value in values):
        return True
    if ordering == ORDER_ASCENDING:
        return values[0] <= values[1] <= values[2]
    return values[0] >= values[1] >= values[2]


@dataclass(frozen=True)
class ValuationAssumption:
    """One forward-looking, reviewable valuation judgment."""

    name: str
    unit: str
    bear: Decimal | str | None
    base: Decimal | str | None
    bull: Decimal | str | None
    basis: str
    rationale: str
    as_of: date
    confidence: str
    sensitivity: str
    evidence_refs: list[dict[str, Any]]
    blockers: list[str]
    ordering: str = ORDER_ASCENDING

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Valuation assumption name is required")
        if not self.unit.strip():
            raise ValueError("Valuation assumption unit is required")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "unit", self.unit.strip())
        object.__setattr__(self, "bear", _normalize_scenario_value(self.bear, "bear"))
        object.__setattr__(self, "base", _normalize_scenario_value(self.base, "base"))
        object.__setattr__(self, "bull", _normalize_scenario_value(self.bull, "bull"))
        if all(value is None for value in (self.bear, self.base, self.bull)):
            raise ValueError("Valuation assumption requires at least one scenario value")
        if self.ordering not in SCENARIO_ORDERINGS:
            raise ValueError("Unknown valuation assumption scenario ordering")
        if not _scenario_values_are_ordered(
            (self.bear, self.base, self.bull), self.ordering
        ):
            raise ValueError(
                "Numeric assumption scenarios must follow their registered ordering"
            )
        if not self.basis.strip() or not self.rationale.strip():
            raise ValueError("Valuation assumption basis and rationale are required")
        if not isinstance(self.as_of, date):
            raise ValueError("Valuation assumption as_of must be a date")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Unknown valuation assumption confidence")
        if self.sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError("Unknown valuation assumption sensitivity")
        _validate_refs(self.evidence_refs)
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("Assumption blockers must be non-empty strings")
        object.__setattr__(self, "basis", self.basis.strip())
        object.__setattr__(self, "rationale", self.rationale.strip())
        object.__setattr__(self, "blockers", [blocker.strip() for blocker in self.blockers])
        object.__setattr__(self, "evidence_refs", [dict(ref) for ref in self.evidence_refs])

    def has_complete_scenarios(self) -> bool:
        return all(value is not None for value in (self.bear, self.base, self.bull))

    def as_policy(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "bear": str(self.bear) if self.bear is not None else None,
            "base": str(self.base) if self.base is not None else None,
            "bull": str(self.bull) if self.bull is not None else None,
            "basis": self.basis,
            "rationale": self.rationale,
            "as_of": self.as_of.isoformat(),
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "blockers": list(self.blockers),
            "ordering": self.ordering,
        }


def _assumption_blockers(assumption: ValuationAssumption) -> list[str]:
    if not assumption.has_complete_scenarios():
        missing = [
            label
            for label, value in (
                ("bear", assumption.bear),
                ("base", assumption.base),
                ("bull", assumption.bull),
            )
            if value is None
        ]
        return [
            f"assumption_scenarios_missing:{assumption.name}:{','.join(missing)}",
            *assumption.blockers,
        ]
    return list(assumption.blockers)


def _derive_status(
    assumptions: list[ValuationAssumption],
    blockers: list[str],
) -> tuple[str, list[str]]:
    derived = list(blockers)
    if not assumptions:
        return STATUS_NOT_READY, [*derived, "assumption_set_is_empty"]
    names = [assumption.name for assumption in assumptions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        return STATUS_INVALID, [*derived, f"duplicate_assumptions:{','.join(duplicates)}"]
    for assumption in assumptions:
        derived.extend(_assumption_blockers(assumption))
    derived = list(dict.fromkeys(derived))
    if derived:
        return STATUS_PARTIAL, derived
    return STATUS_READY, derived


@dataclass(frozen=True)
class ValuationAssumptionSet:
    """A named set of assumptions for one symbol and valuation model."""

    symbol: str
    profile_id: str
    model_type: str
    as_of: date
    assumptions: list[ValuationAssumption]
    status: str
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Valuation-assumption symbol must contain six digits")
        if not self.profile_id.strip():
            raise ValueError("Valuation-assumption profile_id is required")
        if not self.model_type.strip():
            raise ValueError("Valuation-assumption model_type is required")
        if not isinstance(self.as_of, date):
            raise ValueError("Valuation-assumption as_of must be a date")
        if self.status not in ASSUMPTION_SET_STATUSES:
            raise ValueError("Unknown valuation-assumption set status")
        if not isinstance(self.assumptions, list) or any(
            not isinstance(assumption, ValuationAssumption)
            for assumption in self.assumptions
        ):
            raise ValueError("Valuation-assumption set requires typed assumptions")
        _validate_refs(self.evidence_refs)
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "blockers", [blocker.strip() for blocker in self.blockers])
        object.__setattr__(self, "evidence_refs", [dict(ref) for ref in self.evidence_refs])

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "model_type": self.model_type,
            "as_of": self.as_of.isoformat(),
            "assumptions": [assumption.as_policy() for assumption in self.assumptions],
            "status": self.status,
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, indent=2)


def build_valuation_assumption_set(
    *,
    symbol: str,
    profile_id: str,
    model_type: str,
    as_of: date,
    assumptions: list[ValuationAssumption],
    blockers: list[str] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
) -> ValuationAssumptionSet:
    """Derive a fail-closed set status from typed assumptions."""

    status, resolved_blockers = _derive_status(assumptions, list(blockers or []))
    return ValuationAssumptionSet(
        symbol=symbol,
        profile_id=profile_id,
        model_type=model_type,
        as_of=as_of,
        assumptions=assumptions,
        status=status,
        blockers=resolved_blockers,
        evidence_refs=list(evidence_refs or []),
    )


def assumption_set_from_payload(payload: dict[str, Any]) -> ValuationAssumptionSet:
    """Restore a serialized assumption set with strict field conversion."""

    assumptions = []
    for raw in payload["assumptions"]:
        assumptions.append(
            ValuationAssumption(
                name=str(raw["name"]),
                unit=str(raw["unit"]),
                bear=_payload_scenario_value(raw.get("bear"), "bear"),
                base=_payload_scenario_value(raw.get("base"), "base"),
                bull=_payload_scenario_value(raw.get("bull"), "bull"),
                basis=str(raw["basis"]),
                rationale=str(raw["rationale"]),
                as_of=date.fromisoformat(str(raw["as_of"])),
                confidence=str(raw["confidence"]),
                sensitivity=str(raw["sensitivity"]),
                evidence_refs=list(raw["evidence_refs"]),
                blockers=list(raw.get("blockers", [])),
                ordering=str(raw.get("ordering", ORDER_ASCENDING)),
            )
        )
    return build_valuation_assumption_set(
        symbol=str(payload["symbol"]),
        profile_id=str(payload["profile_id"]),
        model_type=str(payload["model_type"]),
        as_of=date.fromisoformat(str(payload["as_of"])),
        assumptions=assumptions,
        blockers=list(payload.get("blockers", [])),
        evidence_refs=list(payload.get("evidence_refs", [])),
    )


def _payload_scenario_value(value: Any, field: str) -> Decimal | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal, string or null")
    if isinstance(value, (int, float)):
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError(f"{field} must be finite")
        return number
    return _normalize_scenario_value(str(value), field)
