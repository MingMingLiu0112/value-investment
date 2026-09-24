"""Fail-closed second-stage M2 channel verification, v2.

AC8 is only a preliminary evidence review. This module consumes the immutable
AC8 packet plus additional source-bound point history and applies a separate,
channel-specific policy before any object may become
VERIFIED_FOR_DEEP_RESEARCH. Evidence existence and field non-emptiness are
never sufficient promotion conditions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .m2_market_data import parse_eastmoney_dividends
from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_LEAD,
    CANDIDATE_CLASS_VERIFIED,
    CHANNELS,
)
from .m2_research_report import (
    M2_RESEARCH_REPORT_SCHEMA,
    VERDICT_INSUFFICIENT,
    VERDICT_PENDING,
    VERDICT_REJECTED,
)


M2_CHANNEL_VERIFICATION_V2_SCHEMA = "m2-channel-verification-v2"
M2_CHANNEL_VERIFICATION_POLICY_SCHEMA = "m2-channel-verification-policy-v2"
DEFAULT_CHANNEL_VERIFICATION_V2_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "m2-channel-verification-v2.json"
)

STATUS_VERIFIED = "VERIFIED_FOR_DEEP_RESEARCH"
STATUS_REJECTED = "REJECTED_AFTER_VERIFICATION"
STATUS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
STATUS_UNSUPPORTED = "UNSUPPORTED"
CHANNEL_VERIFICATION_STATUSES = frozenset(
    {STATUS_VERIFIED, STATUS_REJECTED, STATUS_INSUFFICIENT, STATUS_UNSUPPORTED}
)

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_MISSING = "MISSING"
CHECK_STATUSES = frozenset({CHECK_PASS, CHECK_FAIL, CHECK_MISSING})

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHINESE_DATETIME = re.compile(
    r"^(?P<year>[0-9]{4})年(?P<month>[0-9]{1,2})月(?P<day>[0-9]{1,2})日 "
    r"(?P<hour>[0-9]{1,2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<micro>[0-9]+))?$"
)
_VERDICTS = {VERDICT_INSUFFICIENT, VERDICT_PENDING, VERDICT_REJECTED}
_FORBIDDEN_KEYS = {
    "trade_approved",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "buy",
    "sell",
    "live_eligible",
    "return_threshold",
    "backtest_return",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _require_sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def _as_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        match = _CHINESE_DATETIME.fullmatch(text)
        if match is None:
            return None
        microsecond = int(match.group("micro") or "0")
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            microsecond,
            tzinfo=timezone(timedelta(hours=8)),
        )
    return parsed if parsed.tzinfo is not None else None


def _reject_execution_keys(value: object) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_KEYS & set(value):
            raise ValueError(
                "Channel verification v2 payload contains execution keys: "
                + ", ".join(sorted(_FORBIDDEN_KEYS & set(value)))
            )
        for child in value.values():
            _reject_execution_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_keys(child)


def _verify_pinned_json(root: Path, path: str, expected_sha256: str) -> dict[str, Any]:
    target = (root / Path(path)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Channel verification v2 path escapes project root: {path}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(
            f"Channel verification v2 SHA-256 mismatch for {path}: "
            f"expected {expected_sha256}, got {digest}"
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Channel verification v2 input must be an object: {path}")
    _reject_execution_keys(payload)
    return payload


@dataclass(frozen=True)
class ChannelVerificationEvidenceV2:
    """One source-bound, point-in-time evidence item used by verification v2."""

    symbol: str
    field_name: str
    period_label: str
    value: str
    unit: str
    validation_status: str
    source_name: str
    source_url: str
    source_sha256: str | None
    published_at: str | None
    fetched_at: str | None

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Verification v2 evidence symbol must be six digits")
        object.__setattr__(self, "field_name", _required_text(self.field_name, "field_name"))
        object.__setattr__(self, "period_label", _required_text(self.period_label, "period_label"))
        object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))
        object.__setattr__(self, "validation_status", _required_text(self.validation_status, "validation_status"))
        object.__setattr__(self, "source_name", _required_text(self.source_name, "source_name"))
        object.__setattr__(self, "source_url", _required_text(self.source_url, "source_url"))
        source_sha256 = _optional_text(self.source_sha256, "source_sha256")
        if source_sha256 is not None:
            source_sha256 = _require_sha256(source_sha256, "source_sha256")
        object.__setattr__(self, "source_sha256", source_sha256)
        object.__setattr__(self, "published_at", _optional_text(self.published_at, "published_at"))
        object.__setattr__(self, "fetched_at", _optional_text(self.fetched_at, "fetched_at"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "field_name": self.field_name,
            "period_label": self.period_label,
            "value": self.value,
            "unit": self.unit,
            "validation_status": self.validation_status,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_sha256": self.source_sha256,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class VerificationCheckSpec:
    """One channel-specific required verification check."""

    id: str
    label: str
    description: str
    minimum_periods: int = 1
    required_fields: tuple[str, ...] = ()
    any_of_fields: tuple[str, ...] = ()
    required_metrics: tuple[str, ...] = ()
    any_of_metrics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "check id"))
        object.__setattr__(self, "label", _required_text(self.label, "check label"))
        object.__setattr__(self, "description", _required_text(self.description, "description"))
        if self.minimum_periods <= 0:
            raise ValueError("Verification check minimum_periods must be positive")
        object.__setattr__(self, "required_fields", tuple(_required_text(item, "required field") for item in self.required_fields))
        object.__setattr__(self, "any_of_fields", tuple(_required_text(item, "any_of field") for item in self.any_of_fields))
        object.__setattr__(self, "required_metrics", tuple(_required_text(item, "required metric") for item in self.required_metrics))
        object.__setattr__(self, "any_of_metrics", tuple(_required_text(item, "any_of metric") for item in self.any_of_metrics))
        if not (self.required_fields or self.any_of_fields or self.required_metrics or self.any_of_metrics):
            raise ValueError(f"Verification check {self.id} has no evidence or metrics")

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "minimum_periods": self.minimum_periods,
            "required_fields": list(self.required_fields),
            "any_of_fields": list(self.any_of_fields),
            "required_metrics": list(self.required_metrics),
            "any_of_metrics": list(self.any_of_metrics),
        }


@dataclass(frozen=True)
class ChannelVerificationPolicyRule:
    """One independent, channel-specific second-stage verification policy."""

    channel: str
    policy_version: str
    profile_constraint: str
    minimum_complete_fiscal_years: int
    required_checks: tuple[VerificationCheckSpec, ...]
    normalization_requirements: tuple[str, ...] = ()
    blocking_negative_fields: tuple[str, ...] = ()
    blocking_counter_keywords: tuple[str, ...] = ()
    evidence_freshness_days: int = 540

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f"Unknown verification policy channel: {self.channel}")
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy version"))
        object.__setattr__(self, "profile_constraint", _required_text(self.profile_constraint, "profile constraint"))
        if self.minimum_complete_fiscal_years <= 0:
            raise ValueError("minimum_complete_fiscal_years must be positive")
        object.__setattr__(self, "required_checks", tuple(self.required_checks))
        ids = [check.id for check in self.required_checks]
        if len(ids) != len(set(ids)):
            raise ValueError("Verification check ids must be unique within a channel")
        object.__setattr__(self, "normalization_requirements", tuple(_required_text(item, "normalization requirement") for item in self.normalization_requirements))
        object.__setattr__(self, "blocking_negative_fields", tuple(_required_text(item, "blocking negative field") for item in self.blocking_negative_fields))
        object.__setattr__(self, "blocking_counter_keywords", tuple(_required_text(item, "blocking counter keyword") for item in self.blocking_counter_keywords))
        if self.evidence_freshness_days <= 0:
            raise ValueError("evidence_freshness_days must be positive")

    def as_policy(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "policy_version": self.policy_version,
            "profile_constraint": self.profile_constraint,
            "minimum_complete_fiscal_years": self.minimum_complete_fiscal_years,
            "required_checks": [item.as_policy() for item in self.required_checks],
            "normalization_requirements": list(self.normalization_requirements),
            "blocking_negative_fields": list(self.blocking_negative_fields),
            "blocking_counter_keywords": list(self.blocking_counter_keywords),
            "evidence_freshness_days": self.evidence_freshness_days,
        }


@dataclass(frozen=True)
class VerificationCheckResult:
    check_id: str
    label: str
    status: str
    message: str
    available_periods: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _required_text(self.check_id, "check id"))
        object.__setattr__(self, "label", _required_text(self.label, "check label"))
        if self.status not in CHECK_STATUSES:
            raise ValueError(f"Unknown verification check status: {self.status}")
        object.__setattr__(self, "message", _required_text(self.message, "check message"))
        object.__setattr__(self, "available_periods", {str(field): tuple(str(period) for period in periods) for field, periods in self.available_periods.items()})

    def as_policy(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "available_periods": {field: list(periods) for field, periods in self.available_periods.items()},
        }

@dataclass(frozen=True)
class ChannelVerificationResultV2:
    verification_id: str
    source_lead_id: str
    source_ac8_report_id: str
    symbol: str
    name: str
    channel: str
    source_verdict: str
    status: str
    verification_policy_version: str
    required_checks: tuple[VerificationCheckResult, ...]
    passed_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]
    evidence_groups: tuple[str, ...]
    period_coverage: Mapping[str, Any]
    normalization_status: str
    channel_specific_blockers: tuple[str, ...]
    confidence: str
    why_verified: str
    why_rejected: str
    why_insufficient: str
    evidence: tuple[ChannelVerificationEvidenceV2, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    missing_evidence: tuple[str, ...]
    positives: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    market_context: Mapping[str, Any]
    source_report_sha256: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Verification v2 symbol must contain six digits")
        object.__setattr__(self, "verification_id", _required_text(self.verification_id, "verification_id"))
        object.__setattr__(self, "source_lead_id", _required_text(self.source_lead_id, "source_lead_id"))
        object.__setattr__(self, "source_ac8_report_id", _required_text(self.source_ac8_report_id, "source_ac8_report_id"))
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        if self.channel not in CHANNELS:
            raise ValueError(f"Unknown verification v2 channel: {self.channel}")
        if self.source_verdict not in _VERDICTS:
            raise ValueError("Unknown source AC8 verdict")
        if self.status not in CHANNEL_VERIFICATION_STATUSES:
            raise ValueError(f"Unknown verification v2 status: {self.status}")
        object.__setattr__(self, "verification_policy_version", _required_text(self.verification_policy_version, "verification policy version"))
        object.__setattr__(self, "required_checks", tuple(self.required_checks))
        object.__setattr__(self, "passed_checks", tuple(_required_text(item, "passed check") for item in self.passed_checks))
        object.__setattr__(self, "failed_checks", tuple(_required_text(item, "failed check") for item in self.failed_checks))
        object.__setattr__(self, "missing_checks", tuple(_required_text(item, "missing check") for item in self.missing_checks))
        object.__setattr__(self, "evidence_groups", tuple(_required_text(item, "evidence group") for item in self.evidence_groups))
        object.__setattr__(self, "period_coverage", dict(self.period_coverage))
        object.__setattr__(self, "normalization_status", _required_text(self.normalization_status, "normalization_status"))
        object.__setattr__(self, "channel_specific_blockers", tuple(_required_text(item, "blocker") for item in self.channel_specific_blockers))
        object.__setattr__(self, "confidence", _required_text(self.confidence, "confidence"))
        object.__setattr__(self, "why_verified", _required_text(self.why_verified, "why_verified"))
        object.__setattr__(self, "why_rejected", _required_text(self.why_rejected, "why_rejected"))
        object.__setattr__(self, "why_insufficient", _required_text(self.why_insufficient, "why_insufficient"))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "evidence_refs", tuple(dict(item) for item in self.evidence_refs))
        object.__setattr__(self, "missing_evidence", tuple(_required_text(item, "missing evidence") for item in self.missing_evidence))
        object.__setattr__(self, "positives", tuple(_required_text(item, "positive") for item in self.positives))
        object.__setattr__(self, "counter_evidence", tuple(_required_text(item, "counter evidence") for item in self.counter_evidence))
        object.__setattr__(self, "market_context", dict(self.market_context))
        object.__setattr__(self, "source_report_sha256", _require_sha256(self.source_report_sha256, "source_report_sha256"))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Verification v2 result must remain no_order")
        if self.status == STATUS_VERIFIED and (self.missing_checks or self.failed_checks or self.channel_specific_blockers):
            raise ValueError("VERIFIED result cannot contain missing/failed checks or blockers")
        if self.status == STATUS_VERIFIED and not self.evidence:
            raise ValueError("VERIFIED result requires source-bound evidence")

    @property
    def candidate_class(self) -> str:
        return CANDIDATE_CLASS_VERIFIED if self.status == STATUS_VERIFIED else CANDIDATE_CLASS_LEAD

    def as_policy(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "source_lead_id": self.source_lead_id,
            "source_ac8_report_id": self.source_ac8_report_id,
            "symbol": self.symbol,
            "name": self.name,
            "channel": self.channel,
            "source_verdict": self.source_verdict,
            "verification_status": self.status,
            "status": self.status,
            "candidate_class": self.candidate_class,
            "verification_policy_version": self.verification_policy_version,
            "required_checks": [item.as_policy() for item in self.required_checks],
            "passed_checks": list(self.passed_checks),
            "failed_checks": list(self.failed_checks),
            "missing_checks": list(self.missing_checks),
            "evidence_groups": list(self.evidence_groups),
            "period_coverage": dict(self.period_coverage),
            "normalization_status": self.normalization_status,
            "channel_specific_blockers": list(self.channel_specific_blockers),
            "confidence": self.confidence,
            "why_verified": self.why_verified,
            "why_rejected": self.why_rejected,
            "why_insufficient": self.why_insufficient,
            "evidence": [item.as_policy() for item in self.evidence],
            "evidence_refs": list(self.evidence_refs),
            "missing_evidence": list(self.missing_evidence),
            "positives": list(self.positives),
            "counter_evidence": list(self.counter_evidence),
            "market_context": dict(self.market_context),
            "source_report_sha256": self.source_report_sha256,
            "action": self.action,
        }

@dataclass(frozen=True)
class M2ChannelVerificationBatchV2:
    schema_version: str
    policy_version: str
    as_of: date
    generated_at: datetime
    action: str
    source_binding: Mapping[str, Any]
    results: tuple[ChannelVerificationResultV2, ...]
    minimum_second_stage_resolutions: int
    minimum_channels: int
    machine_status: str
    acceptance_status: str
    coverage_summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != M2_CHANNEL_VERIFICATION_V2_SCHEMA:
            raise ValueError("Unknown M2 verification v2 schema")
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy version"))
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError("Verification v2 as_of must be a date")
        if not isinstance(self.generated_at, datetime) or self.generated_at.utcoffset() is None:
            raise ValueError("Verification v2 generated_at must be timezone-aware")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Verification v2 batch must remain no_order")
        object.__setattr__(self, "results", tuple(self.results))
        ids = [item.verification_id for item in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("Verification v2 ids must be unique")
        if self.minimum_second_stage_resolutions <= 0:
            raise ValueError("minimum_second_stage_resolutions must be positive")
        if self.minimum_channels <= 0:
            raise ValueError("minimum_channels must be positive")
        object.__setattr__(self, "source_binding", dict(self.source_binding))
        object.__setattr__(self, "coverage_summary", dict(self.coverage_summary))

    def counts(self) -> dict[str, int]:
        return {status: sum(item.status == status for item in self.results) for status in sorted(CHANNEL_VERIFICATION_STATUSES)}

    def verified_symbols(self) -> tuple[str, ...]:
        return tuple(sorted({item.symbol for item in self.results if item.status == STATUS_VERIFIED}))

    def human_review_packet(self, quality_coverage: Mapping[str, Any]) -> dict[str, Any]:
        counts = self.counts()
        verified = [item for item in self.results if item.status == STATUS_VERIFIED]
        rejected = [item for item in self.results if item.status == STATUS_REJECTED]
        insufficient = [item for item in self.results if item.status == STATUS_INSUFFICIENT]
        return {
            "review_required": True,
            "review_scope": "M2 Verification v2 second-stage channel resolutions",
            "summary": {
                "universe_count": int(quality_coverage.get("universe_count") or 0),
                "lead_count": len(self.results),
                "verified_for_deep_research": counts[STATUS_VERIFIED],
                "rejected_after_verification": counts[STATUS_REJECTED],
                "insufficient_evidence": counts[STATUS_INSUFFICIENT],
                "unsupported": counts[STATUS_UNSUPPORTED],
                "verified_symbols": list(self.verified_symbols()),
                "verified_channels": sorted({item.channel for item in verified}),
                "quality_coverage_status": "COVERAGE_LIMITED",
                "coverage_summary": dict(self.coverage_summary),
            },
            "verified_examples": [
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "channel": item.channel,
                    "required_checks": [check.as_policy() for check in item.required_checks],
                    "passed_checks": list(item.passed_checks),
                    "missing_checks": list(item.missing_checks),
                    "period_coverage": dict(item.period_coverage),
                    "normalization_status": item.normalization_status,
                    "key_evidence": [{"field_name": point.field_name, "period_label": point.period_label, "source_url": point.source_url} for point in item.evidence],
                    "remaining_unknowns": list(item.missing_evidence),
                    "why_verified": item.why_verified,
                }
                for item in verified
            ],
            "rejected_examples": [
                {"symbol": item.symbol, "name": item.name, "channel": item.channel, "original_lead_reason": "; ".join(item.positives), "why_rejected": item.why_rejected}
                for item in rejected[:2]
            ],
            "insufficient_examples": [
                {"symbol": item.symbol, "name": item.name, "channel": item.channel, "missing_critical_evidence": list(item.channel_specific_blockers) or list(item.missing_evidence), "why_insufficient": item.why_insufficient}
                for item in insufficient[:1]
            ],
            "rules": [
                "Only the 18 pre-registered AC9 selected_leads were resolved.",
                "Every channel uses an explicit required-check policy; evidence count is not a promotion rule.",
                "VERIFIED_FOR_DEEP_RESEARCH admits an item to a research queue only.",
                "Zero VERIFIED items is a legal, non-market conclusion.",
                "All resolutions remain action=no_order.",
            ],
            "rows": [
                {"symbol": item.symbol, "name": item.name, "channel": item.channel, "status": item.status, "verification_id": item.verification_id, "evidence_count": len(item.evidence), "missing_check_count": len(item.missing_checks), "failed_check_count": len(item.failed_checks)}
                for item in sorted(self.results, key=lambda row: row.symbol)
            ],
            "action": ACTION_NO_ORDER,
        }

    def as_policy(self, quality_coverage: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "action": self.action,
            "source_binding": dict(self.source_binding),
            "minimum_second_stage_resolutions": self.minimum_second_stage_resolutions,
            "minimum_channels": self.minimum_channels,
            "machine_status": self.machine_status,
            "acceptance_status": self.acceptance_status,
            "summary": {**self.counts(), "lead_count": len(self.results), "verified_symbols": list(self.verified_symbols())},
            "coverage_summary": dict(self.coverage_summary),
            "quality_coverage": {
                "status": "COVERAGE_LIMITED",
                "universe_count": int(quality_coverage.get("universe_count") or 0),
                "evidence_count": int(quality_coverage.get("financial_evidence_count") or 0),
                "pass_count": int(quality_coverage.get("pass_count") or 0),
            },
            "results": [item.as_policy() for item in self.results],
            "human_review_packet": self.human_review_packet(quality_coverage),
        }


@dataclass(frozen=True)
class M2ChannelVerificationPolicyV2:
    schema_version: str
    policy_version: str
    as_of: date
    ac8_report_path: str
    ac8_report_sha256: str
    ac9_audit_report_path: str
    ac9_audit_report_sha256: str
    m2_receipt_path: str
    m2_receipt_sha256: str
    financial_points_path: str
    financial_points_sha256: str
    dividend_path: str
    dividend_sha256: str
    minimum_second_stage_resolutions: int
    minimum_channels: int
    minimum_confidence: str
    channel_policies: tuple[ChannelVerificationPolicyRule, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != M2_CHANNEL_VERIFICATION_POLICY_SCHEMA:
            raise ValueError("Unknown M2 verification v2 policy schema")
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy version"))
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError("Verification v2 policy as_of must be a date")
        object.__setattr__(self, "ac8_report_path", _required_text(self.ac8_report_path, "ac8_report_path"))
        object.__setattr__(self, "ac8_report_sha256", _require_sha256(self.ac8_report_sha256, "ac8_report_sha256"))
        object.__setattr__(self, "ac9_audit_report_path", _required_text(self.ac9_audit_report_path, "ac9_audit_report_path"))
        object.__setattr__(self, "ac9_audit_report_sha256", _require_sha256(self.ac9_audit_report_sha256, "ac9_audit_report_sha256"))
        object.__setattr__(self, "m2_receipt_path", _required_text(self.m2_receipt_path, "m2_receipt_path"))
        object.__setattr__(self, "m2_receipt_sha256", _require_sha256(self.m2_receipt_sha256, "m2_receipt_sha256"))
        object.__setattr__(self, "financial_points_path", _required_text(self.financial_points_path, "financial_points_path"))
        object.__setattr__(self, "financial_points_sha256", _require_sha256(self.financial_points_sha256, "financial_points_sha256"))
        object.__setattr__(self, "dividend_path", _required_text(self.dividend_path, "dividend_path"))
        object.__setattr__(self, "dividend_sha256", _require_sha256(self.dividend_sha256, "dividend_sha256"))
        if self.minimum_second_stage_resolutions <= 0:
            raise ValueError("minimum_second_stage_resolutions must be positive")
        if self.minimum_channels <= 0:
            raise ValueError("minimum_channels must be positive")
        object.__setattr__(self, "minimum_confidence", _required_text(self.minimum_confidence, "minimum_confidence"))
        object.__setattr__(self, "channel_policies", tuple(self.channel_policies))
        channels = [item.channel for item in self.channel_policies]
        if len(channels) != len(set(channels)):
            raise ValueError("Verification v2 channel policies must be unique")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Verification v2 policy must remain no_order")

    def rule_for(self, channel: str) -> ChannelVerificationPolicyRule:
        for rule in self.channel_policies:
            if rule.channel == channel:
                return rule
        raise ValueError(f"No verification v2 policy for channel: {channel}")


def load_m2_channel_verification_policy_v2(path: Path | str = DEFAULT_CHANNEL_VERIFICATION_V2_PATH) -> M2ChannelVerificationPolicyV2:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _reject_execution_keys(payload)
    rules = []
    for channel, raw_rule in (payload.get("channel_policies") or {}).items():
        rules.append(
            ChannelVerificationPolicyRule(
                channel=str(channel),
                policy_version=str(raw_rule.get("policy_version") or ""),
                profile_constraint=str(raw_rule.get("profile_constraint") or ""),
                minimum_complete_fiscal_years=int(raw_rule.get("minimum_complete_fiscal_years") or 0),
                required_checks=tuple(
                    VerificationCheckSpec(
                        id=str(item.get("id") or ""),
                        label=str(item.get("label") or ""),
                        description=str(item.get("description") or ""),
                        minimum_periods=int(item.get("minimum_periods") or 1),
                        required_fields=tuple(item.get("required_fields") or ()),
                        any_of_fields=tuple(item.get("any_of_fields") or ()),
                        required_metrics=tuple(item.get("required_metrics") or ()),
                        any_of_metrics=tuple(item.get("any_of_metrics") or ()),
                    )
                    for item in raw_rule.get("required_checks") or []
                ),
                normalization_requirements=tuple(raw_rule.get("normalization_requirements") or ()),
                blocking_negative_fields=tuple(raw_rule.get("blocking_negative_fields") or ()),
                blocking_counter_keywords=tuple(raw_rule.get("blocking_counter_keywords") or ()),
                evidence_freshness_days=int(raw_rule.get("evidence_freshness_days") or 540),
            )
        )
    return M2ChannelVerificationPolicyV2(
        schema_version=str(payload["schema_version"]),
        policy_version=str(payload["policy_version"]),
        as_of=date.fromisoformat(str(payload["as_of"])),
        ac8_report_path=str(payload["ac8_report_path"]),
        ac8_report_sha256=str(payload["ac8_report_sha256"]),
        ac9_audit_report_path=str(payload["ac9_audit_report_path"]),
        ac9_audit_report_sha256=str(payload["ac9_audit_report_sha256"]),
        m2_receipt_path=str(payload["m2_receipt_path"]),
        m2_receipt_sha256=str(payload["m2_receipt_sha256"]),
        financial_points_path=str(payload["financial_points_path"]),
        financial_points_sha256=str(payload["financial_points_sha256"]),
        dividend_path=str(payload["dividend_path"]),
        dividend_sha256=str(payload["dividend_sha256"]),
        minimum_second_stage_resolutions=int(payload["minimum_second_stage_resolutions"]),
        minimum_channels=int(payload["minimum_channels"]),
        minimum_confidence=str(payload["minimum_confidence"]),
        channel_policies=tuple(rules),
        action=str(payload.get("action", ACTION_NO_ORDER)),
    )

def _complete_fiscal_year(period_label: str) -> int | None:
    text = period_label.strip()
    match = re.fullmatch(r"FY([0-9]{4})", text)
    if match:
        return int(match.group(1))
    try:
        parsed = date.fromisoformat(text.split(" ", 1)[0])
    except ValueError:
        return None
    return parsed.year if (parsed.month, parsed.day) == (12, 31) else None


def _evidence_from_ac8(item: Mapping[str, Any], symbol: str) -> ChannelVerificationEvidenceV2:
    raw_sha = item.get("source_sha256")
    return ChannelVerificationEvidenceV2(
        symbol=symbol,
        field_name=str(item.get("field_name") or ""),
        period_label=str(item.get("period_label") or ""),
        value=str(item.get("value") or ""),
        unit=str(item.get("unit") or ""),
        validation_status=str(item.get("validation_status") or ""),
        source_name=str(item.get("source_name") or ""),
        source_url=str(item.get("source_url") or ""),
        source_sha256=str(raw_sha) if raw_sha else None,
        published_at=str(item["published_at"]) if item.get("published_at") is not None else None,
        fetched_at=str(item["fetched_at"]) if item.get("fetched_at") is not None else None,
    )


def _evidence_from_financial_point(item: Mapping[str, Any], symbol: str) -> ChannelVerificationEvidenceV2:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    raw_sha = item.get("sha256") or metadata.get("official_file_sha256") or metadata.get("sha256")
    fetched = item.get("available_at") or item.get("fetched_at") or item.get("created_at")
    return ChannelVerificationEvidenceV2(
        symbol=symbol,
        field_name=str(item.get("field_name") or ""),
        period_label=str(item.get("period_label") or ""),
        value=str(item.get("value") or ""),
        unit=str(item.get("unit") or ""),
        validation_status=str(item.get("validation_status") or ""),
        source_name=str(item.get("source_name") or ""),
        source_url=str(item.get("source_url") or ""),
        source_sha256=str(raw_sha) if raw_sha else None,
        published_at=str(item["published_at"]) if item.get("published_at") is not None else None,
        fetched_at=str(fetched) if fetched else None,
    )


def _dividend_evidence(
    symbol: str,
    row: Mapping[str, Any],
    *,
    source_sha256: str,
    fetched_at: str,
) -> ChannelVerificationEvidenceV2 | None:
    if row.get("cash_dps") in (None, ""):
        return None
    return ChannelVerificationEvidenceV2(
        symbol=symbol,
        field_name="cash_dividend_per_share",
        period_label=f"FY{row.get('fiscal_year') or 'unknown'}",
        value=str(row.get("cash_dps") or ""),
        unit="CNY/share",
        validation_status="pending",
        source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
        source_url="https://data.eastmoney.com/yjfp/",
        source_sha256=source_sha256,
        published_at=str(row["declaration_date"]) if row.get("declaration_date") else None,
        fetched_at=fetched_at,
    )


def _validate_evidence_pit(
    evidence: Sequence[ChannelVerificationEvidenceV2],
    *,
    generated_at: datetime,
    as_of: date,
) -> None:
    for item in evidence:
        available_at = _parse_datetime(item.fetched_at)
        if available_at is None:
            raise ValueError(
                "Verification v2 evidence has an invalid availability timestamp: "
                f"{item.symbol}:{item.field_name}:{item.period_label}"
            )
        if available_at > generated_at:
            raise ValueError(
                "Verification v2 evidence became available after evaluation time: "
                f"{item.symbol}:{item.field_name}:{item.period_label}"
            )
        if item.field_name == "current_price" and available_at.date() > as_of:
            raise ValueError(
                "Verification v2 price session is newer than as_of: "
                f"{item.symbol}:{item.period_label}"
            )


def _latest_field_value(evidence: Sequence[ChannelVerificationEvidenceV2], field_name: str) -> ChannelVerificationEvidenceV2 | None:
    candidates = [item for item in evidence if item.field_name == field_name and item.validation_status in {"verified", "pending"}]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (_period_sort_key(item.period_label), str(item.fetched_at or "")))


def _period_sort_key(value: str) -> tuple[Any, ...]:
    year = _complete_fiscal_year(value)
    if year is not None:
        return (0, year, 12, 31)
    try:
        parsed = date.fromisoformat(str(value).split(" ", 1)[0])
    except ValueError:
        return (9, 9999, 12, 31)
    return (0, parsed.year, parsed.month, parsed.day)


def _metric_value(market_context: Mapping[str, Any], field: str) -> Any:
    value = market_context.get(field)
    return value if value not in (None, "") else None


def _evaluate_check(spec: VerificationCheckSpec, evidence: Sequence[ChannelVerificationEvidenceV2], market_context: Mapping[str, Any]) -> VerificationCheckResult:
    available = {}
    for field in set(spec.required_fields) | set(spec.any_of_fields):
        periods = tuple(
            sorted(
                {
                    _complete_fiscal_year(item.period_label)
                    for item in evidence
                    if item.field_name == field
                    and item.validation_status in {"verified", "pending"}
                    and _complete_fiscal_year(item.period_label) is not None
                },
                reverse=True,
            )
        )
        if periods:
            available[field] = periods

    missing_fields = [field for field in spec.required_fields if field not in available]
    if spec.any_of_fields and not (set(spec.any_of_fields) & set(available)):
        missing_fields.append("one_of:" + "/".join(spec.any_of_fields))
    missing_metrics = [field for field in spec.required_metrics if _metric_value(market_context, field) is None]
    if spec.any_of_metrics and not any(_metric_value(market_context, field) is not None for field in spec.any_of_metrics):
        missing_metrics.append("one_of:" + "/".join(spec.any_of_metrics))

    if missing_fields or missing_metrics:
        return VerificationCheckResult(
            check_id=spec.id,
            label=spec.label,
            status=CHECK_MISSING,
            message="缺少核心证据：" + ", ".join(missing_fields + missing_metrics),
            available_periods=available,
        )

    candidate_fields = set(spec.required_fields)
    if spec.any_of_fields:
        candidate_fields |= set(spec.any_of_fields) & set(available)
    short_fields = [field for field in candidate_fields if len(available.get(field, ())) < spec.minimum_periods]
    if short_fields:
        return VerificationCheckResult(
            check_id=spec.id,
            label=spec.label,
            status=CHECK_FAIL,
            message=f"完整财年覆盖不足 {spec.minimum_periods} 期：" + ", ".join(short_fields),
            available_periods=available,
        )

    return VerificationCheckResult(
        check_id=spec.id,
        label=spec.label,
        status=CHECK_PASS,
        message=f"{spec.label}通过 {spec.minimum_periods} 个完整财年核验。",
        available_periods=available,
    )


def _normalization_status(rule: ChannelVerificationPolicyRule, evidence: Sequence[ChannelVerificationEvidenceV2], market_context: Mapping[str, Any]) -> str:
    missing = [
        item
        for item in rule.normalization_requirements
        if item not in {point.field_name for point in evidence}
        and _metric_value(market_context, item) is None
    ]
    return "COMPLETE" if not missing else "MISSING:" + ",".join(missing)


def _negative_blockers(rule: ChannelVerificationPolicyRule, evidence: Sequence[ChannelVerificationEvidenceV2]) -> list[str]:
    blockers = []
    for field in rule.blocking_negative_fields:
        point = _latest_field_value(evidence, field)
        if point is None:
            continue
        value = _as_decimal(point.value)
        if value is not None and value < 0:
            blockers.append(f"{field}<0")
    return blockers


def _counter_blockers(rule: ChannelVerificationPolicyRule, counter_evidence: Sequence[str]) -> list[str]:
    joined = "\n".join(counter_evidence)
    return [keyword for keyword in rule.blocking_counter_keywords if keyword in joined]


def _evidence_refs(evidence: Sequence[ChannelVerificationEvidenceV2]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "id": f"evidence-{index + 1}",
            "field_name": item.field_name,
            "period_label": item.period_label,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "source_sha256": item.source_sha256,
        }
        for index, item in enumerate(evidence)
    )


def evaluate_channel_verification(
    rule: ChannelVerificationPolicyRule,
    *,
    source_verdict: str,
    evidence: Sequence[ChannelVerificationEvidenceV2],
    market_context: Mapping[str, Any],
    missing_evidence: Sequence[str],
    positives: Sequence[str],
    counter_evidence: Sequence[str],
) -> tuple[str, tuple[VerificationCheckResult, ...], Mapping[str, Any], str, tuple[str, ...], str, str, str, str]:
    checks = tuple(_evaluate_check(spec, evidence, market_context) for spec in rule.required_checks)
    passed = tuple(item.check_id for item in checks if item.status == CHECK_PASS)
    failed = tuple(item.check_id for item in checks if item.status == CHECK_FAIL)
    missing = tuple(item.check_id for item in checks if item.status == CHECK_MISSING)
    blockers = [f"{check.label}缺失" for check in checks if check.status == CHECK_MISSING]
    blockers += [f"{check.label}覆盖不足" for check in checks if check.status == CHECK_FAIL]
    blockers += _negative_blockers(rule, evidence)
    blockers += _counter_blockers(rule, counter_evidence)
    normalization = _normalization_status(rule, evidence, market_context)
    if normalization != "COMPLETE":
        blockers.append(f"正常化证据缺失:{normalization}")
    period_coverage = {
        "minimum_complete_fiscal_years": rule.minimum_complete_fiscal_years,
        "checks": {check.check_id: check.as_policy() for check in checks},
        "coverage_sufficient": not failed and not missing,
    }

    if source_verdict == VERDICT_REJECTED:
        status = STATUS_REJECTED
    elif source_verdict == VERDICT_INSUFFICIENT:
        status = STATUS_INSUFFICIENT
    elif source_verdict != VERDICT_PENDING:
        status = STATUS_UNSUPPORTED
    elif missing or failed or normalization != "COMPLETE":
        status = STATUS_INSUFFICIENT
    elif blockers:
        status = STATUS_REJECTED
    else:
        status = STATUS_VERIFIED

    remaining = "；".join(missing_evidence) or "无额外记录"
    why_verified = (
        f"{rule.channel} 通道通过 {len(passed)} 项显式二阶段检查："
        f"{'、'.join(passed)}；剩余未知：{remaining}。"
        "该状态仅表示进入深研队列，不表示估值、便宜、仓位或 BUY。"
    )
    why_rejected = (
        f"预注册线索原由：{'；'.join(positives) or '低估值初筛'}。"
        f"二阶段阻断：{'；'.join(blockers) or '；'.join(counter_evidence)}。"
        "低 PE/PB 或单一触发条件不构成低估证据。"
    )
    why_insufficient = (
        f"{rule.channel} 通道仍缺关键证据："
        f"{'；'.join(blockers) or '；'.join(missing_evidence) or '当前证据不足'}。"
        "保留为证据不足，不冒充拒绝或研究机会。"
    )
    confidence = "LOW" if status == STATUS_VERIFIED else "NOT_ESTIMATED"
    return (
        status,
        checks,
        period_coverage,
        normalization,
        tuple(dict.fromkeys(blockers)),
        confidence,
        why_verified,
        why_rejected,
        why_insufficient,
    )

def _quality_coverage(receipt: Mapping[str, Any]) -> dict[str, Any]:
    summary = receipt.get("summary") or {}
    data_health = summary.get("data_health") or {}
    data_health = receipt.get("data_health") or data_health
    quality = summary.get("coverage_counts") or {}
    quality = quality.get("quality") or {}
    channel_results = receipt.get("channel_results") or {}
    quality = (channel_results.get("quality") or {}).get("coverage") or quality
    return {
        "universe_count": int(data_health.get("universe_count") or 0),
        "financial_evidence_count": int(data_health.get("financial_evidence_count") or 0),
        "pass_count": int(quality.get("pass_count") or 0),
        "data_gap_count": int(quality.get("data_gap_count") or 0),
    }


def _coverage_summary(results: Sequence[ChannelVerificationResultV2], rules: Sequence[ChannelVerificationPolicyRule]) -> dict[str, Any]:
    base = {
        "total_leads": 0,
        "resolved": 0,
        "verified": 0,
        "rejected": 0,
        "insufficient": 0,
        "unsupported": 0,
        "period_coverage_sufficient": 0,
        "missing_core_evidence": 0,
    }
    by_channel = {rule.channel: dict(base) for rule in rules}
    status_to_count = {
        STATUS_VERIFIED: "verified",
        STATUS_REJECTED: "rejected",
        STATUS_INSUFFICIENT: "insufficient",
        STATUS_UNSUPPORTED: "unsupported",
    }
    for item in results:
        row = by_channel.setdefault(item.channel, dict(base))
        row["total_leads"] += 1
        row["resolved"] += 1
        row[status_to_count[item.status]] += 1
        if item.period_coverage.get("coverage_sufficient"):
            row["period_coverage_sufficient"] += 1
        if item.missing_checks:
            row["missing_core_evidence"] += 1
    return {
        "by_channel": by_channel,
        "total_leads": len(results),
        "resolved": len(results),
        "verified": sum(item.status == STATUS_VERIFIED for item in results),
        "rejected": sum(item.status == STATUS_REJECTED for item in results),
        "insufficient": sum(item.status == STATUS_INSUFFICIENT for item in results),
        "unsupported": sum(item.status == STATUS_UNSUPPORTED for item in results),
    }


def build_m2_channel_verification_v2(
    policy: M2ChannelVerificationPolicyV2,
    *,
    root: Path | str,
    generated_at: datetime,
) -> M2ChannelVerificationBatchV2:
    root = Path(root).resolve()
    if generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    ac8 = _verify_pinned_json(root, policy.ac8_report_path, policy.ac8_report_sha256)
    ac9 = _verify_pinned_json(root, policy.ac9_audit_report_path, policy.ac9_audit_report_sha256)
    receipt = _verify_pinned_json(root, policy.m2_receipt_path, policy.m2_receipt_sha256)
    financial_payload = _verify_pinned_json(root, policy.financial_points_path, policy.financial_points_sha256)
    dividend_payload = _verify_pinned_json(root, policy.dividend_path, policy.dividend_sha256)
    if ac8.get("schema_version") != M2_RESEARCH_REPORT_SCHEMA:
        raise ValueError("Unexpected AC8 research report schema")
    for payload in (ac8, ac9, receipt):
        if payload.get("action") != ACTION_NO_ORDER:
            raise ValueError("Verification v2 batch input must remain no_order")
    if ac9.get("audit_status") != "MACHINE_CHECKS_PASS":
        raise ValueError("AC9 coverage audit has not passed machine checks")

    source_binding = dict(ac8.get("source_binding") or {})
    for binding_key, policy_hash in (
        ("ac9_audit_report_sha256", policy.ac9_audit_report_sha256),
        ("m2_receipt_sha256", policy.m2_receipt_sha256),
        ("financial_points_sha256", policy.financial_points_sha256),
        ("dividend_sha256", policy.dividend_sha256),
    ):
        if source_binding.get(binding_key) != policy_hash:
            raise ValueError(f"AC8 source binding does not match {binding_key}")

    receipt_refs = {str(item.get("id") or ""): item for item in receipt.get("evidence_refs") or []}
    for reference_id, policy_hash in (
        ("financial", policy.financial_points_sha256),
        ("dividend", policy.dividend_sha256),
    ):
        reference = receipt_refs.get(reference_id)
        if reference is None or reference.get("sha256") != policy_hash:
            raise ValueError(f"M2 receipt does not bind the pinned {reference_id} artifact")
    dividend_fetched_at = str((receipt_refs.get("dividend") or {}).get("fetched_at") or "")
    if not dividend_fetched_at:
        raise ValueError("M2 receipt dividend reference has no fetched_at")

    expected_leads = set()
    for stratum in ac9.get("strata") or []:
        if stratum.get("stratum_id") != "selected_leads":
            continue
        for sample in stratum.get("samples") or []:
            if sample.get("candidate_class") != CANDIDATE_CLASS_LEAD:
                continue
            expected_leads.add((str(sample.get("symbol") or "").zfill(6), str(sample.get("channel") or "")))
    if len(expected_leads) != 18:
        raise ValueError("Expected exactly 18 pre-registered selected_leads")

    financial_points = financial_payload.get("points") or []
    dividends = {row["symbol"]: row for row in parse_eastmoney_dividends(dividend_payload)}
    financial_by_symbol = {}
    for point in financial_points:
        symbol = str(point.get("symbol") or "").zfill(6)
        if _SYMBOL.fullmatch(symbol):
            financial_by_symbol.setdefault(symbol, []).append(point)

    results = []
    for report in ac8.get("reports") or []:
        symbol = str(report.get("symbol") or "").zfill(6)
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("AC8 report contains an invalid symbol")
        report_id = str(report.get("report_id") or "")
        name = str(report.get("name") or "")
        market_context = dict(report.get("market_context") or {})
        ac8_evidence = tuple(_evidence_from_ac8(item, symbol) for item in report.get("evidence") or [])
        additional = tuple(_evidence_from_financial_point(item, symbol) for item in financial_by_symbol.get(symbol, ()))
        dividend_row = dividends.get(symbol)
        dividend_point = (
            _dividend_evidence(
                symbol,
                dividend_row,
                source_sha256=policy.dividend_sha256,
                fetched_at=dividend_fetched_at,
            )
            if dividend_row
            else None
        )
        unique = {(item.field_name, item.period_label): item for item in (*ac8_evidence, *additional) if item.validation_status in {"verified", "pending"}}
        evidence = tuple(unique.values())
        if dividend_point is not None:
            evidence += (dividend_point,)
        evidence = tuple(sorted(evidence, key=lambda item: (item.field_name, _period_sort_key(item.period_label))))
        _validate_evidence_pit(evidence, generated_at=generated_at, as_of=policy.as_of)

        for channel, source_verdict in (report.get("channel_verdicts") or {}).items():
            if (symbol, str(channel)) not in expected_leads:
                raise ValueError(f"Unregistered lead was resolved: {symbol}:{channel}")
            rule = policy.rule_for(str(channel))
            status, checks, period_coverage, normalization, blockers, confidence, why_verified, why_rejected, why_insufficient = evaluate_channel_verification(
                rule,
                source_verdict=str(source_verdict),
                evidence=evidence,
                market_context=market_context,
                missing_evidence=tuple(str(item) for item in report.get("missing_evidence") or ()),
                positives=tuple(str(item) for item in report.get("positives") or ()),
                counter_evidence=tuple(str(item) for item in report.get("counter_evidence") or ()),
            )
            passed = tuple(item.check_id for item in checks if item.status == CHECK_PASS)
            failed = tuple(item.check_id for item in checks if item.status == CHECK_FAIL)
            missing = tuple(item.check_id for item in checks if item.status == CHECK_MISSING)
            results.append(
                ChannelVerificationResultV2(
                    verification_id=f"{report_id}-{channel}-verification-v2",
                    source_lead_id=f"{symbol}:{channel}",
                    source_ac8_report_id=report_id,
                    symbol=symbol,
                    name=name,
                    channel=str(channel),
                    source_verdict=str(source_verdict),
                    status=status,
                    verification_policy_version=policy.policy_version,
                    required_checks=checks,
                    passed_checks=passed,
                    failed_checks=failed,
                    missing_checks=missing,
                    evidence_groups=tuple(check.check_id for check in checks),
                    period_coverage=period_coverage,
                    normalization_status=normalization,
                    channel_specific_blockers=blockers,
                    confidence=confidence,
                    why_verified=why_verified,
                    why_rejected=why_rejected,
                    why_insufficient=why_insufficient,
                    evidence=evidence,
                    evidence_refs=_evidence_refs(evidence),
                    missing_evidence=tuple(str(item) for item in report.get("missing_evidence") or ()),
                    positives=tuple(str(item) for item in report.get("positives") or ()),
                    counter_evidence=tuple(str(item) for item in report.get("counter_evidence") or ()),
                    market_context=market_context,
                    source_report_sha256=policy.ac8_report_sha256,
                )
            )

    actual_leads = {(item.symbol, item.channel) for item in results}
    if actual_leads != expected_leads:
        raise ValueError(f"Verification v2 lead identity changed: missing={expected_leads - actual_leads}, extra={actual_leads - expected_leads}")
    results.sort(key=lambda item: (item.symbol, item.channel))
    coverage = _coverage_summary(results, policy.channel_policies)
    all_verified_sound = all(
        item.status != STATUS_VERIFIED
        or (not item.missing_checks and not item.failed_checks and not item.channel_specific_blockers and bool(item.period_coverage.get("coverage_sufficient")))
        for item in results
    )
    machine_status = (
        "MACHINE_CHECKS_PASS"
        if (
            len(results) >= policy.minimum_second_stage_resolutions
            and len({item.channel for item in results}) >= policy.minimum_channels
            and actual_leads == expected_leads
            and all(item.action == ACTION_NO_ORDER for item in results)
            and all_verified_sound
        )
        else "MACHINE_CHECKS_FAIL"
    )
    quality_coverage = _quality_coverage(receipt)
    return M2ChannelVerificationBatchV2(
        schema_version=M2_CHANNEL_VERIFICATION_V2_SCHEMA,
        policy_version=policy.policy_version,
        as_of=policy.as_of,
        generated_at=generated_at,
        action=ACTION_NO_ORDER,
        source_binding={
            "ac8_report_sha256": policy.ac8_report_sha256,
            "ac9_audit_report_sha256": policy.ac9_audit_report_sha256,
            "m2_receipt_sha256": policy.m2_receipt_sha256,
            "financial_points_sha256": policy.financial_points_sha256,
            "dividend_sha256": policy.dividend_sha256,
            "v1_status": "SEMANTICALLY_SUPERSEDED",
            "pit_status": "PASS",
        },
        results=tuple(results),
        minimum_second_stage_resolutions=policy.minimum_second_stage_resolutions,
        minimum_channels=policy.minimum_channels,
        machine_status=machine_status,
        acceptance_status="CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION" if machine_status == "MACHINE_CHECKS_PASS" else "CHECKPOINT_A_NOT_READY",
        coverage_summary=coverage,
    )
