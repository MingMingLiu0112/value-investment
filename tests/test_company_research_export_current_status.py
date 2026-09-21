from pathlib import Path

from value_investment_agent.company_research_export import (
    load_cash_anchor_paper_contract_status,
    load_company_research,
    load_finance_cost_scope_sensitivity_status,
    load_current_conditional_observation,
    load_current_execution_contract_status,
    load_current_valuation_admission_status,
    load_simulation_closure_status,
)


ROOT = Path(__file__).resolve().parents[1]


def test_current_export_separates_verified_session_from_unapproved_valuation():
    observation = load_current_conditional_observation(ROOT)
    admission = load_current_valuation_admission_status(ROOT)
    sensitivity = load_finance_cost_scope_sensitivity_status(ROOT)
    cash_anchor = load_cash_anchor_paper_contract_status(ROOT)
    execution = load_current_execution_contract_status(ROOT)
    closure = load_simulation_closure_status(ROOT)
    assert "报价交易会话已验证" in observation
    assert "模型日期与报价会话不一致" in observation
    assert "未计算安全边际、不生成订单" in observation
    assert "正式合理价、模拟、交易及实盘准入仍未通过" in observation
    assert "上交所会话已验证" in admission
    assert "虚拟账户执行机制已验证" in admission
    assert "P1模型契约已冻结：候选主模型为合并归母权益残余收益/分红能力模型" in admission
    assert "条件值仅用于已登记研究日期" in admission
    assert "P1当前模型已完成限定纸面研究准入" in admission
    assert "P2仍须绑定日线状态、流动性、限价与账户执行条款" in admission
    assert "当前合理价为空，不得生成买卖指令" in admission
    assert "不是费用分摊或上界" in sensitivity
    assert "不能解除估值和交易门禁" in sensitivity
    assert "2310日按点时保守端点完成模型评估" in cash_anchor
    assert "仅执行机械条件已登记，不构成估值、订单或实盘准入" in execution
    assert "不是正式合理价、策略收益或实盘建议" in cash_anchor
    assert "上交所交易日历和四段官方停复牌查询已核验" in closure
    assert "旧全拒绝执行契约" in closure
    assert "保守日线模拟契约" in closure
    assert "当前双源会话已验证，观察/无订单" not in closure
    assert "仅验证T+1、费用、现金、持仓与幂等性" in closure


def test_company_research_keeps_zero_signal_counterevidence_before_long_history_detail():
    status = load_company_research(ROOT)["600519"][2]
    zero_signal = "下端在20%/30%/40%均为0个信号"
    long_history = "历史条件估值输入包"
    assert zero_signal in status
    assert status.index(zero_signal) < status.index(long_history)
