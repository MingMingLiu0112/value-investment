"""Render the isolated daily result without deriving investment conclusions."""
from typing import Mapping, Any


_BLOCKER_EXPLANATIONS = {
    'BLOCKED_SCOPE_REQUIRED': '本次研究调度未获准重新计算，保留既有研究状态。',
    'SAME_DAY_POST_CLOSE_REQUIRED': '这不是对应交易日收盘后形成的完整观察。',
    'REAL_PROSPECTIVE_EVENT_INPUT_REQUIRED': '事件输入尚不能证明为真实的前瞻采集。',
    'EVENT_COVERAGE_INCOMPLETE': '公告扫描覆盖尚未证明完整。',
    'EVENT_SOURCE_OR_EMPTY_SCAN_EVIDENCE_REQUIRED': '缺少公告原件，或缺少可核验的当日空扫描证据。',
    'DAG_EXECUTION_INCOMPLETE': '每日研究链有节点未执行完。',
    'COMPLETE_SOURCE_BOUND_DAG_RUN_RECEIPT_REQUIRED': '运行收据尚不能证明完整的来源绑定计算链。',
    'SHARED_RESEARCH_DAILY_INPUT_CONSUMPTION_NOT_PROVEN': '未证明共享研究计算实际消费了本次行情与事件输入。',
    'SHARED_DECISION_REVIEW_LINEAGE_REQUIRED': '决策复核未绑定本次研究结果。',
    'PORTFOLIO_GATE_LINEAGE_REQUIRED': '组合风险门未完成可追溯评估。',
}


def _blocker_explanation(code: str) -> str:
    if code.startswith('MISSING_DAG_ARTIFACT:quote'):
        return '缺少本次已核验的收盘行情，不能比较当前价格与估值。'
    if code.startswith('B1_MATCHED_SAME_DAY_CLOSE_REQUIRED:'):
        return '缺少对应公司的同日有效收盘价。'
    if code.startswith('EVENT_SCAN_TIME_MISSING:') or code == 'EVENT_SCAN_NOT_CURRENT':
        return '事件扫描时间缺失或不属于本次观察日。'
    if code.startswith('MODEL_RESEARCH_PROJECTION_MISMATCH:'):
        return '估值/价格桥接输出未能与共享研究结果对齐。'
    return _BLOCKER_EXPLANATIONS.get(code, '需按原始审计代码复核此项。')


def _main_reasons(blockers: list[str]) -> list[str]:
    codes = set(blockers)
    reasons = []
    if 'BLOCKED_SCOPE_REQUIRED' in codes:
        reasons.append('研究：本次未获准重新计算，不能把既有估值当作今天的新结论。')
    if any(code.startswith(('MISSING_DAG_ARTIFACT:quote', 'B1_MATCHED_SAME_DAY_CLOSE_REQUIRED:'))
           for code in codes):
        reasons.append('行情：缺少同日有效收盘价，价格与内在价值尚不能桥接。')
    if any(code.startswith('EVENT_') or code == 'REAL_PROSPECTIVE_EVENT_INPUT_REQUIRED'
           for code in codes):
        reasons.append('事件：公告扫描的时间、覆盖或原始证据尚不完整。')
    if any(code.startswith(('MODEL_', 'SHARED_', 'COMPLETE_SOURCE_BOUND_DAG_'))
           or code in {'DAG_EXECUTION_INCOMPLETE', 'PORTFOLIO_GATE_LINEAGE_REQUIRED'}
           for code in codes):
        reasons.append('计算链：研究、模型、决策或组合门尚未形成同次可追溯结果。')
    if not reasons and blockers:
        reasons.append('仍有未解决的审计缺项；见文末原始代码。')
    return reasons


