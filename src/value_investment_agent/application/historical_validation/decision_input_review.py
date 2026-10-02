"""Join real reconstruction and observations without admitting a strategy."""
from datetime import datetime
from copy import deepcopy


def review_historical_decision_inputs(reconstruction: dict, history: dict) -> dict:
    if (reconstruction.get('schema_version') != 'reconstructed-equity-input-v1'
            or history.get('schema_version') != 'historical-price-bridge-replay-v1'
            or reconstruction.get('symbol') != history.get('symbol')
            or not reconstruction.get('workbench_sha256')
            or reconstruction['workbench_sha256'] != history.get('valuation_reference_sha256')
            or any(item.get('action') != 'no_order' for item in (reconstruction, history))
            or any(item.get('strict_pit_admitted') is not False for item in (reconstruction, history))):
        raise ValueError('decision input review requires matching non-admitted real-input replays')
    def indexed(rows):
        result = {}
        for row in rows:
            point = datetime.fromisoformat(row['cutoff'])
            if point.utcoffset() is None or point in result:
                raise ValueError('decision input cutoffs require unique aware timestamps')
            result[point] = row
        return result
    facts = indexed(reconstruction['cutoffs'])
    observations = indexed(history['rows'])
    if not facts or facts.keys() != observations.keys():
        raise ValueError('decision inputs must share exactly the same cutoffs')
    rows = []
    for point in sorted(facts):
        fact = facts[point]
        observation = observations[point]
        timeline = []
        for source in reconstruction.get('facts', []):
            available = datetime.fromisoformat(source['reconstructed_availability']['available_from'])
            reviewed = datetime.fromisoformat(source['original_review_available_at'])
            if available.utcoffset() is None or reviewed.utcoffset() is None:
                raise ValueError('fact availability and review times require timezones')
            eligible = available <= point
            matching = [item for item in fact['eligible_facts']
                        if item['fact_name'] == source['fact_name']]
            if len(matching) != int(eligible) or (matching and matching[0] != source):
                raise ValueError('eligible facts must match source evidence and cutoff availability')
            timeline.append(dict(**deepcopy(source), publicly_available_at_cutoff=eligible,
                review_observed_at_cutoff=reviewed <= point,
                semantic_status='VERIFIED' if source.get('source_excerpt_semantics_verified') is True
                                else 'NOT_VERIFIED'))
        blockers = []
        if fact['missing_facts']:
            blockers.append('财务基础数据尚未公开：' + ', '.join(fact['missing_facts']))
        if not observation['quote_observed']:
            blockers.append('保留行情在决策截止后才抓取，不能回填当时已观察行情。')
        if not observation['valuation_observed']:
            blockers.append('保留估值结果在截止后生成，不能回填当时已运行模型。')
        blockers.extend(observation['blockers'])
        blockers.extend(['预测假设为事后重建；尚无单独冻结并获研究性重建准入的完整规则/假设输入。不能冒充当时运行。',
                         '原财务行语义及完整 FinancialFacts 尚未批准。',
                         '完整 ResearchCase、事件影响与投资决策门未通过历史准入。',
                         '没有对应真实决策的下一交易日成交输入与组合约束。'])
        rows.append(dict(cutoff=point.isoformat(),
            publicly_available_basis_facts=[item['fact_name'] for item in fact['eligible_facts']],
            fact_evidence_timeline=timeline,
            missing_basis_facts=fact['missing_facts'],
            retained_quote_observed=observation['quote_observed'],
            retained_valuation_observed=observation['valuation_observed'],
            bridge_arithmetic_status=(observation['bridge'] or {}).get('bridge_status', 'NOT_ESTABLISHED'),
            decision_input_status='NOT_READY', suggested_state='NOT_READY',
            blockers=list(dict.fromkeys(blockers)), position_guidance=None, orders=[], fills=[], action='no_order'))
    return dict(schema_version='historical-decision-input-review-v1', symbol=history['symbol'], rows=rows,
        scope='REAL_INPUT_TEMPORAL_REVIEW_NOT_STRATEGY_ADMISSION', action='no_order',
        strict_pit_admitted=False, historical_execution_validated=False, performance_claim_allowed=False,
        next_input_contract=['source-bound complete facts with available_at',
            'separately frozen assumptions and rule versions with declared reconstruction status',
            'historical research/financial/event/model gates',
            'cutoff-consistent quotes and next-session execution evidence',
            'portfolio constraints and applicable dated cost/cash-event rules'])


def render_decision_input_review(review: dict) -> str:
    lines = ['## 真实历史决策输入核验', '',
             '公开财报、事后重建、当时观察与真实历史策略是不同的验收；action=no_order。', '']
    for row in review['rows']:
        lines.extend([f"### {row['cutoff']}",
            f"当时已公开的基础字段：{', '.join(row['publicly_available_basis_facts']) or '无'}",
            f"保留行情已观察：{row['retained_quote_observed']}；保留估值已观察：{row['retained_valuation_observed']}",
            f"价格桥接算术：{row['bridge_arithmetic_status']}；决策：NOT_READY", ''])
        lines.extend(f'- {blocker}' for blocker in row['blockers'])
        if row.get('fact_evidence_timeline'):
            lines.extend(['', '#### 财务输入证据时间线',
                          '公开可用、实际复核与语义验证分别显示；公开可用不代表完整财务门已通过。'])
        for fact in row.get('fact_evidence_timeline', []):
            availability = fact['reconstructed_availability']
            lines.extend([f"- {fact['fact_name']}：{fact['value']} {fact['unit']}；期间 {fact['period']}",
                f"  来源 {fact['source_id']}；原件物理页 {fact['physical_page']}；Hash {fact['source_file_hash']}",
                f"  保守可用时点 {availability['available_from']}；依据 {availability['basis']}；精度 {availability['timestamp_precision']}",
                f"  截止时已公开：{fact['publicly_available_at_cutoff']}；实际复核时点 {fact['original_review_available_at']}；截止时已复核：{fact['review_observed_at_cutoff']}",
                f"  原文语义核验：{fact['semantic_status']}"])
        lines.append('')
    lines.extend(['### 后续完整输入合同', *[f'- {item}' for item in review['next_input_contract']]])
    return '\n'.join(lines)
