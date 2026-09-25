"""Evidence-bound contracts for historical validation admission.

This module answers one narrow question: may a historical replay be described
as a strict point-in-time strategy replay, a retrospective policy replay, or
not PIT-safe at all?  It does not value a company, generate orders, or replace
the existing virtual-account/backtest mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PureWindowsPath
import re
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "historical-validation-admission-v1"
POLICY_VERSION = "historical-validation-policy-v1"
ACTION_NO_ORDER = "no_order"

STRICT_CONTEMPORANEOUS_REPLAY = "STRICT_CONTEMPORANEOUS_REPLAY"
RETROSPECTIVE_POLICY_REPLAY = "RETROSPECTIVE_POLICY_REPLAY"
NOT_PIT_SAFE = "NOT_PIT_SAFE"
CLASSIFICATIONS = (
    STRICT_CONTEMPORANEOUS_REPLAY,
    RETROSPECTIVE_POLICY_REPLAY,
    NOT_PIT_SAFE,
)

ADMITTED_FOR_STRICT_REPLAY = "ADMITTED_FOR_STRICT_REPLAY"
ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH = (
    "ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH"
)
NOT_ADMITTED = "NOT_ADMITTED"
ADMISSION_STATUSES = (
    ADMITTED_FOR_STRICT_REPLAY,
    ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH,
    NOT_ADMITTED,
)

PIT_VERIFIED = "VERIFIED"
PIT_CONSERVATIVE = "CONSERVATIVE"
PIT_UNSUPPORTED = "UNSUPPORTED"
PIT_NOT_PROVEN = "NOT_PROVEN"
PIT_NOT_APPLICABLE = "NOT_APPLICABLE"
PIT_STATUSES = (
    PIT_VERIFIED,
    PIT_CONSERVATIVE,
    PIT_UNSUPPORTED,
    PIT_NOT_PROVEN,
    PIT_NOT_APPLICABLE,
)

RULE_CONTEMPORANEOUS = "CONTEMPORANEOUS_RULE"
RULE_RETROSPECTIVE = "RETROSPECTIVE_RESEARCH_EXTENSION"
RULE_STATUSES = (RULE_CONTEMPORANEOUS, RULE_RETROSPECTIVE)

SURVIVORSHIP_CONTROLLED = "CONTROLLED"
SURVIVORSHIP_UNRESOLVED = "UNRESOLVED"
SURVIVORSHIP_NOT_APPLICABLE = "NOT_APPLICABLE"
SURVIVORSHIP_STATUSES = (
    SURVIVORSHIP_CONTROLLED,
    SURVIVORSHIP_UNRESOLVED,
    SURVIVORSHIP_NOT_APPLICABLE,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _sha256(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return text


def _iso_date(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 date") from error
    if parsed.isoformat() != text:
        raise ValueError(f"{field_name} must be an ISO-8601 date")
    return text


def _unique_texts(values: Iterable[object], field_name: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _required_text(value, field_name)
        if text not in result:
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class EvidenceReference:
    """A retained artifact that can be independently re-hashed."""

    evidence_id: str
    kind: str
    path: str
    sha256: str
    available_at: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _required_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        path = _required_text(self.path, "path").replace("\\", "/")
        if (
            Path(path).is_absolute()
            or PureWindowsPath(path).is_absolute()
            or ".." in Path(path).parts
        ):
            raise ValueError("evidence path must be repository-relative and must not escape it")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        if self.available_at is not None:
            object.__setattr__(self, "available_at", _required_text(self.available_at, "available_at"))
        if self.source_url is not None:
            object.__setattr__(self, "source_url", _required_text(self.source_url, "source_url"))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
        }
        if self.available_at is not None:
            payload["available_at"] = self.available_at
        if self.source_url is not None:
            payload["source_url"] = self.source_url
        return payload


@dataclass(frozen=True)
class PitAssessment:
    """One point-in-time dimension, with explicit non-proof state."""

    status: str
    detail: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in PIT_STATUSES:
            raise ValueError(f"Unsupported PIT status: {self.status}")
        object.__setattr__(self, "detail", _required_text(self.detail, "detail"))
        object.__setattr__(self, "evidence_refs", _unique_texts(self.evidence_refs, "evidence_ref"))
        object.__setattr__(self, "blockers", _unique_texts(self.blockers, "blocker"))
        if self.status in (PIT_VERIFIED, PIT_CONSERVATIVE) and not self.evidence_refs:
            raise ValueError("A proven or conservative PIT assessment requires evidence")
        if self.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN) and not self.blockers:
            raise ValueError("An unsupported PIT assessment requires an explicit blocker")

    @property
    def is_proven(self) -> bool:
        return self.status in (PIT_VERIFIED, PIT_CONSERVATIVE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class ExecutionContract:
    """Frozen execution assumptions and the evidence boundary for them."""

    signal_to_fill: str
    settlement: str
    board_lot: int
    cash_policy: str
    suspension_policy: str
    price_limit_policy: str
    liquidity_policy: str
    corporate_action_policy: str
    fee_policy: str
    status: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.signal_to_fill != "next_session_open":
            raise ValueError("Historical validation requires next-session-open execution")
        if self.settlement != "T+1":
            raise ValueError("Historical validation requires an explicit T+1 settlement contract")
        if type(self.board_lot) is not int or self.board_lot not in (1, 100):
            raise ValueError("board_lot must be the A-share board lot (1 or 100 shares)")
        for name in (
            "cash_policy",
            "suspension_policy",
            "price_limit_policy",
            "liquidity_policy",
            "corporate_action_policy",
            "fee_policy",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.status not in PIT_STATUSES:
            raise ValueError(f"Unsupported execution status: {self.status}")
        object.__setattr__(self, "evidence_refs", _unique_texts(self.evidence_refs, "evidence_ref"))
        object.__setattr__(self, "blockers", _unique_texts(self.blockers, "blocker"))
        if self.status in (PIT_VERIFIED, PIT_CONSERVATIVE) and not self.evidence_refs:
            raise ValueError("A proven or conservative execution contract requires evidence")
        if self.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN) and not self.blockers:
            raise ValueError("An unsupported execution contract requires an explicit blocker")

    @property
    def is_proven(self) -> bool:
        return self.status in (PIT_VERIFIED, PIT_CONSERVATIVE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_to_fill": self.signal_to_fill,
            "settlement": self.settlement,
            "board_lot": self.board_lot,
            "cash_policy": self.cash_policy,
            "suspension_policy": self.suspension_policy,
            "price_limit_policy": self.price_limit_policy,
            "liquidity_policy": self.liquidity_policy,
            "corporate_action_policy": self.corporate_action_policy,
            "fee_policy": self.fee_policy,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
        }


def _classification(
    *,
    facts_pit: PitAssessment,
    assumptions_pit: PitAssessment,
    valuation_pit: PitAssessment,
    quote_pit: PitAssessment,
    corporate_actions_pit: PitAssessment,
    fees_pit: PitAssessment,
    execution_contract: ExecutionContract,
    portfolio_context: PitAssessment,
    benchmark_contract: PitAssessment,
    universe_pit: PitAssessment,
    survivorship_status: str,
    approved_value_model_sessions: int,
    rule_registration_status: str,
    rule_evidence_refs: Sequence[str],
) -> str:
    critical = (
        facts_pit,
        assumptions_pit,
        valuation_pit,
        quote_pit,
        corporate_actions_pit,
        portfolio_context,
        benchmark_contract,
        universe_pit,
    )
    if approved_value_model_sessions <= 0:
        return NOT_PIT_SAFE
    if survivorship_status != SURVIVORSHIP_CONTROLLED:
        return NOT_PIT_SAFE
    if any(item.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN) for item in critical):
        return NOT_PIT_SAFE
    if fees_pit.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN):
        return NOT_PIT_SAFE
    if execution_contract.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN):
        return NOT_PIT_SAFE
    if any(item.status != PIT_VERIFIED for item in critical):
        return NOT_PIT_SAFE
    if fees_pit.status not in (PIT_VERIFIED, PIT_CONSERVATIVE):
        return NOT_PIT_SAFE
    if execution_contract.status not in (PIT_VERIFIED, PIT_CONSERVATIVE):
        return NOT_PIT_SAFE
    if not rule_evidence_refs:
        return NOT_PIT_SAFE
    if rule_registration_status != RULE_CONTEMPORANEOUS:
        return RETROSPECTIVE_POLICY_REPLAY
    return STRICT_CONTEMPORANEOUS_REPLAY


def _admission_status(classification: str) -> str:
    if classification == STRICT_CONTEMPORANEOUS_REPLAY:
        return ADMITTED_FOR_STRICT_REPLAY
    if classification == RETROSPECTIVE_POLICY_REPLAY:
        return ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH
    return NOT_ADMITTED


@dataclass(frozen=True)
class HistoricalValidationAdmission:
    """The gate for one historical replay scope.

    ``approved_value_model_sessions`` is deliberately explicit.  A historical
    research range, a conditional DCF, or a current model copied backwards must
    never be counted as an approved point-in-time value model.
    """

    admission_id: str
    symbol: str
    scope: str
    window_start: str
    window_end: str
    information_cutoff_policy: str
    rule_version: str
    rule_registration_status: str
    rule_evidence_refs: tuple[str, ...]
    facts_pit: PitAssessment
    assumptions_pit: PitAssessment
    valuation_pit: PitAssessment
    quote_pit: PitAssessment
    corporate_actions_pit: PitAssessment
    fees_pit: PitAssessment
    execution_contract: ExecutionContract
    portfolio_context: PitAssessment
    benchmark_contract: PitAssessment
    universe_pit: PitAssessment
    survivorship_status: str
    approved_value_model_sessions: int
    blockers: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[EvidenceReference, ...] = field(default_factory=tuple)
    action: str = ACTION_NO_ORDER
    classification: str = ""
    admission_status: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission_id", _required_text(self.admission_id, "admission_id"))
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        start = _iso_date(self.window_start, "window_start")
        end = _iso_date(self.window_end, "window_end")
        if start > end:
            raise ValueError("window_start must not be after window_end")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)
        object.__setattr__(self, "information_cutoff_policy", _required_text(self.information_cutoff_policy, "information_cutoff_policy"))
        object.__setattr__(self, "rule_version", _required_text(self.rule_version, "rule_version"))
        if self.rule_registration_status not in RULE_STATUSES:
            raise ValueError("Unsupported rule registration status")
        object.__setattr__(self, "rule_evidence_refs", _unique_texts(self.rule_evidence_refs, "rule_evidence_ref"))
        if type(self.approved_value_model_sessions) is not int or self.approved_value_model_sessions < 0:
            raise ValueError("approved_value_model_sessions must be a non-negative integer")
        if self.survivorship_status not in SURVIVORSHIP_STATUSES:
            raise ValueError("Unsupported survivorship status")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Historical validation admission must remain action=no_order")
        object.__setattr__(self, "blockers", _unique_texts(self.blockers, "blocker"))
        if not self.evidence_refs:
            raise ValueError("Historical validation admission requires evidence")
        if len({ref.evidence_id for ref in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Evidence ids must be unique")
        evidence_ids = {ref.evidence_id for ref in self.evidence_refs}
        dimension_refs = {
            ref
            for item in (
                self.facts_pit,
                self.assumptions_pit,
                self.valuation_pit,
                self.quote_pit,
                self.corporate_actions_pit,
                self.fees_pit,
                self.portfolio_context,
                self.benchmark_contract,
                self.universe_pit,
            )
            for ref in item.evidence_refs
        } | set(self.execution_contract.evidence_refs)
        unknown_refs = dimension_refs - evidence_ids
        if unknown_refs:
            raise ValueError(
                "PIT assessments reference evidence ids absent from the admission manifest: "
                + ", ".join(sorted(unknown_refs))
            )
        unknown_rule_refs = set(self.rule_evidence_refs) - evidence_ids
        if unknown_rule_refs:
            raise ValueError(
                "Rule evidence references ids absent from the admission manifest: "
                + ", ".join(sorted(unknown_rule_refs))
            )
        computed = _classification(
            facts_pit=self.facts_pit,
            assumptions_pit=self.assumptions_pit,
            valuation_pit=self.valuation_pit,
            quote_pit=self.quote_pit,
            corporate_actions_pit=self.corporate_actions_pit,
            fees_pit=self.fees_pit,
            execution_contract=self.execution_contract,
            portfolio_context=self.portfolio_context,
            benchmark_contract=self.benchmark_contract,
            universe_pit=self.universe_pit,
            survivorship_status=self.survivorship_status,
            approved_value_model_sessions=self.approved_value_model_sessions,
            rule_registration_status=self.rule_registration_status,
            rule_evidence_refs=self.rule_evidence_refs,
        )
        if self.classification and self.classification != computed:
            raise ValueError("classification does not match the supplied PIT evidence")
        if self.admission_status and self.admission_status != _admission_status(computed):
            raise ValueError("admission_status does not match classification")
        object.__setattr__(self, "classification", computed)
        object.__setattr__(self, "admission_status", _admission_status(computed))
        if computed == NOT_PIT_SAFE and not self.blockers:
            raise ValueError("NOT_PIT_SAFE admission requires an explicit blocker")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "admission_id": self.admission_id,
            "symbol": self.symbol,
            "scope": self.scope,
            "window": {"start": self.window_start, "end": self.window_end},
            "information_cutoff_policy": self.information_cutoff_policy,
            "rule_version": self.rule_version,
            "rule_registration_status": self.rule_registration_status,
            "rule_evidence_refs": list(self.rule_evidence_refs),
            "facts_pit": self.facts_pit.as_dict(),
            "assumptions_pit": self.assumptions_pit.as_dict(),
            "valuation_pit": self.valuation_pit.as_dict(),
            "quote_pit": self.quote_pit.as_dict(),
            "corporate_actions_pit": self.corporate_actions_pit.as_dict(),
            "fees_pit": self.fees_pit.as_dict(),
            "execution_contract": self.execution_contract.as_dict(),
            "portfolio_context": self.portfolio_context.as_dict(),
            "benchmark_contract": self.benchmark_contract.as_dict(),
            "universe_pit": self.universe_pit.as_dict(),
            "survivorship_status": self.survivorship_status,
            "approved_value_model_sessions": self.approved_value_model_sessions,
            "classification": self.classification,
            "admission_status": self.admission_status,
            "blockers": list(self.blockers),
            "evidence_refs": [ref.as_dict() for ref in self.evidence_refs],
            "action": self.action,
        }


__all__ = [
    "SCHEMA_VERSION",
    "POLICY_VERSION",
    "ACTION_NO_ORDER",
    "STRICT_CONTEMPORANEOUS_REPLAY",
    "RETROSPECTIVE_POLICY_REPLAY",
    "NOT_PIT_SAFE",
    "CLASSIFICATIONS",
    "ADMITTED_FOR_STRICT_REPLAY",
    "ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH",
    "NOT_ADMITTED",
    "ADMISSION_STATUSES",
    "PIT_VERIFIED",
    "PIT_CONSERVATIVE",
    "PIT_UNSUPPORTED",
    "PIT_NOT_PROVEN",
    "PIT_NOT_APPLICABLE",
    "PIT_STATUSES",
    "RULE_CONTEMPORANEOUS",
    "RULE_RETROSPECTIVE",
    "RULE_STATUSES",
    "SURVIVORSHIP_CONTROLLED",
    "SURVIVORSHIP_UNRESOLVED",
    "SURVIVORSHIP_NOT_APPLICABLE",
    "SURVIVORSHIP_STATUSES",
    "EvidenceReference",
    "PitAssessment",
    "ExecutionContract",
    "HistoricalValidationAdmission",
]