def render_shadow_company_review(*, research: Mapping[str, Any], model: Mapping[str, Any],
                                 decision: Mapping[str, Any], product: Mapping[str, Any],
                                 audit: Mapping[str, Any]) -> str:
    result = research['result']
    research_status = result['status']
    decision_status = decision['suggested_state']
    lines = [f'# {result["symbol"]} 公司复核卡', '',
        f'观察日：{research["session_date"]}；运行：{research["run_id"]}', '',
        '## 当前能做什么',
        f'研究结果：{"研究调度未开放" if research_status == "BLOCKED_BY_RESEARCH_SCHEDULER" else research_status}（{research_status}）。'
        f'决策复核：{"暂不可判断" if decision_status == "NOT_READY" else decision_status}（{decision_status}）。',
        '这是隔离研究输出，不是买入、加仓或卖出指令。未生成个性化仓位建议。', '',
        '## 为什么现在不能行动']
    blockers = list(dict.fromkeys([*result.get('blockers', []),
                                  *decision.get('blockers', []), *audit['blockers']]))
    lines.extend('- ' + reason for reason in _main_reasons(blockers))
    if not blockers:
        lines.append('本次未提供人工买入或加仓意图；研究状态不自动成为交易决策。')
    lines.extend(['', '## 已披露事实与仍需核实的问题'])
    followup = product.get('source_anchored_explanation')
    if followup:
        lines.extend(f'- {label}：{value}' for label, value in followup['rows'].items())
        lines.extend(['', '以下缺项未因新公告而自动消除：'])
        lines.extend('- ' + question for question in followup['unresolved_questions'])
        lines.append(f'解释来源 SHA-256：{followup["sha256"]}')
    else:
        lines.append('本次未连接经过原文逐页复验的事实解释，不推断经营或估值结论。')
    valuation = model.get('valuation_result')
    lines.extend(['', '## 估值与价格'])
    if isinstance(valuation, dict):
        lines.extend([f'估值状态：{valuation.get("status", "未提供")}；置信度：{valuation.get("confidence", "未提供")}',
            f'Bear / Base / Bull：{valuation.get("bear_value", "未提供")} / {valuation.get("base_value", "未提供")} / {valuation.get("bull_value", "未提供")}'])
    else:
        lines.append('本次研究未形成估值结果，不用旧数值或模拟数填补。')
    validity = model.get('model_validity')
    bridge = model.get('price_bridge')
    validity_status = validity.get('status', '未提供') if isinstance(validity, Mapping) else validity
    bridge_status = bridge.get('bridge_status', '未提供') if isinstance(bridge, Mapping) else bridge
    lines.append(f'模型有效性：{validity_status or "未提供"}；价格桥接：{bridge_status or "未提供"}。')
    risk = product.get('simulated_portfolio_review')
    if risk:
        assessment = risk['risk_assessment']
        lines.extend(['', '## 模拟组合风险演示（不是你的账户）',
            f'样本日期：{risk["input_as_of"]}；风险状态：{assessment["status"]}。',
            '只验证风险流程；未改成当日持仓，不能确认个人加仓容量。'])
        lines.extend(f'- {finding["subject"]}：{finding["message"]}'
                     for finding in assessment['findings'])
        lines.append('个性化仓位建议：未生成；真实 Shadow 日计数仍为零。')
    lines.extend(['价格桥接与模型有效性以同目录 model.json 为准；有估值不代表当前价格可用。', '',
        '## 再次复核条件',
        '只在具体缺项取得可验证证据后重新复核；公告内容不自动证明材料性审批或原投资逻辑仍成立。',
        '买入后的一致性、加减仓和仓位复核仍需要原始买入逻辑及确认后的组合输入。', '',
        '## 证据与执行边界',
        f'日级输入审查：{audit["input_consistency_status"]}；真实 Shadow 运行日计数：0。',
        '本卡只投影同次研究、模型、决策和原文复验结果；工程运行不是投资有效性证明。',
        'action=no_order', '', '## 审计细项'])
    lines.extend(f'- {_blocker_explanation(blocker)}（{blocker}）' for blocker in blockers)
    if not blockers:
        lines.append('- 本次没有列出的审计缺项；这不等于投资准入。')
    lines.append('')
    return '\n'.join(lines)
