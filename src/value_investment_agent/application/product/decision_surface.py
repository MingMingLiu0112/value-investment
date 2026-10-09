"""Project one replay-verified security decision into the existing M7 cards."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import hashlib
import json
import re

from ..decision.artifact_bundle import ReadOnlyArtifactBundleRepository
from ..decision.restore_decision_recommendation import (
    RestoredDecisionRecommendation, verify_decision_recommendation_payload,
)
from ...domain.research.human_research_approval import resolve_human_research_approval
from ...domain.research.research_gate import (
    GATE_BUSINESS, GATE_EVIDENCE, GATE_FINANCIAL, GATE_VALUATION,
)
from ...model_validity import model_validity_identity_blockers
from ...price_bridge import price_bridge_binding_blockers
from .common import require_inside, sha256_file


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
_ZONE_LABELS = {
    "NOT_ASSESSABLE": "暂不可评估",
    "PRICE_NOT_ATTRACTIVE": "价格缺乏吸引力",
    "WAITING_FOR_BETTER_PRICE": "等待更好的价格",
    "KEY_OBSERVATION": "重点观察区，价格规则尚未登记",
    "RESEARCH_ATTRACTIVE": "人工买入复核的价格条件满足",
}
_DECISION_LABELS = {
    "NO_ACTION": "暂不进入人工买入复核",
    "BUY_CANDIDATE": "证券级人工买入复核条件待确认",
    "ADD_CANDIDATE": "证券级人工加仓复核条件待确认",
    "HOLD": "研究结论维持，继续跟踪",
    "TRIM_CANDIDATE": "证券级人工减仓复核触发",
    "SELL_CANDIDATE": "证券级人工退出复核触发",
}
# Thesis-based risk reduction never needs a current quote to be projectable.
_NO_QUOTE_DECISION_TYPES = frozenset({"HOLD", "TRIM_CANDIDATE", "SELL_CANDIDATE"})
_DECISION_BOUNDARY_TEXT = {
    "BUY_CANDIDATE": "证券级研究和价格前置已满足；仍需人工核对证据及个人组合容量。",
    "ADD_CANDIDATE": "原始买入逻辑与增量证据已具备；仍需人工核对证据及个人组合容量。",
    "HOLD": "原始买入逻辑仍在且模型有效；不构成加仓、减仓或仓位指令。",
    "TRIM_CANDIDATE": "原始买入逻辑已削弱并附证据；减仓属人工复核触发，不是自动指令。",
    "SELL_CANDIDATE": "原始买入逻辑已破坏并附证据；退出属人工复核触发，不是自动指令。",
}
_DECISION_STEPS = (
    "financial_facts", "business_quality", "model_applicability", "valuation",
    "price_bridge", "research_gate", "portfolio_gate", "decision_gate",
)


def _assessment(status: str, value: str | None, evidence_id: str) -> dict[str, Any]:
    if value is None:
        return {
            "status": status, "available": False, "value_text": None,
            "unavailable_reason": "当前没有可验证的同口径结果。",
            "needed_evidence": "补齐已绑定的研究、模型或价格证据。",
            "evidence_refs": [evidence_id],
        }
    return {
        "status": status, "available": True, "value_text": value,
        "unavailable_reason": None, "needed_evidence": None,
        "evidence_refs": [evidence_id],
    }


def current_recommendation_type(recommendation: Any) -> str:
    """Prefer the current contract property while retaining legacy objects."""
    kind = getattr(recommendation, "recommendation_type", None)
    return kind if kind is not None else recommendation.recommendation_action


def verify_current_decision_workbench(
    workbench: dict[str, Any],
) -> RestoredDecisionRecommendation:
    """Reuse repository replay before presenting a current security assessment."""
    if (workbench.get("schema_version") != "product-current-workbench-request-v1"
            or workbench.get("action") != "no_order"
            or workbench.get("research_status") == "BLOCKED_BY_RESEARCH_SCHEDULER"
            or workbench.get("position_guidance") is not None
            or workbench.get("portfolio_input_status") != "BLOCKED_PRIVATE_INPUT"):
        raise ValueError("Decision workbench is not a current no-order security assessment")
    workbench_at = datetime.fromisoformat(workbench["generated_at"])
    if workbench_at.tzinfo is None:
        raise ValueError("Decision workbench requires an aware timestamp")
    recommendation_payload = workbench.get("decision_recommendation")
    bundle = workbench.get("artifact_bundle")
    if not isinstance(recommendation_payload, dict) or not isinstance(bundle, dict):
        raise ValueError("Decision workbench requires replayable decision artifacts")
    repository = ReadOnlyArtifactBundleRepository(bundle)
    for row in bundle["artifacts"]:
        available_at = datetime.fromisoformat(row["identity"]["available_at"])
        if available_at.tzinfo is None or available_at > workbench_at:
            raise ValueError("Decision workbench contains future-available artifacts")
    restored = verify_decision_recommendation_payload(
        repository, payload=recommendation_payload,
        recommendation_artifact=repository.recommendation_artifact(recommendation_payload),
    )
    recommendation = restored.recommendation
    kind = current_recommendation_type(recommendation)
    zone = restored.dependency_objects.get("price_attractiveness")
    workbench_date = workbench_at.astimezone(_MARKET_TIMEZONE).date()
    if (workbench.get("symbol") != recommendation.symbol
            or recommendation.decision_as_of > workbench_date
            or recommendation.action != "no_order"
            or recommendation.position_guidance is not None
            or recommendation.portfolio_input_status != "BLOCKED_PRIVATE_INPUT"
            or kind not in _DECISION_LABELS
            or ("suggested_state" in workbench and workbench["suggested_state"] != kind)):
        raise ValueError("Decision workbench identity, chronology or action differs from recommendation")
    if zone is None:
        if kind not in _NO_QUOTE_DECISION_TYPES:
            raise ValueError("Decision workbench has no registered price zone")
        if recommendation.current_price is not None:
            raise ValueError("Decision workbench reports a price without a price zone")
    else:
        if zone.status not in _ZONE_LABELS:
            raise ValueError("Decision workbench has no registered price zone")
        if recommendation.price_attractiveness_status != zone.status:
            raise ValueError("Decision price zone differs from replayed dependency")
    return restored


def _register_replayed_company(payload: dict[str, Any], restored: RestoredDecisionRecommendation,
                               evidence_id: str) -> None:
    case = restored.dependency_objects["research_case"]
    symbol = restored.recommendation.symbol
    summaries = {
        "business_quality": case.thesis,
        "financial_quality": "财务事实已绑定；完整财务质量结论须按决策过程核验。",
        "capital_allocation": "资本配置及可分配现金尚未完成独立评估。",
        "valuation": "当前情景及批准状态见估值与决策过程。",
        "dividend": "分红可持续性尚未准入，不能从估值推导。",
        "risks_counterevidence": "；".join(
            str(item.get("text") or "").strip() for item in case.counter_evidence
            if str(item.get("text") or "").strip()
        ) or "尚未形成完整反证结论。",
    }
    payload["companies"].append({
        "symbol": symbol, "company_name": case.name, "research_status": "PARTIAL",
        "price": _assessment("UNAVAILABLE", None, evidence_id),
        "valuation": _assessment("NOT_READY", None, evidence_id),
        "margin_of_safety": _assessment("NOT_READY", None, evidence_id),
        "dividend": _assessment("INSUFFICIENT_EVIDENCE", None, evidence_id),
        "sections": [{"key": key, "status": "PARTIAL", "summary": summary,
                      "evidence_refs": [evidence_id]} for key, summary in summaries.items()],
        "scenarios": [{"key": key, "assessment": _assessment("NOT_READY", None, evidence_id)}
                      for key in ("bear", "base", "bull")],
        "latest_change": "新增已绑定证据的共享研究结果；具体准入状态见决策过程。",
        "next_trigger": "核验研究假设、事件影响与模型有效性。",
        "original_thesis": "尚未建立用户确认的原始买入论点。",
        "thesis_change": "UNKNOWN", "evidence_refs": [evidence_id], "action": "no_order",
    })
    payload["opportunities"].append({
        "symbol": symbol, "company_name": case.name,
        "why_now": "新增共享研究结果，供复核；不代表买入推荐。",
        "research_status": "PARTIAL", "valuation_status": "NOT_READY",
        "dividend_status": "INSUFFICIENT_EVIDENCE", "price_status": "UNAVAILABLE",
        "main_risk": "研究与价格准入须逐项核验。",
        "next_trigger": "核验研究假设、事件影响与模型有效性。",
        "evidence_refs": [evidence_id], "action": "no_order",
    })


def project_verified_decision_workbench(
    payload: dict[str, Any], *, root: Path, path: Path, expected_sha256: str,
    register_company: bool = False,
) -> None:
    """Mutate a candidate payload only after exact artifact and date replay."""
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Decision workbench requires a SHA-256 pin")
    root = root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root / "runtime") or not target.is_file():
        raise ValueError("Decision workbench must be an existing runtime file")
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Decision workbench hash mismatch")
    workbench = json.loads(raw)
    source_verification = workbench.get("source_verification")
    if source_verification is not None:
        if (not isinstance(source_verification, dict)
                or source_verification.get("status") != "LOCAL_BYTES_VERIFIED"
                or not source_verification.get("sources")):
            raise ValueError("Decision workbench requires verified local sources")
        for source in source_verification["sources"]:
            original = require_inside(root, root / source["path"], "decision source")
            if sha256_file(original) != source["sha256"]:
                raise ValueError("Decision source hash mismatch")
    workbench_at = datetime.fromisoformat(workbench["generated_at"])
    product_at = datetime.fromisoformat(payload["generated_at"])
    if (workbench_at.tzinfo is None or product_at.tzinfo is None
            or workbench_at > product_at):
        raise ValueError("Decision workbench is later than the product snapshot")
    restored = verify_current_decision_workbench(workbench)
    recommendation = restored.recommendation
    kind = current_recommendation_type(recommendation)
    symbol = recommendation.symbol
    if recommendation.decision_as_of != date.fromisoformat(payload["as_of"]):
        raise ValueError("Decision workbench identity, date or action differs from product")
    companies = [card for card in payload["companies"] if card["symbol"] == symbol]
    opportunities = [card for card in payload["opportunities"] if card["symbol"] == symbol]
    zone = restored.dependency_objects.get("price_attractiveness")

    evidence_id = f"decision-workbench-{symbol}-{expected_sha256[:16]}"
    if any(item["evidence_id"] == evidence_id for item in payload["audit"]["evidence"]):
        raise ValueError("Decision workbench evidence id already exists")
    if not companies and not opportunities and register_company:
        _register_replayed_company(payload, restored, evidence_id)
        companies = [payload["companies"][-1]]
        opportunities = [payload["opportunities"][-1]]
    if len(companies) != 1 or len(opportunities) != 1:
        raise ValueError("Decision company must already exist in both product views")
    payload["audit"]["evidence"].append({
        "evidence_id": evidence_id,
        "title": f"{symbol} 当前研究决策制品",
        "artifact_type": "verified_decision_workbench",
        "path": target.relative_to(root).as_posix(),
        "sha256": expected_sha256,
        "available_at": datetime.fromisoformat(workbench["generated_at"]).date().isoformat(),
        "action": "no_order",
    })
    company = companies[0]
    opportunity = opportunities[0]
    refs = list(dict.fromkeys([*company["evidence_refs"], evidence_id]))
    company["evidence_refs"] = refs
    opportunity["evidence_refs"] = list(dict.fromkeys([*opportunity["evidence_refs"], evidence_id]))
    label = _DECISION_LABELS[kind]
    zone_label = (
        _ZONE_LABELS[zone.status] if zone is not None else "暂不可评估：尚无当前报价"
    )
    primary_reason = (
        recommendation.blockers[0] if recommendation.blockers else
        zone.reasons[0] if zone is not None and zone.reasons else
        "研究和价格前置仍需复核。"
    )
    valuation = restored.dependency_objects["valuation"]
    objects = restored.dependency_objects
    gate = objects["research_gate"]
    approval = objects.get("human_approval")
    approval_decision = None
    if approval is not None and recommendation.input_model_id:
        approval_decision = resolve_human_research_approval(
            approval, valuation, model_id=recommendation.input_model_id,
            research_case_payload=restored.dependencies["research_case"].envelope.payload_object(),
            facts_payload=restored.dependencies["financial_facts"].envelope.payload_object(),
            assumptions_payload=(
                restored.dependencies["valuation_assumptions"].envelope.payload_object()
                if "valuation_assumptions" in restored.dependencies else {}
            ),
        )
    approval_ready = bool(
        approval_decision is not None and approval_decision.approved
        and not approval_decision.blockers
        and approval.review_as_of <= recommendation.decision_as_of
    )
    valuation_ready = (
        valuation.status in {"approved_research_only", "ready", "conditional_research_only"}
        and not valuation.blockers and gate.results.get(GATE_VALUATION) is True
        and approval_ready and valuation.valuation_date <= recommendation.decision_as_of
    )
    valuation_conditional = (
        valuation.status == "conditional_research_only" and not valuation.blockers
        and (approval is None or approval_ready)
    )
    next_event = next(
        (str(item.get("text") or "").strip() for item in recommendation.next_events
         if str(item.get("text") or "").strip()),
        "等待新的官方证据和人工复核。",
    )
    breaker_text = "；".join(
        str(item.get("text") or "").strip() for item in recommendation.thesis_breakers
        if str(item.get("text") or "").strip()
    ) or "尚无已登记的具体 Thesis Breaker；须补齐原始买入逻辑后评估。"
    counter_text = "；".join(
        str(item.get("text") or "").strip() for item in recommendation.counter_evidence
        if str(item.get("text") or "").strip()
    ) or "当前研究制品尚未形成具体反证。"
    managed_labels = {
        "当前研究结论", "价格区域", "当前决策状态", "为什么未进入更高状态",
        "人工买入复核条件", "人工加仓复核条件", "停止加仓条件", "减仓/退出复核触发",
        "下一触发", "个人仓位", "加仓、减仓与退出", "最强反证", "当前动作复核边界",
    }
    company["decision_review"] = [
        *(row for row in company.get("decision_review", []) if row.get("label") not in managed_labels),
        {"label": "当前研究结论", "value": recommendation.thesis},
        {"label": "价格区域", "value": zone_label},
        {"label": "当前决策状态", "value": label},
        {"label": "为什么未进入更高状态", "value": primary_reason},
        {"label": "最强反证", "value": counter_text},
        {"label": "当前动作复核边界", "value": _DECISION_BOUNDARY_TEXT.get(
            kind, f"尚未满足证券级前置：{primary_reason}"
        )},
        {"label": "人工买入复核条件", "value": (
            "证券级研究和价格前置已满足；仍需人工核对证据及个人组合容量。"
            if kind == "BUY_CANDIDATE"
            else f"尚未满足证券级前置：{primary_reason}"
        )},
        {"label": "人工加仓复核条件", "value": "需真实持仓、原始 Entry Thesis、有效估值与组合容量；当前未评估。"},
        {"label": "停止加仓条件", "value": "模型失效、重大反证或原始投资逻辑受损时暂停；需持仓后逐项复核。"},
        {"label": "减仓/退出复核触发", "value": f"原始逻辑破坏线索：{breaker_text}；不得仅凭涨跌自动执行。"},
        {"label": "下一触发", "value": next_event},
        {"label": "个人仓位", "value": "尚未接入真实组合；不生成个人仓位建议。"},
        {"label": "加仓、减仓与退出", "value": "需真实持仓、原始买入逻辑和组合输入后激活人工复核。"},
    ]
    for section in company.get("sections", []):
        if section["key"] in {"business_quality", "risks_counterevidence"}:
            section["summary"] = recommendation.thesis if section["key"] == "business_quality" else counter_text
            section["evidence_refs"] = [evidence_id]
            # Updated research text is not a new quality or approval assessment.
            section["status"] = "PARTIAL"
    if recommendation.next_events:
        next_event = str(recommendation.next_events[0].get("text") or "").strip()
        if next_event:
            company["next_trigger"] = next_event
            opportunity["next_trigger"] = next_event
    if recommendation.thesis_breakers:
        breaker = str(recommendation.thesis_breakers[0].get("text") or "").strip()
        if breaker:
            opportunity["main_risk"] = breaker
    bridge = restored.dependency_objects.get("price_bridge")
    if (
        recommendation.current_price is not None
        and recommendation.price_bridge_status == "READY"
        and bridge is not None
    ):
        company["price"] = _assessment(
            "AVAILABLE", f"{recommendation.current_price} 元；{bridge.quote_date}", evidence_id,
        )
        opportunity["price_status"] = "AVAILABLE"
    else:
        company["price"] = _assessment("UNAVAILABLE", None, evidence_id)
        opportunity["price_status"] = "UNAVAILABLE"
    values = recommendation.valuation_range
    if all(value is not None for value in (values.bear, values.base, values.bull)):
        valuation_status = "AVAILABLE" if valuation_ready else "UNDER_REVIEW"
        company["valuation"] = _assessment(
            valuation_status,
            f"Bear {values.bear:.2f} / Base {values.base:.2f} / Bull {values.bull:.2f} 元；"
            f"置信度{recommendation.confidence}；模型状态{valuation.status}",
            evidence_id,
        )
        opportunity["valuation_status"] = valuation_status
        for scenario in company["scenarios"]:
            scenario["assessment"] = _assessment(
                valuation_status, f"{getattr(values, scenario['key']):.2f} 元", evidence_id,
            )
    else:
        company["valuation"] = _assessment("NOT_READY", None, evidence_id)
        opportunity["valuation_status"] = "NOT_READY"
        for scenario in company["scenarios"]:
            scenario["assessment"] = _assessment("NOT_READY", None, evidence_id)
    if recommendation.margin_of_safety.to_bear is not None:
        company["margin_of_safety"] = _assessment(
            "AVAILABLE",
            f"相对 Bear {recommendation.margin_of_safety.to_bear:.1%}；"
            f"相对 Base {recommendation.margin_of_safety.to_base:.1%}",
            evidence_id,
        )
    else:
        company["margin_of_safety"] = _assessment("NOT_READY", None, evidence_id)
    company["decision_process"] = [
        {
            "key": key, "status": "BLOCKED",
            "reason": "尚未提供该步骤的正式评估结果。",
            "next_action": "补齐评估记录、证据和复核结果。",
            "evidence_refs": [evidence_id],
        }
        for key in _DECISION_STEPS
    ]
    decisions = {step["key"]: step for step in company["decision_process"]}
    facts = objects["financial_facts"]
    facts_ready = (
        gate.results.get(GATE_EVIDENCE) is True
        and gate.results.get(GATE_FINANCIAL) is True
        and facts.verified and not facts.blockers and bool(facts.evidence_refs)
        and facts.symbol == symbol and facts.as_of <= recommendation.decision_as_of
    )
    validity = objects.get("model_validity")
    model_ready = bool(
        validity is not None and validity.status == "VALID" and not validity.blockers
        and not model_validity_identity_blockers(validity, valuation)
        and validity.valid_from <= recommendation.decision_as_of
    )
    research_ready = bool(
        gate.valuation_ready and gate.ready_for_price_assessment and not gate.blockers
        and facts_ready and valuation_ready and approval_ready
        and approval_decision.price_assessment_eligible
    )
    financial_reason = "已绑定财务事实及证据门、财务门结果。"
    financial_scope = objects["research_case"].financial_summary.get("financial_scope_review")
    if isinstance(financial_scope, dict) and financial_scope.get("scope") == (
        "historical_financial_basis_and_conditional_residual_income_research_only"
    ):
        financial_reason = (
            "历史财务基础及条件剩余收益研究范围已审阅；"
            "正常化盈利、持续分配、金融尾部及主估值未获批准。"
        )
    for key, passed, reason in (
        ("financial_facts", facts_ready, financial_reason),
        ("business_quality", gate.results.get(GATE_BUSINESS) is True,
         "已绑定商业论点、支持与反证；论点门通过不等于高质量或投资批准。"),
        ("model_applicability", model_ready, "已绑定模型身份及有效性评估。"),
        ("research_gate", research_ready, "已绑定研究门及精确研究批准结果。"),
        ("portfolio_gate", False, "BLOCKED_PRIVATE_INPUT；个人仓位 position_guidance=null。"),
    ):
        decisions[key].update({
            "status": "PASS" if passed else "BLOCKED",
            "reason": reason if passed or key == "portfolio_gate" else f"{reason}当前前置未通过或证据不足。",
            "next_action": "补齐真实 IPS 与组合输入。" if key == "portfolio_gate" else "复核对应依赖证据与批准结果。",
            "evidence_refs": [evidence_id], "assessment_id": evidence_id,
        })
    decisions["valuation"].update({
        "status": "PASS" if valuation_ready else "CONDITIONAL" if valuation_conditional else "BLOCKED",
        "reason": ("已形成经批准的研究估值。" if valuation_ready else
                   "仅有条件性研究情景，不能据此判断当前买点。" if valuation_conditional else
                   "当前估值尚未就绪。"),
        "next_action": "继续核验假设、反证和模型有效性。",
        "evidence_refs": [evidence_id],
        "assessment_id": evidence_id,
    })
    bridge = objects.get("price_bridge")
    bridge_ready = bool(
        bridge is not None and bridge.bridge_status == "READY"
        and not bridge.blockers and model_ready
        and not price_bridge_binding_blockers(valuation, bridge)
        and bridge.quote_date is not None and bridge.quote_date <= recommendation.decision_as_of
    )
    decisions["price_bridge"].update({
        "status": "PASS" if bridge_ready else "BLOCKED",
        "reason": ("当前报价与有效模型已完成价格桥接。" if bridge_ready else
                   "当前报价尚未与有效模型完成价格桥接。"),
        "next_action": "继续核验报价来源、模型有效性和重大事件。",
        "evidence_refs": [evidence_id],
        "assessment_id": evidence_id,
    })
    decisions["decision_gate"].update({
        "status": (
            "PASS" if kind == "HOLD"
            else "BLOCKED" if kind == "NO_ACTION"
            else "CONDITIONAL"
        ),
        "reason": f"{label}。{primary_reason}",
        "next_action": (
            "人工复核研究与价格；个人仓位待真实组合输入。"
            if kind in {"BUY_CANDIDATE", "ADD_CANDIDATE"}
            else "人工复核原始买入逻辑、证据与组合约束；个人仓位待真实组合输入。"
        ),
        "evidence_refs": [evidence_id],
        "assessment_id": evidence_id,
    })
    payload["today_items"] = [
        row for row in payload["today_items"]
        if not (row.get("symbol") == symbol and row.get("category") == "RESEARCH_CHANGE"
                and any(ref.startswith(f"decision-workbench-{symbol}-")
                        for ref in row.get("evidence_refs", [])))
    ]
    payload["today_items"].append({
        "category": "RESEARCH_CHANGE", "company": company["company_name"], "symbol": symbol,
        "what_happened": "共享研究与决策结果已更新。",
        "why_it_matters": primary_reason, "current_status": label,
        "next_step": company["next_trigger"], "evidence_refs": [evidence_id],
    })
    payload["overview"]["pending_count"] = len(payload["today_items"])
    payload["system_health"]["message"] = (
        f'已登记 {len(payload["companies"])} 家公司使用同一研究展示路径；'
        '各自事实、估值与缺项分开。非个性化建议按各公司的决策状态展示；不执行订单。'
    )
