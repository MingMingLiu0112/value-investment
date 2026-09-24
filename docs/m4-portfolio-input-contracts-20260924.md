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

## 私有输入加密封装：2026-09-24

`private_portfolio_intake.py` 现提供一个只在私有受控目录中运行的最小封装边界：

- `encrypt_private_portfolio_bundle` 仅接受已人工确认、已对账、`ACTUAL` 的
  `PortfolioInputBundle`，以 AES-256-GCM 写入新的不可覆盖密文；
- `load_private_portfolio_bundle` 仅在内存中解密并重新运行全部领域合同，不把 IPS、
  现金、持仓或交易信息写入仓库、公开 runtime 或回执；
- 私有根目录必须与仓库隔离；`WPSDrive` 是内置失败关闭规则，调用者还可显式传入
  其他同步根目录；密钥必须在仓库、私有根和同步根之外，且只接受独立的 32-byte hex
  密钥文件；
- 回执只有密文 Hash、密钥标识、时间与 `no_order` 状态，不含个人组合数值。

该接口不读取券商账户、不自动导入任何个人文件、不持久化解密结果、不计算订单，且不等于
M4 个性化验收。真实 IPS/组合只会在用户另行提供私有输入并完成对账后，才可进入后续人工
复核流程。

## 私有快照对账：2026-09-25

`portfolio_reconciliation.py` 提供 `reconcile_portfolio_snapshots`：它只比较同一账户、
同一日期的两个 `ACTUAL` 快照，并把现金、持仓是否缺失、交易所、数量和公司行为调整的
差异保留在私有报告中。报告状态只能是：

- `MATCH_PENDING_HUMAN_CONFIRMATION`：比较一致，但仍必须由用户确认，绝不自动把快照
  改为 `RECONCILED`；
- `MISMATCH`：有明确、私有的差异项；
- `INCOMPLETE`：缺少关键比较值，不能将未知当作一致。

对账报告不写入公开 runtime、不提供公开序列化接口、不计算风险/仓位/订单；其输出固定
`action=no_order`、`sensitivity=PRIVATE_USER_CONFIRMED`。

使用时只允许对已加密输入执行校验，命令只打印脱敏回执：

```powershell
python scripts/verify_private_portfolio_input.py `
  --encrypted <private-root>\inputs\portfolio.viportfolio `
  --key-file <key-outside-private-root>\portfolio.key `
  --private-root <private-root> `
  --forbidden-sync-root C:\Users\we\WPSDrive
```

该命令不会输出解密后的资产、持仓或 IPS 内容。

## 尚未实现

- 私有数据的长期持久化/轮换/恢复运营流程和真实账户导入；
- 原 Excel 的 M4 展示页。

## 2026-09-24 输入完整性收紧

- JSON boolean 字段不再经过 `bool()` 的宽松转换；字符串 `"false"` 直接失败关闭。
- 组合及嵌套持仓/证据对象递归拒绝执行字段。
- 仓位指引要求每个已对账持仓都有证券风险属性；缺失时保持 `INCOMPLETE`，不把未知
  持仓的行业和周期暴露当成零。
- 指引日期不得早于 IPS、快照或 tier policy。

本轮 M4 合同、风险、仓位、股息和展示联合定向回归为 `59 passed`，仍全部为
`action=no_order`。

`PortfolioRiskAssessment`、`PositionGuidance` 和 `DividendIncomeProjection` 已在
同日后续批次完成；真实个人化风险、仓位和收入报告仍需用户确认 IPS 与持仓后生成。

非个人化工程审计及待用户输入清单见
[M4 非个人化工程审计](m4-nonpersonal-engineering-audit-20260925.md)。

这些项目只在 M3 人工决策链稳定且用户提供真实 IPS/持仓后继续，本轮不提前构造
个人化结论。

## 验证

- `tests/test_portfolio_contracts.py`：7 passed。
- 测试覆盖缺失关闭、非法金额/百分比、重复持仓、未对账/模拟快照、往返、
  账户范围不匹配和时点顺序。
