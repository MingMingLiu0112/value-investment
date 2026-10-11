"""A compact daily view of the existing, verified product read model."""
from __future__ import annotations

from decimal import Decimal

from .read_models.existing_research_report import public_workbench_payload_from_snapshot
from .read_models.product_workbench import product_workbench_from_payload


def render_published_research(published: dict, symbols: list[str] | None = None, *, details: bool = False) -> str:
    payload = public_workbench_payload_from_snapshot(published['snapshot'])
    product_workbench_from_payload(payload)
    companies = payload['companies']
    if symbols is not None:
        if len(set(symbols)) != len(symbols) or set(symbols) - {c['symbol'] for c in companies}:
            raise ValueError('unknown or duplicate published company')
        companies = [c for c in companies if c['symbol'] in symbols]
    lines = ['# 今日研究查看', '',
             '已发布研究版本；本次查看不重算模型、不提交审核、不更新工作簿。',
             f"行情观察日期：{published['quote_observation_as_of']}。行情观察不等于价格准入。", '']
    for company in companies:
        rows = company.get('decision_review', [])
        has_candidate = any(row['label'] == '完整主估值候选待审' for row in rows)
        lines += [f"## {company['symbol']} {company['company_name']}", '',
                  f"研究状态：{company['research_status']}"]
        candidate = published.get('pending_candidates', {}).get(company['symbol'])
        if candidate:
            value = candidate['candidate_valuation']
            amounts = ' / '.join(f"{Decimal(value[key]):.2f}" if value.get(key) is not None else '未形成'
                                 for key in ('bear_value', 'base_value', 'bull_value'))
            lines += [f"当前待审候选：{candidate['selected_choice']}；研究日 {candidate['candidate_research_as_of']}",
                      f"待审条件估值 Bear / Base / Bull：{amounts} 元/股；未批准，不能据此计算正式安全边际。"]
        if not has_candidate or details:
            lines.append(f"已保存基线情景（不是新候选）：{company['valuation'].get('value_text') or '未形成'}")
        summary_labels = {'本次重点', '事实与估计', '完整主估值候选待审', '主估值候选最强反证',
                          '当前正式准入', '审核入口', '研究变化归因', '事件复核重点',
                          '当前决策状态', '人工买入复核条件', '减仓/退出复核触发'}
        for row in rows:
            if not details and row['label'] not in summary_labels:
                continue
            lines.append(f"{row['label']}：{row['value']}")
        if details:
            lines += ['', '决策过程（对应保留基线，候选审批独立）：']
            lines.extend(f"- {node['key']}：{node['status']}；{node['reason']}"
                         for node in company.get('decision_process', []))
        lines += ['', f"下一复核：{company.get('next_trigger') or '查看公司页已绑定的复核条件'}", '']
    lines += ['私人组合未接入：position_guidance=null。action=no_order。',
              '审核操作：同一入口 --mode review --symbol 股票代码；未签名不会产生正式批准。', '']
    return '\n'.join(lines)
