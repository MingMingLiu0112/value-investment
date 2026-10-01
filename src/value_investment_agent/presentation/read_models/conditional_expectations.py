"""Presentation-only historical expectations on the existing company card."""
from dataclasses import replace
from decimal import Decimal
from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel


def project_conditional_expectations(model: ProductWorkbenchReadModel, expectations: dict,
                                     evidence: EvidenceRecord) -> ProductWorkbenchReadModel:
    if (expectations.get('schema_version') != 'retrospective-equity-expectations-v1'
            or expectations.get('scope') != 'RETROSPECTIVE_CONDITIONAL_EXPECTATIONS_NOT_CURRENT_ADVICE'
            or expectations.get('action') != 'no_order'
            or any(expectations.get(key) is not False for key in ('strict_pit_admitted',
                'current_model_admitted', 'performance_claim_allowed', 'assumptions_contemporaneously_registered'))):
        raise ValueError('company expectations cannot admit current decisions')
    cards = [card for card in model.companies if card.symbol == expectations['symbol']]
    if len(cards) != 1 or evidence.available_at > model.as_of:
        raise ValueError('expectations require matching company and available evidence')
    card = cards[0]
    if any(step.status != 'BLOCKED' for step in card.decision_process if step.key != 'valuation'):
        raise ValueError('historical expectations cannot inherit approved decision gates')
    rows = []
    for row in expectations['scenarios']:
        if row['status'] == 'NOT_ASSESSABLE':
            rows.append(f"{row['scenario']}: 不可评估")
        else:
            rows.append(f"{row['scenario']}: {Decimal(row['implied_terminal_roe']):.1%}")
    review = tuple(item for item in card.decision_review if item[0] not in {
        '历史价格日期（非当前行情）', '价格隐含终局ROE（条件性）', '反向估值解释边界'}) + (
        ('历史价格日期（非当前行情）', expectations['quote_date']),
        ('价格隐含终局ROE（条件性）', '; '.join(rows)),
        ('反向估值解释边界', '固定其他事后情景假设，仅反求终局ROE；不是预测，也不证明高估或低估。公告影响、模型准入和当前价格仍需验证。'))
    updated = replace(card, decision_review=review,
                      evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, evidence.evidence_id))))
    records = {record.evidence_id: record for record in model.audit_evidence}
    if evidence.evidence_id in records and records[evidence.evidence_id] != evidence:
        raise ValueError('expectations evidence conflicts with existing audit')
    records[evidence.evidence_id] = evidence
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   audit_evidence=tuple(records.values()))


def render_company_review_cards(model: ProductWorkbenchReadModel) -> str:
    lines = ['# 公司研究卡片（历史研究展示）', '',
        f'展示观察日期：{model.as_of.isoformat()}。行情与财报仍使用各自原始日期。',
        '不是当前买卖建议；不提供个性化仓位；action=no_order。', '']
    for card in model.companies:
        lines.extend([f'## {card.symbol} {card.company_name}', '',
            f'研究状态：{card.research_status.user_label}',
            f'当前价格状态：{card.price.status.user_label}',
            f'估值状态：{card.valuation.status.user_label}', '',
            '| 情景 | 保留的研究结果 | 状态 |', '| --- | --- | --- |'])
        for scenario in card.scenarios:
            assessment = scenario.assessment
            lines.append(f'| {scenario.title} | {assessment.value_text or "不可评估"} | {assessment.status.user_label} |')
        lines.extend(['', '### 决策过程', ''])
        lines.extend(f'- {step.title}：{step.status}。{step.reason}' for step in card.decision_process)
        lines.extend(['', '### 研究解释', ''])
        lines.extend(f'- {label}：{value}' for label, value in card.decision_review)
        lines.extend(['', f'下一触发条件：{card.next_trigger}', ''])
    return '\n'.join(lines)
