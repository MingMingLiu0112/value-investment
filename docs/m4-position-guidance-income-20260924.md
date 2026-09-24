# M4 分层仓位与股息收入投影：2026-09-24

更新：2026-09-24。本文记录 M4 非个人化 `PositionGuidance` 与
`DividendIncomeProjection` 的第一批离线工程。所有输入均为显式模拟，不读取真实
账户、IPS、现金或持仓；所有动作保持 `action=no_order`。M2 当前为
`PENDING_HUMAN_REVIEW`，M3、M4 均仍为 `PARTIAL`。

## 已实现

- `src/value_investment_agent/position_guidance.py`
  - `PositionTierPolicy`：人工确认的 Starter/Normal/Max 上限，不使用通用 20%；
    上限必须满足 Starter <= Normal <= Max <= IPS 单股上限。
  - `PositionCandidateInput`：研究、人工批准、事件复核、模型、价格、反证和
    流动性前置条件；`BUY_REVIEW` / `ADD_REVIEW` 必须强绑定同向 M3
    `InvestmentDecisionReview`，不能只靠重建布尔前置绕过真实决策制品。
  - `PositionGuidanceLine`：只输出分层上限、当前权重、剩余上限空间、共同预算
    状态、停止加仓条件和减仓复核触发，不输出目标仓位或订单。
  - `PositionGuidanceResult`：组合共同预算、保留现金、行业/周期限制和候选间
    预算冲突；全现金且无候选是合法状态。
- `src/value_investment_agent/dividend_income_projection.py`
  - `DividendIncomeObservation`：已到账、已宣告、Forward、Normalized 四种口径；
    普通与特别分红分别保存，特别分红禁止进入 Forward/Normalized。
  - `DividendTaxTreatment`：已有完整批次日期时调用既定税费计算，未结算时显式
    保持 `UNKNOWN_PENDING_DISPOSAL`，不虚构净收入。
  - `SecurityDividendIncomeProjection` 与 `PortfolioDividendIncomeProjection`：
    组合口径总额、税费状态和年度股息目标差额，缺失口径仍为 PARTIAL。
- 独立模拟 Excel 候选：`A股价值投资_M4仓位与股息候选_20260924.xlsx`
  - 5 页：`00_总览`、`01_仓位分层`、`02_共同预算`、
    `03_股息收入`、`04_输入与边界`。
  - 候选文件 11,504 字节，SHA-256
    `764f8d201dfc798012a6e27f9080d927d2b6f7b0ada6bb53bf947c6a5ff2e45e`。
- 2026-09-24 M4 Decision Binding v2 候选：
  `A股价值投资_M4仓位与股息候选_v2_20260924.xlsx`
  - 与 v1 相同的 5 页展示和模拟边界，正向候选改为显式 M3 binding。
  - 候选文件 11,552 字节，SHA-256
    `2f17b4926d8634fd45c8a57335b99b477aa6c9559616e6bd5053dbb506e9a037`。
  - WPS 云盘同名副本逐字节一致，WPS 只读验证 `passed`。

## 风险与预算口径

- 仓位上限是 IPS/分层政策给出的边界，不是自动分配；多个候选的总剩余上限超过
  可用预算时统一标记 `BUDGET_CONFLICT`，系统不替用户选择谁获得预算。
- 当前权重已经达到或超过分层上限时只停止继续加仓并提示减仓复核，不生成减仓
  指令。
- 行业与周期暴露使用已确认持仓计算；受限或未知流动性要求人工复核，不给出
  数值空间。
- 已到账股息只在批次取得、登记和处置结算日期完整时计算税费；已宣告、Forward
  与 Normalized 的净额在未结算前保持未知。
- 普通和特别分红不合并，特别分红不自动年化；目标差额按四种口径分别显示。

## 尚未实现

- 私有账户/IPS/持仓的持久化、加密备份和真实导入；
- 原 55 页生产工作簿中的 M4 页面集成；
- M5 事件驱动失效、有界重算和通知恢复；
- 真实组合对账和用户确认后的个人化仓位/收入报告。

这些项目继续按总Goal推进；真实 IPS/持仓仍由用户确认后提供，系统不猜测风险
偏好、不默认 20% 仓位，也不生成订单。

## 验证

2026-09-24 人工审查后，M4 正向容量层新增以下反例：

- 未绑定 BUY / ADD 候选直接拒绝；
- BUY 绑定 ADD 状态、ADD 绑定 BUY 状态均拒绝；
- 正向 intent 使用非 `RESEARCH_ATTRACTIVE` 价格状态拒绝；
- HOLD 仍可无绑定展示，但不能产生新增容量。

定向回归 `51 passed`；仓库内隔离 basetemp 全量离线回归
`2369 passed、6 skipped、0 failed、18 warnings`。

- M4 合同/风险/仓位/股息/工作簿联合定向回归：36 passed。
- 新增领域定向回归：`test_position_guidance.py` 11 passed、
  `test_dividend_income_projection.py` 7 passed、
  `test_m4_guidance_income_workbook.py` 2 passed。
- WPS 只读收据：
  `runtime/m4-guidance-income-wps-20260924/receipt.json`，`passed`。
- WPS 云盘同名副本与仓库候选逐字节一致。
- 未修改原 55 页生产工作簿，未读取真实账户、现金、IPS、持仓或交易记录。
