"""Display a verified bounded followup without changing investment assessments."""
from dataclasses import replace
from datetime import datetime
from .product_workbench import EvidenceRecord, StatusView, TodayItem


def project_event_followup(model, followup):
    if followup.get("scope") != "SOURCE_ANCHORED_EXPLANATION_ONLY" or followup.get("action") != "no_order":
        raise ValueError("event followup cannot authorize investment")
    cards = [card for card in model.companies if card.symbol == followup["symbol"]]
    if len(cards) != 1:
        raise ValueError("event followup requires exactly one existing company")
    card = cards[0]
    point = datetime.fromisoformat(followup["observed_at"])
    if point.utcoffset() is None or point.date() > model.as_of:
        raise ValueError("event followup observation is outside product cutoff")
    if any(step.status != "BLOCKED" for step in card.decision_process if step.key != "valuation"):
        raise ValueError("event followup cannot inherit admitted decisions")
    rows = dict(card.decision_review)
    if set(rows) & followup["rows"].keys():
        raise ValueError("event followup labels must be new")
    rows.update(followup["rows"])
    for label in followup["historical_labels"]:
        if label not in dict(card.decision_review):
            raise ValueError("historical explanation must exist in the prior company card")
        old = rows.pop(label)
        target = "历史缺项记录（新披露前） " + label
        if target in rows:
            raise ValueError("historical explanation label conflict")
        rows[target] = old
    unresolved = followup["unresolved_questions"]
    rows["新披露后的待复核事项"] = "；".join(unresolved) + "。不代表估值、重大性或买卖准入。"
    rows["观察与披露时点边界"] = ("本次复核观察时点：" + point.isoformat()
        + "；公告落款见原件。旧包披露/可用字段按原标注口径理解，不作为经独立验证的盘中发布时间。")
    identity = card.symbol + "-event-followup-" + followup["sha256"][:12]
    record = EvidenceRecord(identity, "新增披露的有界研究解释（未获准入）", "event_followup",
        followup["path"], followup["sha256"], point.date())
    if any(item.evidence_id == identity for item in model.audit_evidence):
        raise ValueError("event followup already exists")
    updated = replace(card, decision_review=tuple(rows.items()), evidence_refs=(*card.evidence_refs, identity))
    today = TodayItem(StatusView("EVENT", "重要事件"), card.company_name,
        "新增正式披露已取得原件；已核对内容见公司卡的研究更新。",
        "部分旧事实缺口有了新依据，但风险评估、估值和组合门禁不因此通过。",
        "待复核；不构成买卖建议", "；".join(unresolved), (identity,), card.symbol)
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   today_items=(*model.today_items, today), audit_evidence=(*model.audit_evidence, record))
