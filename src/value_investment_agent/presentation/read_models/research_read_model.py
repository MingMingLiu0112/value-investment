"""Minimal point-in-time research dossier read model.

This module turns retained research facts into a presentation-facing view.  It
keeps completed work, unknown work, missing work and blockers visibly separate,
and it never turns a research state into an order or position.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any, Mapping, Sequence


DOSSIER_SCHEMA_VERSION = "research-dossier-v1"
ACTION_NO_ORDER = "no_order"

STATEMENT_FACT = "fact"
STATEMENT_INTERPRETATION = "interpretation"
STATEMENT_HYPOTHESIS = "hypothesis"
STATEMENT_GAP = "gap"
STATEMENT_KINDS = frozenset(
    {
        STATEMENT_FACT,
        STATEMENT_INTERPRETATION,
        STATEMENT_HYPOTHESIS,
        STATEMENT_GAP,
    }
)

SECTION_COMPLETE = "COMPLETE"
SECTION_PARTIAL = "PARTIAL"
SECTION_UNKNOWN = "UNKNOWN"
SECTION_MISSING = "MISSING"
SECTION_NOT_APPLICABLE = "NOT_APPLICABLE"
SECTION_BLOCKED = "BLOCKED"
SECTION_NOT_STARTED = "NOT_STARTED"
SECTION_STATUSES = frozenset(
    {
        SECTION_COMPLETE,
        SECTION_PARTIAL,
        SECTION_UNKNOWN,
        SECTION_MISSING,
        SECTION_NOT_APPLICABLE,
        SECTION_BLOCKED,
        SECTION_NOT_STARTED,
    }
)

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNKNOWN = "UNKNOWN"
CONFIDENCE_STATUSES = frozenset(
    {
        CONFIDENCE_HIGH,
        CONFIDENCE_MEDIUM,
        CONFIDENCE_LOW,
        CONFIDENCE_UNKNOWN,
    }
)

DOSSIER_READABLE = "READABLE"
DOSSIER_PARTIAL = "PARTIAL"
DOSSIER_NOT_STARTED = "NOT_STARTED"
DOSSIER_BLOCKED = "BLOCKED"

SECTION_BUSINESS_QUALITY = "business_quality"
SECTION_FINANCIAL_QUALITY = "financial_quality"
SECTION_CAPITAL_ALLOCATION = "capital_allocation"
SECTION_THESIS = "thesis"
SECTION_COUNTER_EVIDENCE = "counter_evidence"
SECTION_THESIS_BREAKERS = "thesis_breakers"
SECTION_NEXT_EVENTS = "next_events"
SECTION_RESEARCH_GAPS = "research_gaps"

REQUIRED_SECTION_KEYS = frozenset(
    {
        SECTION_BUSINESS_QUALITY,
        SECTION_FINANCIAL_QUALITY,
        SECTION_CAPITAL_ALLOCATION,
        SECTION_THESIS,
        SECTION_COUNTER_EVIDENCE,
        SECTION_THESIS_BREAKERS,
        SECTION_NEXT_EVENTS,
        SECTION_RESEARCH_GAPS,
    }
)

BUSINESS_DIMENSION_MOAT = "moat"
BUSINESS_DIMENSION_PRICING_CUSTOMERS = "pricing_customers"
BUSINESS_DIMENSION_INDUSTRY_STRUCTURE = "industry_structure"
BUSINESS_DIMENSION_ROIC = "roic_and_incremental_roic"
BUSINESS_DIMENSION_REINVESTMENT = "reinvestment"
BUSINESS_DIMENSION_CAPITAL_INTENSITY = "capital_intensity"
BUSINESS_DIMENSION_CASH_CONVERSION = "cash_conversion"
BUSINESS_DIMENSION_DURATION = "competitive_advantage_duration"
REQUIRED_BUSINESS_DIMENSIONS = frozenset(
    {
        BUSINESS_DIMENSION_MOAT,
        BUSINESS_DIMENSION_PRICING_CUSTOMERS,
        BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
        BUSINESS_DIMENSION_ROIC,
        BUSINESS_DIMENSION_REINVESTMENT,
        BUSINESS_DIMENSION_CAPITAL_INTENSITY,
        BUSINESS_DIMENSION_CASH_CONVERSION,
        BUSINESS_DIMENSION_DURATION,
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_KEYS = frozenset(
    {
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "proposed_entry",
        "buy",
        "sell",
        "live_eligible",
    }
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{field} must be a date")
    return value


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _ref_ids(value: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(_required_text(item, "evidence reference id") for item in value)
    if len(set(refs)) != len(refs):
        raise ValueError("Research statement evidence ids must be unique")
    return refs


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Research dossier numbers must be finite")
        return str(value)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Research dossier timestamps must include a timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
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
            raise ValueError("Research dossier numbers must be finite")
        return value
    raise TypeError(f"Unsupported research dossier value: {type(value).__name__}")


@dataclass(frozen=True)
class ResearchStatement:
    """One evidence-graded statement inside a dossier section."""

    kind: str
    text: str
    confidence: str
    status: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in STATEMENT_KINDS:
            raise ValueError("Unknown research statement kind")
        object.__setattr__(self, "text", _required_text(self.text, "statement text"))
        if self.confidence not in CONFIDENCE_STATUSES:
            raise ValueError("Unknown research statement confidence")
        if self.status not in SECTION_STATUSES:
            raise ValueError("Unknown research statement status")
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.kind in {STATEMENT_FACT, STATEMENT_INTERPRETATION} and not self.evidence_refs:
            raise ValueError("Facts and interpretations require evidence references")

    def as_policy(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "confidence": self.confidence,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ResearchDimension:
    """Explicit unknown/not-applicable state for a research dimension."""

    key: str
    status: str
    observation: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _required_text(self.key, "dimension key"))
        if self.status not in SECTION_STATUSES:
            raise ValueError("Unknown research dimension status")
        object.__setattr__(
            self,
            "observation",
            _required_text(self.observation, "dimension observation"),
        )
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "observation": self.observation,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ResearchSection:
    """A named research section with visible completion or gap state."""

    key: str
    title: str
    status: str
    findings: tuple[ResearchStatement, ...] = ()
    dimensions: tuple[ResearchDimension, ...] = ()
    blockers: tuple[str, ...] = ()
    explanation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _required_text(self.key, "section key"))
        object.__setattr__(self, "title", _required_text(self.title, "section title"))
        if self.status not in SECTION_STATUSES:
            raise ValueError("Unknown research section status")
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "dimensions", tuple(self.dimensions))
        object.__setattr__(
            self,
            "blockers",
            tuple(_required_text(item, "section blocker") for item in self.blockers),
        )
        object.__setattr__(self, "explanation", self.explanation.strip())

    @property
    def is_complete(self) -> bool:
        return self.status in {SECTION_COMPLETE, SECTION_NOT_APPLICABLE}

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        refs: list[str] = []
        for finding in self.findings:
            refs.extend(finding.evidence_refs)
        for dimension in self.dimensions:
            refs.extend(dimension.evidence_refs)
        return tuple(dict.fromkeys(refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "findings": [finding.as_policy() for finding in self.findings],
            "dimensions": [dimension.as_policy() for dimension in self.dimensions],
            "blockers": list(self.blockers),
            "explanation": self.explanation,
        }


def _section_from_payload(payload: Mapping[str, Any]) -> ResearchSection:
    data = dict(payload)
    key = _required_text(data.get("key"), "section key")
    title = _required_text(data.get("title"), "section title")
    status = _required_text(data.get("status"), "section status")
    findings = tuple(
        ResearchStatement(
            kind=_required_text(item.get("kind"), "statement kind"),
            text=_required_text(item.get("text"), "statement text"),
            confidence=_required_text(item.get("confidence"), "statement confidence"),
            status=_required_text(item.get("status"), "statement status"),
            evidence_refs=tuple(
                _required_text(ref, "statement evidence reference")
                for ref in (item.get("evidence_refs") or [])
            ),
        )
        for item in (data.get("findings") or [])
    )
    dimensions = tuple(
        ResearchDimension(
            key=_required_text(item.get("key"), "dimension key"),
            status=_required_text(item.get("status"), "dimension status"),
            observation=_required_text(
                item.get("observation"), "dimension observation"
            ),
            evidence_refs=tuple(
                _required_text(ref, "dimension evidence reference")
                for ref in (item.get("evidence_refs") or [])
            ),
        )
        for item in (data.get("dimensions") or [])
    )
    return ResearchSection(
        key=key,
        title=title,
        status=status,
        findings=findings,
        dimensions=dimensions,
        blockers=tuple(str(item) for item in (data.get("blockers") or [])),
        explanation=str(data.get("explanation") or ""),
    )


def _normalize_evidence_refs(
    refs: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in refs:
        ref = dict(raw)
        ref_id = _required_text(ref.get("id"), "evidence reference id")
        if ref_id in seen:
            raise ValueError("Evidence reference ids must be unique")
        seen.add(ref_id)
        result.append(_json_value(ref))
    return tuple(result)


@dataclass(frozen=True)
class ResearchDossier:
    """Readable, point-in-time company dossier with no execution semantics."""

    schema_version: str
    symbol: str
    name: str
    as_of: date
    run_id: str
    generated_at: datetime
    research_version: str
    profile_id: str
    primary_model: str | None
    action: str
    business_quality: ResearchSection
    financial_quality: ResearchSection
    capital_allocation: ResearchSection
    thesis: ResearchSection
    counter_evidence: ResearchSection
    thesis_breakers: ResearchSection
    next_events: ResearchSection
    research_gaps: ResearchSection
    evidence_refs: tuple[dict[str, Any], ...]
    financial_period: date | None = None
    valuation_status: str = "NOT_READY"
    research_status: str = "NOT_STARTED"

    def __post_init__(self) -> None:
        if self.schema_version != DOSSIER_SCHEMA_VERSION:
            raise ValueError("Unknown research dossier schema")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Dossier symbol must contain six digits")
        object.__setattr__(self, "name", _required_text(self.name, "company name"))
        object.__setattr__(self, "as_of", _required_date(self.as_of, "dossier as_of"))
        object.__setattr__(self, "run_id", _required_text(self.run_id, "dossier run id"))
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "dossier generated_at"),
        )
        object.__setattr__(
            self,
            "research_version",
            _required_text(self.research_version, "dossier research version"),
        )
        object.__setattr__(
            self,
            "profile_id",
            _required_text(self.profile_id, "dossier profile id"),
        )
        if self.primary_model is not None:
            object.__setattr__(
                self,
                "primary_model",
                _required_text(self.primary_model, "dossier primary model"),
            )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Research dossiers must remain no_order")
        if self.financial_period is not None and (
            not isinstance(self.financial_period, date)
            or isinstance(self.financial_period, datetime)
        ):
            raise ValueError("Dossier financial_period must be a date")
        sections = (
            self.business_quality,
            self.financial_quality,
            self.capital_allocation,
            self.thesis,
            self.counter_evidence,
            self.thesis_breakers,
            self.next_events,
            self.research_gaps,
        )
        keys = [section.key for section in sections]
        if set(keys) != REQUIRED_SECTION_KEYS:
            raise ValueError("Research dossier sections do not match the required contract")
        evidence_ids = {ref["id"] for ref in self.evidence_refs}
        for section in sections:
            unknown = set(section.evidence_refs) - evidence_ids
            if unknown:
                raise ValueError(
                    f"{section.key} references unknown evidence: {sorted(unknown)}"
                )
        if self.business_quality.status == SECTION_COMPLETE:
            dimension_keys = {
                dimension.key for dimension in self.business_quality.dimensions
            }
            if dimension_keys != REQUIRED_BUSINESS_DIMENSIONS:
                raise ValueError(
                    "A complete business-quality section requires every registered dimension"
                )
            if any(
                dimension.status
                not in {
                    SECTION_COMPLETE,
                    SECTION_NOT_APPLICABLE,
                    # UNKNOWN is a valid completed research conclusion: the
                    # question was examined and the answer is not yet known.
                    SECTION_UNKNOWN,
                }
                for dimension in self.business_quality.dimensions
            ):
                raise ValueError(
                    "A complete business-quality section cannot retain missing, "
                    "blocked, partial, or unstarted dimensions"
                )

    @property
    def readiness(self) -> str:
        sections = (
            self.business_quality,
            self.financial_quality,
            self.capital_allocation,
            self.thesis,
            self.counter_evidence,
            self.thesis_breakers,
            self.next_events,
            self.research_gaps,
        )
        if all(section.status == SECTION_NOT_STARTED for section in sections):
            return DOSSIER_NOT_STARTED
        if any(section.status == SECTION_BLOCKED for section in sections):
            return DOSSIER_BLOCKED
        if not all(section.is_complete for section in sections):
            return DOSSIER_PARTIAL
        for section in (
            self.counter_evidence,
            self.thesis_breakers,
            self.next_events,
        ):
            if not section.findings:
                return DOSSIER_PARTIAL
        return DOSSIER_READABLE

    @property
    def visible_blockers(self) -> tuple[str, ...]:
        result: list[str] = []
        for section in (
            self.business_quality,
            self.financial_quality,
            self.capital_allocation,
            self.thesis,
            self.counter_evidence,
            self.thesis_breakers,
            self.next_events,
            self.research_gaps,
        ):
            result.extend(section.blockers)
        return tuple(dict.fromkeys(result))

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "name": self.name,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "research_version": self.research_version,
            "profile_id": self.profile_id,
            "primary_model": self.primary_model,
            "action": self.action,
            "business_quality": self.business_quality.as_policy(),
            "financial_quality": self.financial_quality.as_policy(),
            "capital_allocation": self.capital_allocation.as_policy(),
            "thesis": self.thesis.as_policy(),
            "counter_evidence": self.counter_evidence.as_policy(),
            "thesis_breakers": self.thesis_breakers.as_policy(),
            "next_events": self.next_events.as_policy(),
            "research_gaps": self.research_gaps.as_policy(),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "financial_period": self.financial_period,
            "valuation_status": self.valuation_status,
            "research_status": self.research_status,
            "readiness": self.readiness,
        }
        return _json_value(payload)

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def _reject_execution_keys(value: object, *, allow_root_action: bool = False) -> None:
    if isinstance(value, dict):
        forbidden = _EXECUTION_KEYS & set(value)
        if allow_root_action:
            forbidden -= {"action"}
        if forbidden:
            raise ValueError(f"Research dossier contains execution keys: {sorted(forbidden)}")
        for child in value.values():
            _reject_execution_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_keys(child)


def _from_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def _from_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def dossier_from_payload(payload: Mapping[str, Any]) -> ResearchDossier:
    if not isinstance(payload, Mapping):
        raise ValueError("Research dossier payload must be an object")
    data = dict(payload)
    _reject_execution_keys(data, allow_root_action=True)
    if data.get("action") != ACTION_NO_ORDER:
        raise ValueError("Research dossier action must remain no_order")
    section_payloads = {
        key: data.get(key)
        for key in REQUIRED_SECTION_KEYS
    }
    if any(value is None for value in section_payloads.values()):
        raise ValueError("Research dossier is missing a required section")
    return ResearchDossier(
        schema_version=_required_text(data.get("schema_version"), "schema version"),
        symbol=_required_text(data.get("symbol"), "dossier symbol"),
        name=_required_text(data.get("name"), "company name"),
        as_of=_from_date(data.get("as_of"), "dossier as_of"),
        run_id=_required_text(data.get("run_id"), "dossier run id"),
        generated_at=_from_datetime(data.get("generated_at"), "dossier generated_at"),
        research_version=_required_text(
            data.get("research_version"), "dossier research version"
        ),
        profile_id=_required_text(data.get("profile_id"), "dossier profile id"),
        primary_model=_optional_text(data.get("primary_model"), "dossier primary model"),
        action=str(data.get("action")),
        business_quality=_section_from_payload(section_payloads[SECTION_BUSINESS_QUALITY]),
        financial_quality=_section_from_payload(section_payloads[SECTION_FINANCIAL_QUALITY]),
        capital_allocation=_section_from_payload(section_payloads[SECTION_CAPITAL_ALLOCATION]),
        thesis=_section_from_payload(section_payloads[SECTION_THESIS]),
        counter_evidence=_section_from_payload(section_payloads[SECTION_COUNTER_EVIDENCE]),
        thesis_breakers=_section_from_payload(section_payloads[SECTION_THESIS_BREAKERS]),
        next_events=_section_from_payload(section_payloads[SECTION_NEXT_EVENTS]),
        research_gaps=_section_from_payload(section_payloads[SECTION_RESEARCH_GAPS]),
        evidence_refs=tuple(
            dict(item) for item in (data.get("evidence_refs") or [])
        ),
        financial_period=(
            _from_date(data["financial_period"], "dossier financial period")
            if data.get("financial_period") is not None
            else None
        ),
        valuation_status=str(data.get("valuation_status") or "NOT_READY"),
        research_status=str(data.get("research_status") or "NOT_STARTED"),
    )


@dataclass(frozen=True)
class DossierDecodeFailure:
    symbol: str | None
    error: str

    def as_policy(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "error": self.error}


@dataclass(frozen=True)
class ResearchDossierCollection:
    """A fail-isolated collection of company dossiers."""

    schema_version: str
    generated_at: datetime
    action: str
    dossiers: tuple[ResearchDossier, ...]
    input_failures: tuple[DossierDecodeFailure, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != DOSSIER_SCHEMA_VERSION:
            raise ValueError("Unknown research dossier collection schema")
        _required_datetime(self.generated_at, "collection generated_at")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Research dossier collections must remain no_order")
        symbols = [dossier.symbol for dossier in self.dossiers]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Research dossier symbols must be unique")
        object.__setattr__(self, "dossiers", tuple(self.dossiers))
        object.__setattr__(self, "input_failures", tuple(self.input_failures))

    @property
    def by_symbol(self) -> dict[str, ResearchDossier]:
        return {dossier.symbol: dossier for dossier in self.dossiers}

    def as_policy(self) -> dict[str, Any]:
        return _json_value({
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "action": self.action,
            "dossiers": [dossier.as_policy() for dossier in self.dossiers],
            "input_failures": [failure.as_policy() for failure in self.input_failures],
        })

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def dossier_collection_from_payload(payload: Mapping[str, Any]) -> ResearchDossierCollection:
    if not isinstance(payload, Mapping):
        raise ValueError("Research dossier collection must be an object")
    data = dict(payload)
    _reject_execution_keys(data, allow_root_action=True)
    if data.get("action") != ACTION_NO_ORDER:
        raise ValueError("Research dossier collection action must remain no_order")
    generated_at = _from_datetime(data.get("generated_at"), "collection generated_at")
    dossiers: list[ResearchDossier] = []
    failures: list[DossierDecodeFailure] = []
    for item in data.get("dossiers") or []:
        if not isinstance(item, Mapping):
            failures.append(DossierDecodeFailure(None, "Dossier entry must be an object"))
            continue
        symbol = str(item.get("symbol")) if item.get("symbol") is not None else None
        try:
            dossiers.append(dossier_from_payload(dict(item)))
        except (TypeError, ValueError) as error:
            failures.append(DossierDecodeFailure(symbol, str(error)))
    for failure in data.get("input_failures") or []:
        raw = dict(failure)
        failures.append(
            DossierDecodeFailure(
                _optional_text(raw.get("symbol"), "failure symbol"),
                _required_text(raw.get("error"), "failure error"),
            )
        )
    return ResearchDossierCollection(
        schema_version=_required_text(data.get("schema_version"), "schema version"),
        generated_at=generated_at,
        action=str(data.get("action")),
        dossiers=tuple(dossiers),
        input_failures=tuple(failures),
    )


def section(
    key: str,
    title: str,
    status: str,
    *,
    findings: Sequence[ResearchStatement] = (),
    dimensions: Sequence[ResearchDimension] = (),
    blockers: Sequence[str] = (),
    explanation: str = "",
) -> ResearchSection:
    return ResearchSection(
        key=key,
        title=title,
        status=status,
        findings=tuple(findings),
        dimensions=tuple(dimensions),
        blockers=tuple(blockers),
        explanation=explanation,
    )


def statement(
    kind: str,
    text: str,
    *,
    confidence: str = CONFIDENCE_UNKNOWN,
    status: str = SECTION_COMPLETE,
    evidence_refs: Sequence[str] = (),
) -> ResearchStatement:
    return ResearchStatement(
        kind=kind,
        text=text,
        confidence=confidence,
        status=status,
        evidence_refs=tuple(evidence_refs),
    )


def not_started_dossier(
    *,
    symbol: str,
    name: str,
    as_of: date,
    run_id: str,
    generated_at: datetime,
    research_version: str,
    profile_id: str,
    primary_model: str | None,
    known_blockers: Sequence[str] = (),
) -> ResearchDossier:
    titles = {
        SECTION_BUSINESS_QUALITY: "Business Quality",
        SECTION_FINANCIAL_QUALITY: "Financial Quality",
        SECTION_CAPITAL_ALLOCATION: "Capital Allocation",
        SECTION_THESIS: "Thesis",
        SECTION_COUNTER_EVIDENCE: "Counter Evidence",
        SECTION_THESIS_BREAKERS: "Thesis Breakers",
        SECTION_NEXT_EVENTS: "Next Events",
        SECTION_RESEARCH_GAPS: "Research Gaps",
    }
    sections = {
        key: section(
            key,
            title,
            SECTION_NOT_STARTED,
            blockers=known_blockers if key == SECTION_RESEARCH_GAPS else (),
            explanation="Real dossier research has not started.",
        )
        for key, title in titles.items()
    }
    return ResearchDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        symbol=symbol,
        name=name,
        as_of=as_of,
        run_id=run_id,
        generated_at=generated_at,
        research_version=research_version,
        profile_id=profile_id,
        primary_model=primary_model,
        action=ACTION_NO_ORDER,
        business_quality=sections[SECTION_BUSINESS_QUALITY],
        financial_quality=sections[SECTION_FINANCIAL_QUALITY],
        capital_allocation=sections[SECTION_CAPITAL_ALLOCATION],
        thesis=sections[SECTION_THESIS],
        counter_evidence=sections[SECTION_COUNTER_EVIDENCE],
        thesis_breakers=sections[SECTION_THESIS_BREAKERS],
        next_events=sections[SECTION_NEXT_EVENTS],
        research_gaps=sections[SECTION_RESEARCH_GAPS],
        evidence_refs=(),
        research_status="NOT_STARTED",
    )
