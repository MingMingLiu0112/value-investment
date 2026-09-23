# M4 组合输入合同：2026-09-24

更新：2026-09-24。本文记录第一批 M4 非个人化输入合同，不读取真实持仓，不计算
仓位，不设置通用百分比，也不生成任何订单。M2、M3、M4 均保持 `PARTIAL`。

## 已实现

- `src/value_investment_agent/portfolio_contracts.py`
  - `InvestorPolicyStatement`：IPS 版本、账户范围、确认状态、现金/流动性/期限、
    单股/行业/周期上限、股息目标、风险口径和限制项。
  - `PortfolioHolding`：证券、交易所、数量、成本/市值、数量确认状态、
    公司行为调整状态和证据引用。
  - `PortfolioSnapshot`：实盘/模拟命名空间、时点、账户范围、现金、持仓、
    对账状态和对账证据。
  - `PortfolioInputBundle`：IPS 与持仓快照共同组成输入包，校验账户范围和
    时点顺序。
- 所有对象固定 `action=no_order`、`sensitivity=PRIVATE_USER_CONFIRMED`；
  公开 JSON 拒绝 `buy/sell/target_weight/position_size/order_quantity` 等键。
- 缺失状态不会补成零值或默认仓位；`missing()` 只用于系统无法获得用户输入时
  显式失败关闭，测试中的合成数据不得冒充真实账户。

## 人工确认门槛

IPS 至少需要用户确认：

- 账户范围；
- 可投资资产与最低现金；
- 投资期限；
- 单股和单行业集中度上限；
- 是否允许集中投资；
- 风险承受口径。

持仓快照至少需要：

- 实际账户快照，而非仅模拟；
- 账户范围；
- 现金；
- 每只证券数量已经人工确认；
- 每只持仓具有可核对市值；
- 快照整体完成对账并保留对账证据。

上述任何一项缺失，`can_support_guidance()` 都为 `False`，并返回缺失字段名；
系统不得自行猜测风险偏好或使用默认 20% 仓位。

## 尚未实现

- `PositionGuidance`：分层仓位、共同预算和容量竞争；
- `PortfolioRiskAssessment`：单股、行业、周期、共同因子和流动性风险；
- `DividendIncomeProjection`：已到账、已宣告、Forward、Normalized 和税费情景；
- 私有数据持久化、加密备份和真实账户导入；
- 原 Excel 的 M4 展示页。

这些项目只在 M3 人工决策链稳定且用户提供真实 IPS/持仓后继续，本轮不提前构造
个人化结论。

## 验证

- `tests/test_portfolio_contracts.py`：7 passed。
- 测试覆盖缺失关闭、非法金额/百分比、重复持仓、未对账/模拟快照、往返、
  账户范围不匹配和时点顺序。
