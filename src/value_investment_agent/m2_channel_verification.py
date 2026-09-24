"""Formal second-stage resolution for pre-registered M2 cheap-screen LEADS.

This module converts the immutable AC8 evidence-bound research reports into a
versioned ChannelVerificationResult packet. It never re-selects a company after
seeing financial outcomes, emits no valuation, BUY, position or order, and
keeps every LEAd in the original candidate class.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

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


M2_CHANNEL_VERIFICATION_SCHEMA = "m2-channel-verification-v1"
DEFAULT_CHANNEL_VERIFICATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "m2-channel-verification-v1.json"
)

STATUS_VERIFIED = "VERIFIED_FOR_DEEP_RESEARCH"
STATUS_REJECTED = "REJECTED_AFTER_VERIFICATION"
STATUS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
STATUS_UNSUPPORTED = "UNSUPPORTED"
CHANNEL_VERIFICATION_STATUSES = frozenset(
    {
        STATUS_VERIFIED,
        STATUS_REJECTED,
        STATUS_INSUFFICIENT,
        STATUS_UNSUPPORTED,
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
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


def _require_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _require_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _reject_execution_keys(value: object) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_KEYS & set(value):
            raise ValueError(
                "Channel verification payload contains execution keys: "
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
        raise ValueError(f"Channel verification path escapes project root: {path}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(
            f"Channel verification SHA-256 mismatch for {path}: "
            f"expected {expected_sha256}, got {digest}"
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Channel verification input must be an object: {path}")
    _reject_execution_keys(payload)
    return payload


@dataclass(frozen=True)
class ChannelVerificationEvidence:
    """One source-bound AC8 evidence point retained in the verification packet."""

    id: str
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
        object.__setattr__(self, "id", _required_text(self.id, "evidence id"))
        object.__setattr__(
            self, "field_name", _required_text(self.field_name, "field_name")
        )
        object.__setattr__(
            self, "period_label", _required_text(self.period_label, "period_label")
        )
        object.__setattr__(self, "value", _required_text(self.value, "value"))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))
        object.__setattr__(
            self,
            "validation_status",
            _required_text(self.validation_status, "validation_status"),
        )
        object.__setattr__(
            self, "source_name", _required_text(self.source_name, "source_name")
        )
        object.__setattr__(
            self, "source_url", _required_text(self.source_url, "source_url")
        )
        if self.source_sha256 is not None:
            object.__setattr__(
                self,
                "source_sha256",
                _require_sha256(self.source_sha256, "source_sha256"),
            )

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.id,
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
class ChannelVerificationResult:
    """One LEAd, one channel, one fail-closed second-stage resolution."""

    verification_id: str
    report_id: str
    symbol: str
    name: str
    channel: str
    source_verdict: str
    status: str
    reason: str
    evidence: tuple[ChannelVerificationEvidence, ...]
    missing_evidence: tuple[str, ...]
    positives: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    market_context: Mapping[str, Any]
    rule_version: str
    source_report_sha256: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Channel verification symbol must contain six digits")
        object.__setattr__(
            self,
            "verification_id",
            _required_text(self.verification_id, "verification_id"),
        )
        object.__setattr__(
            self, "report_id", _required_text(self.report_id, "report_id")
        )
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        if self.channel not in CHANNELS:
            raise ValueError("Unknown channel verification channel")
        if self.source_verdict not in {
            VERDICT_INSUFFICIENT,
            VERDICT_PENDING,
            VERDICT_REJECTED,
        }:
            raise ValueError("Unknown source channel verdict")
        if self.status not in CHANNEL_VERIFICATION_STATUSES:
            raise ValueError("Unknown channel verification status")
        object.__setattr__(
            self, "reason", _required_text(self.reason, "reason")
        )
        object.__setattr__(
            self,
            "rule_version",
            _required_text(self.rule_version, "rule_version"),
        )
        object.__setattr__(
            self,
            "source_report_sha256",
            _require_sha256(self.source_report_sha256, "source_report_sha256"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Channel verification must remain no_order")
        if self.status == STATUS_VERIFIED and not self.evidence:
            raise ValueError(
                "VERIFIED_FOR_DEEP_RESEARCH requires source-bound evidence"
            )
        if self.status != STATUS_VERIFIED and self.source_verdict == VERDICT_PENDING:
            raise ValueError(
                "PENDING_DEEP_RESEARCH cannot be converted to a non-verified status"
            )
        object.__setattr__(
            self,
            "evidence",
            tuple(self.evidence),
        )
        object.__setattr__(
            self,
            "missing_evidence",
            tuple(_required_text(item, "missing evidence") for item in self.missing_evidence),
        )
        object.__setattr__(
            self,
            "positives",
            tuple(_required_text(item, "positive") for item in self.positives),
        )
        object.__setattr__(
            self,
            "counter_evidence",
            tuple(
                _required_text(item, "counter evidence")
                for item in self.counter_evidence
            ),
        )
        object.__setattr__(
            self, "market_context", dict(self.market_context)
        )

    @property
    def candidate_class(self) -> str:
        return (
            CANDIDATE_CLASS_VERIFIED
            if self.status == STATUS_VERIFIED
            else CANDIDATE_CLASS_LEAD
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "report_id": self.report_id,
            "symbol": self.symbol,
            "name": self.name,
            "channel": self.channel,
            "source_verdict": self.source_verdict,
            "status": self.status,
            "candidate_class": self.candidate_class,
            "reason": self.reason,
            "evidence": [item.as_policy() for item in self.evidence],
            "missing_evidence": list(self.missing_evidence),
            "positives": list(self.positives),
            "counter_evidence": list(self.counter_evidence),
            "market_context": dict(self.market_context),
            "rule_version": self.rule_version,
            "source_report_sha256": self.source_report_sha256,
            "action": self.action,
        }


@dataclass(frozen=True)
class M2ChannelVerificationBatch:
    """Machine-verified packet for Checkpoint A human resubmission."""

    schema_version: str
    policy_version: str
    as_of: date
    generated_at: datetime
    action: str
    source_binding: Mapping[str, Any]
    results: tuple[ChannelVerificationResult, ...]
    minimum_second_stage_resolutions: int
    minimum_channels: int
    machine_status: str
    acceptance_status: str

    def __post_init__(self) -> None:
        if self.schema_version != M2_CHANNEL_VERIFICATION_SCHEMA:
            raise ValueError("Unknown channel verification schema")
        object.__setattr__(
            self, "policy_version", _required_text(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "as_of", _require_date(self.as_of, "as_of"))
        object.__setattr__(
            self, "generated_at", _require_datetime(self.generated_at, "generated_at")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Channel verification batch must remain no_order")
        object.__setattr__(self, "results", tuple(self.results))
        ids = [item.verification_id for item in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("Channel verification ids must be unique")
        if self.minimum_second_stage_resolutions <= 0:
            raise ValueError("Minimum second-stage resolutions must be positive")
        if self.minimum_channels <= 0:
            raise ValueError("Minimum verified channels must be positive")
        object.__setattr__(self, "source_binding", dict(self.source_binding))

    def counts(self) -> dict[str, int]:
        return {
            status: sum(item.status == status for item in self.results)
            for status in sorted(CHANNEL_VERIFICATION_STATUSES)
        }

    def resolution_count(self) -> int:
        return len(self.results)

    def verified_symbols(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.symbol
                    for item in self.results
                    if item.status == STATUS_VERIFIED
                }
            )
        )

    def verified_channels(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.channel
                    for item in self.results
                    if item.status == STATUS_VERIFIED
                }
            )
        )

    def human_review_packet(self) -> dict[str, Any]:
        counts = self.counts()
        return {
            "review_required": True,
            "review_scope": "M2 Channel Verification second-stage resolutions",
            "summary": {
                "lead_count": len(self.results),
                "verified_for_deep_research": counts[STATUS_VERIFIED],
                "rejected_after_verification": counts[STATUS_REJECTED],
                "insufficient_evidence": counts[STATUS_INSUFFICIENT],
                "unsupported": counts[STATUS_UNSUPPORTED],
                "verified_symbols": list(self.verified_symbols()),
                "verified_channels": list(self.verified_channels()),
            },
            "rules": [
                "Only pre-registered AC9 selected_leads were resolved.",
                "All outcomes are legal; a negative resolution is not a market conclusion.",
                "VERIFIED_FOR_DEEP_RESEARCH is a research-queue admission, not a valuation or BUY.",
            ],
            "rows": [
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "channel": item.channel,
                    "status": item.status,
                    "verification_id": item.verification_id,
                    "evidence_count": len(item.evidence),
                }
                for item in sorted(self.results, key=lambda row: row.symbol)
            ],
            "action": ACTION_NO_ORDER,
        }

    def as_policy(self) -> dict[str, Any]:
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
            "summary": {
                **self.counts(),
                "lead_count": len(self.results),
                "verified_symbols": list(self.verified_symbols()),
                "verified_channels": list(self.verified_channels()),
            },
            "results": [item.as_policy() for item in self.results],
            "human_review_packet": self.human_review_packet(),
        }


@dataclass(frozen=True)
class M2ChannelVerificationPolicy:
    """Hash-pinned inputs used to construct one verification packet."""

    schema_version: str
    policy_version: str
    as_of: date
    ac8_report_path: str
    ac8_report_sha256: str
    ac9_audit_report_path: str
    ac9_audit_report_sha256: str
    m2_receipt_path: str
    m2_receipt_sha256: str
    minimum_second_stage_resolutions: int
    minimum_channels: int
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != "m2-channel-verification-policy-v1":
            raise ValueError("Unknown channel verification policy schema")
        object.__setattr__(
            self, "policy_version", _required_text(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "as_of", _require_date(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "ac8_report_path",
            _required_text(self.ac8_report_path, "ac8_report_path"),
        )
        object.__setattr__(
            self,
            "ac8_report_sha256",
            _require_sha256(self.ac8_report_sha256, "ac8_report_sha256"),
        )
        object.__setattr__(
            self,
            "ac9_audit_report_path",
            _required_text(self.ac9_audit_report_path, "ac9_audit_report_path"),
        )
        object.__setattr__(
            self,
            "ac9_audit_report_sha256",
            _require_sha256(self.ac9_audit_report_sha256, "ac9_audit_report_sha256"),
        )
        object.__setattr__(
            self,
            "m2_receipt_path",
            _required_text(self.m2_receipt_path, "m2_receipt_path"),
        )
        object.__setattr__(
            self,
            "m2_receipt_sha256",
            _require_sha256(self.m2_receipt_sha256, "m2_receipt_sha256"),
        )
        if self.minimum_second_stage_resolutions <= 0:
            raise ValueError("Minimum second-stage resolutions must be positive")
        if self.minimum_channels <= 0:
            raise ValueError("Minimum channels must be positive")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Channel verification policy must remain no_order")


def load_m2_channel_verification_policy(
    path: Path | str,
) -> M2ChannelVerificationPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _reject_execution_keys(payload)
    return M2ChannelVerificationPolicy(
        schema_version=str(payload["schema_version"]),
        policy_version=str(payload["policy_version"]),
        as_of=date.fromisoformat(str(payload["as_of"])),
        ac8_report_path=str(payload["ac8_report_path"]),
        ac8_report_sha256=str(payload["ac8_report_sha256"]),
        ac9_audit_report_path=str(payload["ac9_audit_report_path"]),
        ac9_audit_report_sha256=str(payload["ac9_audit_report_sha256"]),
        m2_receipt_path=str(payload["m2_receipt_path"]),
        m2_receipt_sha256=str(payload["m2_receipt_sha256"]),
        minimum_second_stage_resolutions=int(
            payload["minimum_second_stage_resolutions"]
        ),
        minimum_channels=int(payload["minimum_channels"]),
        action=str(payload.get("action", ACTION_NO_ORDER)),
    )


def _evidence_from_payload(
    report: Mapping[str, Any],
    item: Mapping[str, Any],
    index: int,
) -> ChannelVerificationEvidence:
    raw_sha = item.get("source_sha256")
    return ChannelVerificationEvidence(
        id=(
            f"{report['report_id']}-evidence-{index + 1}"
        ),
        field_name=str(item.get("field_name") or ""),
        period_label=str(item.get("period_label") or ""),
        value=str(item.get("value") or ""),
        unit=str(item.get("unit") or ""),
        validation_status=str(item.get("validation_status") or ""),
        source_name=str(item.get("source_name") or ""),
        source_url=str(item.get("source_url") or ""),
        source_sha256=str(raw_sha) if raw_sha else None,
        published_at=(
            str(item["published_at"])
            if item.get("published_at") is not None
            else None
        ),
        fetched_at=(
            str(item["fetched_at"])
            if item.get("fetched_at") is not None
            else None
        ),
    )


def _status_for(source_verdict: str, evidence_count: int) -> str:
    if source_verdict == VERDICT_PENDING:
        return STATUS_VERIFIED if evidence_count else STATUS_INSUFFICIENT
    if source_verdict == VERDICT_REJECTED:
        return STATUS_REJECTED
    if source_verdict == VERDICT_INSUFFICIENT:
        return STATUS_INSUFFICIENT
    return STATUS_UNSUPPORTED


def _reason_for(
    status: str,
    symbol: str,
    channel: str,
    evidence_count: int,
) -> str:
    if status == STATUS_VERIFIED:
        return (
            f"{symbol} 的 {channel} 预注册线索完成二阶段证据核验，"
            f"当前绑定 {evidence_count} 条可追溯证据；仅为深研队列准入，"
            "不构成估值、仓位、BUY 或交易结论。"
        )
    if status == STATUS_REJECTED:
        return (
            f"{symbol} 的 {channel} 预注册线索经证据核验后否决；"
            "低 PE/PB 或单一触发条件不足以上升为已核候选。"
        )
    if status == STATUS_INSUFFICIENT:
        return (
            f"{symbol} 缺少 {channel} 二阶段所需的核心可追溯证据；"
            "保留为证据不足，不冒充拒绝或无机会。"
        )
    return f"{symbol} 的 {channel} 通道当前不支持通用核验。"


def build_m2_channel_verification(
    policy: M2ChannelVerificationPolicy,
    *,
    root: Path | str,
    generated_at: datetime,
) -> M2ChannelVerificationBatch:
    root = Path(root).resolve()
    ac8 = _verify_pinned_json(
        root,
        policy.ac8_report_path,
        policy.ac8_report_sha256,
    )
    ac9 = _verify_pinned_json(
        root,
        policy.ac9_audit_report_path,
        policy.ac9_audit_report_sha256,
    )
    receipt = _verify_pinned_json(
        root,
        policy.m2_receipt_path,
        policy.m2_receipt_sha256,
    )
    if ac8.get("schema_version") != M2_RESEARCH_REPORT_SCHEMA:
        raise ValueError("Unexpected AC8 research report schema")
    if ac8.get("action") != ACTION_NO_ORDER:
        raise ValueError("AC8 research report must remain no_order")
    if ac9.get("action") != ACTION_NO_ORDER:
        raise ValueError("AC9 coverage audit must remain no_order")
    if receipt.get("action") != ACTION_NO_ORDER:
        raise ValueError("M2 receipt must remain no_order")
    source_binding = dict(ac8.get("source_binding") or {})
    if source_binding.get("ac9_audit_report_sha256") != policy.ac9_audit_report_sha256:
        raise ValueError("AC8 source binding does not match the pinned AC9 report")
    if source_binding.get("m2_receipt_sha256") != policy.m2_receipt_sha256:
        raise ValueError("AC8 source binding does not match the pinned M2 receipt")

    results: list[ChannelVerificationResult] = []
    for report in ac8.get("reports") or []:
        symbol = str(report.get("symbol") or "").zfill(6)
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("AC8 report contains an invalid symbol")
        report_id = str(report.get("report_id") or "")
        name = str(report.get("name") or "")
        evidence = tuple(
            _evidence_from_payload(report, item, index)
            for index, item in enumerate(report.get("evidence") or [])
        )
        channel_verdicts = dict(report.get("channel_verdicts") or {})
        if not channel_verdicts:
            raise ValueError("AC8 report has no channel verdicts")
        for channel, source_verdict in channel_verdicts.items():
            status = _status_for(str(source_verdict), len(evidence))
            results.append(
                ChannelVerificationResult(
                    verification_id=f"{report_id}-{channel}-verification",
                    report_id=report_id,
                    symbol=symbol,
                    name=name,
                    channel=str(channel),
                    source_verdict=str(source_verdict),
                    status=status,
                    reason=_reason_for(
                        status, symbol, str(channel), len(evidence)
                    ),
                    evidence=evidence,
                    missing_evidence=tuple(
                        str(item) for item in report.get("missing_evidence") or ()
                    ),
                    positives=tuple(
                        str(item) for item in report.get("positives") or ()
                    ),
                    counter_evidence=tuple(
                        str(item) for item in report.get("counter_evidence") or ()
                    ),
                    market_context=dict(report.get("market_context") or {}),
                    rule_version=str(ac8.get("policy_version") or ""),
                    source_report_sha256=policy.ac8_report_sha256,
                )
            )

    results.sort(key=lambda item: (item.symbol, item.channel))
    channels = {item.channel for item in results}
    resolution_count = len(results)
    machine_status = (
        "MACHINE_CHECKS_PASS"
        if (
            resolution_count >= policy.minimum_second_stage_resolutions
            and len(channels) >= policy.minimum_channels
        )
        else "MACHINE_CHECKS_FAIL"
    )
    return M2ChannelVerificationBatch(
        schema_version=M2_CHANNEL_VERIFICATION_SCHEMA,
        policy_version=policy.policy_version,
        as_of=policy.as_of,
        generated_at=generated_at,
        action=ACTION_NO_ORDER,
        source_binding={
            "ac8_report_sha256": policy.ac8_report_sha256,
            "ac9_audit_report_sha256": policy.ac9_audit_report_sha256,
            "m2_receipt_sha256": policy.m2_receipt_sha256,
        },
        results=tuple(results),
        minimum_second_stage_resolutions=policy.minimum_second_stage_resolutions,
        minimum_channels=policy.minimum_channels,
        machine_status=machine_status,
        acceptance_status=(
            "CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION"
            if machine_status == "MACHINE_CHECKS_PASS"
            else "CHECKPOINT_A_NOT_READY"
        ),
    )
