"""Profile-aware price attractiveness assessment; never an execution signal."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any

from .price_bridge import PriceBridgeResult, price_bridge_binding_blockers
from .research_gate import ResearchGate
from .research_profile import (
    CYCLICAL_CASH_RETURN,
    MATURE_MANUFACTURING,
    QUALITY_COMPOUNDER,
)
from .valuation_models.base import ValuationResult


STATUS_NOT_ASSESSABLE = "NOT_ASSESSABLE"
STATUS_PRICE_NOT_ATTRACTIVE = "PRICE_NOT_ATTRACTIVE"
STATUS_WAITING_FOR_BETTER_PRICE = "WAITING_FOR_BETTER_PRICE"
STATUS_KEY_OBSERVATION = "KEY_OBSERVATION"
STATUS_RESEARCH_ATTRACTIVE = "RESEARCH_ATTRACTIVE"

PRICE_ATTRACTIVENESS_STATUSES = {
    STATUS_NOT_ASSESSABLE,
    STATUS_PRICE_NOT_ATTRACTIVE,
    STATUS_WAITING_FOR_BETTER_PRICE,
    STATUS_KEY_OBSERVATION,
    STATUS_RESEARCH_ATTRACTIVE,
}

PRICE_ATTRACTIVENESS_DISPLAY = {
    STATUS_NOT_ASSESSABLE: "不可判断价格吸引力",
    STATUS_PRICE_NOT_ATTRACTIVE: "价格缺乏吸引力",
    STATUS_WAITING_FOR_BETTER_PRICE: "等待更有吸引力的价格",
    STATUS_KEY_OBSERVATION: "重点观察",
    STATUS_RESEARCH_ATTRACTIVE: "估值具备研究吸引力",
}

_MODEL_TO_PROFILE = {
    "FCFF": MATURE_MANUFACTURING.profile_id,
    "cyclical_normalized": CYCLICAL_CASH_RETURN.profile_id,
    "residual_income_or_equity_value": QUALITY_COMPOUNDER.profile_id,
}


def infer_profile_id(valuation: ValuationResult) -> str | None:
    """Map the explicit valuation contract to a profile without guessing from the ticker."""
    if valuation.model_type in _MODEL_TO_PROFILE:
        return _MODEL_TO_PROFILE[valuation.model_type]
    if valuation.model_type.startswith("归母权益剩余收益"):
        return QUALITY_COMPOUNDER.profile_id
    return None


@dataclass(frozen=True)
class PriceAttractivenessAssessment:
    symbol: str
    profile_id: str
    status: str
    margin_to_bear: Decimal | None
    margin_to_base: Decimal | None
    downside_reference: Decimal | None
    upside_reference: Decimal | None
    confidence: str
    reasons: list[str]
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Price attractiveness symbol must contain six digits")
        if not self.profile_id.strip():
            raise ValueError("Price attractiveness requires a profile id")
        if self.status not in PRICE_ATTRACTIVENESS_STATUSES:
            raise ValueError("Unknown price attractiveness status")
        if self.confidence not in {"高", "中", "低"}:
            raise ValueError("Price attractiveness confidence must be 高, 中 or 低")
        if self.status != STATUS_NOT_ASSESSABLE and (
                self.margin_to_bear is None or self.margin_to_base is None):
            raise ValueError("Price assessment requires both research margins")
        if self.status == STATUS_NOT_ASSESSABLE and (
                self.margin_to_bear is not None or self.margin_to_base is not None):
            raise ValueError("NOT_ASSESSABLE must not carry bridge margins")
        if any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("Price attractiveness evidence requires named references")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "status": self.status,
            "display_status": PRICE_ATTRACTIVENESS_DISPLAY[self.status],
            "margin_to_bear": (
                str(self.margin_to_bear) if self.margin_to_bear is not None else None
            ),
            "margin_to_base": (
                str(self.margin_to_base) if self.margin_to_base is not None else None
            ),
            "downside_reference": (
                str(self.downside_reference)
                if self.downside_reference is not None else None
            ),
            "upside_reference": (
                str(self.upside_reference)
                if self.upside_reference is not None else None
            ),
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


def _quality_compounder_assessment(
        valuation: ValuationResult,
        price_bridge: PriceBridgeResult,
) -> tuple[str, list[str], list[str]]:
    """Conservative quality-compounder rule; it is not a universal safety-margin gate."""
    if valuation.confidence == "低":
        return (
            STATUS_WAITING_FOR_BETTER_PRICE,
            ["估值置信度为低，只能等待更好的证据与价格条件"],
            ["valuation_confidence_low"],
        )
    if price_bridge.margin_to_bear is not None and price_bridge.margin_to_bear < 0:
        return (
            STATUS_PRICE_NOT_ATTRACTIVE,
            ["当前价格高于熊情景，无法满足质量复利路径的保守观察条件"],
            ["price_above_bear_reference"],
        )
    if price_bridge.margin_to_base is not None and price_bridge.margin_to_base <= 0:
        return (
            STATUS_WAITING_FOR_BETTER_PRICE,
            ["当前价格尚未低于基准情景，继续观察"],
            ["price_not_below_base_reference"],
        )
    return (
        STATUS_RESEARCH_ATTRACTIVE,
        ["价格位于熊与基准情景之间或更低，研究路径登记的价格条件成立"],
        [],
    )


def assess_price_attractiveness(
        gate: ResearchGate,
        valuation: ValuationResult,
        price_bridge: PriceBridgeResult,
        *,
        profile_id: str | None = None,
        human_approval_price_assessment_eligible: bool | None = None,
) -> PriceAttractivenessAssessment:
    """Require a legal bridge before comparing research value with market price."""
    if not isinstance(gate, ResearchGate):
        raise ValueError("Price assessment requires a ResearchGate")
    if not isinstance(valuation, ValuationResult):
        raise ValueError("Price assessment requires a ValuationResult")
    if not isinstance(price_bridge, PriceBridgeResult):
        raise ValueError("Price assessment requires a PriceBridgeResult")
    if not (gate.symbol == valuation.symbol == price_bridge.symbol):
        raise ValueError("Price assessment inputs must share one symbol")

    binding_blockers = price_bridge_binding_blockers(valuation, price_bridge)
    if binding_blockers:
        return PriceAttractivenessAssessment(
            symbol=valuation.symbol,
            profile_id=profile_id or infer_profile_id(valuation) or "unspecified",
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence=valuation.confidence,
            reasons=["PriceBridge 与估值身份不一致，不能进行价格判断"],
            blockers=[f"price_bridge_binding:{blocker}" for blocker in binding_blockers],
            evidence_refs=list(price_bridge.evidence_refs),
        )

    resolved_profile = profile_id or infer_profile_id(valuation) or "unspecified"
    base_evidence_refs = list(price_bridge.evidence_refs)

    if human_approval_price_assessment_eligible is False:
        return PriceAttractivenessAssessment(
            symbol=valuation.symbol,
            profile_id=resolved_profile,
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence=valuation.confidence,
            reasons=["人工 G3 批准未授权当前模型进入价格吸引力判断"],
            blockers=["human_approval_price_assessment_not_eligible"],
            evidence_refs=base_evidence_refs,
        )

    if price_bridge.bridge_status != "READY":
        return PriceAttractivenessAssessment(
            symbol=valuation.symbol,
            profile_id=resolved_profile,
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence=valuation.confidence,
            reasons=["没有合法 READY PriceBridge，不能判断价格吸引力"],
            blockers=[f"price_bridge_{price_bridge.bridge_status.lower()}"],
            evidence_refs=base_evidence_refs,
        )

    if not gate.ready_for_price_assessment:
        return PriceAttractivenessAssessment(
            symbol=valuation.symbol,
            profile_id=resolved_profile,
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence=valuation.confidence,
            reasons=["ResearchGate 尚未完成，价格桥接不能替代研究门禁"],
            blockers=["research_gate_not_ready_for_price_assessment"],
            evidence_refs=base_evidence_refs,
        )

    if (
            valuation.status == "not_ready"
            or any(value is None for value in (
                valuation.bear_value, valuation.base_value, valuation.bull_value,
            ))
    ):
        return PriceAttractivenessAssessment(
            symbol=valuation.symbol,
            profile_id=resolved_profile,
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence=valuation.confidence,
            reasons=["估值情景尚未形成，不能进行价格吸引力判断"],
            blockers=["valuation_scenarios_incomplete"],
            evidence_refs=base_evidence_refs,
        )

    if resolved_profile == QUALITY_COMPOUNDER.profile_id:
        status, reasons, blockers = _quality_compounder_assessment(valuation, price_bridge)
    elif resolved_profile in {
        MATURE_MANUFACTURING.profile_id,
        CYCLICAL_CASH_RETURN.profile_id,
    }:
        status, reasons, blockers = (
            STATUS_KEY_OBSERVATION,
            ["该路径的正式价格规则尚未登记，第一版只做重点观察"],
            [f"profile_{resolved_profile}_price_rule_not_registered"],
        )
    else:
        status, reasons, blockers = (
            STATUS_KEY_OBSERVATION,
            ["未识别 ResearchProfile，第一版不推断价格吸引力"],
            ["profile_not_identified"],
        )

    return PriceAttractivenessAssessment(
        symbol=valuation.symbol,
        profile_id=resolved_profile,
        status=status,
        margin_to_bear=price_bridge.margin_to_bear,
        margin_to_base=price_bridge.margin_to_base,
        downside_reference=valuation.bear_value,
        upside_reference=valuation.base_value,
        confidence=valuation.confidence,
        reasons=reasons,
        blockers=blockers,
        evidence_refs=base_evidence_refs,
    )
