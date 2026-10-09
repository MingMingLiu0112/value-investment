"""Display a verified bounded followup without changing investment assessments."""
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo
from .product_workbench import EvidenceRecord, EventCard, EventAuditRecord, StatusView, TodayItem


def project_event_followup(model, followup):
    if followup.get("scope") != "SOURCE_ANCHORED_EXPLANATION_ONLY" or followup.get("action") != "no_order":
        raise ValueError("event followup cannot authorize investment")
    cards = [card for card in model.companies if card.symbol == followup["symbol"]]
    if len(cards) != 1:
        raise ValueError("event followup requires exactly one existing company")
    card = cards[0]
    point = datetime.fromisoformat(followup["observed_at"])
    observed_date = point.astimezone(ZoneInfo("Asia/Shanghai")).date() if point.utcoffset() is not None else None
    if observed_date is None or observed_date > model.as_of:
        raise ValueError("event followup observation is outside product cutoff")
    research_steps = {"financial_facts", "business_quality"}
    partial_research = any(step.status != "BLOCKED" for step in card.decision_process
                           if step.key in research_steps)
    if any(step.status != "BLOCKED" for step in card.decision_process
           if step.key not in {"valuation", *research_steps}):
        raise ValueError("event followup cannot inherit admitted decisions")
    rows = dict(card.decision_review)
    if set(rows) & followup["rows"].keys():
        raise ValueError("event followup labels must be new")
    rows.update(followup["rows"])
    impacts = followup.get("assumption_impacts", [])
    # Completed facts/business research is distinct from investment admission;
    # preserve it only when this followup binds the same displayed workbench.
    if impacts or partial_research:
        binding = followup["model_binding"]
        matches = [record for record in model.audit_evidence
                   if record.sha256 == binding["sha256"]
                   and record.path.replace("\\", "/") == binding["path"].replace("\\", "/")
                   and record.artifact_type == "verified_decision_workbench"]
        active_refs = {ref for step in card.decision_process if step.key == "valuation"
                       for ref in step.evidence_refs}
        if len(matches) != 1 or matches[0].evidence_id not in active_refs:
            raise ValueError("event followup model differs from the displayed company decision")
    if impacts:
        for impact in impacts:
            names = dict.fromkeys("前瞻ROE路径" if name.startswith("forecast_roes_") else {
                "cost_of_equity": "权益成本", "terminal_roe": "终值ROE",
                "terminal_growth": "终值增长", "retention": "留存比例",
            }.get(name, name) for name in impact["assumption_names"])
            rows["当前模型影响研究 " + impact["announcement_id"]] = (
                "涉及：" + ("、".join(names) or "未发现新增定量预测") + "。"
                + impact["reason"] + "；重开条件：" + impact["reopen_condition"])
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
        followup["path"], followup["sha256"], observed_date)
    if any(item.evidence_id == identity for item in model.audit_evidence):
        raise ValueError("event followup already exists")
    steps = tuple(replace(step,
        reason=("本次新披露后研究门尚未重新评审；以下为披露前阻断记录，部分事实可能已更新："
                + step.reason),
        next_action=("先复核新披露的影响与未解问题：" + "；".join(unresolved)
                     + "。再重新评审研究门；不得沿用旧缺项或自动通过。"),
        evidence_refs=tuple(dict.fromkeys((*step.evidence_refs, identity))))
        if step.key == "research_gate" else step for step in card.decision_process)
    updated = replace(card, decision_review=tuple(rows.items()),
        decision_process=steps,
        evidence_refs=(*card.evidence_refs, identity),
        latest_change=(f'{observed_date.isoformat()} 新增正式披露已核对原件；'
                       '影响、重大性及投资状态尚未批准。'),
        next_trigger=('新披露后需复核：' + '；'.join(unresolved)
                      + '。不因原件到手自动通过估值或买卖门。'))
    today = TodayItem(StatusView("EVENT", "重要事件"), card.company_name,
        "新增正式披露已取得原件；已核对内容见公司卡的研究更新。",
        "部分旧事实缺口有了新依据，但风险评估、估值和组合门禁不因此通过。",
        "待复核；不构成买卖建议", "；".join(unresolved), (identity,), card.symbol)
    events, audits = [], []
    for impact in impacts:
        event_id = f"research-followup-{card.symbol}-{impact['announcement_id']}-{followup['sha256'][:12]}"
        visible = impact["user_visible"]
        if visible:
            events.append(EventCard(event_id, StatusView("EVIDENCE_GAP", "模型研究证据缺口"),
                card.company_name, followup["rows"][impact["claim_labels"][0]],
                "前瞻盈利、资本分配及当前模型适用性", "原文已核对；影响仍未获准入。" + impact["reason"],
                StatusView("REOPEN_RESEARCH", "需要重新研究"), impact["reopen_condition"], (identity,)))
        disposition = "EVIDENCE_GAP" if visible else (
            "SUPPRESSED_DUPLICATE" if impact["kind"] == "DERIVED_DUPLICATE" else "AUDIT_ONLY")
        audits.append(EventAuditRecord(event_id, "RESEARCH_EXPLANATION_ONLY", disposition, visible,
            (identity,), published_at=impact["published_at"], observed_at=point.isoformat(),
            corrected_conclusion="来源与参数已绑定；重大性、模型和投资批准均未升级。"))
    if {item.event_id for item in events} & {item.event_id for item in model.events}:
        raise ValueError("event followup duplicates a displayed research event")
    if {item.event_id for item in audits} & {item.event_id for item in model.event_audit_decisions}:
        raise ValueError("event followup duplicates an audited research event")
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   today_items=(*model.today_items, today), audit_evidence=(*model.audit_evidence, record),
                   events=(*model.events, *events), event_audit_decisions=(*model.event_audit_decisions, *audits),
                   overview=replace(model.overview, pending_count=len(model.today_items) + 1))
