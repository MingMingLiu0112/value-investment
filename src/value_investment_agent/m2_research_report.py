"""Evidence-bound AC8 research and rejection reports for M2 selected leads.

The report builder consumes the pre-registered AC9 ``selected_leads`` sample and
the pinned M2 input files. It never selects a company after seeing its financial
outcome, produces no valuation, BUY, position or order, and does not call an
``INSUFFICIENT_EVIDENCE`` report substantive.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .m2_market_data import parse_eastmoney_dividends
from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_LEAD,
    CHANNEL_CYCLICAL,
    CHANNEL_DIVIDEND,
    CHANNEL_QUALITY,
    CHANNEL_VALUE,
    CHANNELS,
    DATA_PARTIAL,
)


M2_RESEARCH_REPORT_SCHEMA = "m2-ac8-research-report-v1"
DEFAULT_RESEARCH_REPORT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "m2-ac8-research-report-v1.json"
)

VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
VERDICT_REJECTED = "REJECTED_FOR_CHANNEL"
VERDICT_PENDING = "PENDING_DEEP_RESEARCH"
RESEARCH_VERDICTS = {
    VERDICT_INSUFFICIENT,
    VERDICT_REJECTED,
    VERDICT_PENDING,
}

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

_FIELD_LABELS = {
    "revenue": "营业收入",
    "revenue_yoy": "营业收入同比",
    "net_income": "归母净利润",
    "net_income_yoy": "归母净利润同比",
    "operating_cash_flow": "经营活动现金流量净额",
    "free_cash_flow": "自由现金流",
    "fcf_per_share": "每股自由现金流",
    "debt_ratio": "资产负债率",
    "roe": "净资产收益率",
    "roic": "投入资本回报率",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "interest_bearing_debt": "有息负债",
    "bvps": "每股净资产",
    "eps_ttm": "TTM 每股收益",
}

_CORE_FIELDS = {
    "net_income",
    "operating_cash_flow",
    "free_cash_flow",
}

_EVIDENCE_FIELDS = (
    "revenue",
    "revenue_yoy",
    "net_income",
    "net_income_yoy",
    "operating_cash_flow",
    "free_cash_flow",
    "fcf_per_share",
    "debt_ratio",
    "roe",
    "roic",
    "gross_margin",
    "net_margin",
    "interest_bearing_debt",
    "bvps",
    "eps_ttm",
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _as_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _reject_execution_keys(value: object) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_KEYS & set(value):
            raise ValueError(
                "AC8 research report policy contains execution keys: "
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
        raise ValueError(f"AC8 evidence path escapes project root: {path}")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError(
            f"AC8 evidence SHA-256 mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"AC8 evidence payload must be an object: {path}")
    _reject_execution_keys(payload)
    return payload


def _available_at(point: Mapping[str, Any], evaluation_at: datetime) -> datetime | None:
    raw = point.get("available_at") or point.get("fetched_at") or point.get("created_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed > evaluation_at:
        return None
    return parsed


def _point_hash(point: Mapping[str, Any]) -> str | None:
    metadata = point.get("metadata") if isinstance(point.get("metadata"), Mapping) else {}
    value = point.get("sha256") or metadata.get("official_file_sha256") or metadata.get("sha256")
    if not value:
        return None
    text = str(value).lower()
    return text if _SHA256.fullmatch(text) else None


def _period_key(value: object) -> tuple[int, int, int]:
    text = str(value or "").split(" ", 1)[0]
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return (9999, 12, 31)
    return (parsed.year, parsed.month, parsed.day)


def _status_rank(point: Mapping[str, Any]) -> int:
    status = str(point.get("validation_status") or "").lower()
    return {"verified": 2, "pending": 1}.get(status, 0)


def _latest_points(
    points: list[dict[str, Any]],
    latest_financial_period: str,
) -> dict[str, dict[str, Any]]:
    period_limit = _period_key(latest_financial_period)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        if _period_key(point.get("period_label")) > period_limit:
            continue
        field = str(point.get("field_name") or "")
        if field and point.get("validation_status") in {"verified", "pending"}:
            grouped.setdefault(field, []).append(point)

    latest: dict[str, dict[str, Any]] = {}
    for field, candidates in grouped.items():
        candidates.sort(
            key=lambda item: (
                _period_key(item.get("period_label")),
                _status_rank(item),
                str(item.get("fetched_at") or item.get("created_at") or ""),
            )
        )
        latest[field] = candidates[-1]
    return latest


@dataclass(frozen=True)
class M2ResearchEvidence:
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
            raise ValueError("Research evidence symbol must be six digits")
        object.__setattr__(self, "field_name", _required_text(self.field_name, "field_name"))
        object.__setattr__(self, "period_label", _required_text(self.period_label, "period_label"))
        object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))
        object.__setattr__(
            self,
            "validation_status",
            _required_text(self.validation_status, "validation_status"),
        )
        object.__setattr__(self, "source_name", _required_text(self.source_name, "source_name"))
        object.__setattr__(self, "source_url", _required_text(self.source_url, "source_url"))
        source_sha256 = _optional_text(self.source_sha256, "source_sha256")
        if source_sha256 is not None and not _SHA256.fullmatch(source_sha256):
            raise ValueError("Research evidence source_sha256 is invalid")
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
class M2ResearchReport:
    report_id: str
    symbol: str
    name: str
    channels: tuple[str, ...]
    primary_channel: str
    verdict: str
    channel_verdicts: Mapping[str, str]
    candidate_class: str
    data_status: str
    title: str
    conclusion: str
    positives: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    next_events: tuple[str, ...]
    market_context: Mapping[str, Any]
    evidence: tuple[M2ResearchEvidence, ...]

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Research report symbol must be six digits")
        object.__setattr__(self, "report_id", _required_text(self.report_id, "report_id"))
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        channels = tuple(dict.fromkeys(self.channels))
        if not channels or set(channels) - set(CHANNELS):
            raise ValueError("Research report channels are invalid")
        object.__setattr__(self, "channels", channels)
        if self.primary_channel not in channels:
            raise ValueError("Research report primary channel must be one of its channels")
        if self.verdict not in RESEARCH_VERDICTS:
            raise ValueError(f"Unknown research verdict: {self.verdict}")
        if set(self.channel_verdicts) != set(channels):
            raise ValueError("Research report channel verdicts must match channels")
        if any(
            verdict not in RESEARCH_VERDICTS
            for verdict in self.channel_verdicts.values()
        ):
            raise ValueError("Research report contains an unknown channel verdict")
        if self.candidate_class != CANDIDATE_CLASS_LEAD:
            raise ValueError("AC8 report may only describe pre-registered LEADS")
        if self.data_status != DATA_PARTIAL:
            raise ValueError("AC8 report data status must remain PARTIAL")
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        object.__setattr__(self, "conclusion", _required_text(self.conclusion, "conclusion"))
        object.__setattr__(self, "positives", tuple(dict.fromkeys(self.positives)))
        object.__setattr__(self, "counter_evidence", tuple(dict.fromkeys(self.counter_evidence)))
        object.__setattr__(self, "missing_evidence", tuple(dict.fromkeys(self.missing_evidence)))
        object.__setattr__(self, "next_events", tuple(dict.fromkeys(self.next_events)))
        object.__setattr__(self, "market_context", dict(self.market_context))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        _reject_execution_keys(self.as_policy())

    def as_policy(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "symbol": self.symbol,
            "name": self.name,
            "channels": list(self.channels),
            "primary_channel": self.primary_channel,
            "verdict": self.verdict,
            "channel_verdicts": dict(self.channel_verdicts),
            "candidate_class": self.candidate_class,
            "data_status": self.data_status,
            "title": self.title,
            "conclusion": self.conclusion,
            "positives": list(self.positives),
            "counter_evidence": list(self.counter_evidence),
            "missing_evidence": list(self.missing_evidence),
            "next_events": list(self.next_events),
            "market_context": dict(self.market_context),
            "evidence": [item.as_policy() for item in self.evidence],
        }


@dataclass(frozen=True)
class M2ResearchReportBatch:
    schema_version: str
    policy_version: str
    action: str
    as_of: date
    minimum_substantive_reports: int
    minimum_channels: int
    source_binding: Mapping[str, Any]
    reports: tuple[M2ResearchReport, ...]
    machine_status: str
    acceptance_status: str

    def __post_init__(self) -> None:
        if self.schema_version != M2_RESEARCH_REPORT_SCHEMA:
            raise ValueError("Unknown M2 research report schema")
        object.__setattr__(
            self, "policy_version", _required_text(self.policy_version, "policy_version")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M2 research report action must remain no_order")
        if self.minimum_substantive_reports <= 0 or self.minimum_channels <= 0:
            raise ValueError("AC8 minimum report requirements must be positive")
        if not self.reports:
            raise ValueError("M2 research report batch must contain reports")
        symbols = [report.symbol for report in self.reports]
        if len(symbols) != len(set(symbols)):
            raise ValueError("M2 research report symbols must be unique")
        substantive = [
            report for report in self.reports if report.verdict != VERDICT_INSUFFICIENT
        ]
        channels = {
            channel
            for report in substantive
            for channel in report.channels
            if report.channel_verdicts.get(channel) != VERDICT_INSUFFICIENT
        }
        if len(substantive) < self.minimum_substantive_reports:
            raise ValueError(
                "AC8 substantive report count is below the registered minimum: "
                f"{len(substantive)} < {self.minimum_substantive_reports}"
            )
        if len(channels) < self.minimum_channels:
            raise ValueError(
                "AC8 substantive reports cover too few channels: " + str(sorted(channels))
            )
        object.__setattr__(self, "source_binding", dict(self.source_binding))
        object.__setattr__(self, "reports", tuple(self.reports))
        object.__setattr__(
            self, "machine_status", _required_text(self.machine_status, "machine_status")
        )
        object.__setattr__(
            self,
            "acceptance_status",
            _required_text(self.acceptance_status, "acceptance_status"),
        )
        _reject_execution_keys(self.as_policy())

    def substantive_reports(self) -> tuple[M2ResearchReport, ...]:
        return tuple(
            report for report in self.reports if report.verdict != VERDICT_INSUFFICIENT
        )

    def substantive_channels(self) -> tuple[str, ...]:
        return tuple(
            channel
            for channel in CHANNELS
            if any(
                report.channel_verdicts.get(channel)
                in {VERDICT_REJECTED, VERDICT_PENDING}
                for report in self.substantive_reports()
            )
        )

    def as_policy(self) -> dict[str, Any]:
        substantive = self.substantive_reports()
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "action": self.action,
            "as_of": self.as_of.isoformat(),
            "source_binding": dict(self.source_binding),
            "summary": {
                "report_count": len(self.reports),
                "substantive_report_count": len(substantive),
                "substantive_channels": list(self.substantive_channels()),
                "insufficient_evidence_count": sum(
                    report.verdict == VERDICT_INSUFFICIENT for report in self.reports
                ),
                "rejected_count": sum(
                    report.verdict == VERDICT_REJECTED for report in self.reports
                ),
                "pending_deep_research_count": sum(
                    report.verdict == VERDICT_PENDING for report in self.reports
                ),
            },
            "machine_status": self.machine_status,
            "acceptance_status": self.acceptance_status,
            "reports": [report.as_policy() for report in self.reports],
        }


@dataclass(frozen=True)
class M2ResearchReportPolicy:
    schema_version: str
    policy_version: str
    as_of: date
    sampling: Mapping[str, Any]
    evidence: Mapping[str, Any]
    minimum_substantive_reports: int
    minimum_channels: int
    latest_financial_period: str

    def __post_init__(self) -> None:
        if self.schema_version != "m2-ac8-research-report-policy-v1":
            raise ValueError("Unknown M2 research report policy schema")
        object.__setattr__(
            self, "policy_version", _required_text(self.policy_version, "policy_version")
        )
        if not self.sampling.get("audit_report_path") or not self.sampling.get("audit_report_sha256"):
            raise ValueError("M2 research report sampling binding is incomplete")
        if not self.sampling.get("stratum_id"):
            raise ValueError("M2 research report sampling stratum is required")
        if self.minimum_substantive_reports <= 0 or self.minimum_channels <= 0:
            raise ValueError("M2 research report minimum requirements must be positive")
        object.__setattr__(self, "sampling", dict(self.sampling))
        object.__setattr__(self, "evidence", dict(self.evidence))
        latest_period = _required_text(
            self.latest_financial_period,
            "latest_financial_period",
        )
        try:
            date.fromisoformat(latest_period)
        except ValueError as exc:
            raise ValueError("latest_financial_period must be an ISO date") from exc
        object.__setattr__(self, "latest_financial_period", latest_period)

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "action": ACTION_NO_ORDER,
            "sampling": dict(self.sampling),
            "evidence": dict(self.evidence),
            "minimum_substantive_reports": self.minimum_substantive_reports,
            "minimum_channels": self.minimum_channels,
            "latest_financial_period": self.latest_financial_period,
        }


def load_m2_research_report_policy(
    path: Path | str = DEFAULT_RESEARCH_REPORT_PATH,
) -> M2ResearchReportPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M2 research report policy must be a JSON object")
    _reject_execution_keys(payload)
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("M2 research report policy action must remain no_order")
    sampling = payload.get("sampling")
    evidence = payload.get("evidence")
    if not isinstance(sampling, Mapping) or not isinstance(evidence, Mapping):
        raise ValueError("M2 research report policy sampling and evidence are required")
    return M2ResearchReportPolicy(
        schema_version=str(payload.get("schema_version") or ""),
        policy_version=str(payload.get("policy_version") or ""),
        as_of=date.fromisoformat(str(payload.get("as_of") or "")),
        sampling=sampling,
        evidence=evidence,
        minimum_substantive_reports=int(payload.get("minimum_substantive_reports") or 0),
        minimum_channels=int(payload.get("minimum_channels") or 0),
        latest_financial_period=str(payload.get("latest_financial_period") or ""),
    )


def _load_samples(policy: M2ResearchReportPolicy, root: Path) -> list[dict[str, Any]]:
    audit = _verify_pinned_json(
        root,
        str(policy.sampling["audit_report_path"]),
        str(policy.sampling["audit_report_sha256"]),
    )
    if audit.get("action") != ACTION_NO_ORDER:
        raise ValueError("AC9 audit report action is not no_order")
    if audit.get("audit_status") != "MACHINE_CHECKS_PASS":
        raise ValueError("AC9 audit report has not passed machine checks")
    samples: list[dict[str, Any]] = []
    for stratum in audit.get("strata") or []:
        if stratum.get("stratum_id") != policy.sampling["stratum_id"]:
            continue
        for sample in stratum.get("samples") or []:
            if sample.get("candidate_class") != CANDIDATE_CLASS_LEAD:
                continue
            if sample.get("data_status") != DATA_PARTIAL:
                continue
            samples.append(dict(sample))
    if not samples:
        raise ValueError("AC8 pinned sampling contains no PARTIAL selected leads")
    return samples


def _sample_groups(samples: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        groups.setdefault(str(sample["symbol"]), []).append(sample)
    return groups


def _evidence_from_point(symbol: str, point: Mapping[str, Any]) -> M2ResearchEvidence:
    return M2ResearchEvidence(
        symbol=symbol,
        field_name=str(point.get("field_name") or ""),
        period_label=str(point.get("period_label") or ""),
        value=str(point.get("value") or ""),
        unit=str(point.get("unit") or ""),
        validation_status=str(point.get("validation_status") or ""),
        source_name=str(point.get("source_name") or ""),
        source_url=str(point.get("source_url") or ""),
        source_sha256=_point_hash(point),
        published_at=(
            str(point["published_at"]) if point.get("published_at") is not None else None
        ),
        fetched_at=(
            str(point.get("fetched_at") or point.get("created_at") or "") or None
        ),
    )


def _dividend_evidence(
    symbol: str, row: Mapping[str, Any] | None, sha256: str, fetched_at: str
) -> M2ResearchEvidence | None:
    if row is None:
        return None
    return M2ResearchEvidence(
        symbol=symbol,
        field_name="cash_dividend_per_share",
        period_label=f"FY{row.get('fiscal_year') or 'unknown'}",
        value=str(row.get("cash_dps") or ""),
        unit="CNY/share",
        validation_status="pending",
        source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
        source_url="https://data.eastmoney.com/yjfp/",
        source_sha256=sha256,
        published_at=str(row["declaration_date"]) if row.get("declaration_date") else None,
        fetched_at=fetched_at,
    )


def _channel_verdict(
    channel: str,
    latest: Mapping[str, dict[str, Any]],
    market_context: Mapping[str, Any],
    has_dividend: bool,
) -> str:
    missing_core = [
        field
        for field in _CORE_FIELDS
        if _as_decimal(latest.get(field, {}).get("value")) is None
    ]
    if missing_core or (channel == CHANNEL_DIVIDEND and not has_dividend):
        return VERDICT_INSUFFICIENT

    operating_cash_flow = _as_decimal(latest["operating_cash_flow"]["value"])
    free_cash_flow = _as_decimal(latest["free_cash_flow"]["value"])
    if operating_cash_flow is None or free_cash_flow is None:
        return VERDICT_INSUFFICIENT

    if channel == CHANNEL_DIVIDEND:
        if operating_cash_flow < 0 or free_cash_flow < 0:
            return VERDICT_REJECTED
        return VERDICT_PENDING

    if channel == CHANNEL_CYCLICAL:
        if free_cash_flow < 0:
            return VERDICT_REJECTED
        if (
            market_context.get("normalized_earnings") is None
            and market_context.get("current_vs_normalized_roe") is None
        ):
            return VERDICT_REJECTED
        return VERDICT_PENDING

    if channel == CHANNEL_VALUE:
        if (
            market_context.get("fcf_yield") is None
            and market_context.get("ev_ebit") is None
        ):
            return VERDICT_REJECTED
        return VERDICT_PENDING

    if channel == CHANNEL_QUALITY:
        return VERDICT_PENDING
    return VERDICT_INSUFFICIENT


def _overall_verdict(channel_verdicts: Mapping[str, str]) -> str:
    values = set(channel_verdicts.values())
    if not values or values <= {VERDICT_INSUFFICIENT}:
        return VERDICT_INSUFFICIENT
    if VERDICT_PENDING in values:
        return VERDICT_PENDING
    return VERDICT_REJECTED


def _market_context(samples: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for sample in samples:
        for key, value in (sample.get("metrics") or {}).items():
            if key not in merged and value is not None:
                merged[str(key)] = value
    return merged


def _metric_text(field: str, point: Mapping[str, Any] | None) -> str:
    if point is None or point.get("value") in (None, ""):
        return f"{_FIELD_LABELS.get(field, field)}缺失"
    return (
        f"{_FIELD_LABELS.get(field, field)} {point['value']} "
        f"{point.get('unit') or ''}"
    ).rstrip()


def _build_content(
    name: str,
    symbol: str,
    channels: tuple[str, ...],
    channel_verdicts: Mapping[str, str],
    latest: Mapping[str, dict[str, Any]],
    market_context: Mapping[str, Any],
    dividend: Mapping[str, Any] | None,
) -> tuple[
    str,
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    positives: list[str] = []
    counter_evidence: list[str] = []
    missing_evidence: list[str] = []

    net_income_yoy = _as_decimal(latest.get("net_income_yoy", {}).get("value"))
    revenue_yoy = _as_decimal(latest.get("revenue_yoy", {}).get("value"))
    operating_cash_flow = _as_decimal(latest.get("operating_cash_flow", {}).get("value"))
    free_cash_flow = _as_decimal(latest.get("free_cash_flow", {}).get("value"))
    debt_ratio = _as_decimal(latest.get("debt_ratio", {}).get("value"))

    if CHANNEL_DIVIDEND in channels and dividend is not None:
        yield_ratio = _as_decimal(dividend.get("declared_yield"))
        positives.append(
            f"FY2025 已披露每股现金分红 {dividend.get('cash_dps')} 元"
            + (
                f"，参考股息率 {float(yield_ratio) * 100:.2f}%"
                if yield_ratio is not None
                else ""
            )
        )
        if operating_cash_flow is not None and operating_cash_flow >= 0:
            positives.append("最新报告期经营活动现金流为正")
        if free_cash_flow is not None and free_cash_flow < 0:
            counter_evidence.append("最新报告期自由现金流为负")
        if operating_cash_flow is not None and operating_cash_flow < 0:
            counter_evidence.append("最新报告期经营活动现金流为负")
        missing_evidence.append("至少两个完整财年的派息历史和自由现金流覆盖")
        missing_evidence.append("派息政策、特别派息与一次性现金流影响")

    if CHANNEL_CYCLICAL in channels:
        if net_income_yoy is not None and net_income_yoy > 0:
            positives.append("最新报告期归母净利润同比增长")
        if operating_cash_flow is not None and operating_cash_flow >= 0:
            positives.append("最新报告期经营活动现金流为正")
        if free_cash_flow is not None and free_cash_flow < 0:
            counter_evidence.append("扩张资本开支使自由现金流为负")
        missing_evidence.append("正常化盈利、周期成本曲线与供需证据")
        missing_evidence.append("current_vs_normalized_roe 和周期位置")

    if CHANNEL_VALUE in channels:
        if market_context.get("pe_ttm") is not None:
            positives.append(f"TTM PE {market_context.get('pe_ttm')}")
        if market_context.get("pb") is not None:
            positives.append(f"PB {market_context.get('pb')}")
        counter_evidence.append("低 PE/PB 尚缺少 FCF Yield、EV/EBIT 和正常化收益")
        missing_evidence.append("资产负债表质量和资产重置价值")

    if net_income_yoy is not None and net_income_yoy < 0:
        counter_evidence.append(f"归母净利润同比下降 {abs(net_income_yoy):.2f}%")
    if revenue_yoy is not None and revenue_yoy < 0:
        counter_evidence.append(f"营业收入同比下降 {abs(revenue_yoy):.2f}%")
    if debt_ratio is not None and debt_ratio > 60:
        counter_evidence.append(f"资产负债率约 {debt_ratio:.2f}%")

    if channel_verdicts.get(CHANNEL_DIVIDEND) == VERDICT_REJECTED:
        conclusion = (
            f"{name}（{symbol}）是股息通道预登记线索，但 2026-06-30 经营现金流或自由现金流"
            "为负，不能通过现金可持续性初筛；当前保留为实质否决反例，不升级为已核候选。"
        )
    elif channel_verdicts.get(CHANNEL_CYCLICAL) == VERDICT_REJECTED:
        conclusion = (
            f"{name}（{symbol}）是周期通道预登记线索，但自由现金流为负且缺少正常化周期"
            "证据；当前低 PE 不能作为低估依据，保留为实质否决反例。"
        )
    elif VERDICT_PENDING in set(channel_verdicts.values()):
        conclusion = (
            f"{name}（{symbol}）已有核心财务和来源证据，但仍需补足派息/周期/价值深研输入。"
            f"当前核心数字：{_metric_text('net_income', latest.get('net_income'))}，"
            f"{_metric_text('operating_cash_flow', latest.get('operating_cash_flow'))}，"
            f"{_metric_text('free_cash_flow', latest.get('free_cash_flow'))}。"
            "保留为深研线索，不构成估值或交易结论。"
        )
    else:
        conclusion = (
            f"{name}（{symbol}）缺少可追溯的最新报告期核心财务点，不能形成实质研究结论。"
            "该样本记录为证据不足，不冒充拒绝或无机会。"
        )

    title = f"{name}：M2 实质研究/否决"
    next_events = (
        "2026 年年度报告及审计意见",
        "下一年度利润分配预案",
        "重大资本开支、融资或行业政策变化",
    )
    return (
        title,
        conclusion,
        tuple(dict.fromkeys(positives)),
        tuple(dict.fromkeys(counter_evidence)),
        tuple(dict.fromkeys(missing_evidence)),
        next_events,
    )


def build_m2_research_reports(
    policy: M2ResearchReportPolicy,
    root: Path | str,
) -> M2ResearchReportBatch:
    root = Path(root).resolve()
    receipt = _verify_pinned_json(
        root,
        str(policy.evidence["receipt_path"]),
        str(policy.evidence["receipt_sha256"]),
    )
    if receipt.get("action") != ACTION_NO_ORDER:
        raise ValueError("M2 receipt action is not no_order")
    generated_at = datetime.fromisoformat(str(receipt["generated_at"]))

    financial_payload = _verify_pinned_json(
        root,
        str(policy.evidence["financial_points_path"]),
        str(policy.evidence["financial_points_sha256"]),
    )
    financial_points = financial_payload.get("points") or []

    dividend_payload = _verify_pinned_json(
        root,
        str(policy.evidence["dividend_path"]),
        str(policy.evidence["dividend_sha256"]),
    )
    dividend_rows = parse_eastmoney_dividends(dividend_payload)
    dividends = {row["symbol"]: row for row in dividend_rows}

    samples = _load_samples(policy, root)
    groups = _sample_groups(samples)
    reports: list[M2ResearchReport] = []
    for symbol, symbol_samples in groups.items():
        points = [
            dict(point)
            for point in financial_points
            if str(point.get("symbol") or "").zfill(6) == symbol
            and _available_at(point, generated_at) is not None
        ]
        latest = _latest_points(points, policy.latest_financial_period)
        channel_order = [
            channel
            for channel in CHANNELS
            if channel in {str(sample["channel"]) for sample in symbol_samples}
        ]
        channels = tuple(channel_order)
        name = next(
            (
                str(sample.get("name") or "").strip()
                for sample in symbol_samples
                if sample.get("name")
            ),
            f"公司{symbol}",
        )
        market_context = _market_context(symbol_samples)
        dividend = dividends.get(symbol)
        channel_verdicts = {
            channel: _channel_verdict(
                channel,
                latest,
                market_context,
                has_dividend=dividend is not None,
            )
            for channel in channels
        }
        verdict = _overall_verdict(channel_verdicts)
        evidence = tuple(
            _evidence_from_point(symbol, latest[field])
            for field in _EVIDENCE_FIELDS
            if field in latest
        )
        if dividend is not None:
            evidence += (
                _dividend_evidence(
                    symbol,
                    dividend,
                    str(policy.evidence["dividend_sha256"]),
                    str(dividend_payload.get("fetched_at") or ""),
                ),
            )
        title, conclusion, positives, counter, missing, events = _build_content(
            name,
            symbol,
            channels,
            channel_verdicts,
            latest,
            market_context,
            dividend,
        )
        reports.append(
            M2ResearchReport(
                report_id=f"m2-ac8-{symbol}-{policy.policy_version}",
                symbol=symbol,
                name=name,
                channels=channels,
                primary_channel=channels[0],
                verdict=verdict,
                channel_verdicts=channel_verdicts,
                candidate_class=CANDIDATE_CLASS_LEAD,
                data_status=DATA_PARTIAL,
                title=title,
                conclusion=conclusion,
                positives=positives,
                counter_evidence=counter,
                missing_evidence=missing,
                next_events=events,
                market_context=market_context,
                evidence=evidence,
            )
        )

    reports.sort(key=lambda report: report.symbol)
    return M2ResearchReportBatch(
        schema_version=M2_RESEARCH_REPORT_SCHEMA,
        policy_version=policy.policy_version,
        action=ACTION_NO_ORDER,
        as_of=policy.as_of,
        minimum_substantive_reports=policy.minimum_substantive_reports,
        minimum_channels=policy.minimum_channels,
        source_binding={
            "ac9_audit_report_sha256": policy.sampling["audit_report_sha256"],
            "m2_receipt_sha256": policy.evidence["receipt_sha256"],
            "financial_points_sha256": policy.evidence["financial_points_sha256"],
            "dividend_sha256": policy.evidence["dividend_sha256"],
        },
        reports=tuple(reports),
        machine_status="MACHINE_CHECKS_PASS",
        acceptance_status="AC8_REVIEW_PENDING",
    )
