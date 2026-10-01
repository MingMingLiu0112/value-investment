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
    drivers = expectations.get('valuation_drivers')
    if drivers is not None:
        if (drivers.get('symbol') != card.symbol or drivers.get('action') != 'no_order'
                or drivers.get('schema_version') != 'source-bound-valuation-drivers-v1'
                or any(drivers.get(key) is not False for key in ('assumptions_approved',
                    'strict_pit_admitted', 'dividend_capacity_proven'))):
            raise ValueError('valuation drivers cannot approve assumptions or dividend capacity')
        for row in drivers['scenarios']:
            inputs = row['assumptions']
            review += ((f"估值假设 {row['scenario']}（非预测批准）",
                f"ROE路径：{' → '.join(format(Decimal(value), '.1%') for value in inputs['forecast_roe'])}；"
                f"权益资本成本{Decimal(inputs['cost_of_equity']):.1%}；终局ROE{Decimal(inputs['terminal_roe']):.1%}；"
                f"终局增长{Decimal(inputs['terminal_growth']):.1%}；显式期利润留存{Decimal(inputs.get('retention', '0.30')):.1%}"),
                (f"估值构成 {row['scenario']}（元/股）",
                f"期初账面权益{Decimal(row['opening_book_per_share_cny']):.2f} + "
                f"显式剩余收益现值{Decimal(row['explicit_residual_per_share_cny']):.2f} + "
                f"终值剩余收益现值{Decimal(row['terminal_residual_per_share_cny']):.2f} = "
                f"{Decimal(row['value_per_share_cny']):.2f}；终值剩余收益贡献{Decimal(row['terminal_residual_contribution_ratio']):.1%}"))
        review += (('估值假设解释边界', '历史加权ROE不是开期账面权益预测ROE。留存率推导的模型股息路径仅作代数对账，'
            '不是可分红现金证明。终值剩余收益可以为负；终局ROE等于资本成本时该项为零，不代表终局企业价值为零。'
            '以上是冻结的事后研究情景，不因价格变化修改。'),)
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
        review = dict(card.decision_review)
        lines.extend([f'## {card.symbol} {card.company_name}', '',
            f'研究状态：{card.research_status.user_label}',
            f'当前价格状态：{card.price.status.user_label}',
            f'估值状态：{card.valuation.status.user_label}', '',
            '| 情景 | 保留的研究结果 | 状态 |', '| --- | --- | --- |'])
        for scenario in card.scenarios:
            assessment = scenario.assessment
            lines.append(f'| {scenario.title} | {assessment.value_text or "不可评估"} | {assessment.status.user_label} |')
        lines.extend(['', '### 先看研究结论与反证', ''])
        for label in ('核心研究论点（非买入批准）', '预期回报来源', '最强反证', '什么事实会削弱论点'):
            if label in review:
                lines.extend([f'**{label}**', review[label], ''])
        lines.extend(['### 估值依赖什么假设', ''])
        driver_rows = [(label, value) for label, value in card.decision_review if label.startswith(('估值假设 ', '估值构成 '))
                       or label == '估值假设解释边界']
        if not driver_rows:
            lines.append('尚未接入来源绑定的假设分解，不能仅凭估值数字判断可靠性。')
        lines.extend(f'- {label}：{value}' for label, value in driver_rows)
        lines.extend(['', '### 为什么目前不能作为买入依据', ''])
        blocked = [step for step in card.decision_process if step.status == 'BLOCKED']
        if blocked:
            lines.extend(f'- {step.title}：{step.reason}' for step in blocked)
        else:
            lines.append('本报告不批准投资或下单；当前决策须另行核验研究、行情、事件和组合输入。')
        lines.extend(['', f'下一触发条件：{card.next_trigger}', '', '### 现金与股息摘要', ''])
        cash_labels = {'经营现金流变化合计（描述性）', '现金流变化解释边界', '财务解释边界',
                       '股息可持续性边界'}
        summary = [(label, value) for label, value in card.decision_review
                   if label in cash_labels or 'CFO减现金资本开支' in label or label.startswith('股息记录 ')]
        if not summary:
            lines.append('尚未接入已核验的现金与股息研究；不推定可持续分红或股息率。')
        for label, value in summary:
            # Source paths and hashes remain below, not in the quick-read summary.
            concise = value.split(' 原件：', 1)[0] if label.startswith('股息记录 ') else value
            if label.startswith('股息记录 '):
                concise = concise.split('；记录缺项：', 1)[0].replace('普通/特别分类：unknown', '普通/特别分类：未核定')
            lines.extend([f'- {label}：{concise}'])
        lines.extend(['', '### 决策过程', ''])
        lines.extend(f'- {step.title}：{step.status}。{step.reason}' for step in card.decision_process)
        groups = [('研究解释与财务明细', []), ('公告原件与待复核事项', []), ('股息原件与生命周期', []), ('来源审计入口', [])]
        for label, value in card.decision_review:
            if label.startswith('待复核公告 ') or label in {'公告覆盖边界', '公告原件核验'}:
                group = 1
            elif label.startswith('股息'):
                group = 2
            elif label.startswith('财报原件入口'):
                group = 3
            else:
                group = 0
            groups[group][1].append((label, value))
        for title, items in groups:
            if items:
                lines.extend(['', f'### {title}', ''])
                lines.extend(f'- {label}：{value}' for label, value in items)
        lines.append('')
    return '\n'.join(lines)
