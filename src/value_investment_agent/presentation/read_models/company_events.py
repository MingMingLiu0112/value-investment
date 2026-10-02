"""Source-backed event questions on a company card, not materiality approval."""
from dataclasses import replace
from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel


def project_company_event_questions(model: ProductWorkbenchReadModel, packet: dict,
                                    evidence: EvidenceRecord) -> ProductWorkbenchReadModel:
    if (packet.get('schema_version') != 'event-source-review-packet-v1'
            or packet.get('action') != 'no_order'
            or packet.get('materiality_approved') is not False
            or packet.get('model_basis_complete') is not False):
        raise ValueError('event presentation must not approve materiality or model basis')
    cards = [card for card in model.companies if card.symbol == packet['symbol']]
    if len(cards) != 1 or evidence.available_at > model.as_of:
        raise ValueError('event questions require matching company and observation date')
    card = cards[0]
    if any(step.status != 'BLOCKED' for step in card.decision_process if step.key != 'valuation'):
        raise ValueError('unapproved event packet cannot inherit decision approval')
    review = dict(card.decision_review)
    if not packet['audit']['evidence_integrity_verified']:
        review['公告原件核验'] = '未通过；不展示可能已变更原件的公告解释，模型有效性仍待核验。'
    else:
        for event in packet['events']:
            if event['materiality_review'] != 'PENDING_HUMAN_REVIEW':
                raise ValueError('event packet cannot substitute human approval')
            review[f"待复核公告 {event['announcement_id']} {event['title']}"] = (
                f"披露/可用时点（按原输入口径）：{event['published_at']}；原件可读不等于已评估其影响。"
                '需判断是否改变估值假设、分红能力或原投资逻辑，以及模型是否已纳入。'
                + '; '.join(f" 原件：{source['source_url']}；SHA256={source['sha256']}；"
                            f"页数={len(source['pages'])}；文本状态={source['text_status']}"
                            for source in event['sources']))
        review['公告覆盖边界'] = ('这是封存历史区间的原件复核，不代表今日公告扫描完整；'
            '标题分类不等于重大性批准。提案不等于实施，回购上限不等于内在价值，担保额度不等于已发生现金损失。')
    records = {item.evidence_id: item for item in model.audit_evidence}
    if evidence.evidence_id in records and records[evidence.evidence_id] != evidence:
        raise ValueError('event presentation evidence conflict')
    records[evidence.evidence_id] = evidence
    updated = replace(card, decision_review=tuple(review.items()),
                      evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, evidence.evidence_id))))
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   audit_evidence=tuple(records.values()))
