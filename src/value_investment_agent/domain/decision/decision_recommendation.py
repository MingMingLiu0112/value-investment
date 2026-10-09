"""Auditable recommendation contract; never an order or execution instruction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping


LEGACY_DECISION_RECOMMENDATION_SCHEMA = "advisory-decision-recommendation-v1"
DECISION_RECOMMENDATION_SCHEMA = "advisory-decision-recommendation-v2"
DECISION_RECOMMENDATION_V3_SCHEMA = "advisory-decision-recommendation-v3"
DECISION_RECOMMENDATION_SCHEMAS = frozenset(
    {
        LEGACY_DECISION_RECOMMENDATION_SCHEMA,
        DECISION_RECOMMENDATION_SCHEMA,
        DECISION_RECOMMENDATION_V3_SCHEMA,
    }
)
ACTION_NO_ORDER = "no_order"

RECOMMENDATION_BUY_CANDIDATE = "BUY_CANDIDATE"
RECOMMENDATION_ADD_CANDIDATE = "ADD_CANDIDATE"
RECOMMENDATION_HOLD = "HOLD"
RECOMMENDATION_TRIM_CANDIDATE = "TRIM_CANDIDATE"
RECOMMENDATION_SELL_CANDIDATE = "SELL_CANDIDATE"
RECOMMENDATION_NO_ACTION = "NO_ACTION"

RECOMMENDATION_ACTIONS = frozenset(
    {
        RECOMMENDATION_BUY_CANDIDATE,
        RECOMMENDATION_ADD_CANDIDATE,
        RECOMMENDATION_HOLD,
        RECOMMENDATION_TRIM_CANDIDATE,
        RECOMMENDATION_SELL_CANDIDATE,
        RECOMMENDATION_NO_ACTION,
    }
)
D2_IMPLEMENTED_ACTIONS = frozenset(
    {RECOMMENDATION_BUY_CANDIDATE, RECOMMENDATION_NO_ACTION}
)
ENTRY_REQUIRED_ACTIONS = frozenset(
    {
        RECOMMENDATION_ADD_CANDIDATE,
        RECOMMENDATION_HOLD,
        RECOMMENDATION_TRIM_CANDIDATE,
        RECOMMENDATION_SELL_CANDIDATE,
    }
)
POSITIVE_ACTIONS = frozenset(
    {RECOMMENDATION_BUY_CANDIDATE, RECOMMENDATION_ADD_CANDIDATE}
)
PROTECTED_ACTIONS = frozenset(RECOMMENDATION_ACTIONS - {RECOMMENDATION_NO_ACTION})

THESIS_CONSISTENCY_STATUSES = frozenset(
    {"CONSISTENT", "FULFILLED", "WEAKENED", "BROKEN"}
)

RESEARCH_PROTECTED_DEPENDENCY_ROLES = frozenset(
    {"research_case", "valuation", "model_validity", "event_materiality"}
)
RISK_REDUCTION_DEPENDENCY_ROLES = RESEARCH_PROTECTED_DEPENDENCY_ROLES | frozenset(
    {"entry_thesis", "investment_consistency_review"}
)
POSITIVE_DEPENDENCY_ROLES = RESEARCH_PROTECTED_DEPENDENCY_ROLES | frozenset(
    {
        "price_bridge",
        "price_attractiveness",
        "pre_decision",
        "human_approval",
    }
)

BASE_PROTECTED_DEPENDENCY_ROLES = frozenset(
    {
        "research_case",
        "valuation",
        "price_bridge",
        "price_attractiveness",
        "pre_decision",
        "event_materiality",
    }
)

PORTFOLIO_BLOCKED_PRIVATE_INPUT = "BLOCKED_PRIVATE_INPUT"
PORTFOLIO_INPUT_STATUSES = frozenset({PORTFOLIO_BLOCKED_PRIVATE_INPUT})

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _protected_dependency_roles(action: str) -> frozenset[str]:
    if action == RECOMMENDATION_BUY_CANDIDATE:
        return POSITIVE_DEPENDENCY_ROLES
    if action == RECOMMENDATION_ADD_CANDIDATE:
        return POSITIVE_DEPENDENCY_ROLES | frozenset(
            {"entry_thesis", "investment_consistency_review"}
        )
    if action in {RECOMMENDATION_HOLD, RECOMMENDATION_TRIM_CANDIDATE,
                  RECOMMENDATION_SELL_CANDIDATE}:
        return RISK_REDUCTION_DEPENDENCY_ROLES
    return BASE_PROTECTED_DEPENDENCY_ROLES


def _artifact_payload(value: Any) -> Any:
    """Return one canonical JSON-compatible payload without trusting a label."""
    if value is None:
        return None
    serializer = getattr(value, "to_json", None)
    if callable(serializer):
        return json.loads(serializer())
    serializer = getattr(value, "as_policy", None)
    if callable(serializer):
        return serializer()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Cannot fingerprint dependency of type {type(value).__name__}")


def decision_input_fingerprint(
    *,
    research_case: Any,
    valuation: Any,
    model_validity: Any,
    price_bridge: Any,
    price_attractiveness: Any,
    pre_decision: Any,
    human_approval: Any,
    event_materiality: Any,
    decision_as_of: date | None = None,
    model_id: str | None = None,
    research_case_payload: Mapping[str, Any] | None = None,
    facts_payload: Mapping[str, Any] | None = None,
    assumptions_payload: Mapping[str, Any] | None = None,
    additional_blockers: tuple[str, ...] = (),
    include_d3_dependencies: bool = False,
    entry_thesis: Any = None,
    investment_consistency_review: Any = None,
) -> str:
    """Bind a recommendation to the exact dependency payloads that produced it."""
    dependencies = {
        "research_case": _artifact_payload(research_case),
        "valuation": _artifact_payload(valuation),
        "model_validity": _artifact_payload(model_validity),
        "price_bridge": _artifact_payload(price_bridge),
        "price_attractiveness": _artifact_payload(price_attractiveness),
        "pre_decision": _artifact_payload(pre_decision),
        "human_approval": _artifact_payload(human_approval),
        "event_materiality": _artifact_payload(event_materiality),
        "decision_as_of": decision_as_of.isoformat() if decision_as_of else None,
        "model_id": model_id,
        "research_case_payload": _artifact_payload(research_case_payload),
        "facts_payload": _artifact_payload(facts_payload),
        "assumptions_payload": _artifact_payload(assumptions_payload),
        "additional_blockers": list(additional_blockers),
    }
    if include_d3_dependencies:
        dependencies["entry_thesis"] = _artifact_payload(entry_thesis)
        dependencies["investment_consistency_review"] = _artifact_payload(
            investment_consistency_review
        )
    encoded = json.dumps(
        dependencies,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def recommendation_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash every visible recommendation field except the sealing hash itself."""
    data = dict(payload)
    data.pop("recommendation_payload_sha256", None)
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_dependency_refs(
    refs: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in refs:
        ref = dict(raw)
        role = str(ref.get("role", "")).strip()
        artifact_id = str(ref.get("artifact_id", "")).strip()
        artifact_type = str(ref.get("artifact_type", "")).strip()
        scope_type = str(ref.get("scope_type", "")).strip()
        scope_key = str(ref.get("scope_key", "")).strip()
        payload_sha256 = str(ref.get("payload_sha256", "")).lower()
        if not role or role in seen:
            raise ValueError("Decision dependency roles must be unique and named")
        if not artifact_id or not artifact_type or not scope_type or not scope_key:
            raise ValueError("Decision dependency artifact identity is incomplete")
        if not _SHA256.fullmatch(payload_sha256):
            raise ValueError("Decision dependency hash must be SHA-256 hex")
        seen.add(role)
        normalized.append(
            {
                "role": role,
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "scope_type": scope_type,
                "scope_key": scope_key,
                "payload_sha256": payload_sha256,
            }
        )
    return tuple(normalized)


def _require_refs(refs: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Decision recommendation evidence requires named references")
    return normalized


@dataclass(frozen=True)
class ValuationRange:
    """Intrinsic-value scenarios, never a market-price observation."""

    bear: Decimal | None
    base: Decimal | None
    bull: Decimal | None
    currency: str = "CNY"
    basis: str = "valuation_result"

    def __post_init__(self) -> None:
        values = (self.bear, self.base, self.bull)
        if any(
            value is not None and (not value.is_finite() or value <= 0)
            for value in values
        ):
            raise ValueError("Valuation range values must be positive and finite")
        present = [value for value in values if value is not None]
        if present and len(present) != 3:
            raise ValueError("Valuation range must be complete or absent")
        if present and not (self.bear <= self.base <= self.bull):
            raise ValueError("Valuation range must be bear <= base <= bull")
        if not self.currency.strip() or not self.basis.strip():
            raise ValueError("Valuation range requires currency and basis")


@dataclass(frozen=True)
class PriceRange:
    """A named price band used only for user review and display."""

    low: Decimal
    high: Decimal
    basis: str

    def __post_init__(self) -> None:
        if not self.low.is_finite() or not self.high.is_finite() or self.low <= 0:
            raise ValueError("Price range requires positive finite bounds")
        if self.high < self.low:
            raise ValueError("Price range high cannot be below low")
        if not self.basis.strip():
            raise ValueError("Price range requires a basis")


@dataclass(frozen=True)
class MarginOfSafety:
    """Price-to-intrinsic-value margins supplied by the existing PriceBridge."""

    to_bear: Decimal | None
    to_base: Decimal | None

    def __post_init__(self) -> None:
        if any(
            value is not None and not value.is_finite()
            for value in (self.to_bear, self.to_base)
        ):
            raise ValueError("Margin of safety values must be finite")
        if (self.to_bear is None) != (self.to_base is None):
            raise ValueError("Margin of safety must be complete or absent")


@dataclass(frozen=True)
class DecisionRecommendation:
    """One fail-closed recommendation derived from existing research gates."""

    symbol: str
    run_id: str
    decision_as_of: date
    recommendation_action: str
    confidence: str
    valuation_range: ValuationRange
    current_price: Decimal | None
    margin_of_safety: MarginOfSafety
    entry_zone: PriceRange | None
    reduce_zone: PriceRange | None
    exit_conditions: tuple[str, ...]
    thesis: str
    counter_evidence: tuple[dict[str, Any], ...]
    thesis_breakers: tuple[dict[str, Any], ...]
    next_events: tuple[dict[str, Any], ...]
    evidence_refs: tuple[dict[str, Any], ...]
    model_validity: dict[str, Any]
    price_bridge_status: str
    price_attractiveness_status: str
    recommendation_reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    requires_human_review: bool = False
    entry_id: str | None = None
    thesis_consistency_status: str | None = None
    rule_evidence: dict[str, Any] | None = None
    portfolio_input_status: str = PORTFOLIO_BLOCKED_PRIVATE_INPUT
    position_guidance: None = None
    action: str = ACTION_NO_ORDER
    decision_input_sha256: str | None = None
    input_model_id: str | None = None
    input_additional_blockers: tuple[str, ...] = ()
    decision_dependency_refs: tuple[dict[str, Any], ...] = ()
    recommendation_payload_sha256: str | None = None
    schema_version: str = DECISION_RECOMMENDATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in DECISION_RECOMMENDATION_SCHEMAS:
            raise ValueError("Unknown decision recommendation schema")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Decision recommendation symbol must contain six digits")
        if not self.run_id.strip():
            raise ValueError("Decision recommendation run id is required")
        if not isinstance(self.decision_as_of, date) or isinstance(
            self.decision_as_of, datetime
        ):
            raise ValueError("Decision recommendation as-of must be a date")
        if self.recommendation_action not in RECOMMENDATION_ACTIONS:
            raise ValueError("Unknown decision recommendation action")
        if (
            self.schema_version != DECISION_RECOMMENDATION_V3_SCHEMA
            and self.recommendation_action not in D2_IMPLEMENTED_ACTIONS
        ):
            raise ValueError("D3 recommendation actions are not implemented")
        if not isinstance(self.requires_human_review, bool):
            raise ValueError("requires_human_review must be boolean")
        if self.schema_version != DECISION_RECOMMENDATION_V3_SCHEMA:
            if (
                self.requires_human_review
                or self.entry_id is not None
                or self.thesis_consistency_status is not None
                or self.rule_evidence is not None
            ):
                raise ValueError("D3 fields require the v3 recommendation schema")
        else:
            expected_human_review = self.recommendation_action in PROTECTED_ACTIONS
            if self.requires_human_review != expected_human_review:
                raise ValueError(
                    "v3 requires_human_review does not match the recommendation action"
                )
            normalized_entry_id = (
                None if self.entry_id is None else str(self.entry_id).strip() or None
            )
            object.__setattr__(self, "entry_id", normalized_entry_id)
            if self.thesis_consistency_status not in {
                None,
                *THESIS_CONSISTENCY_STATUSES,
            }:
                raise ValueError("Unknown thesis consistency status")
            if self.recommendation_action in ENTRY_REQUIRED_ACTIONS:
                if self.entry_id is None:
                    raise ValueError(
                        "Entry-required recommendation requires an original entry id"
                    )
                if self.thesis_consistency_status not in THESIS_CONSISTENCY_STATUSES:
                    raise ValueError(
                        "Entry-required recommendation requires a consistency status"
                    )
            elif self.recommendation_action == RECOMMENDATION_BUY_CANDIDATE:
                if self.entry_id is not None or self.thesis_consistency_status is not None:
                    raise ValueError(
                        "New-buy recommendation cannot carry an existing entry thesis"
                    )
            if not isinstance(self.rule_evidence, Mapping):
                raise ValueError("v3 recommendation requires rule evidence")
            rule_evidence = dict(self.rule_evidence)
            allowed_rule_fields = {
                "has_entry",
                "consistency_status",
                "full_buy_gate_passed",
                "add_evidence_present",
                "hold_logic_present",
                "trim_reason_present",
                "sell_reason_present",
                "exit_condition_present",
                "event_review_current",
                "model_validity_status",
                "blockers",
            }
            unknown_rule_fields = set(rule_evidence) - allowed_rule_fields
            if unknown_rule_fields:
                raise ValueError(
                    "Unknown v3 rule evidence fields: "
                    + ", ".join(sorted(unknown_rule_fields))
                )
            for field in allowed_rule_fields - {"consistency_status", "model_validity_status", "blockers"}:
                if not isinstance(rule_evidence.get(field), bool):
                    raise ValueError(f"v3 rule evidence {field} must be boolean")
            consistency = rule_evidence.get("consistency_status")
            if consistency is not None and consistency not in THESIS_CONSISTENCY_STATUSES:
                raise ValueError("Unknown v3 rule evidence consistency status")
            model_status = str(rule_evidence.get("model_validity_status", ""))
            if model_status not in {"VALID", "STALE", "INVALID", "UNKNOWN"}:
                raise ValueError("Unknown v3 rule evidence model validity status")
            rule_blockers = rule_evidence.get("blockers") or ()
            if not isinstance(rule_blockers, (list, tuple)):
                raise ValueError("v3 rule evidence blockers must be a sequence")
            rule_evidence["blockers"] = [
                str(item) for item in rule_blockers
            ]
            if self.recommendation_action != RECOMMENDATION_NO_ACTION and bool(
                rule_evidence["has_entry"]
            ) != (self.recommendation_action in ENTRY_REQUIRED_ACTIONS):
                raise ValueError("v3 rule evidence entry flag does not match the action")
            if consistency != self.thesis_consistency_status:
                raise ValueError(
                    "v3 rule evidence consistency does not match the recommendation"
                )
            if model_status != self.model_validity.get("status"):
                raise ValueError(
                    "v3 rule evidence model validity does not match the recommendation"
                )
            object.__setattr__(self, "rule_evidence", rule_evidence)
        if self.confidence not in {"高", "中", "低"}:
            raise ValueError("Decision recommendation confidence must be 高, 中 or 低")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision recommendation must remain no_order")
        if self.current_price is not None and (
            not self.current_price.is_finite() or self.current_price <= 0
        ):
            raise ValueError("Current price must be positive and finite")
        if self.portfolio_input_status not in PORTFOLIO_INPUT_STATUSES:
            raise ValueError("Unsupported portfolio input status")
        if self.position_guidance is not None:
            raise ValueError("D2 recommendation cannot invent position guidance")
        if not self.thesis.strip():
            raise ValueError("Decision recommendation requires a thesis")
        if not self.price_bridge_status.strip():
            raise ValueError("Decision recommendation requires a PriceBridge status")
        if not self.price_attractiveness_status.strip():
            raise ValueError("Decision recommendation requires a price status")
        if not self.model_validity.get("status"):
            raise ValueError("Decision recommendation requires model validity status")
        if self.recommendation_action in PROTECTED_ACTIONS:
            if not self.decision_input_sha256 or not _SHA256.fullmatch(
                self.decision_input_sha256
            ):
                raise ValueError(
                    "Protected recommendation requires a dependency fingerprint"
                )
            refs = _validate_dependency_refs(self.decision_dependency_refs)
            roles = {ref["role"] for ref in refs}
            required_roles = (
                _protected_dependency_roles(self.recommendation_action)
                if self.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
                else BASE_PROTECTED_DEPENDENCY_ROLES
            )
            missing = required_roles - roles
            if missing:
                raise ValueError(
                    "Protected recommendation requires repository dependency refs: "
                    + ", ".join(sorted(missing))
                )
            if (
                self.schema_version != DECISION_RECOMMENDATION_V3_SCHEMA
                and
                self.recommendation_action in POSITIVE_ACTIONS
                and "human_approval" not in roles
            ):
                raise ValueError(
                    "Positive recommendation requires a human approval dependency ref"
                )
            if self.recommendation_payload_sha256 is not None and not _SHA256.fullmatch(
                self.recommendation_payload_sha256
            ):
                raise ValueError("Protected recommendation payload fingerprint is invalid")
        if self.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA:
            if (
                self.recommendation_action == RECOMMENDATION_HOLD
                and self.model_validity.get("status") != "VALID"
            ):
                raise ValueError("HOLD requires VALID model validity")
            if self.recommendation_action in {
                RECOMMENDATION_TRIM_CANDIDATE,
                RECOMMENDATION_SELL_CANDIDATE,
            } and not self.recommendation_reasons:
                raise ValueError("Risk-reduction recommendation requires reasons")
            if (
                self.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
                and not self.exit_conditions
            ):
                raise ValueError("SELL recommendation requires exit conditions")
        if self.recommendation_action in POSITIVE_ACTIONS:
            if self.blockers:
                raise ValueError("Positive recommendation cannot carry blockers")
            if self.confidence == "低":
                raise ValueError("Positive recommendation requires medium/high confidence")
            if self.price_attractiveness_status != "RESEARCH_ATTRACTIVE":
                raise ValueError(
                    "Positive recommendation requires RESEARCH_ATTRACTIVE price assessment"
                )
            if self.price_bridge_status != "READY":
                raise ValueError("Positive recommendation requires a READY PriceBridge")
            if self.model_validity["status"] != "VALID":
                raise ValueError("Positive recommendation requires VALID model validity")
            if self.current_price is None or self.entry_zone is None:
                raise ValueError("Positive recommendation requires price and entry zone")
            if any(
                value is None
                for value in (
                    self.valuation_range.bear,
                    self.valuation_range.base,
                    self.valuation_range.bull,
                )
            ):
                raise ValueError(
                    "Positive recommendation requires a complete valuation range"
                )
            if (
                self.margin_of_safety.to_bear is None
                or self.margin_of_safety.to_base is None
            ):
                raise ValueError(
                    "Positive recommendation requires complete margin-of-safety values"
                )
            if not any(ref.get("sha256") for ref in self.evidence_refs):
                raise ValueError(
                    "Positive recommendation requires at least one hash-bound evidence ref"
                )
        object.__setattr__(self, "exit_conditions", tuple(self.exit_conditions))
        object.__setattr__(
            self, "recommendation_reasons", tuple(self.recommendation_reasons)
        )
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        object.__setattr__(
            self, "counter_evidence", tuple(dict(item) for item in self.counter_evidence)
        )
        object.__setattr__(
            self, "thesis_breakers", tuple(dict(item) for item in self.thesis_breakers)
        )
        object.__setattr__(
            self, "next_events", tuple(dict(item) for item in self.next_events)
        )
        object.__setattr__(self, "evidence_refs", _require_refs(self.evidence_refs))
        object.__setattr__(self, "model_validity", dict(self.model_validity))
        object.__setattr__(
            self,
            "input_model_id",
            None if self.input_model_id is None else str(self.input_model_id).strip() or None,
        )
        object.__setattr__(
            self,
            "input_additional_blockers",
            tuple(dict.fromkeys(str(item) for item in self.input_additional_blockers)),
        )
        object.__setattr__(
            self,
            "decision_dependency_refs",
            _validate_dependency_refs(self.decision_dependency_refs),
        )
        if self.recommendation_action in PROTECTED_ACTIONS and self.recommendation_payload_sha256 is None:
            object.__setattr__(
                self,
                "recommendation_payload_sha256",
                recommendation_payload_fingerprint(self.as_policy()),
            )
        if self.recommendation_payload_sha256 is not None:
            expected_payload_sha256 = recommendation_payload_fingerprint(self.as_policy())
            if self.recommendation_payload_sha256 != expected_payload_sha256:
                raise ValueError("Recommendation payload fingerprint does not match")

    @property
    def recommendation_type(self) -> str:
        """Advisory classification, independent of the permanent no-order action."""
        return self.recommendation_action

    def as_policy(self) -> dict[str, Any]:
        recommendation_key = (
            "recommendation_action"
            if self.schema_version == LEGACY_DECISION_RECOMMENDATION_SCHEMA
            else "recommendation_type"
        )
        payload = {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "run_id": self.run_id,
            "decision_as_of": self.decision_as_of.isoformat(),
            recommendation_key: self.recommendation_type,
            "confidence": self.confidence,
            "valuation_range": {
                "bear": _decimal(self.valuation_range.bear),
                "base": _decimal(self.valuation_range.base),
                "bull": _decimal(self.valuation_range.bull),
                "currency": self.valuation_range.currency,
                "basis": self.valuation_range.basis,
            },
            "current_price": _decimal(self.current_price),
            "margin_of_safety": {
                "to_bear": _decimal(self.margin_of_safety.to_bear),
                "to_base": _decimal(self.margin_of_safety.to_base),
            },
            "entry_zone": _price_range_payload(self.entry_zone),
            "reduce_zone": _price_range_payload(self.reduce_zone),
            "exit_conditions": list(self.exit_conditions),
            "thesis": self.thesis,
            "counter_evidence": [dict(item) for item in self.counter_evidence],
            "thesis_breakers": [dict(item) for item in self.thesis_breakers],
            "next_events": [dict(item) for item in self.next_events],
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "model_validity": dict(self.model_validity),
            "price_bridge_status": self.price_bridge_status,
            "price_attractiveness_status": self.price_attractiveness_status,
            "recommendation_reasons": list(self.recommendation_reasons),
            "blockers": list(self.blockers),
            "portfolio_input_status": self.portfolio_input_status,
            "position_guidance": None,
            "action": self.action,
            "decision_input_sha256": self.decision_input_sha256,
            "input_model_id": self.input_model_id,
            "input_additional_blockers": list(self.input_additional_blockers),
            "decision_dependency_refs": [dict(ref) for ref in self.decision_dependency_refs],
            "recommendation_payload_sha256": self.recommendation_payload_sha256,
        }
        if self.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA:
            payload.update(
                {
                    "requires_human_review": self.requires_human_review,
                    "entry_id": self.entry_id,
                    "thesis_consistency_status": self.thesis_consistency_status,
                    "rule_evidence": (
                        None
                        if self.rule_evidence is None
                        else {
                            **self.rule_evidence,
                            "blockers": list(self.rule_evidence.get("blockers") or ()),
                        }
                    ),
                }
            )
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _price_range_payload(value: PriceRange | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"low": str(value.low), "high": str(value.high), "basis": value.basis}


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return parsed


def _price_range_from_payload(value: object, field: str) -> PriceRange | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object or null")
    low = _optional_decimal(value.get("low"), f"{field}.low")
    high = _optional_decimal(value.get("high"), f"{field}.high")
    if low is None or high is None:
        raise ValueError(f"{field} bounds are required")
    return PriceRange(low=low, high=high, basis=str(value.get("basis", "")))


def _strict_optional_bool(value: object, field: str) -> bool:
    """Reject coercible stand-ins so a payload cannot launder a flag."""
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _validate_protected_dependencies(
    recommendation: DecisionRecommendation,
    dependencies: Mapping[str, Any],
) -> None:
    """Bind user-visible recommendation fields to the supplied domain objects."""
    research_case = dependencies["research_case"]
    valuation = dependencies["valuation"]
    model_validity = dependencies["model_validity"]
    price_bridge = dependencies.get("price_bridge")
    price_attractiveness = dependencies.get("price_attractiveness")
    required_roles = (
        _protected_dependency_roles(recommendation.recommendation_action)
        if recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
        else BASE_PROTECTED_DEPENDENCY_ROLES
    )
    if "price_bridge" in required_roles and price_bridge is None:
        raise ValueError("Recommendation requires a PriceBridge dependency")
    if "price_attractiveness" in required_roles and price_attractiveness is None:
        raise ValueError("Recommendation requires a price attractiveness dependency")

    if valuation.symbol != recommendation.symbol:
        raise ValueError("Recommendation valuation symbol does not match payload")
    expected_range = (
        valuation.bear_value,
        valuation.base_value,
        valuation.bull_value,
    )
    actual_range = (
        recommendation.valuation_range.bear,
        recommendation.valuation_range.base,
        recommendation.valuation_range.bull,
    )
    if actual_range != expected_range:
        raise ValueError("Recommendation valuation range does not match dependencies")
    if price_bridge is not None:
        if recommendation.current_price != price_bridge.current_price:
            raise ValueError("Recommendation current price does not match PriceBridge")
        if (
            recommendation.margin_of_safety.to_bear != price_bridge.margin_to_bear
            or recommendation.margin_of_safety.to_base != price_bridge.margin_to_base
        ):
            raise ValueError("Recommendation margins do not match PriceBridge")
        if recommendation.price_bridge_status != price_bridge.bridge_status:
            raise ValueError("Recommendation PriceBridge status does not match dependency")
    elif recommendation.current_price is not None:
        raise ValueError(
            "Recommendation carries a price without a PriceBridge dependency"
        )
    if (
        price_attractiveness is not None
        and recommendation.price_attractiveness_status != price_attractiveness.status
    ):
        raise ValueError("Recommendation price status does not match dependency")
    expected_validity = (
        model_validity.status if model_validity is not None else "UNKNOWN"
    )
    if recommendation.model_validity.get("status") != expected_validity:
        raise ValueError("Recommendation model validity does not match dependency")
    if recommendation.thesis != research_case.thesis:
        raise ValueError("Recommendation thesis does not match ResearchCase")
    if recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA:
        entry = dependencies.get("entry_thesis")
        consistency_review = dependencies.get("investment_consistency_review")
        if recommendation.recommendation_action in ENTRY_REQUIRED_ACTIONS:
            if entry is None or consistency_review is None:
                raise ValueError(
                    "Entry-required recommendation requires entry and consistency review"
                )
            if getattr(entry, "symbol", None) != recommendation.symbol:
                raise ValueError("Entry thesis symbol does not match recommendation")
            if getattr(entry, "entry_id", None) != recommendation.entry_id:
                raise ValueError("Entry thesis id does not match recommendation")
            if getattr(consistency_review, "symbol", None) != recommendation.symbol:
                raise ValueError(
                    "Investment consistency review symbol does not match recommendation"
                )
            if getattr(consistency_review, "entry_id", None) != recommendation.entry_id:
                raise ValueError(
                    "Investment consistency review entry id does not match recommendation"
                )
            if getattr(consistency_review, "status", None) != (
                recommendation.thesis_consistency_status
            ):
                raise ValueError(
                    "Investment consistency status does not match recommendation"
                )
            expected_statuses = {
                RECOMMENDATION_ADD_CANDIDATE: {"CONSISTENT", "FULFILLED"},
                RECOMMENDATION_HOLD: {"CONSISTENT", "FULFILLED"},
                RECOMMENDATION_TRIM_CANDIDATE: {"WEAKENED"},
                RECOMMENDATION_SELL_CANDIDATE: {"BROKEN"},
            }.get(recommendation.recommendation_action, frozenset())
            if recommendation.thesis_consistency_status not in expected_statuses:
                raise ValueError(
                    "Thesis consistency status does not support the recommendation action"
                )
        elif recommendation.recommendation_action == RECOMMENDATION_BUY_CANDIDATE:
            if entry is not None or consistency_review is not None:
                raise ValueError(
                    "New-buy recommendation cannot restore an existing entry thesis"
                )
    if recommendation.recommendation_action in POSITIVE_ACTIONS:
        if recommendation.entry_zone is None:
            raise ValueError("Positive recommendation requires an entry zone")
        if (
            recommendation.entry_zone.low != valuation.bear_value
            or recommendation.entry_zone.high != valuation.base_value
        ):
            raise ValueError("Positive recommendation entry zone changed")
        if recommendation.decision_as_of < max(
            research_case.as_of,
            valuation.valuation_date,
            (
                price_bridge.quote_date
                if price_bridge is not None and price_bridge.quote_date is not None
                else research_case.as_of
            ),
        ):
            raise ValueError("Recommendation decision date predates its dependencies")


def decision_recommendation_from_payload(
    payload: Mapping[str, Any],
    *,
    dependencies: Mapping[str, Any] | None = None,
    verify_dependencies: bool = True,
) -> DecisionRecommendation:
    schema = payload.get("schema_version")
    if schema not in DECISION_RECOMMENDATION_SCHEMAS:
        raise ValueError("Unknown decision recommendation schema")
    recommendation_key = (
        "recommendation_action"
        if schema == LEGACY_DECISION_RECOMMENDATION_SCHEMA
        else "recommendation_type"
    )
    alternate_key = (
        "recommendation_type" if recommendation_key == "recommendation_action"
        else "recommendation_action"
    )
    if recommendation_key not in payload or alternate_key in payload:
        raise ValueError("Recommendation classification does not match its schema")
    v3_fields = {
        "requires_human_review",
        "entry_id",
        "thesis_consistency_status",
        "rule_evidence",
    }
    if schema != DECISION_RECOMMENDATION_V3_SCHEMA and any(
        field in payload for field in v3_fields
    ):
        raise ValueError("D3 fields require the v3 recommendation schema")
    if payload.get(recommendation_key) in PROTECTED_ACTIONS and not payload.get(
        "recommendation_payload_sha256"
    ):
        raise ValueError("Protected recommendation requires a payload fingerprint")
    valuation_range = payload["valuation_range"]
    margin = payload["margin_of_safety"]
    recommendation = DecisionRecommendation(
        symbol=str(payload["symbol"]),
        run_id=str(payload["run_id"]),
        decision_as_of=date.fromisoformat(str(payload["decision_as_of"])),
        recommendation_action=str(payload[recommendation_key]),
        confidence=str(payload["confidence"]),
        valuation_range=ValuationRange(
            bear=_optional_decimal(valuation_range.get("bear"), "valuation_range.bear"),
            base=_optional_decimal(valuation_range.get("base"), "valuation_range.base"),
            bull=_optional_decimal(valuation_range.get("bull"), "valuation_range.bull"),
            currency=str(valuation_range.get("currency", "CNY")),
            basis=str(valuation_range.get("basis", "valuation_result")),
        ),
        current_price=_optional_decimal(payload.get("current_price"), "current_price"),
        margin_of_safety=MarginOfSafety(
            to_bear=_optional_decimal(margin.get("to_bear"), "margin.to_bear"),
            to_base=_optional_decimal(margin.get("to_base"), "margin.to_base"),
        ),
        entry_zone=_price_range_from_payload(payload.get("entry_zone"), "entry_zone"),
        reduce_zone=_price_range_from_payload(payload.get("reduce_zone"), "reduce_zone"),
        exit_conditions=tuple(str(item) for item in payload.get("exit_conditions") or ()),
        thesis=str(payload["thesis"]),
        counter_evidence=tuple(dict(item) for item in payload.get("counter_evidence") or ()),
        thesis_breakers=tuple(dict(item) for item in payload.get("thesis_breakers") or ()),
        next_events=tuple(dict(item) for item in payload.get("next_events") or ()),
        evidence_refs=tuple(dict(item) for item in payload.get("evidence_refs") or ()),
        model_validity=dict(payload["model_validity"]),
        price_bridge_status=str(payload["price_bridge_status"]),
        price_attractiveness_status=str(payload["price_attractiveness_status"]),
        recommendation_reasons=tuple(
            str(item) for item in payload.get("recommendation_reasons") or ()
        ),
        blockers=tuple(str(item) for item in payload.get("blockers") or ()),
        requires_human_review=_strict_optional_bool(
            payload.get("requires_human_review", False), "requires_human_review"
        ),
        entry_id=(
            str(payload["entry_id"])
            if payload.get("entry_id") is not None
            else None
        ),
        thesis_consistency_status=(
            str(payload["thesis_consistency_status"])
            if payload.get("thesis_consistency_status") is not None
            else None
        ),
        rule_evidence=(
            dict(payload["rule_evidence"])
            if payload.get("rule_evidence") is not None
            else None
        ),
        portfolio_input_status=str(
            payload.get("portfolio_input_status", PORTFOLIO_BLOCKED_PRIVATE_INPUT)
        ),
        position_guidance=payload.get("position_guidance"),
        action=str(payload.get("action", ACTION_NO_ORDER)),
        decision_input_sha256=(
            str(payload["decision_input_sha256"])
            if payload.get("decision_input_sha256") is not None
            else None
        ),
        input_model_id=(
            str(payload["input_model_id"])
            if payload.get("input_model_id") is not None
            else None
        ),
        input_additional_blockers=tuple(
            str(item) for item in payload.get("input_additional_blockers") or ()
        ),
        decision_dependency_refs=tuple(
            dict(item) for item in payload.get("decision_dependency_refs") or ()
        ),
        recommendation_payload_sha256=(
            str(payload["recommendation_payload_sha256"])
            if payload.get("recommendation_payload_sha256") is not None
            else None
        ),
        schema_version=str(schema),
    )
    if recommendation.recommendation_action in PROTECTED_ACTIONS and verify_dependencies:
        if dependencies is None:
            raise ValueError(
                "Protected recommendation restoration requires dependency contracts"
            )
        required_dependencies = tuple(
            sorted(_protected_dependency_roles(recommendation.recommendation_action))
            if recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
            else (
                "research_case",
                "valuation",
                "model_validity",
                "price_bridge",
                "price_attractiveness",
                "pre_decision",
                "event_materiality",
            )
        )
        missing = [
            key for key in required_dependencies if dependencies.get(key) is None
        ]
        if missing:
            raise ValueError(
                "Decision dependency contracts are incomplete: "
                + ", ".join(missing)
            )
        if (
            recommendation.recommendation_action in POSITIVE_ACTIONS
            and dependencies.get("human_approval") is None
        ):
            raise ValueError(
                "Positive recommendation restoration requires a raw human approval receipt"
            )
        expected = decision_input_fingerprint(
            research_case=dependencies.get("research_case"),
            valuation=dependencies.get("valuation"),
            model_validity=dependencies.get("model_validity"),
            price_bridge=dependencies.get("price_bridge"),
            price_attractiveness=dependencies.get("price_attractiveness"),
            pre_decision=dependencies.get("pre_decision"),
            human_approval=dependencies.get("human_approval"),
            event_materiality=dependencies.get("event_materiality"),
            decision_as_of=recommendation.decision_as_of,
            model_id=dependencies.get("model_id"),
            research_case_payload=dependencies.get("research_case_payload"),
            facts_payload=dependencies.get("facts_payload"),
            assumptions_payload=dependencies.get("assumptions_payload"),
            additional_blockers=tuple(dependencies.get("additional_blockers") or ()),
            include_d3_dependencies=(
                recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
            ),
            entry_thesis=dependencies.get("entry_thesis"),
            investment_consistency_review=dependencies.get(
                "investment_consistency_review"
            ),
        )
        if recommendation.decision_input_sha256 != expected:
            raise ValueError(
                "Recommendation dependency fingerprint does not match"
            )
        _validate_protected_dependencies(recommendation, dependencies)
    return recommendation


__all__ = [
    "ACTION_NO_ORDER",
    "DECISION_RECOMMENDATION_SCHEMA",
    "DECISION_RECOMMENDATION_SCHEMAS",
    "DECISION_RECOMMENDATION_V3_SCHEMA",
    "D2_IMPLEMENTED_ACTIONS",
    "ENTRY_REQUIRED_ACTIONS",
    "LEGACY_DECISION_RECOMMENDATION_SCHEMA",
    "DecisionRecommendation",
    "MarginOfSafety",
    "PORTFOLIO_BLOCKED_PRIVATE_INPUT",
    "PROTECTED_ACTIONS",
    "PriceRange",
    "RECOMMENDATION_ACTIONS",
    "THESIS_CONSISTENCY_STATUSES",
    "ValuationRange",
    "decision_input_fingerprint",
    "decision_recommendation_from_payload",
]
