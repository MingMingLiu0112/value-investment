"""Present verified disclosed rows without promoting research admission."""
from dataclasses import replace
from decimal import Decimal

from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel


def project_reported_financials(model: ProductWorkbenchReadModel, review: dict,
                               cash_proxy: dict | None, evidence: EvidenceRecord,
                               cash_change: dict | None = None,
                               earnings_cash_trends: dict | None = None) -> ProductWorkbenchReadModel:
    if (review.get('schema_version') != 'disclosed-metric-review-v1'
            or review.get('action') != 'no_order'
            or any(review.get(key) is not False for key in
                   ('financial_gate_admitted', 'forecast_assumptions_approved', 'strict_pit_admitted'))):
        raise ValueError('disclosed rows cannot approve research gates')
    cards = [card for card in model.companies if card.symbol == review['symbol']]
    if len(cards) != 1 or evidence.available_at > model.as_of:
        raise ValueError('disclosed rows require matching company and observation date')
    card = cards[0]
    if any(step.status != 'BLOCKED' for step in card.decision_process if step.key != 'valuation'):
        raise ValueError('disclosed rows cannot inherit approved decision gates')
    labels = {
        'reported_parent_net_profit': '归母净利润',
        'reported_operating_cash_flow': '经营现金流',
        'reported_cash_capex': '现金资本开支',
        'reported_weighted_roe': '加权ROE',
        'reported_recurring_weighted_roe': '扣非加权ROE',
    }
    additions = []
    for fact in review['facts']:
        if fact['symbol'] != card.symbol or fact['verification_status'] != 'TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY':
            raise ValueError('unverified or mismatched disclosed fact')
        if fact['metric_name'].startswith('cash_bridge_'):
            continue
        value = Decimal(fact['value'])
        if not value.is_finite() or fact['unit'] not in {'CNY', 'percent'}:
            raise ValueError('invalid disclosed metric value/unit')
        amount = f'{value / Decimal("100000000"):.2f}亿元' if fact['unit'] == 'CNY' else f'{value}%'
        name = labels.get(fact['metric_name'], fact['metric_name'])
        scope = {'CONSOLIDATED': '合并报表', 'PARENT': '母公司报表',
                 'UNSPECIFIED': '主要指标表，未单独核定报表范围'}[fact.get('statement_scope', 'UNSPECIFIED')]
        additions.append((f"已披露 {fact['period']} {name}（{scope}）",
                          f"{amount}；原报告物理页{fact['physical_page']}；仅数字对应复核"))
    sources = {fact['source_binding']['sha256']: fact['source_binding'] for fact in review['facts']}
    additions.append((f'财报原件入口（{evidence.evidence_id}）', '; '.join(
        f"{source.get('source_url', source.get('path', '未提供URL'))}；SHA256={digest}"
        for digest, source in sources.items())))
    if cash_proxy is not None:
        if (cash_proxy.get('symbol') != card.symbol or cash_proxy.get('action') != 'no_order'
                or cash_proxy.get('schema_version') != 'reported-cash-capex-proxy-v1'
                or any(cash_proxy.get(key) is not False for key in ('financial_gate_admitted',
                           'dividend_sustainability_admitted', 'valuation_model_admitted'))):
            raise ValueError('cash proxy cannot approve dividend or valuation')
        for row in cash_proxy['rows']:
            amount = ('不可评估' if row['status'] == 'NOT_ASSESSABLE' else
                      f"{Decimal(row['proxy_cny']) / Decimal('100000000'):.2f}亿元")
            additions.append((f"已披露 {row['period']} CFO减现金资本开支（描述性）", amount))
    if cash_change is not None:
        if (cash_change.get('symbol') != card.symbol or cash_change.get('action') != 'no_order'
                or cash_change.get('schema_version') != 'reported-operating-cash-change-v1'
                or cash_change.get('sustainable_cash_proven') is not False
                or cash_change.get('forecast_approved') is not False):
            raise ValueError('cash change cannot admit forecasts or sustainable cash')
        labels = dict(sales_receipts='销售收款', interest_receipts='利息等收款', tax_refunds='退税',
            other_receipts='其他经营收款', purchases_paid='采购付款', employees_paid='职工付款',
            taxes_paid='税费付款', other_payments='其他经营付款')
        additions.append(('经营现金流变化合计（描述性）',
            f"{cash_change['prior_period']}→{cash_change['current_period']}："
            f"{Decimal(cash_change['cfo_change_cny']) / Decimal('100000000'):.2f}亿元；原始元金额精确对账"))
        additions.extend((f'对现金流变化的贡献：{labels[key]}',
                          f"{Decimal(value) / Decimal('100000000'):.2f}亿元")
                         for key, value in cash_change['contributions_cny'].items())
        additions.append(('现金流变化解释边界', '销售回款不等于收入；收付款变化不证明持续性。'
                          '仍需核验营运资本、一次性因素和金融业务，不能直接推定利润质量或分红覆盖。'))
    additions.append(('财务解释边界', '后期报告比较数不能回填历史可得性；加权ROE不是预测ROE；'
                      'CFO减资本开支不是FCFF/FCFE或可分红现金。维持性投资、营运资本、金融业务、债务及少数股东影响仍需研究。'))
    if earnings_cash_trends is not None:
        trends = earnings_cash_trends
        if (trends.get('schema_version') != 'reported-earnings-cash-trends-v1'
                or trends.get('symbol') != card.symbol or trends.get('action') != 'no_order'
                or trends.get('cash_conversion_ratio') is not None
                or any(trends.get(key) is not False for key in (
                    'quality_assessment_admitted', 'financial_gate_admitted', 'forecast_approved'))):
            raise ValueError('reported trends cannot approve quality or cash conversion')
        if any(fact['source_binding'] != trends.get('source_binding') for fact in review['facts']
               if fact['metric_name'] in {'reported_parent_net_profit', 'reported_operating_cash_flow'}):
            raise ValueError('reported trends source binding mismatch')
        for row in trends['rows']:
            def growth(series):
                return ('不可评估（上期非正数）' if series['growth_rate'] is None else
                        f"{Decimal(series['growth_rate']) * Decimal('100'):.2f}%")
            additions.append((f"利润与现金流方向 {row['prior_period']}→{row['current_period']}",
                f"归母净利润同比 {growth(row['parent_profit'])}；经营现金流同比 {growth(row['operating_cash'])}。"
                + ('两项变动方向相反；需进一步核查营运资本、一次性损益和现金流归属，不据此判定利润质量。'
                   if row['opposite_directions'] else '未出现相反变动方向，但不能据此判定现金转化或利润质量。')))
        additions.append(('利润现金比较边界', '归母利润与经营现金流归属不同，不计算同口径现金转换率；'
                          '本报告比较数不是历史当时可得数据。尚未完成营运资本与非经常性损益复核。'))
    merged = dict(card.decision_review)
    merged.update(additions)
    records = {item.evidence_id: item for item in model.audit_evidence}
    if evidence.evidence_id in records and records[evidence.evidence_id] != evidence:
        raise ValueError('financial evidence conflict')
    records[evidence.evidence_id] = evidence
    updated = replace(card, decision_review=tuple(merged.items()),
                      evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, evidence.evidence_id))))
    return replace(model, companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
                   audit_evidence=tuple(records.values()))
