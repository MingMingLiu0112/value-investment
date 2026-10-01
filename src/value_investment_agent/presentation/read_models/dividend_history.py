"""Dividend lifecycle explanation; never treat a policy as future cash."""
from dataclasses import replace
from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel


def project_dividend_history(model: ProductWorkbenchReadModel, history: dict,
                             evidence: EvidenceRecord) -> ProductWorkbenchReadModel:
    if (history.get('schema_version') != 'source-bound-dividend-history-v1'
            or history.get('action') != 'no_order'
            or any(history.get(key) is not False for key in ('dividend_sustainability_admitted',
                'current_yield_admitted', 'strict_pit_admitted'))):
        raise ValueError('dividend history cannot admit yield or sustainability')
    cards = [card for card in model.companies if card.symbol == history['symbol']]
    if len(cards) != 1 or evidence.available_at > model.as_of:
        raise ValueError('dividend presentation requires matching company and observation date')
    card = cards[0]
    if any(step.status != 'BLOCKED' for step in card.decision_process if step.key != 'valuation'):
        raise ValueError('historical dividend ledger cannot inherit decision approval')
    review = dict(card.decision_review)
    sources = {source['id']: source for source in history['sources']}
    labels = {'proposed': '提案', 'approved': '批准', 'paid': '实施公告记录（非个人到账证明）'}
    for record in history['records']:
        review[f"股息记录 {record['fiscal_period']} {labels[record['status']]}"] = (
            f"每股{record['dividend_per_share']} {record['currency']}；"
            f"除息日{record['ex_date'] or '未确立'}；支付日{record['payment_date'] or '未确立'}；"
            f"普通/特别分类：{record['dividend_type']}；记录缺项：{'；'.join(record['blockers']) or '无'}。"
            + '; '.join(f" 原件：{sources[ref['id']]['location']}；SHA256={sources[ref['id']]['sha256']}"
                        for ref in record['evidence_refs']))
    review['股息可持续性边界'] = ('生命周期与原件绑定不等于独立语义审核；历史实施不保证未来分红。'
        '政策、提案、批准、实施分别保留；不将同一分红各阶段重复相加。'
        '未引入旧报价股息率，普通/特别分类未核定时不推定普通股息，正常化股息尚未准入。')
    review['股息研究待核验（原包历史状态）'] = (
        f"原包截至{history['package_as_of']}；不是今日审核结论。" + '；'.join(history['blockers']))
    records = {item.evidence_id: item for item in model.audit_evidence}
    if evidence.evidence_id in records and records[evidence.evidence_id] != evidence:
        raise ValueError('dividend evidence conflict')
    records[evidence.evidence_id] = evidence
    updated = replace(card, decision_review=tuple(review.items()),
                      evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, evidence.evidence_id))))
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   audit_evidence=tuple(records.values()))
