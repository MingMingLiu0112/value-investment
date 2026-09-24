"""Reconstructed official-disclosure continuity trace for M3.

This module deliberately is not an Entry, Journal or human decision record.
It reconstructs what official issuer filings show after a frozen historical
research baseline.  The baseline rule remains ``RETROSPECTIVE_RESEARCH_EXTENSION``,
the trace remains ``action=no_order``, and no actual user holding, human
decision or contemporaneous-rule PIT is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .research_artifacts import canonicalize_artifact_payload, sha256_text


TRACE_SCHEMA = "m3-reconstructed-evidence-continuity-v1"
TRACE_NAMESPACE = "RECONSTRUCTED_EVIDENCE_CONTINUITY"
CONCLUSION_RECONSTRUCTED_EVIDENCE_ONLY = "RECONSTRUCTED_EVIDENCE_ONLY"
CONCLUSION_STATUSES = frozenset({CONCLUSION_RECONSTRUCTED_EVIDENCE_ONLY})

DIRECTION_UP = "UP"
DIRECTION_DOWN = "DOWN"
DIRECTION_UNCHANGED = "UNCHANGED"
DIRECTION_NOT_COMPARABLE = "NOT_COMPARABLE"
DIRECTIONS = frozenset(
    {
        DIRECTION_UP,
        DIRECTION_DOWN,
        DIRECTION_UNCHANGED,
        DIRECTION_NOT_COMPARABLE,
    }
)

IMPACT_STRENGTHENED = "STRENGTHENED"
IMPACT_WEAKENED = "WEAKENED"
IMPACT_NEUTRAL = "NEUTRAL"
IMPACT_NOT_COMPARABLE = "NOT_COMPARABLE"
IMPACTS = frozenset(
    {
        IMPACT_STRENGTHENED,
        IMPACT_WEAKENED,
        IMPACT_NEUTRAL,
        IMPACT_NOT_COMPARABLE,
    }
)

METRIC_PARENT_PROFIT = "parent_profit"
METRIC_PARENT_EQUITY = "parent_equity"
METRIC_BASIC_EPS = "basic_eps"
METRIC_ENDING_SHARES = "ending_shares"
METRIC_CLOSE_PRICE = "close_price"
METRIC_CASH_PER_SHARE = "cash_per_share"
METRIC_KEYS = frozenset(
    {
        METRIC_PARENT_PROFIT,
        METRIC_PARENT_EQUITY,
        METRIC_BASIC_EPS,
        METRIC_ENDING_SHARES,
        METRIC_CLOSE_PRICE,
        METRIC_CASH_PER_SHARE,
    }
)

PERIOD_BASIS_BASELINE = "BASELINE"
PERIOD_BASIS_FY = "FY"
PERIOD_BASIS_YTD = "YTD"
PERIOD_BASES = frozenset(
    {
        PERIOD_BASIS_BASELINE,
        PERIOD_BASIS_FY,
        PERIOD_BASIS_YTD,
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object | None) -> str:
    return str(value).strip() if value is not None else ""


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _datetime(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _date(value: object, field: str) -> date:
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO-8601 date") from error
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return parsed


def _change_direction(current: Decimal, comparative: Decimal) -> str:
    if current > comparative:
        return DIRECTION_UP
    if current < comparative:
        return DIRECTION_DOWN
    return DIRECTION_UNCHANGED


def _percentage_change(current: Decimal, comparative: Decimal) -> Decimal | None:
    if comparative == 0:
        return None
    return ((current - comparative) / comparative) * Decimal("100")


@dataclass(frozen=True)
class ContinuityEvidenceReference:
    """One immutable local artifact and its independently checkable source URL."""

    ref_id: str
    kind: str
    path: str
    sha256: str
    source_url: str
    available_at: datetime
    role: str
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _required_text(self.ref_id, "ref_id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "path", _required_text(self.path, "path"))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        object.__setattr__(self, "source_url", _optional_text(self.source_url))
        object.__setattr__(
            self, "available_at", _datetime(self.available_at, "available_at")
        )
        object.__setattr__(self, "role", _required_text(self.role, "role"))
        object.__setattr__(self, "notes", _optional_text(self.notes))

    def as_policy(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "source_url": self.source_url,
            "available_at": self.available_at.isoformat(),
            "role": self.role,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ContinuityMetric:
    """One disclosed metric with its disclosed comparative, if present."""

    metric: str
    period_end: date
    period_basis: str
    current_value: Decimal
    comparative_value: Decimal | None
    unit: str
    reference_id: str
    validation_status: str
    source_label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _required_text(self.metric, "metric"))
        if self.metric not in METRIC_KEYS:
            raise ValueError("Unknown continuity metric")
        object.__setattr__(
            self, "period_end", _date(self.period_end, "period_end")
        )
        object.__setattr__(
            self, "period_basis", _required_text(self.period_basis, "period_basis")
        )
        if self.period_basis not in PERIOD_BASES:
            raise ValueError("Unknown continuity period basis")
        object.__setattr__(
            self, "current_value", _decimal(self.current_value, "current_value")
        )
        if self.current_value <= 0:
            raise ValueError("Continuity metric current value must be positive")
        if self.comparative_value is not None:
            object.__setattr__(
                self,
                "comparative_value",
                _decimal(self.comparative_value, "comparative_value"),
            )
            if self.comparative_value <= 0:
                raise ValueError("Continuity metric comparative value must be positive")
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))
        object.__setattr__(
            self, "reference_id", _required_text(self.reference_id, "reference_id")
        )
        object.__setattr__(
            self,
            "validation_status",
            _required_text(self.validation_status, "validation_status"),
        )
        object.__setattr__(self, "source_label", _optional_text(self.source_label))

    @property
    def change_direction(self) -> str:
        if self.comparative_value is None:
            return DIRECTION_NOT_COMPARABLE
        return _change_direction(self.current_value, self.comparative_value)

    @property
    def percentage_change(self) -> Decimal | None:
        if self.comparative_value is None:
            return None
        return _percentage_change(self.current_value, self.comparative_value)

    def as_policy(self) -> dict[str, Any]:
        change = self.percentage_change
        return {
            "metric": self.metric,
            "period_end": self.period_end.isoformat(),
            "period_basis": self.period_basis,
            "current_value": str(self.current_value),
            "comparative_value": (
                str(self.comparative_value) if self.comparative_value is not None else None
            ),
            "unit": self.unit,
            "reference_id": self.reference_id,
            "validation_status": self.validation_status,
            "source_label": self.source_label,
            "change_direction": self.change_direction,
            "percentage_change": str(change) if change is not None else None,
        }


@dataclass(frozen=True)
class ReconstructedBaseline:
    """Facts already bound by the frozen historical research replay."""

    baseline_date: date
    source_replay_id: str
    rule_version: str
    rule_registered_at: datetime
    rule_registration_status: str
    future_rule_version_used: bool
    strict_contemporaneous_rule_pit: bool
    facts: tuple[ContinuityMetric, ...]
    note: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "baseline_date", _date(self.baseline_date, "baseline_date")
        )
        object.__setattr__(
            self,
            "source_replay_id",
            _required_text(self.source_replay_id, "source_replay_id"),
        )
        object.__setattr__(
            self, "rule_version", _required_text(self.rule_version, "rule_version")
        )
        object.__setattr__(
            self,
            "rule_registered_at",
            _datetime(self.rule_registered_at, "rule_registered_at"),
        )
        object.__setattr__(
            self,
            "rule_registration_status",
            _required_text(self.rule_registration_status, "rule_registration_status"),
        )
        object.__setattr__(
            self,
            "future_rule_version_used",
            bool(self.future_rule_version_used),
        )
        object.__setattr__(
            self,
            "strict_contemporaneous_rule_pit",
            bool(self.strict_contemporaneous_rule_pit),
        )
        if self.strict_contemporaneous_rule_pit:
            raise ValueError("Reconstructed baseline cannot claim strict PIT")
        if not self.future_rule_version_used:
            raise ValueError("Reconstructed baseline must mark the later rule version")
        object.__setattr__(self, "facts", tuple(self.facts))
        if not self.facts:
            raise ValueError("Reconstructed baseline requires facts")
        object.__setattr__(self, "note", _required_text(self.note, "note"))

    def metric(self, key: str) -> ContinuityMetric | None:
        for fact in self.facts:
            if fact.metric == key:
                return fact
        return None

    def as_policy(self) -> dict[str, Any]:
        return {
            "baseline_date": self.baseline_date.isoformat(),
            "source_replay_id": self.source_replay_id,
            "rule_version": self.rule_version,
            "rule_registered_at": self.rule_registered_at.isoformat(),
            "rule_registration_status": self.rule_registration_status,
            "future_rule_version_used": self.future_rule_version_used,
            "strict_contemporaneous_rule_pit": self.strict_contemporaneous_rule_pit,
            "facts": [fact.as_policy() for fact in self.facts],
            "note": self.note,
        }


@dataclass(frozen=True)
class OfficialDisclosureObservation:
    """One official issuer disclosure with extracted metrics."""

    observation_id: str
    disclosure_id: str
    title: str
    report_period: date
    period_basis: str
    available_at: datetime
    evidence_quality: str
    metrics: tuple[ContinuityMetric, ...]
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", _required_text(self.observation_id, "observation_id")
        )
        object.__setattr__(
            self, "disclosure_id", _required_text(self.disclosure_id, "disclosure_id")
        )
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        object.__setattr__(
            self, "report_period", _date(self.report_period, "report_period")
        )
        object.__setattr__(
            self, "period_basis", _required_text(self.period_basis, "period_basis")
        )
        if self.period_basis not in {PERIOD_BASIS_FY, PERIOD_BASIS_YTD}:
            raise ValueError("Official disclosure must be FY or YTD")
        object.__setattr__(
            self, "available_at", _datetime(self.available_at, "available_at")
        )
        object.__setattr__(
            self,
            "evidence_quality",
            _required_text(self.evidence_quality, "evidence_quality"),
        )
        object.__setattr__(self, "metrics", tuple(self.metrics))
        if not self.metrics:
            raise ValueError("Official disclosure requires metrics")
        object.__setattr__(self, "note", _optional_text(self.note))

    def metric(self, key: str) -> ContinuityMetric | None:
        for metric in self.metrics:
            if metric.metric == key:
                return metric
        return None

    def as_policy(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "disclosure_id": self.disclosure_id,
            "title": self.title,
            "report_period": self.report_period.isoformat(),
            "period_basis": self.period_basis,
            "available_at": self.available_at.isoformat(),
            "evidence_quality": self.evidence_quality,
            "metrics": [metric.as_policy() for metric in self.metrics],
            "note": self.note,
        }


@dataclass(frozen=True)
class ContinuityObservationComparison:
    """Arithmetic change for one baseline dimension at one later disclosure."""

    dimension: str
    baseline_value: Decimal
    observation_id: str
    observation_value: Decimal
    change_direction: str
    impact: str
    arithmetic_note: str
    evidence_ref_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dimension", _required_text(self.dimension, "dimension")
        )
        if self.dimension not in METRIC_KEYS:
            raise ValueError("Unknown continuity comparison dimension")
        object.__setattr__(
            self, "baseline_value", _decimal(self.baseline_value, "baseline_value")
        )
        object.__setattr__(
            self,
            "observation_id",
            _required_text(self.observation_id, "observation_id"),
        )
        object.__setattr__(
            self,
            "observation_value",
            _decimal(self.observation_value, "observation_value"),
        )
        object.__setattr__(
            self,
            "change_direction",
            _required_text(self.change_direction, "change_direction"),
        )
        if self.change_direction not in DIRECTIONS:
            raise ValueError("Unknown continuity change direction")
        object.__setattr__(self, "impact", _required_text(self.impact, "impact"))
        if self.impact not in IMPACTS:
            raise ValueError("Unknown continuity impact")
        object.__setattr__(
            self,
            "arithmetic_note",
            _required_text(self.arithmetic_note, "arithmetic_note"),
        )
        object.__setattr__(
            self, "evidence_ref_ids", tuple(dict.fromkeys(self.evidence_ref_ids))
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "baseline_value": str(self.baseline_value),
            "observation_id": self.observation_id,
            "observation_value": str(self.observation_value),
            "change_direction": self.change_direction,
            "impact": self.impact,
            "arithmetic_note": self.arithmetic_note,
            "evidence_ref_ids": list(self.evidence_ref_ids),
        }


@dataclass(frozen=True)
class M3ReconstructedEvidenceContinuity:
    """Public reconstructed evidence trace; never an investment decision."""

    trace_id: str
    schema_version: str
    namespace: str
    symbol: str
    generated_at: datetime
    baseline: ReconstructedBaseline
    disclosures: tuple[OfficialDisclosureObservation, ...]
    comparisons: tuple[ContinuityObservationComparison, ...]
    evidence_references: tuple[ContinuityEvidenceReference, ...]
    conclusion_status: str
    actual_entry_present: bool
    human_decision: str | None
    requires_human_review: bool
    blockers: tuple[str, ...]
    action: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "trace_id", _required_text(self.trace_id, "trace_id")
        )
        if self.schema_version != TRACE_SCHEMA:
            raise ValueError("Unknown reconstructed continuity schema")
        if self.namespace != TRACE_NAMESPACE:
            raise ValueError("Unknown reconstructed continuity namespace")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Reconstructed continuity symbol must contain six digits")
        object.__setattr__(
            self, "generated_at", _datetime(self.generated_at, "generated_at")
        )
        object.__setattr__(
            self, "disclosures", tuple(self.disclosures)
        )
        if not self.disclosures:
            raise ValueError("Reconstructed continuity requires disclosures")
        object.__setattr__(
            self, "comparisons", tuple(self.comparisons)
        )
        if not self.comparisons:
            raise ValueError("Reconstructed continuity requires comparisons")
        object.__setattr__(
            self,
            "evidence_references",
            tuple(self.evidence_references),
        )
        if not self.evidence_references:
            raise ValueError("Reconstructed continuity requires evidence references")

        ref_ids = {ref.ref_id for ref in self.evidence_references}
        if len(ref_ids) != len(self.evidence_references):
            raise ValueError("Reconstructed continuity evidence ids must be unique")
        baseline_ids = {metric.reference_id for metric in self.baseline.facts}
        observation_ids = set()
        for disclosure in self.disclosures:
            if disclosure.observation_id in observation_ids:
                raise ValueError("Reconstructed continuity observation ids must be unique")
            observation_ids.add(disclosure.observation_id)
            if disclosure.available_at.date() <= self.baseline.baseline_date:
                raise ValueError("Reconstructed disclosure cannot predate its baseline")
            for metric in disclosure.metrics:
                if metric.reference_id not in ref_ids:
                    raise ValueError("Reconstructed disclosure metric references unknown evidence")
        if any(ref_id not in ref_ids for ref_id in baseline_ids):
            raise ValueError("Reconstructed baseline fact references unknown evidence")
        for comparison in self.comparisons:
            if comparison.observation_id not in observation_ids:
                raise ValueError("Reconstructed comparison references unknown observation")
            if any(ref_id not in ref_ids for ref_id in comparison.evidence_ref_ids):
                raise ValueError("Reconstructed comparison references unknown evidence")

        object.__setattr__(
            self,
            "conclusion_status",
            _required_text(self.conclusion_status, "conclusion_status"),
        )
        if self.conclusion_status not in CONCLUSION_STATUSES:
            raise ValueError("Unknown reconstructed continuity conclusion")
        if self.actual_entry_present:
            raise ValueError("Reconstructed trace cannot contain an actual entry")
        if self.human_decision is not None:
            raise ValueError("Reconstructed trace cannot contain a human decision")
        if not self.requires_human_review:
            raise ValueError("Reconstructed trace requires human review")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Reconstructed trace must remain no_order")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))

    @property
    def trace_sha256(self) -> str:
        return sha256_text(canonicalize_artifact_payload(self.as_policy()))

    def as_policy(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "symbol": self.symbol,
            "generated_at": self.generated_at.isoformat(),
            "baseline": self.baseline.as_policy(),
            "disclosures": [item.as_policy() for item in self.disclosures],
            "comparisons": [item.as_policy() for item in self.comparisons],
            "evidence_references": [item.as_policy() for item in self.evidence_references],
            "conclusion_status": self.conclusion_status,
            "actual_entry_present": self.actual_entry_present,
            "human_decision": self.human_decision,
            "requires_human_review": self.requires_human_review,
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


def _metric_from_payload(payload: Mapping[str, Any]) -> ContinuityMetric:
    return ContinuityMetric(
        metric=str(payload.get("metric") or ""),
        period_end=_date(payload.get("period_end"), "period_end"),
        period_basis=str(payload.get("period_basis") or ""),
        current_value=payload.get("current_value"),
        comparative_value=payload.get("comparative_value"),
        unit=str(payload.get("unit") or ""),
        reference_id=str(payload.get("reference_id") or ""),
        validation_status=str(payload.get("validation_status") or ""),
        source_label=str(payload.get("source_label") or ""),
    )


def from_payload(payload: Mapping[str, Any]) -> M3ReconstructedEvidenceContinuity:
    """Decode a public reconstructed continuity payload."""
    if payload.get("schema_version") != TRACE_SCHEMA:
        raise ValueError("Unknown reconstructed continuity schema")
    evidence = tuple(
        ContinuityEvidenceReference(
            ref_id=str(item.get("ref_id") or ""),
            kind=str(item.get("kind") or ""),
            path=str(item.get("path") or ""),
            sha256=str(item.get("sha256") or ""),
            source_url=str(item.get("source_url") or ""),
            available_at=_datetime(item.get("available_at"), "available_at"),
            role=str(item.get("role") or ""),
            notes=str(item.get("notes") or ""),
        )
        for item in payload.get("evidence_references") or ()
    )
    baseline_raw = payload.get("baseline")
    if not isinstance(baseline_raw, Mapping):
        raise ValueError("Reconstructed baseline is required")
    baseline = ReconstructedBaseline(
        baseline_date=_date(baseline_raw.get("baseline_date"), "baseline_date"),
        source_replay_id=str(baseline_raw.get("source_replay_id") or ""),
        rule_version=str(baseline_raw.get("rule_version") or ""),
        rule_registered_at=_datetime(
            baseline_raw.get("rule_registered_at"), "rule_registered_at"
        ),
        rule_registration_status=str(baseline_raw.get("rule_registration_status") or ""),
        future_rule_version_used=bool(baseline_raw.get("future_rule_version_used")),
        strict_contemporaneous_rule_pit=bool(
            baseline_raw.get("strict_contemporaneous_rule_pit")
        ),
        facts=tuple(_metric_from_payload(item) for item in baseline_raw.get("facts") or ()),
        note=str(baseline_raw.get("note") or ""),
    )
    disclosures = tuple(
        OfficialDisclosureObservation(
            observation_id=str(item.get("observation_id") or ""),
            disclosure_id=str(item.get("disclosure_id") or ""),
            title=str(item.get("title") or ""),
            report_period=_date(item.get("report_period"), "report_period"),
            period_basis=str(item.get("period_basis") or ""),
            available_at=_datetime(item.get("available_at"), "available_at"),
            evidence_quality=str(item.get("evidence_quality") or ""),
            metrics=tuple(_metric_from_payload(metric) for metric in item.get("metrics") or ()),
            note=str(item.get("note") or ""),
        )
        for item in payload.get("disclosures") or ()
    )
    comparisons = tuple(
        ContinuityObservationComparison(
            dimension=str(item.get("dimension") or ""),
            baseline_value=item.get("baseline_value"),
            observation_id=str(item.get("observation_id") or ""),
            observation_value=item.get("observation_value"),
            change_direction=str(item.get("change_direction") or ""),
            impact=str(item.get("impact") or ""),
            arithmetic_note=str(item.get("arithmetic_note") or ""),
            evidence_ref_ids=tuple(item.get("evidence_ref_ids") or ()),
        )
        for item in payload.get("comparisons") or ()
    )
    return M3ReconstructedEvidenceContinuity(
        trace_id=str(payload.get("trace_id") or ""),
        schema_version=str(payload.get("schema_version") or ""),
        namespace=str(payload.get("namespace") or ""),
        symbol=str(payload.get("symbol") or ""),
        generated_at=_datetime(payload.get("generated_at"), "generated_at"),
        baseline=baseline,
        disclosures=disclosures,
        comparisons=comparisons,
        evidence_references=evidence,
        conclusion_status=str(payload.get("conclusion_status") or ""),
        actual_entry_present=bool(payload.get("actual_entry_present")),
        human_decision=payload.get("human_decision"),
        requires_human_review=bool(payload.get("requires_human_review")),
        blockers=tuple(payload.get("blockers") or ()),
        action=str(payload.get("action") or ""),
    )
