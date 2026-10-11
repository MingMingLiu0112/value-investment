"""Explain an already replay-verified decision; never select actions or prices."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..decision.restore_decision_recommendation import RestoredDecisionRecommendation
from ...domain.decision.decision_recommendation import DECISION_RECOMMENDATION_V3_SCHEMA
from ...research_artifact_codecs import artifact_payload


_ACTION_TEXT = {
    "BUY_CANDIDATE": "证券级买入候选，仍须本人复核及核对组合容量。",
    "ADD_CANDIDATE": "原论点与增量证据支持加仓候选，不因价格下跌自动加仓。",
    "HOLD": "原论点仍成立，继续跟踪；不表示可以买入或加仓。",
    "TRIM_CANDIDATE": "原论点已削弱，进入人工减仓复核；不是卖出指令。",
    "SELL_CANDIDATE": "原论点已失效，进入人工退出复核；不要求以当前价格证明论点失效。",
    "NO_ACTION": "当前没有合法动作候选，按实际阻塞和下一事件继续复核。",
}


def project_value_decision_explanation(
    verified_decision: RestoredDecisionRecommendation, *, evidence_scope: str,
) -> dict[str, Any]:
    """Consume the existing restore API result, not an arbitrary decision payload.

    Callers must restore against their pinned repository/bundle first. This is a
    presentation use case, not an authentication or investment admission API.
    """
    if evidence_scope not in {"RETAINED_RESEARCH", "SYNTHETIC_TEST"}:
        raise ValueError("explicit retained-research or synthetic evidence scope required")
    if not isinstance(verified_decision, RestoredDecisionRecommendation):
        raise ValueError("value explanation requires a repository-restored decision")
    verification = verified_decision.verification
    if (verification.get("repository_replay") is not True
            or verification.get("semantic_revalidation") is not True):
        raise ValueError("value explanation requires successful existing replay")
    recommendation = verified_decision.recommendation
    if (recommendation.schema_version != DECISION_RECOMMENDATION_V3_SCHEMA
            or recommendation.action != "no_order"
            or recommendation.position_guidance is not None
            or recommendation.portfolio_input_status != "BLOCKED_PRIVATE_INPUT"):
        raise ValueError("value explanation requires the existing public v3 no-order contract")
    payload = recommendation.as_policy()
    kind = payload["recommendation_type"]
    objects = verified_decision.dependency_objects
    case = objects["research_case"]
    if case.symbol != recommendation.symbol:
        raise ValueError("value explanation research issuer mismatch")

    def retained(role: str) -> dict[str, Any] | None:
        value = objects.get(role)
        return None if value is None else artifact_payload(value)[1]

    predecision = retained("pre_decision")
    # Copy the existing eligibility result; do not infer admission from a quote
    # observation or a trim/exit candidate that does not need a price.
    price_eligible = (predecision is not None
                      and predecision.get("positive_price_review_eligible") is True)
    return deepcopy({
        "schema_version": "public-value-decision-explanation-v1",
        "symbol": payload["symbol"], "company_name": case.name,
        "research_version": case.research_version,
        "decision_as_of": payload["decision_as_of"],
        "evidence_scope": evidence_scope,
        "candidate_action": kind, "candidate_explanation": _ACTION_TEXT[kind],
        "requires_human_review": payload["requires_human_review"],
        "thesis": payload["thesis"], "return_driver": case.return_driver,
        "mispricing_hypothesis": case.mispricing_hypothesis,
        "support": case.positives, "counter_evidence": payload["counter_evidence"],
        "thesis_breakers": payload["thesis_breakers"],
        "next_events": payload["next_events"],
        "recommendation_reasons": payload["recommendation_reasons"],
        "blockers": payload["blockers"], "confidence": payload["confidence"],
        "research_status": case.research_status,
        "financial_period": None if case.financial_period is None else case.financial_period.isoformat(),
        "valuation": retained("valuation"),
        "valuation_range": payload["valuation_range"],
        "pre_decision": predecision, "model_validity": payload["model_validity"],
        "human_approval": retained("human_approval"),
        "event_materiality": retained("event_materiality"),
        "price_context": {
            "price_bridge": retained("price_bridge"),
            "price_attractiveness": retained("price_attractiveness"),
            "positive_price_review_eligible": price_eligible,
            "formal_comparison": ({
                "current_price": payload["current_price"],
                "margin_of_safety": payload["margin_of_safety"],
                "entry_zone": payload["entry_zone"],
                "reduce_zone": payload["reduce_zone"],
            } if price_eligible else None),
            "boundary": "报价观察与正式价格准入分开；论点减仓/退出复核不自动证明价格有吸引力。",
        },
        "entry_id": payload["entry_id"],
        "thesis_consistency_status": payload["thesis_consistency_status"],
        "entry_thesis": retained("entry_thesis"),
        "investment_consistency_review": retained("investment_consistency_review"),
        "exit_conditions": payload["exit_conditions"],
        "rule_evidence": payload["rule_evidence"],
        "evidence_refs": payload["evidence_refs"],
        "decision_dependency_refs": payload["decision_dependency_refs"],
        "decision_input_sha256": payload["decision_input_sha256"],
        "recommendation_payload_sha256": payload["recommendation_payload_sha256"],
        "verification": dict(verification),
        "approval_changed": False, "valuation_recomputed": False,
        "decision_changed": False, "canonical_written": False,
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
        "position_guidance": None, "action": "no_order",
    })
