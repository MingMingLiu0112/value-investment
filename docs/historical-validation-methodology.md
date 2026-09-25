# Historical Validation Methodology

更新：2026-09-25。本文定义历史验证的准入语义，不新增收益目标，不替代研究、估值或人工交易决策。

## 1. 结论级别

历史 replay 只能落入以下三类之一：

| 分类 | 含义 | 允许的结论 |
| --- | --- | --- |
| `STRICT_CONTEMPORANEOUS_REPLAY` | 决策时可知的事实、假设、估值、报价、公司行动、费用、执行、组合、基准和 Universe 均可证明 PIT；规则版本也必须在决策日之前已登记 | 可以在明确 ResearchCase 范围内讨论策略重放结果 |
| `RETROSPECTIVE_POLICY_REPLAY` | 数据/执行链足以复算，但规则版本是事后注册的追溯扩展 | 只能检验政策逻辑和反例，不得写成 VALIDATED STRATEGY BACKTEST |
| `NOT_PIT_SAFE` | 任一决策关键维度无法证明，或 approved historical value model sessions 为零 | 不运行历史绩效；保留阻断原因和重开条件 |

“工程测试通过”、“脚本可复现”、“没有未来数据报错”都不等于 strict PIT。`NOT_PIT_SAFE` 是合法且必须保留的结果。

## 2. 决策时钟和信息截止点

- 决策时点是每个 SSE/交易所session收盘后；具体日期和时区写入 admission。
- 每条 Fact、公告、quote、benchmark level、assumption 和规则版本必须有 `available_at <= decision_at`。
- 只有日期精度时，使用中国标准时间下一日零点作为 exclusive upper bound；不得把抓取时间当历史可用时间。
- 晚到数据、更正、重新修订行情和后来注册的模型不能倒灌历史决策。
- 未来价格只能由执行账本在冻结决策之后使用，不能进入同一 session 的决策输入。

## 3. 必须分开的 PIT 维度

1. `facts_pit`：经营、现金流、资产负债表和股本事实的范围、单位和来源。
2. `assumptions_pit`：WACC、增长、税率、正常化利润等假设的版本和可用时间。
3. `valuation_pit`：当时可复算的 approved value model；conditional range 不能冒充正式估值。
4. `quote_pit`：未复权价格、交易状态和修订版本；晚抓取不自动获得历史版本证明。
5. `corporate_actions_pit`：登记日、除权日、派款日、送转上市日、税费和股本分母。
6. `fees_pit`：按实际成交日适用的印花税、过户费和明确声明的佣金场景。
7. `execution_contract`：信号后下一session开盘、T+1、100 股手数、现金约束、停牌、涨跌停、流动性和公司行动处理。
8. `portfolio_context`：冻结的初始现金、持仓、批次和容量边界；不得把私人组合写入公开仓库。
9. `benchmark_contract`：同期全收益指数的版本、口径、货币、除息和现金对齐。
10. `universe_pit`：当时已知的证券集合、纳入/剔除规则和 survivorship 处理。

任何维度无法证明时写 `UNSUPPORTED` 或 `NOT_PROVEN`，不得用缺少字段的默认值、0、今日模型或事后最优参数补齐。费用/执行可以使用有界的 `CONSERVATIVE`，但必须写明保守方向和证据。

## 4. 执行现实性

现有 `VirtualAccount` 是研究账本，不是券商账户：它按下一session开盘成交，执行 T+1、现金预算、100 股手数、停牌/执行状态门、除权除息、应收股利、送转锁定和去重。它不证明真实排队、分笔成交、申报限制或大额容量。

费用必须按成交日而非信号日计算。2015-08 之前沪市过户费的成交面额和券商留存部分没有完整依据时，early-SSE 成交保持 `UNSUPPORTED`，不能用当前费率或零费用替代。股息不能与复权价格重复计入；税率、未售批次和处置日也必须显式。

## 5. Walk-forward 和过拟合

Walk-forward 只有在 admission 不是 `NOT_PIT_SAFE` 且每个评分 session 都有可复算 approved value model 时才能运行。训练、验证和 sealed-test 分段必须在观察结果之前登记；参数不得用验证集或 sealed-test 调整。

可以记录 `NOT_RUN`，但不得伪造 folds、收益、回撤或基准差。回放成功、回测收益和历史排名都只描述过去；它们不是未来收益、买入信号、仓位授权或生产授权。

## 6. 最低复算材料

每次 admission 至少保留：

```text
HistoricalValidationAdmission
immutable input manifest
walk-forward result 或明确的 NOT_RUN
machine-readable receipt
user-readable status report
```

所有文件保留 SHA-256、窗口、信息截止点、规则版本、证据引用、阻断原因和 `action=no_order`。
