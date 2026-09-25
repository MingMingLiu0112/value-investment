"""Versioned, serializable input contracts shared by the research input layer.

These objects describe the point-in-time window, source provenance and the
explicit link from a reviewed assumption to the scenario input that a valuation
model actually consumes. They deliberately contain no model selection policy,
symbol-specific branch or execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


INPUT_DESCRIPTOR_SCHEMA = "m1-fixed-sample-input-v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCENARIO = re.compile(r"^(bear|base|bull)$")


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
    raise ValueError(f"Unsupported contract value: {type(value).__name__}")


@dataclass(frozen=True)
class ResearchSourceDescriptor:
    """Hash-verified source identity plus parser and availability timestamps."""

    id: str
    kind: str
    location: str
    sha256: str
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    parser_version: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.kind.strip() or not self.location.strip():
            raise ValueError("Research source id, kind and location are required")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("Research source hash must be SHA-256 hex")
        for field in ("published_at", "retrieved_at"):
            value = getattr(self, field)
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"Research source {field} must include timezone")
        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "kind", self.kind.strip())
        object.__setattr__(self, "location", self.location.strip())

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "location": self.location,
            "sha256": self.sha256,
            "published_at": (
                self.published_at.isoformat() if self.published_at else None
            ),
            "retrieved_at": (
                self.retrieved_at.isoformat() if self.retrieved_at else None
            ),
            "parser_version": self.parser_version,
        }


@dataclass(frozen=True)
class ResearchDependencyFingerprint:
    """Version inputs that must invalidate a previously computed research run."""

    rule_version: str
    profile_id: str
    model_id: str
    model_version: str
    parser_version: str | None = None
    scan_watermark: str | None = None

    def __post_init__(self) -> None:
        for field in ("rule_version", "profile_id", "model_id", "model_version"):
            if not getattr(self, field).strip():
                raise ValueError(f"Research dependency {field} is required")

    def as_policy(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "profile_id": self.profile_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "parser_version": self.parser_version,
            "scan_watermark": self.scan_watermark,
        }


@dataclass(frozen=True)
class ResearchPitFrame:
    """Distinct dates that a trusted descriptor must keep separately."""

    report_period: date
    research_as_of: date
    valuation_date: date
    available_at: datetime
    computed_at: datetime

    def __post_init__(self) -> None:
        for field in ("available_at", "computed_at"):
            if getattr(self, field).utcoffset() is None:
                raise ValueError(f"Research PIT {field} must include timezone")
        if self.available_at > self.computed_at:
            raise ValueError("Research availability cannot follow computation")
        if self.report_period > self.research_as_of:
            raise ValueError("Research report period cannot follow research as-of")
        if self.valuation_date > self.research_as_of:
            raise ValueError("Valuation date cannot follow research as-of")
        if self.available_at.date() < self.research_as_of:
            raise ValueError("Research availability cannot precede research as-of")

    def as_policy(self) -> dict[str, Any]:
        return {
            "report_period": self.report_period.isoformat(),
            "research_as_of": self.research_as_of.isoformat(),
            "valuation_date": self.valuation_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(frozen=True)
class ResearchValuationApproval:
    """Human approval bound to one exact valuation result, not to a symbol."""

    model_id: str
    model_type: str
    model_version: str
    valuation_date: date
    result_sha256: str
    approved_at: datetime
    approver: str
    evidence_refs: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        for field in ("model_id", "model_type", "model_version", "approver"):
            if not getattr(self, field).strip():
                raise ValueError(f"Research valuation approval {field} is required")
        if not isinstance(self.valuation_date, date):
            raise ValueError("Research valuation approval date must be a date")
        if not _SHA256.fullmatch(self.result_sha256):
            raise ValueError("Research valuation approval hash must be SHA-256 hex")
        if self.approved_at.tzinfo is None:
            raise ValueError("Research valuation approval time must include timezone")
        refs = [dict(ref) for ref in self.evidence_refs]
        if any(not ref.get("id") for ref in refs):
            raise ValueError("Research valuation approval evidence requires ids")
        object.__setattr__(self, "evidence_refs", tuple(refs))

    def matches(self, valuation: Any) -> bool:
        return (
            self.model_type == valuation.model_type
            and self.model_version == valuation.model_version
            and self.valuation_date == valuation.valuation_date
            and self.result_sha256 == valuation_result_sha256(valuation)
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "model_version": self.model_version,
            "valuation_date": self.valuation_date.isoformat(),
            "result_sha256": self.result_sha256,
            "approved_at": self.approved_at.isoformat(),
            "approver": self.approver,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


def valuation_result_sha256(valuation: Any) -> str:
    """Hash the exact domain result that an approval can legally bind."""

    payload = {
        "symbol": valuation.symbol,
        "model_type": valuation.model_type,
        "valuation_date": valuation.valuation_date,
        "bear_value": valuation.bear_value,
        "base_value": valuation.base_value,
        "bull_value": valuation.bull_value,
        "confidence": valuation.confidence,
        "assumptions": valuation.assumptions,
        "sensitivities": valuation.sensitivities,
        "evidence_refs": valuation.evidence_refs,
        "blockers": valuation.blockers,
        "status": valuation.status,
        "model_version": valuation.model_version,
    }
    return hashlib.sha256(
        canonical_contract_payload(payload).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class AssumptionScenarioBinding:
    """Provable link from one reviewed assumption to a consumed model input."""

    assumption_name: str
    scenario: str
    field_path: str
    expected_value: Any
    evidence_refs: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.assumption_name.strip() or not self.field_path.strip():
            raise ValueError("Assumption binding name and field path are required")
        if not _SCENARIO.fullmatch(self.scenario):
            raise ValueError("Assumption binding scenario must be bear, base or bull")
        refs = [dict(ref) for ref in self.evidence_refs]
        if any(not ref.get("id") for ref in refs):
            raise ValueError("Assumption binding evidence requires named references")
        object.__setattr__(self, "assumption_name", self.assumption_name.strip())
        object.__setattr__(self, "field_path", self.field_path.strip())
        object.__setattr__(self, "expected_value", _json_value(self.expected_value))
        object.__setattr__(self, "evidence_refs", tuple(refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "assumption_name": self.assumption_name,
            "scenario": self.scenario,
            "field_path": self.field_path,
            "expected_value": _json_value(self.expected_value),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


def validate_assumption_bindings(
    facts: Any,
    bindings: tuple[AssumptionScenarioBinding, ...],
) -> list[str]:
    """Return blockers when registered assumptions do not match model inputs."""

    if not bindings:
        return []
    scenarios = getattr(facts, "scenario_inputs", None)
    if not isinstance(scenarios, Mapping):
        return ["assumption_bindings_require_registered_scenario_inputs"]

    blockers: list[str] = []
    for binding in bindings:
        scenario = scenarios.get(binding.scenario)
        if scenario is None:
            blockers.append(
                f"assumption_binding_missing_scenario:{binding.assumption_name}"
            )
            continue
        try:
            value = scenario
            for component in binding.field_path.split("."):
                if isinstance(value, Sequence) and not isinstance(
                    value, (str, bytes, Mapping)
                ):
                    try:
                        index = int(component)
                    except ValueError:
                        raise TypeError from None
                    if index < 0 or index >= len(value):
                        raise IndexError from None
                    value = value[index]
                elif isinstance(value, Mapping):
                    value = value[component]
                else:
                    value = getattr(value, component)
        except (KeyError, AttributeError, IndexError, TypeError):
            blockers.append(
                f"assumption_binding_unknown_field:{binding.assumption_name}"
            )
            continue
        if _json_value(value) != _json_value(binding.expected_value):
            blockers.append(
                f"assumption_binding_value_mismatch:{binding.assumption_name}"
            )
    return blockers


def canonical_contract_payload(payload: Mapping[str, Any]) -> str:
    """Return canonical JSON with strict deterministic shape validation."""

    if not isinstance(payload, dict) or not payload:
        raise ValueError("Research input contract payload must be a nonempty object")
    normalized = json.loads(
        json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
