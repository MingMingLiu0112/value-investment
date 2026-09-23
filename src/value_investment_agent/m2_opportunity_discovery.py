"""Point-in-time contracts for the M2 multi-channel opportunity funnel.

This domain module contains no HTTP, database, Excel or trading logic.  It
describes a replayable screening receipt and the fail-closed evidence rules
that the production adapter must satisfy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


M2_SCHEMA_VERSION = "m2-opportunity-discovery-v1"
M2_RULE_VERSION = "m2-multi-channel-cheap-screen-v1"
ACTION_NO_ORDER = "no_order"

CHANNEL_QUALITY = "quality"
CHANNEL_DIVIDEND = "dividend_cash_return"
CHANNEL_VALUE = "value"
CHANNEL_CYCLICAL = "cyclical"
CHANNELS = (
    CHANNEL_QUALITY,
    CHANNEL_DIVIDEND,
    CHANNEL_VALUE,
    CHANNEL_CYCLICAL,
)

PROFILE_SUPPORTED = "SUPPORTED"
PROFILE_UNKNOWN = "UNKNOWN"
PROFILE_UNSUPPORTED = "UNSUPPORTED"

DATA_COMPLETE = "COMPLETE"
DATA_PARTIAL = "PARTIAL"
DATA_MISSING = "MISSING"
DATA_UNSUPPORTED = "UNSUPPORTED"

PRIORITY_A = "A"
PRIORITY_B = "B"
PRIORITY_C = "C"

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHANNELS = set(CHANNELS)
_DATA_STATUSES = {DATA_COMPLETE, DATA_PARTIAL, DATA_MISSING, DATA_UNSUPPORTED}
_PROFILE_STATUSES = {PROFILE_SUPPORTED, PROFILE_UNKNOWN, PROFILE_UNSUPPORTED}
_PRIORITY_TIERS = {PRIORITY_A, PRIORITY_B, PRIORITY_C}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _decimal(value: object, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return number


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Discovery receipt decimals must be finite")
        return str(value)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Discovery receipt timestamps require timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (
            value != value or value in (float("inf"), float("-inf"))
        ):
            raise ValueError("Discovery receipt number is not finite")
        return value
    raise TypeError(f"Unsupported discovery receipt value: {type(value).__name__}")


@dataclass(frozen=True)
class EvidenceReference:
    id: str
    path: str
    sha256: str
    source_name: str
    source_url: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "evidence id"))
        object.__setattr__(self, "path", _required_text(self.path, "evidence path"))
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("Evidence sha256 must be lowercase SHA-256 hex")
        object.__setattr__(self, "sha256", self.sha256.lower())
        object.__setattr__(self, "source_name", _required_text(self.source_name, "source name"))
        object.__setattr__(self, "source_url", _required_text(self.source_url, "source url"))
        _required_datetime(self.fetched_at, "evidence fetched_at")

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "sha256": self.sha256,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(),
        }


def evidence_reference_from_payload(value: Mapping[str, Any]) -> EvidenceReference:
    data = dict(value)
    return EvidenceReference(
        id=str(data.get("id") or ""),
        path=str(data.get("path") or ""),
        sha256=str(data.get("sha256") or ""),
        source_name=str(data.get("source_name") or ""),
        source_url=str(data.get("source_url") or ""),
        fetched_at=datetime.fromisoformat(str(data.get("fetched_at") or "")),
    )


@dataclass(frozen=True)
class UniverseRecord:
    symbol: str
    name: str
    board: str
    exchange: str
    listed_on: str
    official_industry: str | None
    security_type: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Universe symbol must be a six-digit code")
        object.__setattr__(self, "name", _required_text(self.name, "universe name"))
        object.__setattr__(self, "board", _required_text(self.board, "universe board"))
        object.__setattr__(self, "exchange", _required_text(self.exchange, "universe exchange"))
        object.__setattr__(self, "listed_on", _required_text(self.listed_on, "universe listed_on"))
        object.__setattr__(self, "official_industry", _optional_text(self.official_industry, "official industry"))
        object.__setattr__(self, "security_type", _required_text(self.security_type, "universe security type"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "board": self.board,
            "exchange": self.exchange,
            "listed_on": self.listed_on,
            "official_industry": self.official_industry,
            "security_type": self.security_type,
        }


def universe_record_from_payload(value: Mapping[str, Any]) -> UniverseRecord:
    data = dict(value)
    return UniverseRecord(
        symbol=str(data.get("symbol") or ""),
        name=str(data.get("name") or ""),
        board=str(data.get("board") or ""),
        exchange=str(data.get("exchange") or ""),
        listed_on=str(data.get("listed_on") or ""),
        official_industry=data.get("official_industry"),
        security_type=str(data.get("security_type") or ""),
    )


@dataclass(frozen=True)
class UniverseSnapshot:
    schema_version: str
    as_of: date
    complete: bool
    scope: str
    records: tuple[UniverseRecord, ...]
    evidence_refs: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != M2_SCHEMA_VERSION:
            raise ValueError("Universe snapshot schema changed")
        _required_date(self.as_of, "universe as_of")
        if not self.records:
            raise ValueError("Universe snapshot cannot be empty")
        if len({item.symbol for item in self.records}) != len(self.records):
            raise ValueError("Universe snapshot contains duplicate symbols")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of.isoformat(),
            "complete": self.complete,
            "scope": self.scope,
            "records": [record.as_policy() for record in self.records],
            "evidence_refs": [reference.as_policy() for reference in self.evidence_refs],
        }


def universe_snapshot_from_payload(value: Mapping[str, Any]) -> UniverseSnapshot:
    data = dict(value)
    return UniverseSnapshot(
        schema_version=_required_text(data.get("schema_version"), "universe schema"),
        as_of=date.fromisoformat(str(data.get("as_of") or "")),
        complete=bool(data.get("complete")),
        scope=_required_text(data.get("scope"), "universe scope"),
        records=tuple(universe_record_from_payload(item) for item in data.get("records") or []),
        evidence_refs=tuple(
            evidence_reference_from_payload(item) for item in data.get("evidence_refs") or []
        ),
    )


@dataclass(frozen=True)
class SecurityQuote:
    symbol: str
    name: str
    industry: str | None
    board: str
    stock_type: str
    current_price: Decimal | None
    pe_ttm: Decimal | None
    pb: Decimal | None
    market_cap: Decimal | None
    quote_date: str | None
    source_names: tuple[str, ...]
    price_conflict: bool
    trading_state: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Quote symbol must be a six-digit code")
        object.__setattr__(self, "name", _required_text(self.name, "quote name"))
        object.__setattr__(self, "board", _required_text(self.board, "quote board"))
        object.__setattr__(self, "stock_type", _required_text(self.stock_type, "quote stock type"))
        object.__setattr__(self, "industry", _optional_text(self.industry, "quote industry"))
        object.__setattr__(self, "quote_date", _optional_text(self.quote_date, "quote date"))
        object.__setattr__(self, "source_names", tuple(dict.fromkeys(self.source_names)))
        if not self.source_names:
            raise ValueError("Security quote requires a source name")
        if not isinstance(self.price_conflict, bool):
            raise ValueError("price_conflict must be boolean")
        object.__setattr__(self, "trading_state", str(self.trading_state or "").strip())

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "industry": self.industry,
            "board": self.board,
            "stock_type": self.stock_type,
            "current_price": _json_value(self.current_price),
            "pe_ttm": _json_value(self.pe_ttm),
            "pb": _json_value(self.pb),
            "market_cap": _json_value(self.market_cap),
            "quote_date": self.quote_date,
            "source_names": list(self.source_names),
            "price_conflict": self.price_conflict,
            "trading_state": self.trading_state,
        }


def security_quote_from_payload(value: Mapping[str, Any]) -> SecurityQuote:
    data = dict(value)
    return SecurityQuote(
        symbol=str(data.get("symbol") or ""),
        name=str(data.get("name") or ""),
        industry=data.get("industry"),
        board=str(data.get("board") or ""),
        stock_type=str(data.get("stock_type") or ""),
        current_price=_decimal(data.get("current_price"), "current_price"),
        pe_ttm=_decimal(data.get("pe_ttm"), "pe_ttm"),
        pb=_decimal(data.get("pb"), "pb"),
        market_cap=_decimal(data.get("market_cap"), "market_cap"),
        quote_date=str(data.get("quote_date")) if data.get("quote_date") else None,
        source_names=tuple(str(item) for item in data.get("source_names") or []),
        price_conflict=bool(data.get("price_conflict")),
        trading_state=str(data.get("trading_state") or ""),
    )


@dataclass(frozen=True)
class FinancialEvidence:
    symbol: str
    model_type: str
    quality_status: str
    total_score: Decimal | None
    coverage_ratio: Decimal | None
    period: str | None
    metrics: dict[str, str]
    reasons: tuple[str, ...]
    source_ids: dict[str, str]
    evidence_date: str | None

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Financial evidence symbol must be six digits")
        object.__setattr__(self, "model_type", _required_text(self.model_type, "model type"))
        object.__setattr__(self, "quality_status", _required_text(self.quality_status, "quality status"))
        object.__setattr__(self, "period", _optional_text(self.period, "financial period"))
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "source_ids", dict(self.source_ids))
        object.__setattr__(self, "evidence_date", _optional_text(self.evidence_date, "financial evidence date"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "model_type": self.model_type,
            "quality_status": self.quality_status,
            "total_score": _json_value(self.total_score),
            "coverage_ratio": _json_value(self.coverage_ratio),
            "period": self.period,
            "metrics": dict(self.metrics),
            "reasons": list(self.reasons),
            "source_ids": dict(self.source_ids),
            "evidence_date": self.evidence_date,
        }


@dataclass(frozen=True)
class DividendEvidence:
    symbol: str
    name: str
    fiscal_year: str
    cash_dps: Decimal
    declared_yield: Decimal
    status: str
    declaration_date: str | None
    ex_dividend_date: str | None
    source_name: str
    source_url: str
    fetched_at: str
    raw_sha256: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Dividend symbol must be six digits")
        object.__setattr__(self, "name", _required_text(self.name, "dividend name"))
        object.__setattr__(self, "fiscal_year", _required_text(self.fiscal_year, "fiscal year"))
        if self.cash_dps < 0 or self.declared_yield < 0:
            raise ValueError("Dividend amounts cannot be negative")
        object.__setattr__(self, "status", _required_text(self.status, "dividend status"))
        object.__setattr__(self, "declaration_date", _optional_text(self.declaration_date, "declaration date"))
        object.__setattr__(self, "ex_dividend_date", _optional_text(self.ex_dividend_date, "ex date"))
        object.__setattr__(self, "source_name", _required_text(self.source_name, "dividend source"))
        object.__setattr__(self, "source_url", _required_text(self.source_url, "dividend source url"))
        object.__setattr__(self, "fetched_at", _required_text(self.fetched_at, "dividend fetched_at"))
        if not _SHA256.fullmatch(self.raw_sha256):
            raise ValueError("Dividend raw hash must be lowercase SHA-256")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "fiscal_year": self.fiscal_year,
            "cash_dps": str(self.cash_dps),
            "declared_yield": str(self.declared_yield),
            "status": self.status,
            "declaration_date": self.declaration_date,
            "ex_dividend_date": self.ex_dividend_date,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
            "raw_sha256": self.raw_sha256,
        }


@dataclass(frozen=True)
class CandidateReason:
    symbol: str
    name: str
    channel: str
    reasons: tuple[str, ...]
    metrics: dict[str, str | None]
    evidence_refs: tuple[EvidenceReference, ...]
    evidence_date: str
    data_status: str
    profile_status: str
    priority_tier: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Candidate symbol must be six digits")
        object.__setattr__(self, "name", _required_text(self.name, "candidate name"))
        if self.channel not in _CHANNELS:
            raise ValueError(f"Unknown candidate channel: {self.channel}")
        object.__setattr__(self, "reasons", tuple(dict.fromkeys(self.reasons)))
        if not self.reasons:
            raise ValueError("Every candidate requires an explicit reason")
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "evidence_date", _required_text(self.evidence_date, "candidate evidence date"))
        if self.data_status not in _DATA_STATUSES:
            raise ValueError("Candidate data status is invalid")
        if self.profile_status not in _PROFILE_STATUSES:
            raise ValueError("Candidate profile status is invalid")
        if self.priority_tier not in _PRIORITY_TIERS:
            raise ValueError("Candidate priority tier is invalid")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "channel": self.channel,
            "reasons": list(self.reasons),
            "metrics": _json_value(self.metrics),
            "evidence_refs": [reference.as_policy() for reference in self.evidence_refs],
            "evidence_date": self.evidence_date,
            "data_status": self.data_status,
            "profile_status": self.profile_status,
            "priority_tier": self.priority_tier,
        }


def candidate_reason_from_payload(value: Mapping[str, Any]) -> CandidateReason:
    data = dict(value)
    metrics = data.get("metrics") or {}
    return CandidateReason(
        symbol=str(data.get("symbol") or ""),
        name=str(data.get("name") or ""),
        channel=str(data.get("channel") or ""),
        reasons=tuple(str(item) for item in data.get("reasons") or []),
        metrics={str(key): str(item) if item is not None else None for key, item in metrics.items()},
        evidence_refs=tuple(
            evidence_reference_from_payload(item) for item in data.get("evidence_refs") or []
        ),
        evidence_date=str(data.get("evidence_date") or ""),
        data_status=str(data.get("data_status") or ""),
        profile_status=str(data.get("profile_status") or ""),
        priority_tier=str(data.get("priority_tier") or ""),
    )


@dataclass(frozen=True)
class ExcludedSecurity:
    symbol: str
    name: str
    reason: str
    profile_status: str
    evidence_date: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Excluded symbol must be six digits")
        object.__setattr__(self, "name", _required_text(self.name, "excluded name"))
        object.__setattr__(self, "reason", _required_text(self.reason, "excluded reason"))
        if self.profile_status not in _PROFILE_STATUSES:
            raise ValueError("Excluded profile status is invalid")
        object.__setattr__(self, "evidence_date", _required_text(self.evidence_date, "excluded evidence date"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "reason": self.reason,
            "profile_status": self.profile_status,
            "evidence_date": self.evidence_date,
        }


@dataclass(frozen=True)
class ChannelResult:
    channel: str
    title: str
    candidates: tuple[CandidateReason, ...]
    excluded: tuple[ExcludedSecurity, ...]
    missing: tuple[ExcludedSecurity, ...]
    rule_version: str

    def __post_init__(self) -> None:
        if self.channel not in _CHANNELS:
            raise ValueError(f"Unknown channel: {self.channel}")
        object.__setattr__(self, "title", _required_text(self.title, "channel title"))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "excluded", tuple(self.excluded))
        object.__setattr__(self, "missing", tuple(self.missing))
        object.__setattr__(self, "rule_version", _required_text(self.rule_version, "channel rule version"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "title": self.title,
            "candidates": [candidate.as_policy() for candidate in self.candidates],
            "excluded": [item.as_policy() for item in self.excluded],
            "missing": [item.as_policy() for item in self.missing],
            "rule_version": self.rule_version,
        }


@dataclass(frozen=True)
class DataHealth:
    universe_count: int
    quote_count: int
    matched_quote_count: int
    missing_quote_count: int
    extra_quote_count: int
    price_conflict_count: int
    industry_mapping_count: int
    financial_evidence_count: int
    dividend_evidence_count: int
    unsupported_financial_count: int
    status: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(value < 0 for value in (
            self.universe_count, self.quote_count, self.matched_quote_count,
            self.missing_quote_count, self.extra_quote_count, self.price_conflict_count,
            self.industry_mapping_count, self.financial_evidence_count,
            self.dividend_evidence_count, self.unsupported_financial_count,
        )):
            raise ValueError("Data health counts cannot be negative")
        object.__setattr__(self, "status", _required_text(self.status, "data health status"))
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))

    def as_policy(self) -> dict[str, Any]:
        return {
            "universe_count": self.universe_count,
            "quote_count": self.quote_count,
            "matched_quote_count": self.matched_quote_count,
            "missing_quote_count": self.missing_quote_count,
            "extra_quote_count": self.extra_quote_count,
            "price_conflict_count": self.price_conflict_count,
            "industry_mapping_count": self.industry_mapping_count,
            "financial_evidence_count": self.financial_evidence_count,
            "dividend_evidence_count": self.dividend_evidence_count,
            "unsupported_financial_count": self.unsupported_financial_count,
            "status": self.status,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class LegacyComparison:
    legacy_candidate_count: int
    legacy_candidates: tuple[str, ...]
    new_candidate_count: int
    overlap_count: int
    note: str

    def as_policy(self) -> dict[str, Any]:
        return {
            "legacy_candidate_count": self.legacy_candidate_count,
            "legacy_candidates": list(self.legacy_candidates),
            "new_candidate_count": self.new_candidate_count,
            "overlap_count": self.overlap_count,
            "note": self.note,
        }


@dataclass(frozen=True)
class DiscoveryRunReceipt:
    schema_version: str
    run_id: str
    rule_version: str
    generated_at: datetime
    as_of: date
    action: str
    universe: UniverseSnapshot
    data_health: DataHealth
    channel_results: dict[str, ChannelResult]
    legacy_comparison: LegacyComparison
    evidence_refs: tuple[EvidenceReference, ...]
    candidate_signature: str

    def __post_init__(self) -> None:
        if self.schema_version != M2_SCHEMA_VERSION:
            raise ValueError("Discovery receipt schema changed")
        object.__setattr__(self, "run_id", _required_text(self.run_id, "run id"))
        object.__setattr__(self, "rule_version", _required_text(self.rule_version, "rule version"))
        _required_datetime(self.generated_at, "receipt generated_at")
        _required_date(self.as_of, "receipt as_of")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M2 receipt action must remain no_order")
        if set(self.channel_results) != _CHANNELS:
            raise ValueError("M2 receipt must contain all four channel results")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(
            self,
            "candidate_signature",
            _required_text(self.candidate_signature, "candidate signature"),
        )

    def candidate_pool(self) -> dict[str, CandidateReason]:
        return {
            candidate.symbol: candidate
            for channel in self.channel_results.values()
            for candidate in channel.candidates
        }

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "rule_version": self.rule_version,
            "generated_at": self.generated_at.isoformat(),
            "as_of": self.as_of.isoformat(),
            "action": self.action,
            "universe": self.universe.as_policy(),
            "data_health": self.data_health.as_policy(),
            "channel_results": {
                channel: result.as_policy() for channel, result in self.channel_results.items()
            },
            "legacy_comparison": self.legacy_comparison.as_policy(),
            "evidence_refs": [reference.as_policy() for reference in self.evidence_refs],
            "candidate_signature": self.candidate_signature,
        }


def candidate_signature(channel_results: Mapping[str, ChannelResult]) -> str:
    entries = []
    for channel in CHANNELS:
        result = channel_results.get(channel)
        if result is None:
            raise ValueError(f"Missing channel result: {channel}")
        for candidate in result.candidates:
            entries.append(
                {
                    "channel": channel,
                    "symbol": candidate.symbol,
                    "tier": candidate.priority_tier,
                    "data_status": candidate.data_status,
                    "profile_status": candidate.profile_status,
                    "reasons": list(candidate.reasons),
                    "metrics": _json_value(candidate.metrics),
                }
            )
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _channel_result_from_payload(value: Mapping[str, Any]) -> ChannelResult:
    data = dict(value)
    return ChannelResult(
        channel=str(data.get("channel") or ""),
        title=str(data.get("title") or ""),
        candidates=tuple(candidate_reason_from_payload(item) for item in data.get("candidates") or []),
        excluded=tuple(_excluded_from_payload(item) for item in data.get("excluded") or []),
        missing=tuple(_excluded_from_payload(item) for item in data.get("missing") or []),
        rule_version=str(data.get("rule_version") or ""),
    )


def _excluded_from_payload(value: Mapping[str, Any]) -> ExcludedSecurity:
    data = dict(value)
    return ExcludedSecurity(
        symbol=str(data.get("symbol") or ""),
        name=str(data.get("name") or ""),
        reason=str(data.get("reason") or ""),
        profile_status=str(data.get("profile_status") or ""),
        evidence_date=str(data.get("evidence_date") or ""),
    )


def discovery_receipt_from_payload(value: Mapping[str, Any]) -> DiscoveryRunReceipt:
    data = dict(value)
    channels = data.get("channel_results") or {}
    legacy_data = dict(data.get("legacy_comparison") or {})
    legacy_data["legacy_candidates"] = tuple(legacy_data.get("legacy_candidates") or ())
    receipt = DiscoveryRunReceipt(
        schema_version=str(data.get("schema_version") or ""),
        run_id=str(data.get("run_id") or ""),
        rule_version=str(data.get("rule_version") or ""),
        generated_at=datetime.fromisoformat(str(data.get("generated_at") or "")),
        as_of=date.fromisoformat(str(data.get("as_of") or "")),
        action=str(data.get("action") or ""),
        universe=universe_snapshot_from_payload(dict(data.get("universe") or {})),
        data_health=DataHealth(**dict(data.get("data_health") or {})),
        channel_results={channel: _channel_result_from_payload(channels[channel]) for channel in CHANNELS},
        legacy_comparison=LegacyComparison(**legacy_data),
        evidence_refs=tuple(
            evidence_reference_from_payload(item) for item in data.get("evidence_refs") or []
        ),
        candidate_signature=str(data.get("candidate_signature") or ""),
    )
    if receipt.candidate_signature != candidate_signature(receipt.channel_results):
        raise ValueError("Discovery candidate signature changed during decode")
    return receipt
