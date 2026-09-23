# M4 组合风险与集中度评估：2026-09-24

更新：2026-09-24。本文记录 M4 非个人化风险域的第一批离线工程。本批只使用显式
模拟组合，不读取真实账户、IPS、现金、持仓或交易记录；所有动作保持
`action=no_order`。M2 当前为 `PENDING_HUMAN_REVIEW`，M3、M4 均仍为 `PARTIAL`。

## 已实现

- `src/value_investment_agent/portfolio_risk.py`
  - `SecurityRiskAttributes`：行业、周期、流动性画像、共同因子和证据引用。
  - `RiskFinding`：单项集中度、现金或流动性风险，保留实测值与政策上限。
  - `PortfolioRiskAssessment`：组合总资产、现金、当前权重、行业/周期暴露、
    共同因子和流动性暴露；缺输入失败关闭。
  - 实际评估只接受人工确认且已对账的 `ACTUAL` 快照；公开工作簿只接受
    `SIMULATED` 评估，防止模拟结果冒充真实组合。
- `src/value_investment_agent/m4_portfolio_risk_workbook.py`
  - 4 页独立候选：`00_组合风险`、`01_持仓与集中度`、
    `02_风险发现`、`03_输入与边界`。
  - 不显示目标仓位、仓位大小、订单或自动调仓文本。
- `scripts/build_m4_portfolio_risk_candidate.py`
  - 从 `tests/fixtures/m4_portfolio_risk_demo.json` 构建确定性模拟候选。
- `scripts/verify_m4_portfolio_risk_candidate_wps.ps1`
  - WPS 只读打开、页序、公式错误、模拟标签、行数与 `no_order` 检查。

## 风险口径

- 单股、单行业和周期暴露按当前组合市值权重计算；超限保留原值和政策上限，不做
  自动减仓或调仓。
- 最低现金与应急/流动性需要分别表达；保守保留现金取
  `max(minimum_cash, emergency_cash + liquidity_needs)`。
- 流动性 `RESTRICTED/UNKNOWN` 不伪造上限，只输出
  `REVIEW_REQUIRED` 并要求人工复核。
- 共同因子只做透明暴露，不生成唯一风险分数。
- 缺失、未确认、未对账或模拟但未显式标记的输入均不能生成真实个人化报告。

## 尚未实现

- 私有持久化、加密备份、真实账户导入和原 Excel M4 展示。

这些项目继续按总Goal推进；真实 IPS/持仓仍由用户确认后提供，系统不猜测风险偏好
或默认 20% 仓位。

`PositionGuidance` 与 `DividendIncomeProjection` 已在
`v2026.09.24-m4-position-guidance-income` 后续批次完成。

## 验证

- M4 风险域定向回归：8 passed。
- M4 合同/风险/工作簿联合回归：18 passed。
- 模拟候选：4 页、3 个持仓、3 项风险发现，`action=no_order`。
- 候选字节数 10,060，SHA-256
  `0594db6981a78063883271cd2fa45e117487fe6a9657a97e14665dc6bf8b07a7`。
- WPS 只读收据：
  `runtime/m4-portfolio-risk-wps-20260924/receipt.json`，`passed`。
- WPS 云盘同名副本与本仓库候选逐字节一致。
