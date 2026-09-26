"""Typed presentation-only read model for the M7 product workbench.

The model consumes already-decided M2-M6 application states and translates
them into user-facing cards. It does not calculate valuation, materiality,
portfolio capacity or dividend sustainability, and it never creates an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Mapping, Sequence


PRODUCT_WORKBENCH_SCHEMA_VERSION = "m7-product-workbench-v1"
ACTION_NO_ORDER = "no_order"

PAGE_TODAY = "今日"
PAGE_OPPORTUNITIES = "机会"
PAGE_COMPANIES = "公司"
PAGE_PORTFOLIO = "我的组合"
PAGE_EVENTS = "事件"
PAGE_SYSTEM_AUDIT = "系统/审计"

HEALTH_VERIFIED = "VERIFIED"
HEALTH_EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
HEALTH_DATA_ERROR = "DATA_ERROR"

COMPANY_SECTION_KEYS = (
    "business_quality",
    "financial_quality",
    "capital_allocation",
    "valuation",
    "dividend",
    "risks_counterevidence",
)
COMPANY_SECTION_TITLES = {
    "business_quality": "商业质量",
    "financial_quality": "财务质量",
    "capital_allocation": "资本配置",
    "valuation": "估值",
    "dividend": "股息",
    "risks_counterevidence": "风险与反证",
}

SCENARIO_KEYS = ("bear", "base", "bull")
SCENARIO_TITLES = {"bear": "Bear", "base": "Base", "bull": "Bull"}

PORTFOLIO_METRIC_KEYS = (
    "total_assets",
    "cash",
    "holdings",
    "industry_exposure",
    "single_stock_concentration",
    "cyclical_exposure",
    "estimated_annual_dividend",
    "normalized_annual_dividend",
    "stock_position",
    "portfolio_risk",
)
PORTFOLIO_METRIC_LABELS = {
    "total_assets": "总资产",
    "cash": "现金",
    "holdings": "持仓",
    "industry_exposure": "行业暴露",
    "single_stock_concentration": "单股集中度",
    "cyclical_exposure": "周期暴露",
    "estimated_annual_dividend": "预计年股息",
    "normalized_annual_dividend": "正常化年股息",
    "stock_position": "股票仓位",
    "portfolio_risk": "组合风险",
}

EVENT_CATEGORY_LABELS = {
    "MATERIAL_REQUIRES_RECALCULATION": "需要重新评估的重大事件",
    "MATERIAL_SUPPORTING_EVIDENCE": "支持现有判断的重大证据",
    "THESIS_RISK": "投资逻辑风险",
    "DIVIDEND_CHANGE": "股息变化",
    "PORTFOLIO_RISK_CHANGE": "组合风险变化",
    "SYSTEM_DATA_RISK": "系统或数据风险",
}

TODAY_CATEGORY_LABELS = {
    "EVENT": "重要事件",
    "RESEARCH_CHANGE": "研究状态变化",
    "PRICE_WATCH": "价格进入关注范围",
    "EVIDENCE_INVALIDATION": "证据失效",
    "PORTFOLIO_RISK": "组合风险变化",
    "DATA_ISSUE": "数据异常",
}

RESEARCH_STATUS_LABELS = {
    "VERIFIED_FOR_DEEP_RESEARCH": "已进入深入研究",
    "PENDING_HUMAN_REVIEW": "等待人工复核",
    "INSUFFICIENT_EVIDENCE": "等待关键经营证据",
    "REJECTED_AFTER_VERIFICATION": "初步筛选未通过",
    "NEED_MORE_EVIDENCE": "等待更多证据",
    "WAIT_FOR_PRICE": "研究完成，等待价格",
    "RESEARCH_INCOMPLETE": "研究尚未完成",
    "NOT_STARTED": "研究尚未开始",
    "PARTIAL": "研究仍在进行",
    "READABLE": "研究资料已完整",
    "RECONSTRUCTED_EVIDENCE_ONLY": "仅有部分历史证据",
    "WAIT": "等待下一步研究",
    "WAITING": "等待下一步研究",
}

VALUATION_STATUS_LABELS = {
    "AVAILABLE": "已有估值结果",
    "UNDER_REVIEW": "估值正在复核",
    "NOT_READY": "估值尚未就绪",
    "UNAVAILABLE": "暂不可评估",
    "NOT_APPLICABLE": "现有估值模型不适用",
    "MODEL_NOT_EXECUTED": "估值模型尚未运行",
    "STALE": "估值输入已过期",
    "WAIT": "等待估值输入",
}

DIVIDEND_STATUS_LABELS = {
    "AVAILABLE": "已有股息评估",
    "NOT_READY": "股息状态尚未就绪",
    "UNAVAILABLE": "股息暂不可评估",
    "INSUFFICIENT_EVIDENCE": "股息证据不足",
    "CHANGE": "股息发生变化",
    "NOT_APPLICABLE": "股息评估不适用",
    "WAIT": "等待股息证据",
}

PRICE_STATUS_LABELS = {
    "AVAILABLE": "已有可用价格",
    "IN_WATCH_RANGE": "价格进入关注范围",
    "OUTSIDE_RANGE": "价格尚未进入关注范围",
    "WAIT_FOR_PRICE": "等待价格",
    "UNAVAILABLE": "暂无可用价格",
    "STALE": "价格信息已过期",
    "WAIT": "等待价格信息",
}

MARGIN_STATUS_LABELS = {
    "AVAILABLE": "已有安全边际结果",
    "NOT_READY": "安全边际尚未就绪",
    "UNAVAILABLE": "安全边际暂不可评估",
    "UNDER_REVIEW": "安全边际正在复核",
    "WAIT": "等待估值输入",
}

SECTION_STATUS_LABELS = {
    "COMPLETE": "已验证",
    "PARTIAL": "仍在验证",
    "UNKNOWN": "暂无法判断",
    "MISSING": "缺少证据",
    "NOT_APPLICABLE": "不适用",
    "BLOCKED": "暂时受阻",
    "NOT_STARTED": "尚未开始",
}

PORTFOLIO_STATUS_LABELS = {
    "PENDING_USER_PRIVATE_INPUT": "尚未接入真实组合",
    "NOT_STARTED": "尚未接入真实组合",
    "REAL_DATA_AVAILABLE": "真实组合已接入",
    "READY": "真实组合已接入",
    "SIMULATED_ONLY": "仅完成模拟演练，尚未接入真实组合",
    "UNAVAILABLE": "真实组合不可用",
}

CONTINUATION_REVIEW_LABELS = {
    "ALLOWED": "允许进入继续复核",
    "NOT_ALLOWED": "暂不进入继续复核",
    "NOT_READY": "尚不能判断是否继续复核",
}

RESEARCH_ACTION_LABELS = {
    "REOPEN_RESEARCH": "需要重新研究",
    "NO_REOPEN_REQUIRED": "无需重新研究",
    "PENDING_REVIEW": "等待人工判断",
    "MONITOR": "继续观察",
}

THESIS_CHANGE_LABELS = {
    "CHANGED": "当前投资逻辑已发生变化",
    "UNCHANGED": "当前投资逻辑未变化",
    "UNKNOWN": "当前投资逻辑是否变化尚待确认",
}

SYSTEM_HEALTH_LABELS = {
    HEALTH_VERIFIED: "已验证",
    "PASS": "已验证",
    HEALTH_EVIDENCE_INSUFFICIENT: "证据不足",
    "WARN": "证据不足",
    HEALTH_DATA_ERROR: "数据异常",
    "FAIL": "数据异常",
}

STAGE_LABELS = {
    "m2": "初步筛选",
    "m3": "研究证据",
    "m4": "个人组合",
    "m5": "事件扫描",
    "m6": "真实监控",
}

STAGE_STATUS_LABELS = {
    "m2": {
        "DONE": "初步筛选已完成",
        "HUMAN_PASS": "初步筛选已人工通过",
        "ENGINEERING_DONE": "初步筛选工程已完成",
        "PENDING_HUMAN_REVIEW": "初步筛选等待人工复核",
        "PARTIAL": "初步筛选仍在进行",
        "NOT_STARTED": "初步筛选尚未开始",
        "WAIT": "等待初步筛选数据",
        "BLOCKED": "初步筛选暂时受阻",
    },
    "m3": {
        "DONE": "研究资料已验证",
        "ENGINEERING_PARTIAL_PLUS": "研究资料仍在补齐",
        "PENDING_HUMAN_REVIEW": "研究资料等待人工复核",
        "PARTIAL": "研究资料仍在补齐",
        "NOT_STARTED": "研究尚未开始",
        "WAIT": "等待研究证据",
        "RECONSTRUCTED_EVIDENCE_ONLY": "仅重建了部分历史证据",
        "STRICT_PIT_PROVEN": "历史时点证据已通过",
        "NOT_PROVEN": "历史时点证据尚未证明",
        "BLOCKED": "研究暂时受阻",
    },
    "m4": {
        "PENDING_USER_PRIVATE_INPUT": "尚未接入个人组合",
        "REAL_DATA_AVAILABLE": "真实组合已接入",
        "READY": "真实组合已接入",
        "SIMULATED_ONLY": "仅完成模拟演练，尚未接入真实组合",
        "ENGINEERING_DONE_SIMULATED": "仅完成模拟演练，尚未接入真实组合",
        "NOT_STARTED": "个人组合尚未接入",
        "WAIT": "等待个人组合输入",
    },
    "m5": {
        "DONE": "事件扫描已完成",
        "ENGINEERING_DONE_OFFLINE": "离线事件扫描已完成",
        "PENDING_HUMAN_REVIEW": "有事件等待人工复核",
        "PENDING_RECONCILIATION": "事件扫描等待对账",
        "PARTIAL": "事件扫描仍在进行",
        "NOT_STARTED": "事件扫描尚未开始",
        "WAIT": "等待事件数据",
        "DEGRADED": "事件扫描需要关注",
    },
    "m6": {
        "PREFLIGHT_DONE": "检查已完成，真实监控尚未开始",
        "NOT_STARTED": "真实监控尚未开始",
        "OPERATIONAL_NOT_STARTED": "真实监控尚未开始",
        "WAIT": "等待系统准备完成",
        "ACTIVE": "真实监控运行中",
        "DEGRADED": "真实监控需要关注",
        "BLOCKED": "真实监控暂时受阻",
    },
}

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_KEYS = frozenset(
    {
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "order_price",
        "order_id",
        "order",
        "quantity",
        "trade",
        "execute",
        "target_position",
        "proposed_entry",
        "buy",
        "sell",
        "broker",
        "live_eligible",
    }
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{field} must be a date")
    return value


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _ref_ids(value: Sequence[str]) -> tuple[str, ...]:
    result = tuple(_required_text(item, "evidence reference id") for item in value)
    if len(set(result)) != len(result):
        raise ValueError("Evidence reference ids must be unique")
    return result


def _reject_execution_keys(value: object, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        forbidden = _EXECUTION_KEYS.intersection(value)
        if forbidden:
            raise ValueError(
                f"Product workbench payload contains execution keys at {path}: "
                + ", ".join(sorted(forbidden))
            )
        for key, child in value.items():
            _reject_execution_keys(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_execution_keys(child, f"{path}[{index}]")


def _require_no_order_actions(value: object, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        if "action" in value and value["action"] != ACTION_NO_ORDER:
            raise ValueError(f"{path}.action must remain no_order")
        for key, child in value.items():
            _require_no_order_actions(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _require_no_order_actions(child, f"{path}[{index}]")


def _status_view(code: object, labels: Mapping[str, str], field: str) -> "StatusView":
    normalized = _required_text(code, field).upper()
    try:
        label = labels[normalized]
    except KeyError as error:
        raise ValueError(f"Unknown {field}: {normalized}") from error
    return StatusView(code=normalized, user_label=label)


@dataclass(frozen=True)
class StatusView:
    """An internal status plus its user-facing translation."""

    code: str
    user_label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "status code").upper())
        object.__setattr__(
            self,
            "user_label",
            _required_text(self.user_label, "status user label"),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    """A source record rendered only in the secondary audit view."""

    evidence_id: str
    title: str
    artifact_type: str
    path: str
    sha256: str
    available_at: date | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _required_text(self.evidence_id, "evidence id"),
        )
        object.__setattr__(self, "title", _required_text(self.title, "evidence title"))
        object.__setattr__(
            self,
            "artifact_type",
            _required_text(self.artifact_type, "evidence artifact type"),
        )
        object.__setattr__(self, "path", _required_text(self.path, "evidence path"))
        digest = _required_text(self.sha256, "evidence sha256").lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("evidence sha256 must be SHA-256 hex")
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(
            self,
            "available_at",
            None
            if self.available_at is None
            else _required_date(self.available_at, "evidence available_at"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Evidence records must remain no_order")


@dataclass(frozen=True)
class StageSummary:
    """Raw M2-M6 status for the audit page."""

    stage_key: str
    stage_label: str
    status: StatusView
    detail: str

    def __post_init__(self) -> None:
        key = _required_text(self.stage_key, "stage key").lower()
        if key not in STAGE_LABELS:
            raise ValueError(f"Unknown stage key: {key}")
        object.__setattr__(self, "stage_key", key)
        object.__setattr__(
            self,
            "stage_label",
            _required_text(self.stage_label, "stage label"),
        )
        object.__setattr__(self, "detail", _required_text(self.detail, "stage detail"))


@dataclass(frozen=True)
class AssessmentView:
    """A precomputed assessment or an explicit non-numeric unavailable state."""

    key: str
    status: StatusView
    available: bool
    value_text: str | None
    unavailable_reason: str | None
    needed_evidence: str | None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _required_text(self.key, "assessment key"))
        if not isinstance(self.available, bool):
            raise ValueError("assessment available must be boolean")
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.available:
            object.__setattr__(
                self,
                "value_text",
                _required_text(self.value_text, "assessment value_text"),
            )
            if self.unavailable_reason is not None or self.needed_evidence is not None:
                raise ValueError(
                    "Available assessments cannot carry unavailable reason or needed evidence"
                )
        else:
            if self.value_text is not None:
                raise ValueError(
                    "Unavailable assessments cannot carry a numeric or text placeholder"
                )
            object.__setattr__(
                self,
                "unavailable_reason",
                _required_text(self.unavailable_reason, "unavailable reason"),
            )
            object.__setattr__(
                self,
                "needed_evidence",
                _required_text(self.needed_evidence, "needed evidence"),
            )


@dataclass(frozen=True)
class TodayItem:
    category: StatusView
    company: str
    what_happened: str
    why_it_matters: str
    current_status: str
    next_step: str
    evidence_refs: tuple[str, ...] = ()
    symbol: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "company",
            "what_happened",
            "why_it_matters",
            "current_status",
            "next_step",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.symbol is not None and not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Today item symbol must contain six digits")


@dataclass(frozen=True)
class OpportunityCard:
    symbol: str
    company_name: str
    why_now: str
    research_status: StatusView
    valuation_status: StatusView
    dividend_status: StatusView
    price_status: StatusView
    main_risk: str
    next_trigger: str
    evidence_refs: tuple[str, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Opportunity symbol must contain six digits")
        for field in ("company_name", "why_now", "main_risk", "next_trigger"):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Opportunity cards must remain no_order")


@dataclass(frozen=True)
class CompanySection:
    key: str
    status: StatusView
    summary: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        key = _required_text(self.key, "company section key")
        if key not in COMPANY_SECTION_KEYS:
            raise ValueError(f"Unknown company section key: {key}")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "summary", _required_text(self.summary, "section summary"))
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))

    @property
    def title(self) -> str:
        return COMPANY_SECTION_TITLES[self.key]


@dataclass(frozen=True)
class ScenarioCard:
    key: str
    assessment: AssessmentView

    def __post_init__(self) -> None:
        key = _required_text(self.key, "scenario key")
        if key not in SCENARIO_KEYS:
            raise ValueError(f"Unknown scenario key: {key}")
        object.__setattr__(self, "key", key)

    @property
    def title(self) -> str:
        return SCENARIO_TITLES[self.key]


@dataclass(frozen=True)
class CompanyCard:
    symbol: str
    company_name: str
    research_status: StatusView
    price: AssessmentView
    valuation: AssessmentView
    margin_of_safety: AssessmentView
    dividend: AssessmentView
    sections: tuple[CompanySection, ...]
    scenarios: tuple[ScenarioCard, ...]
    latest_change: str
    next_trigger: str
    original_thesis: str
    thesis_change: StatusView
    evidence_refs: tuple[str, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Company symbol must contain six digits")
        for field in (
            "company_name",
            "latest_change",
            "next_trigger",
            "original_thesis",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        section_keys = tuple(section.key for section in self.sections)
        if section_keys != COMPANY_SECTION_KEYS:
            raise ValueError("Company card requires all six sections in order")
        scenario_keys = tuple(scenario.key for scenario in self.scenarios)
        if scenario_keys != SCENARIO_KEYS:
            raise ValueError("Company card requires Bear, Base and Bull scenarios")
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Company cards must remain no_order")


@dataclass(frozen=True)
class PortfolioMetric:
    key: str
    label: str
    value_text: str

    def __post_init__(self) -> None:
        key = _required_text(self.key, "portfolio metric key")
        if key not in PORTFOLIO_METRIC_KEYS:
            raise ValueError(f"Unknown portfolio metric key: {key}")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", _required_text(self.label, "portfolio metric label"))
        object.__setattr__(
            self,
            "value_text",
            _required_text(self.value_text, "portfolio metric value_text"),
        )


@dataclass(frozen=True)
class PortfolioPositionCard:
    symbol: str
    company_name: str
    current_position_text: str
    allowed_capacity_text: str
    current_risk_text: str
    continuation_review: StatusView
    reason: str
    evidence_refs: tuple[str, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Portfolio position symbol must contain six digits")
        for field in (
            "company_name",
            "current_position_text",
            "allowed_capacity_text",
            "current_risk_text",
            "reason",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio positions must remain no_order")


@dataclass(frozen=True)
class PortfolioCard:
    real_data_available: bool
    status: StatusView
    connection_hint: str
    summary: tuple[PortfolioMetric, ...] = ()
    positions: tuple[PortfolioPositionCard, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not isinstance(self.real_data_available, bool):
            raise ValueError("portfolio real_data_available must be boolean")
        object.__setattr__(
            self,
            "connection_hint",
            _required_text(self.connection_hint, "portfolio connection hint"),
        )
        if not self.real_data_available and (self.summary or self.positions):
            raise ValueError("A simulated or absent portfolio cannot expose metrics or positions")
        if not self.real_data_available and self.status.code in {
            "REAL_DATA_AVAILABLE",
            "READY",
        }:
            raise ValueError("An absent portfolio cannot claim real data is available")
        if self.real_data_available:
            if self.status.code not in {"REAL_DATA_AVAILABLE", "READY"}:
                raise ValueError("A real portfolio requires an available status")
            metric_keys = tuple(metric.key for metric in self.summary)
            if set(metric_keys) != set(PORTFOLIO_METRIC_KEYS):
                raise ValueError("A real portfolio requires every registered summary metric")
            if len(metric_keys) != len(set(metric_keys)):
                raise ValueError("Portfolio summary metric keys must be unique")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio cards must remain no_order")


@dataclass(frozen=True)
class EventCard:
    event_id: str
    category: StatusView
    company_name: str
    what_happened: str
    impact_area: str
    current_conclusion: str
    research_action: StatusView
    next_step: str
    evidence_refs: tuple[str, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event id"))
        for field in (
            "company_name",
            "what_happened",
            "impact_area",
            "current_conclusion",
            "next_step",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "evidence_refs", _ref_ids(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event cards must remain no_order")


@dataclass(frozen=True)
class SystemHealthCard:
    status: StatusView
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _required_text(self.message, "system health message"))


@dataclass(frozen=True)
class WorkbenchOverview:
    data_updated_at: datetime
    pending_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_updated_at",
            _required_datetime(self.data_updated_at, "data_updated_at"),
        )
        object.__setattr__(
            self,
            "pending_count",
            _non_negative_int(self.pending_count, "pending_count"),
        )


def _company_evidence_refs(card: CompanyCard) -> tuple[str, ...]:
    refs: list[str] = list(card.evidence_refs)
    for assessment in (
        card.price,
        card.valuation,
        card.margin_of_safety,
        card.dividend,
    ):
        refs.extend(assessment.evidence_refs)
    for section in card.sections:
        refs.extend(section.evidence_refs)
    for scenario in card.scenarios:
        refs.extend(scenario.assessment.evidence_refs)
    return tuple(refs)


@dataclass(frozen=True)
class ProductWorkbenchReadModel:
    schema_version: str
    generated_at: datetime
    as_of: date
    overview: WorkbenchOverview
    system_health: SystemHealthCard
    stage_summaries: tuple[StageSummary, ...]
    today_items: tuple[TodayItem, ...]
    opportunities: tuple[OpportunityCard, ...]
    companies: tuple[CompanyCard, ...]
    portfolio: PortfolioCard
    events: tuple[EventCard, ...]
    audit_evidence: tuple[EvidenceRecord, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != PRODUCT_WORKBENCH_SCHEMA_VERSION:
            raise ValueError("Unsupported product workbench schema")
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "generated_at"),
        )
        object.__setattr__(
            self,
            "as_of",
            _required_date(self.as_of, "as_of"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Product workbench must remain no_order")

        stage_keys = {item.stage_key for item in self.stage_summaries}
        if stage_keys != set(STAGE_LABELS):
            raise ValueError("Product workbench requires M2-M6 stage summaries")

        company_symbols = [company.symbol for company in self.companies]
        opportunity_symbols = [card.symbol for card in self.opportunities]
        if len(company_symbols) != len(set(company_symbols)):
            raise ValueError("Company symbols must be unique")
        if len(opportunity_symbols) != len(set(opportunity_symbols)):
            raise ValueError("Opportunity symbols must be unique")

        evidence_ids = [record.evidence_id for record in self.audit_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Audit evidence ids must be unique")

        known = set(evidence_ids)
        referenced: set[str] = set()
        for item in self.today_items:
            referenced.update(item.evidence_refs)
        for card in self.opportunities:
            referenced.update(card.evidence_refs)
        for company in self.companies:
            referenced.update(_company_evidence_refs(company))
        for position in self.portfolio.positions:
            referenced.update(position.evidence_refs)
        for event in self.events:
            referenced.update(event.evidence_refs)
        missing = referenced - known
        if missing:
            raise ValueError(
                "Product workbench cards reference missing audit evidence: "
                + ", ".join(sorted(missing))
            )


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _required_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _parse_evidence(value: object) -> EvidenceRecord:
    item = _required_mapping(value, "evidence item")
    available_at = item.get("available_at")
    parsed_date = None
    if available_at not in (None, ""):
        try:
            parsed_date = date.fromisoformat(_required_text(available_at, "available_at"))
        except ValueError as error:
            raise ValueError("available_at must be ISO date") from error
    return EvidenceRecord(
        evidence_id=_required_text(item.get("evidence_id"), "evidence_id"),
        title=_required_text(item.get("title"), "evidence title"),
        artifact_type=_required_text(item.get("artifact_type"), "artifact_type"),
        path=_required_text(item.get("path"), "evidence path"),
        sha256=_required_text(item.get("sha256"), "evidence sha256"),
        available_at=parsed_date,
        action=str(item.get("action") or ACTION_NO_ORDER),
    )


def _parse_stage(key: str, value: object) -> StageSummary:
    item = _required_mapping(value, f"stages.{key}")
    return StageSummary(
        stage_key=key,
        stage_label=STAGE_LABELS[key],
        status=_status_view(
            item.get("status"),
            STAGE_STATUS_LABELS[key],
            f"stages.{key}.status",
        ),
        detail=_required_text(item.get("detail"), f"stages.{key}.detail"),
    )


def _parse_assessment(
    value: object,
    *,
    key: str,
    labels: Mapping[str, str],
) -> AssessmentView:
    item = _required_mapping(value, key)
    available = item.get("available")
    if not isinstance(available, bool):
        raise ValueError(f"{key}.available must be boolean")
    return AssessmentView(
        key=key,
        status=_status_view(item.get("status"), labels, f"{key}.status"),
        available=available,
        value_text=item.get("value_text"),
        unavailable_reason=item.get("unavailable_reason"),
        needed_evidence=item.get("needed_evidence"),
        evidence_refs=tuple(item.get("evidence_refs") or ()),
    )


def _parse_today_item(value: object) -> TodayItem:
    item = _required_mapping(value, "today item")
    return TodayItem(
        category=_status_view(
            item.get("category"),
            TODAY_CATEGORY_LABELS,
            "today.category",
        ),
        company=_required_text(item.get("company"), "today company"),
        what_happened=_required_text(item.get("what_happened"), "what_happened"),
        why_it_matters=_required_text(item.get("why_it_matters"), "why_it_matters"),
        current_status=_required_text(item.get("current_status"), "current_status"),
        next_step=_required_text(item.get("next_step"), "next_step"),
        evidence_refs=tuple(item.get("evidence_refs") or ()),
        symbol=_optional_text(item.get("symbol"), "today symbol"),
    )


def _parse_opportunity(value: object) -> OpportunityCard:
    item = _required_mapping(value, "opportunity")
    return OpportunityCard(
        symbol=_required_text(item.get("symbol"), "opportunity symbol"),
        company_name=_required_text(item.get("company_name"), "company_name"),
        why_now=_required_text(item.get("why_now"), "why_now"),
        research_status=_status_view(
            item.get("research_status"),
            RESEARCH_STATUS_LABELS,
            "opportunity.research_status",
        ),
        valuation_status=_status_view(
            item.get("valuation_status"),
            VALUATION_STATUS_LABELS,
            "opportunity.valuation_status",
        ),
        dividend_status=_status_view(
            item.get("dividend_status"),
            DIVIDEND_STATUS_LABELS,
            "opportunity.dividend_status",
        ),
        price_status=_status_view(
            item.get("price_status"),
            PRICE_STATUS_LABELS,
            "opportunity.price_status",
        ),
        main_risk=_required_text(item.get("main_risk"), "main_risk"),
        next_trigger=_required_text(item.get("next_trigger"), "next_trigger"),
        evidence_refs=tuple(item.get("evidence_refs") or ()),
        action=str(item.get("action") or ACTION_NO_ORDER),
    )


def _parse_company(value: object) -> CompanyCard:
    item = _required_mapping(value, "company")
    raw_sections = _required_list(item.get("sections"), "company.sections")
    sections: list[CompanySection] = []
    for raw_section in raw_sections:
        section = _required_mapping(raw_section, "company section")
        sections.append(
            CompanySection(
                key=_required_text(section.get("key"), "section key"),
                status=_status_view(
                    section.get("status"),
                    SECTION_STATUS_LABELS,
                    "company section status",
                ),
                summary=_required_text(section.get("summary"), "section summary"),
                evidence_refs=tuple(section.get("evidence_refs") or ()),
            )
        )

    raw_scenarios = _required_list(item.get("scenarios"), "company.scenarios")
    scenarios: list[ScenarioCard] = []
    for raw_scenario in raw_scenarios:
        scenario = _required_mapping(raw_scenario, "scenario")
        scenario_key = _required_text(scenario.get("key"), "scenario key")
        scenarios.append(
            ScenarioCard(
                key=scenario_key,
                assessment=_parse_assessment(
                    scenario.get("assessment"),
                    key=f"scenario.{scenario_key}",
                    labels=VALUATION_STATUS_LABELS,
                ),
            )
        )

    return CompanyCard(
        symbol=_required_text(item.get("symbol"), "company symbol"),
        company_name=_required_text(item.get("company_name"), "company_name"),
        research_status=_status_view(
            item.get("research_status"),
            RESEARCH_STATUS_LABELS,
            "company.research_status",
        ),
        price=_parse_assessment(item.get("price"), key="price", labels=PRICE_STATUS_LABELS),
        valuation=_parse_assessment(
            item.get("valuation"),
            key="valuation",
            labels=VALUATION_STATUS_LABELS,
        ),
        margin_of_safety=_parse_assessment(
            item.get("margin_of_safety"),
            key="margin_of_safety",
            labels=MARGIN_STATUS_LABELS,
        ),
        dividend=_parse_assessment(
            item.get("dividend"),
            key="dividend",
            labels=DIVIDEND_STATUS_LABELS,
        ),
        sections=tuple(sections),
        scenarios=tuple(scenarios),
        latest_change=_required_text(item.get("latest_change"), "latest_change"),
        next_trigger=_required_text(item.get("next_trigger"), "next_trigger"),
        original_thesis=_required_text(item.get("original_thesis"), "original_thesis"),
        thesis_change=_status_view(
            item.get("thesis_change"),
            THESIS_CHANGE_LABELS,
            "company.thesis_change",
        ),
        evidence_refs=tuple(item.get("evidence_refs") or ()),
        action=str(item.get("action") or ACTION_NO_ORDER),
    )


def _parse_portfolio(value: object) -> PortfolioCard:
    item = _required_mapping(value, "portfolio")
    real_data_available = item.get("real_data_available")
    if not isinstance(real_data_available, bool):
        raise ValueError("portfolio.real_data_available must be boolean")

    if real_data_available and not _portfolio_provenance_confirmed(
        item.get("portfolio_provenance")
    ):
        return PortfolioCard(
            real_data_available=False,
            status=_status_view(
                "PENDING_USER_PRIVATE_INPUT",
                PORTFOLIO_STATUS_LABELS,
                "portfolio.status",
            ),
            connection_hint="缺少已确认且已复核的组合收据，暂不显示真实组合数据。",
            summary=(),
            positions=(),
            action=str(item.get("action") or ACTION_NO_ORDER),
        )

    metrics: list[PortfolioMetric] = []
    for raw_metric in _required_list(item.get("summary") or [], "portfolio.summary"):
        metric = _required_mapping(raw_metric, "portfolio metric")
        metric_key = _required_text(metric.get("key"), "metric key")
        try:
            metric_label = PORTFOLIO_METRIC_LABELS[metric_key]
        except KeyError as error:
            raise ValueError(f"Unknown portfolio metric key: {metric_key}") from error
        metrics.append(
            PortfolioMetric(
                key=metric_key,
                label=metric_label,
                value_text=_required_text(metric.get("value_text"), "metric value_text"),
            )
        )

    positions: list[PortfolioPositionCard] = []
    for raw_position in _required_list(
        item.get("positions") or [],
        "portfolio.positions",
    ):
        position = _required_mapping(raw_position, "portfolio position")
        positions.append(
            PortfolioPositionCard(
                symbol=_required_text(position.get("symbol"), "position symbol"),
                company_name=_required_text(
                    position.get("company_name"),
                    "position company_name",
                ),
                current_position_text=_required_text(
                    position.get("current_position_text"),
                    "current_position_text",
                ),
                allowed_capacity_text=_required_text(
                    position.get("allowed_capacity_text"),
                    "allowed_capacity_text",
                ),
                current_risk_text=_required_text(
                    position.get("current_risk_text"),
                    "current_risk_text",
                ),
                continuation_review=_status_view(
                    position.get("continuation_review"),
                    CONTINUATION_REVIEW_LABELS,
                    "portfolio.continuation_review",
                ),
                reason=_required_text(position.get("reason"), "position reason"),
                evidence_refs=tuple(position.get("evidence_refs") or ()),
                action=str(position.get("action") or ACTION_NO_ORDER),
            )
        )

    return PortfolioCard(
        real_data_available=real_data_available,
        status=_status_view(
            item.get("status"),
            PORTFOLIO_STATUS_LABELS,
            "portfolio.status",
        ),
        connection_hint=_required_text(item.get("connection_hint"), "connection_hint"),
        summary=tuple(metrics),
        positions=tuple(positions),
        action=str(item.get("action") or ACTION_NO_ORDER),
    )


def _portfolio_provenance_confirmed(value: object) -> bool:
    if not isinstance(value, Mapping) or value.get("reconciled") is not True:
        return False
    fingerprint = value.get("confirmation_receipt_fingerprint")
    if isinstance(fingerprint, str):
        return bool(fingerprint.strip())
    if isinstance(fingerprint, Mapping):
        receipt_sha256 = fingerprint.get("receipt_sha256")
        return isinstance(receipt_sha256, str) and bool(receipt_sha256.strip())
    return False


def _parse_event(value: object) -> EventCard:
    item = _required_mapping(value, "event")
    return EventCard(
        event_id=_required_text(item.get("event_id"), "event_id"),
        category=_status_view(
            item.get("event_type"),
            EVENT_CATEGORY_LABELS,
            "event.event_type",
        ),
        company_name=_required_text(item.get("company_name"), "event company_name"),
        what_happened=_required_text(item.get("what_happened"), "what_happened"),
        impact_area=_required_text(item.get("impact_area"), "impact_area"),
        current_conclusion=_required_text(
            item.get("current_conclusion"),
            "current_conclusion",
        ),
        research_action=_status_view(
            item.get("research_action"),
            RESEARCH_ACTION_LABELS,
            "event.research_action",
        ),
        next_step=_required_text(item.get("next_step"), "event next_step"),
        evidence_refs=tuple(item.get("evidence_refs") or ()),
        action=str(item.get("action") or ACTION_NO_ORDER),
    )


def product_workbench_from_payload(
    payload: Mapping[str, Any],
) -> ProductWorkbenchReadModel:
    """Build the typed, user-facing model from a no-order candidate payload."""

    data = dict(_required_mapping(payload, "product workbench payload"))
    _reject_execution_keys(data)
    _require_no_order_actions(data)
    if data.get("schema_version") != PRODUCT_WORKBENCH_SCHEMA_VERSION:
        raise ValueError("Unsupported product workbench schema")
    if data.get("action") != ACTION_NO_ORDER:
        raise ValueError("Product workbench action must remain no_order")

    try:
        generated_at = datetime.fromisoformat(
            _required_text(data.get("generated_at"), "generated_at")
        )
        as_of = date.fromisoformat(_required_text(data.get("as_of"), "as_of"))
    except ValueError as error:
        raise ValueError("generated_at and as_of must be ISO values") from error

    overview = _required_mapping(data.get("overview"), "overview")
    system_health = _required_mapping(data.get("system_health"), "system_health")
    stages = _required_mapping(data.get("stages"), "stages")
    stage_summaries = tuple(
        _parse_stage(stage_key, stages.get(stage_key))
        for stage_key in STAGE_LABELS
    )

    audit = _required_mapping(data.get("audit"), "audit")
    evidence = tuple(
        _parse_evidence(item)
        for item in _required_list(audit.get("evidence") or [], "audit.evidence")
    )

    return ProductWorkbenchReadModel(
        schema_version=PRODUCT_WORKBENCH_SCHEMA_VERSION,
        generated_at=generated_at,
        as_of=as_of,
        overview=WorkbenchOverview(
            data_updated_at=generated_at,
            pending_count=overview.get("pending_count"),
        ),
        system_health=SystemHealthCard(
            status=_status_view(
                system_health.get("status"),
                SYSTEM_HEALTH_LABELS,
                "system_health.status",
            ),
            message=_required_text(
                system_health.get("message"),
                "system health message",
            ),
        ),
        stage_summaries=stage_summaries,
        today_items=tuple(
            _parse_today_item(item)
            for item in _required_list(data.get("today_items") or [], "today_items")
        ),
        opportunities=tuple(
            _parse_opportunity(item)
            for item in _required_list(
                data.get("opportunities") or [],
                "opportunities",
            )
        ),
        companies=tuple(
            _parse_company(item)
            for item in _required_list(data.get("companies") or [], "companies")
        ),
        portfolio=_parse_portfolio(data.get("portfolio")),
        events=tuple(
            _parse_event(item)
            for item in _required_list(data.get("events") or [], "events")
        ),
        audit_evidence=evidence,
        action=str(data.get("action")),
    )


__all__ = [
    "ACTION_NO_ORDER",
    "PRODUCT_WORKBENCH_SCHEMA_VERSION",
    "AssessmentView",
    "CompanyCard",
    "CompanySection",
    "EventCard",
    "EvidenceRecord",
    "OpportunityCard",
    "PortfolioCard",
    "PortfolioMetric",
    "PortfolioPositionCard",
    "ProductWorkbenchReadModel",
    "ScenarioCard",
    "StageSummary",
    "StatusView",
    "SystemHealthCard",
    "TodayItem",
    "WorkbenchOverview",
    "product_workbench_from_payload",
]
