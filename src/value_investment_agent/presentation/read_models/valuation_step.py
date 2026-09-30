"""Project bound intrinsic-value arithmetic without admitting a trade gate."""
from __future__ import annotations

from dataclasses import replace

from value_investment_agent.domain.research.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult
from value_investment_agent.price_bridge import PriceBridgeResult
from .product_workbench import AssessmentView, CompanyCard, DecisionStepView, ProductWorkbenchReadModel, ScenarioCard, StatusView


def company_with_pending_price_bridge(
    card: CompanyCard, result: ValuationResult, bridge: PriceBridgeResult,
) -> CompanyCard:
    """Display a pending bridge; do not infer or change another admission gate."""
    if not isinstance(bridge, PriceBridgeResult):
        raise TypeError("price bridge must be typed")
    if (card.symbol != result.symbol or bridge.symbol != result.symbol
            or bridge.model_version != result.model_version
            or bridge.model_as_of != result.valuation_date
            or bridge.valuation_date != result.valuation_date
            or bridge.valuation_bear_value != result.bear_value
            or bridge.valuation_base_value != result.base_value):
        raise ValueError("pending price bridge valuation binding mismatch")
    if (bridge.bridge_status != "PENDING_EXTERNAL_DATA"
            or bridge.current_price is not None or bridge.quote_date is not None
            or bridge.margin_to_base is not None or bridge.margin_to_bear is not None):
        raise ValueError("pending projection requires an absent quote and margins")
    if card.price.available or card.margin_of_safety.available:
        raise ValueError("pending projection cannot replace an available price assessment")
    if any(step.status != "BLOCKED" for step in card.decision_process
           if step.key in {"price_bridge", "decision_gate"}):
        raise ValueError("pending projection requires blocked price and decision gates")
    status = StatusView("PENDING_EXTERNAL_DATA", "等待已验证行情")
    reason = (f"研究估值基准日 {bridge.valuation_date.isoformat()}；"
              f"模型有效性 {bridge.model_validity_status}；当前价格、价格日期和安全边际均未准入。")
    reopen = "核验当前重大事件及模型有效性，再接入已验证、口径一致的行情；不是买卖建议。"
    price = AssessmentView("price", status, False, None, reason, reopen, ())
    margin = AssessmentView("margin_of_safety", status, False, None, reason, reopen, ())
    return replace(
        card, price=price, margin_of_safety=margin,
        decision_process=tuple(
            replace(step, reason=reason, next_action=reopen) if step.key == "price_bridge" else step
            for step in card.decision_process
        ),
    )


def workbench_with_bound_valuation(
    model: ProductWorkbenchReadModel, result: ValuationResult, *, expected_sha256: str, assessment_id: str,
) -> ProductWorkbenchReadModel:
    """Consume an already admitted result using the enclosing audit's bindings.

    File verification belongs to Application/Data, not this presentation adapter.
    """
    cards = [card for card in model.companies if card.symbol == result.symbol]
    if len(cards) != 1:
        raise ValueError("valuation requires one existing company card")
    audit = {record.evidence_id: record for record in model.audit_evidence}
    for ref in result.evidence_refs:
        record = audit.get(ref["id"])
        if record is None:
            raise ValueError("valuation reference missing audit evidence")
        if not ref.get("sha256") or record.sha256 != ref["sha256"]:
            raise ValueError("valuation evidence hash mismatch")
        if ref.get("url") and record.source_url != ref["url"]:
            raise ValueError("valuation evidence source mismatch")
        if record.available_at is None or record.available_at > model.as_of:
            raise ValueError("valuation evidence availability not established")
    if result.valuation_date > model.as_of:
        raise ValueError("valuation basis is after workbench cutoff")
    projected = company_with_bound_valuation(cards[0], result, expected_sha256=expected_sha256, assessment_id=assessment_id)
    return replace(
        model,
        companies=tuple(projected if card.symbol == result.symbol else card for card in model.companies),
        opportunities=tuple(replace(card, valuation_status=projected.valuation.status)
                            if card.symbol == result.symbol else card for card in model.opportunities),
    )


def company_with_bound_valuation(
    card: CompanyCard, result: ValuationResult, *, expected_sha256: str, assessment_id: str,
) -> CompanyCard:
    """Replace valuation presentation only; never infer admission of another gate."""
    if card.symbol != result.symbol:
        raise ValueError("company and valuation symbol mismatch")
    step = bound_valuation_step(result, expected_sha256=expected_sha256, assessment_id=assessment_id)
    available = step.status == "CONDITIONAL"
    status = StatusView("UNDER_REVIEW" if available else "NOT_READY", "条件性研究估值" if available else "估值尚未就绪")

    def assessment(key: str, value: str) -> AssessmentView:
        return AssessmentView(
            key=key, status=status, available=available,
            value_text=value if available else None,
            unavailable_reason=None if available else step.reason,
            needed_evidence=None if available else step.next_action,
            evidence_refs=step.evidence_refs,
        )

    scenarios = tuple(
        ScenarioCard(key=key, assessment=assessment(key, f"CNY {value:.2f} / 股" if value is not None else ""))
        for key, value in zip(("bear", "base", "bull"), (result.bear_value, result.base_value, result.bull_value))
    )
    return replace(
        card, valuation=assessment("valuation", step.reason), scenarios=scenarios,
        sections=tuple(replace(section, status=StatusView("PARTIAL", "仍在验证"), summary=step.reason,
                               evidence_refs=step.evidence_refs) if section.key == "valuation" else section
                       for section in card.sections),
        decision_process=tuple(step if existing.key == "valuation" else existing for existing in card.decision_process),
        evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, *step.evidence_refs))),
    )


def bound_valuation_step(
    result: ValuationResult, *, expected_sha256: str, assessment_id: str,
) -> DecisionStepView:
    if not isinstance(result, ValuationResult):
        raise TypeError("valuation result must be typed")
    if valuation_result_sha256(result) != expected_sha256:
        raise ValueError("valuation result binding mismatch")
    refs = tuple(dict.fromkeys(ref["id"] for ref in result.evidence_refs))
    values = (result.bear_value, result.base_value, result.bull_value)
    if result.status == "not_ready" or any(value is None for value in values):
        return DecisionStepView(
            key="valuation", status="BLOCKED",
            reason="估值情景未齐全：" + "；".join(result.blockers or ["模型结果尚未就绪"]),
            next_action="补齐适用模型所需事实及假设后，通过共享研究流程重新评估。",
            evidence_refs=refs, assessment_id=assessment_id,
        )
    return DecisionStepView(
        key="valuation", status="CONDITIONAL",
        reason=(
            f"研究估值基准日 {result.valuation_date.isoformat()}；"
            f"Bear/Base/Bull：{result.bear_value:.2f}/{result.base_value:.2f}/{result.bull_value:.2f}；"
            f"置信度：{result.confidence}。仅证明绑定的估值情景已生成，不代表当前买卖门通过。"
            + (" 限制：" + "；".join(result.blockers) if result.blockers else "")
        ),
        next_action="独立核验模型有效性、当前 PriceBridge、研究及组合门；未经核验不生成买卖建议。",
        evidence_refs=refs, assessment_id=assessment_id,
    )
