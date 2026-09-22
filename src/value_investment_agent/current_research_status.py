"""Aggregate research, valuation and price-bridge state for presentation only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from .price_bridge import PriceBridgeResult
from .research_gate import ResearchGate
from .valuation_models.base import ValuationResult


ENGINEERING_NOT_STARTED = "NOT_STARTED"
ENGINEERING_IN_PROGRESS = "IN_PROGRESS"
ENGINEERING_READY = "READY"
ENGINEERING_FAILED = "FAILED"
ENGINEERING_STATUSES = {
    ENGINEERING_NOT_STARTED,
    ENGINEERING_IN_PROGRESS,
    ENGINEERING_READY,
    ENGINEERING_FAILED,
}

CURRENT_DATA_READY = "READY"
CURRENT_DATA_PENDING_EXTERNAL_DATA = "PENDING_EXTERNAL_DATA"
CURRENT_DATA_STALE = "STALE"
CURRENT_DATA_CONFLICT = "CONFLICT"
CURRENT_DATA_INVALID = "INVALID"
CURRENT_DATA_UNAVAILABLE = "UNAVAILABLE"
CURRENT_DATA_STATUSES = {
    CURRENT_DATA_READY,
    CURRENT_DATA_PENDING_EXTERNAL_DATA,
    CURRENT_DATA_STALE,
    CURRENT_DATA_CONFLICT,
    CURRENT_DATA_INVALID,
    CURRENT_DATA_UNAVAILABLE,
}

CONCLUSION_DATA_INSUFFICIENT = "数据不足"
CONCLUSION_RESEARCH_INCOMPLETE = "研究未完成"
CONCLUSION_VALUATION_NOT_READY = "估值未就绪"
CONCLUSION_RESEARCH_NOT_PASSED = "研究不通过"
CONCLUSION_PRICE_NOT_ATTRACTIVE = "价格缺乏吸引力"
CONCLUSION_WAITING_FOR_BETTER_PRICE = "等待更有吸引力的价格"
CONCLUSION_KEY_OBSERVATION = "重点观察"
CONCLUSION_RESEARCH_ATTRACTIVE = "估值具备研究吸引力"
CONCLUSION_HOLD_TRACKING = "持有研究跟踪"
CONCLUSION_PAUSED = "暂停新增研究"
CONCLUSION_THESIS_DAMAGED = "论点受损，需复评"
CONCLUSION_REMOVED = "退出研究池"
ALLOWED_RESEARCH_CONCLUSIONS = {
    CONCLUSION_DATA_INSUFFICIENT,
    CONCLUSION_RESEARCH_INCOMPLETE,
    CONCLUSION_VALUATION_NOT_READY,
    CONCLUSION_RESEARCH_NOT_PASSED,
    CONCLUSION_PRICE_NOT_ATTRACTIVE,
    CONCLUSION_WAITING_FOR_BETTER_PRICE,
    CONCLUSION_KEY_OBSERVATION,
    CONCLUSION_RESEARCH_ATTRACTIVE,
    CONCLUSION_HOLD_TRACKING,
    CONCLUSION_PAUSED,
    CONCLUSION_THESIS_DAMAGED,
    CONCLUSION_REMOVED,
}

_BRIDGE_TO_CURRENT_DATA_STATUS = {
    "READY": CURRENT_DATA_READY,
    "PENDING_EXTERNAL_DATA": CURRENT_DATA_PENDING_EXTERNAL_DATA,
    "STALE_MODEL": CURRENT_DATA_STALE,
    "INVALID": CURRENT_DATA_INVALID,
}

_DEFAULT_WAITING_FOR = {
    CURRENT_DATA_READY: (),
    CURRENT_DATA_PENDING_EXTERNAL_DATA: ("已验证收盘行情",),
    CURRENT_DATA_STALE: ("重大事项后的模型重估",),
    CURRENT_DATA_CONFLICT: ("来源冲突复核",),
    CURRENT_DATA_INVALID: ("模型有效性复核",),
    CURRENT_DATA_UNAVAILABLE: ("数据源恢复",),
}


def _validate_refs(refs: list[dict[str, Any]]) -> None:
    if any(not ref.get("id") for ref in refs):
        raise ValueError("Current-research evidence requires named references")


def _merge_refs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for refs in groups:
        for ref in refs:
            ref_id = ref.get("id")
            if ref_id in merged and merged[ref_id] != ref:
                raise ValueError(f"Evidence references with the same id must match: {ref_id}")
            merged[ref_id] = dict(ref)
    return list(merged.values())


@dataclass(frozen=True)
class CurrentDataStatus:
    """Production data readiness, kept separate from engineering readiness."""

    status: str
    waiting_for: list[str]
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if self.status not in CURRENT_DATA_STATUSES:
            raise ValueError("Unknown current data status")
        if self.status != CURRENT_DATA_READY and not self.waiting_for:
            raise ValueError("A non-ready current data status must name what it is waiting for")
        _validate_refs(self.evidence_refs)

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "waiting_for": list(self.waiting_for),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class CurrentResearchStatus:
    """Read-only company status; it never contains trade, order or position state."""

    symbol: str
    research_conclusion: str
    valuation_status: str
    price_bridge_status: str
    engineering_status: str
    current_data_status: CurrentDataStatus
    display_text: str
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Current-research symbol must contain six digits")
        if self.research_conclusion not in ALLOWED_RESEARCH_CONCLUSIONS:
            raise ValueError("Unknown current research conclusion")
        if self.engineering_status not in ENGINEERING_STATUSES:
            raise ValueError("Unknown engineering status")
        if not isinstance(self.current_data_status, CurrentDataStatus):
            raise ValueError("Current research status requires a CurrentDataStatus")
        _validate_refs(self.evidence_refs)

    @property
    def research_attractive(self) -> bool:
        return self.research_conclusion == CONCLUSION_RESEARCH_ATTRACTIVE

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "research_conclusion": self.research_conclusion,
            "valuation_status": self.valuation_status,
            "price_bridge_status": self.price_bridge_status,
            "engineering_status": self.engineering_status,
            "current_data_status": self.current_data_status.as_policy(),
            "display_text": self.display_text,
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def _infer_current_data_status(price_bridge: PriceBridgeResult) -> CurrentDataStatus:
    status = _BRIDGE_TO_CURRENT_DATA_STATUS[price_bridge.bridge_status]
    return CurrentDataStatus(
        status=status,
        waiting_for=list(_DEFAULT_WAITING_FOR[status]),
        blockers=list(price_bridge.blockers),
        evidence_refs=list(price_bridge.evidence_refs),
    )


def _scenarios_complete(valuation: ValuationResult) -> bool:
    return all(
        value is not None
        for value in (valuation.bear_value, valuation.base_value, valuation.bull_value)
    )


def _resolve_conclusion(
    gate: ResearchGate,
    valuation: ValuationResult,
    price_bridge: PriceBridgeResult,
    blockers: list[str],
) -> str:
    if gate.conclusion not in {
        CONCLUSION_WAITING_FOR_BETTER_PRICE,
        CONCLUSION_RESEARCH_ATTRACTIVE,
    }:
        return gate.conclusion

    if valuation.status == "not_ready" or not _scenarios_complete(valuation):
        blockers.append("valuation_not_ready")
        return CONCLUSION_VALUATION_NOT_READY

    if valuation.status == "conditional_research_only":
        blockers.append("conditional_valuation_is_not_formal_research_attractiveness")
        return (
            CONCLUSION_WAITING_FOR_BETTER_PRICE
            if valuation.confidence == "低"
            else CONCLUSION_KEY_OBSERVATION
        )

    if valuation.confidence == "低":
        blockers.append("valuation_confidence_low_blocks_research_attractiveness")
        return CONCLUSION_WAITING_FOR_BETTER_PRICE

    if price_bridge.bridge_status in {"STALE_MODEL", "INVALID"}:
        blockers.append(f"model_bridge_{price_bridge.bridge_status.lower()}")
        return CONCLUSION_KEY_OBSERVATION

    # Pending external data retains the completed research and valuation result.
    return gate.conclusion


def _display_text(
    conclusion: str,
    valuation: ValuationResult,
    engineering_status: str,
    current_data_status: CurrentDataStatus,
) -> str:
    if current_data_status.status == CURRENT_DATA_PENDING_EXTERNAL_DATA:
        retained = (
            "估值结果已保留；等待已验证收盘行情后更新价格桥接和安全边际。"
            if _scenarios_complete(valuation)
            else "已有估值对象已保留；价格相关结论仍待形成。"
        )
    elif current_data_status.status == CURRENT_DATA_STALE:
        retained = "价格桥接已停用；须在重大事项后重估，再恢复价格比较。"
    elif current_data_status.status == CURRENT_DATA_INVALID:
        retained = "价格桥接不可用；须先完成模型有效性复核。"
    elif current_data_status.status == CURRENT_DATA_READY:
        retained = "价格桥接已形成，可用于研究层价格观察。"
    else:
        retained = "当前数据暂不支持最新研究判断。"

    return (
        f"研究结论：{conclusion}；估值状态：{valuation.status}；"
        f"工程链路：{engineering_status}；当前数据：{current_data_status.status}。"
        f"{retained}该状态只属于研究层，不生成交易、仓位或订单。"
    )


def evaluate_current_research_status(
    gate: ResearchGate,
    valuation: ValuationResult,
    price_bridge: PriceBridgeResult,
    *,
    engineering_status: str = ENGINEERING_READY,
    current_data_status: CurrentDataStatus | None = None,
) -> CurrentResearchStatus:
    """Combine retained domain results without creating an execution instruction."""
    if not isinstance(gate, ResearchGate):
        raise ValueError("Current research status requires a ResearchGate")
    if not isinstance(valuation, ValuationResult):
        raise ValueError("Current research status requires a ValuationResult")
    if not isinstance(price_bridge, PriceBridgeResult):
        raise ValueError("Current research status requires a PriceBridgeResult")
    if not (gate.symbol == valuation.symbol == price_bridge.symbol):
        raise ValueError("Research, valuation and price-bridge symbols must match")
    if engineering_status not in ENGINEERING_STATUSES:
        raise ValueError("Unknown engineering status")

    inferred_data_status = _infer_current_data_status(price_bridge)
    if current_data_status is None:
        current_data_status = inferred_data_status
    else:
        if not isinstance(current_data_status, CurrentDataStatus):
            raise ValueError("current_data_status must be a CurrentDataStatus")
        if current_data_status.status != inferred_data_status.status:
            raise ValueError(
                "Explicit current data status contradicts the price-bridge status"
            )
        current_data_status = CurrentDataStatus(
            status=current_data_status.status,
            waiting_for=list(current_data_status.waiting_for),
            blockers=list(dict.fromkeys([
                *inferred_data_status.blockers,
                *current_data_status.blockers,
            ])),
            evidence_refs=_merge_refs(
                inferred_data_status.evidence_refs,
                current_data_status.evidence_refs,
            ),
        )

    blockers = [*gate.blockers, *valuation.blockers]
    if engineering_status != ENGINEERING_READY:
        blockers.append(f"engineering_status_{engineering_status.lower()}")
    conclusion = _resolve_conclusion(gate, valuation, price_bridge, blockers)
    blockers = list(dict.fromkeys(blockers))
    evidence_refs = _merge_refs(
        valuation.evidence_refs,
        current_data_status.evidence_refs,
    )

    return CurrentResearchStatus(
        symbol=valuation.symbol,
        research_conclusion=conclusion,
        valuation_status=valuation.status,
        price_bridge_status=price_bridge.bridge_status,
        engineering_status=engineering_status,
        current_data_status=current_data_status,
        display_text=_display_text(
            conclusion,
            valuation,
            engineering_status,
            current_data_status,
        ),
        blockers=blockers,
        evidence_refs=evidence_refs,
    )


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date string") from exc


def _required_date(value: object, field: str) -> date:
    parsed = _optional_date(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal string") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal string")
    return number


def current_research_status_from_payloads(
    gate_payload: dict[str, Any],
    valuation_payload: dict[str, Any],
    price_bridge_payload: dict[str, Any],
    *,
    engineering_status: str = ENGINEERING_READY,
    current_data_status: CurrentDataStatus | None = None,
) -> CurrentResearchStatus:
    """Restore serialized domain results before aggregating them."""
    gate = ResearchGate(
        symbol=str(valuation_payload["symbol"]),
        results=dict(gate_payload["results"]),
        blockers=list(gate_payload["blockers"]),
        conclusion=str(gate_payload["conclusion"]),
    )
    valuation = ValuationResult(
        symbol=str(valuation_payload["symbol"]),
        model_type=str(valuation_payload["model_type"]),
        valuation_date=_required_date(valuation_payload["valuation_date"], "valuation_date"),
        bear_value=_optional_decimal(valuation_payload.get("bear_value"), "bear_value"),
        base_value=_optional_decimal(valuation_payload.get("base_value"), "base_value"),
        bull_value=_optional_decimal(valuation_payload.get("bull_value"), "bull_value"),
        confidence=str(valuation_payload["confidence"]),
        assumptions=dict(valuation_payload["assumptions"]),
        sensitivities=list(valuation_payload["sensitivities"]),
        evidence_refs=list(valuation_payload["evidence_refs"]),
        blockers=list(valuation_payload["blockers"]),
        status=str(valuation_payload["status"]),
        model_version=str(valuation_payload["model_version"]),
    )
    price_bridge = PriceBridgeResult(
        symbol=str(valuation_payload["symbol"]),
        valuation_date=_required_date(
            price_bridge_payload["valuation_date"], "price_bridge_valuation_date"
        ),
        quote_date=_optional_date(
            price_bridge_payload.get("quote_date"), "price_bridge_quote_date"
        ),
        current_price=_optional_decimal(
            price_bridge_payload.get("current_price"), "current_price"
        ),
        margin_to_bear=_optional_decimal(
            price_bridge_payload.get("margin_to_bear"), "margin_to_bear"
        ),
        margin_to_base=_optional_decimal(
            price_bridge_payload.get("margin_to_base"), "margin_to_base"
        ),
        model_validity_status=str(price_bridge_payload["model_validity_status"]),
        quote_status=str(price_bridge_payload["quote_status"]),
        bridge_status=str(price_bridge_payload["bridge_status"]),
        evidence_refs=list(price_bridge_payload["evidence_refs"]),
        blockers=list(price_bridge_payload["blockers"]),
    )
    return evaluate_current_research_status(
        gate,
        valuation,
        price_bridge,
        engineering_status=engineering_status,
        current_data_status=current_data_status,
    )
