"""Present verified research questions without changing any decision gate."""
from dataclasses import replace
from datetime import datetime

from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel


def project_research_readiness(model: ProductWorkbenchReadModel, packet: dict) -> ProductWorkbenchReadModel:
    result = packet["result"]
    if (result.get("action") != "no_order" or result.get("suggested_state") != "NOT_READY"
            or result.get("position_guidance") is not None
            or result.get("research_status") != "BLOCKED_BY_RESEARCH_SCHEDULER"):
        raise ValueError("readiness projection cannot admit research or positions")
    observed = datetime.fromisoformat(packet["observed_at"])
    if observed.utcoffset() is None or observed.date() > model.as_of:
        raise ValueError("readiness observation exceeds product date")
    cards = [card for card in model.companies if card.symbol == result["symbol"]]
    if len(cards) != 1:
        raise ValueError("readiness requires one existing company card")
    card = cards[0]
    if any(step.status != "BLOCKED" for step in card.decision_process if step.key != "valuation"):
        raise ValueError("stopped readiness cannot inherit decision approval")
    evidence = dict((item.evidence_id, item) for item in model.audit_evidence)
    refs = []
    for binding in packet["source_bindings"]:
        identity = f"{card.symbol}-readiness-{binding['sha256'][:12]}"
        record = EvidenceRecord(identity, "研究缺项台账与展示结果", "research_readiness",
                                binding["path"], binding["sha256"], observed.date())
        if identity in evidence and evidence[identity] != record:
            raise ValueError("readiness evidence conflict")
        evidence[identity] = record
        refs.append(identity)
    review = dict(card.decision_review)
    for stop in result["evidence_stops"]:
        if stop["symbol"] != card.symbol:
            raise ValueError("readiness question symbol mismatch")
        review[f"研究缺项 {stop['stop_id']}"] = (
            f"问题：{stop['research_question_id']}；期间：{stop['period']}；来源：{stop['source_id']}。"
            f"重开条件（原文）：{stop['reopen_condition']}；已查材料：{', '.join(stop['reviewed_evidence_ids'])}。"
        )
    review["研究缺项展示边界"] = "缺项来自已核验停止台账；不是新财报审查、历史时点证明或投资批准。已封存估值继续保留，当前门禁不变。"
    updated = replace(card, decision_review=tuple(review.items()),
                      evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, *refs))))
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   audit_evidence=tuple(evidence.values()))
