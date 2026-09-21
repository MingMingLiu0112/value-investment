# 外部数据阻塞处理政策

生效日期：2026-09-21。适用范围：价值投资 Agent 的开发、测试、Excel 发布和当前研究验证。

## 核心原则

区分工程是否能继续与当前投资研究结论是否能更新。投资结论在数据不充分时 fail-closed；工程开发不得因为尚未收盘、第三方接口暂不可用、未来披露尚未出现而停止。

外部等待不是默认 `BLOCKED`。生产数据尚未形成时，使用 `PENDING_EXTERNAL_DATA`；只有输入定义、会计口径、模型数学、业务规则或数据结构本身无法正确确定，或已有数据存在无法解释的重大冲突时，才阻塞对应模块，且不得默认阻塞整个项目。

## 双状态记录

每个实时数据模块独立记录：

| Engineering Status | 含义 |
| --- | --- |
| `NOT_STARTED` / `IN_PROGRESS` / `READY` / `FAILED` | 代码、接口、历史 Snapshot 测试、异常测试和 Excel/下游接入的工程状态 |

| Current Data Status | 含义 |
| --- | --- |
| `READY` / `PENDING_EXTERNAL_DATA` / `STALE` / `CONFLICT` / `INVALID` / `UNAVAILABLE` | 当前生产数据能否支持最新研究判断 |

允许且常见的状态是 `Engineering Status = READY`、`Current Data Status = PENDING_EXTERNAL_DATA`。它不能被描述成项目停滞。

## 开发与生产验证流程

真实当前数据缺失时，依次：

1. 当前研究结论保持 fail-closed；不得伪造、估算或将旧日/盘中数据表述为今日正式收盘数据。
2. 标记 `PENDING_EXTERNAL_DATA`，说明等待的来源、受影响结论和生产验证解除条件。
3. 使用最近已验证、已封存的真实 Snapshot，以及固定 Fixture，完成模型、JSON、Excel、集成和异常分支测试。
4. 完成所有不依赖当前数据的最高优先任务，不因未来自然时间反复轮询或重新开发已完成模块。
5. 数据形成后，仅执行 Current / Production Validation，并记录其结果。

所有实时里程碑必须拆成 Engineering Implementation、Snapshot Validation、Production Validation。前两项不得等待当日市场自然形成；只有最后一项可以是 `PENDING_EXTERNAL_DATA`。

## 估值与价格桥接

估值不得主动请求实时行情，结构固定为：

```text
FinancialFacts -> ValuationModel -> ValuationResult
                                      |
ModelValidity + QuoteSnapshot -> PriceBridge -> CurrentResearchStatus
```

`ValuationResult` 与 `PriceBridge` 分开保存。行情未形成时保留已验证的估值结果，价格桥接显示 `PENDING_EXTERNAL_DATA`，Excel 显示等待原因与上一有效行情/研究状态，不清空历史研究。

研究级价格桥接不以 `model_date == quote_date` 作为唯一合法条件；必须通过 `ModelValidity` 判断：`model_as_of`、`valid_from`、`last_material_event_check`、资本结构是否变化、是否发现重大事件和状态。未出现影响价值的重要财报、资本结构、收购/处置或其他重大事项时，可在有效窗口内桥接后续报价；重大事件使模型 `STALE` 并触发重估。

这不放宽模拟订单或 Paper Eligibility 的版本化事实、模型、报价及下一会话执行要求。研究级价格桥接、模拟准入和真实交易始终分层。

## Codex 强制动作与汇报

遇到外部数据等待时，必须先判定工程阻塞还是生产数据等待；后者必须寻找最近有效 Snapshot，完成可独立推进的工程、测试和 Excel/JSON 接入，并登记待做的 Production Validation。汇报统一包含：

```text
Engineering Status:
Current Data Status:
已完成:
等待的外部数据:
下一项不依赖外部数据的任务:
```

不得只汇报“目标阻塞，等待外部数据”。
