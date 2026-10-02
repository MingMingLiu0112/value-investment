"""Render the isolated daily result without deriving investment conclusions."""
from typing import Mapping, Any


def render_shadow_company_review(*, research: Mapping[str, Any], model: Mapping[str, Any],
                                 decision: Mapping[str, Any], product: Mapping[str, Any],
                                 audit: Mapping[str, Any]) -> str:
    result = research['result']
    lines = [f'# {result["symbol"]} 公司复核卡', '',
        f'观察日：{research["session_date"]}；运行：{research["run_id"]}', '',
        '## 当前能做什么',
        f'研究结果：{result["status"]}。决策复核：{decision["suggested_state"]}。',
        '这是隔离研究输出，不是买入、加仓或卖出指令。未生成个性化仓位建议。', '',
        '## 已披露事实与仍需核实的问题']
    followup = product.get('source_anchored_explanation')
    if followup:
        lines.extend(f'- {label}：{value}' for label, value in followup['rows'].items())
        lines.extend(['', '以下缺项未因新公告而自动消除：'])
        lines.extend('- ' + question for question in followup['unresolved_questions'])
        lines.append(f'解释来源 SHA-256：{followup["sha256"]}')
    else:
        lines.append('本次未连接经过原文逐页复验的事实解释，不推断经营或估值结论。')
    lines.extend(['', '## 为什么尚不能据此买入或加仓'])
    blockers = list(dict.fromkeys([*result.get('blockers', []),
                                  *decision.get('blockers', []), *audit['blockers']]))
    lines.extend('- ' + blocker for blocker in blockers)
    if not blockers:
        lines.append('本次未提供人工买入或加仓意图；研究状态不自动成为交易决策。')
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
        'action=no_order', ''])
    return '\n'.join(lines)
