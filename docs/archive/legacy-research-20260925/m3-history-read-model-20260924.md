# M3 论点连续性历史链只读模型：2026-09-24

更新：2026-09-24。本文记录 M3 历史链的第一批公开离线工程。本批只使用显式
`simulated` 数据，不读取真实账户、IPS、持仓或真实 Entry；所有动作保持
`action=no_order`。M2、M3、M4 均仍为 `PARTIAL`。

## 已实现

- `src/value_investment_agent/m3_history_read_model.py`
  - `EntryThesisCard`：冻结原始论点、回报来源、预期差、三情景、风险、
    Breaker、加/减/退出条件及事后重建标记。
  - `DecisionJournalLine`：按时间保存人工决定、系统原因、人工原因、确认价
    和更正前驱。
  - `ConsistencyReviewCard`：逐维度比较 Original 与 Current，区分未变化、
    加强、削弱、兑现和破坏。
  - `DecisionHistoryChain`：校验证券、Entry、日志前驱和一致性引用；公开链
    只接受 `simulated`。同链日志与一致性 ID 必须唯一，Journal 的 Entry 引用
    必须指向冻结 Entry。更正前任必须存在、时间必须严格晚于前任；日志不得
    早于 Entry 确认时间，一致性复核不得早于 Entry 日期。
- `src/value_investment_agent/investment_decision.py`
  - `DecisionJournalEntry` 对人工确认决定和复核状态做同向绑定，非交易决定
    不能携带确认价。
- `src/value_investment_agent/m3_history_workbook.py`
  - 5 页独立候选：`00_历史链`、`01_原Entry`、`02_决策日志`、
    `03_一致性复核`、`04_来源哈希`。
  - 不显示目标仓位、仓位大小或订单指令；不覆盖已有文件。
- `scripts/build_m3_history_candidate.py`
  - 从 `tests/fixtures/m3_history_demo.json` 构建确定性模拟候选和 manifest。

## 安全边界

- 公开工作簿拒绝非模拟命名空间，避免误把真实账户记录提交到公开仓库。
- Entry、Journal、Consistency 每条输入均绑定不可变 SHA-256。
- 本批没有修改 WPS 原 55 页生产工作簿，也未把模拟链标记为真实成交。
- 示例链路中的买入、持有、减仓只演示理由链形态，不代表任何投资建议。

## 验证

- 定向回归：4 passed。
- M3 日志链完整性反向回归：5 passed；新增重复 ID、错 Entry、乱序更正与
  决定/状态矛盾四类。
- M3 历史链时序反向回归：新增同时间戳更正、日志早于 Entry、一致性复核早于
  Entry 日期三类；相关 M3 定向回归 `86 passed`（含 `test_decision_read_model`
  与发布层替换回归）。
- M3/M4 相关定向回归：40 passed。
- 示例候选：5 页、1 条模拟链、`action=no_order`，字节数 12,121。
- 候选 SHA-256：
  `5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0`。
- WPS 只读打开、页序、公式错误、历史行数和 `no_order` 检查通过，收据
  `runtime/m3-history-wps-20260924/receipt.json` 为 `passed`。
- WPS 云盘同名副本与本仓库候选逐字节一致。

## 尚未完成

- 真实 Entry 的确认、实际账户命名空间和真实历史链仍需用户输入。
- Checkpoint B 的用户理解验收不能由本工具代理。
- 历史链尚未并入原生产工作簿 `00_决策复核`。
