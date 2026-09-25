# 600519 Historical Validation Current Status

更新：2026-09-25。本文件记录第一案例的实际 admission 结论，不把历史研究实验写成正式回测。

## 结论

```text
SYMBOL = 600519
WINDOW = 2015-01-05 .. 2015-01-30 (preregistered 20-session window)
CLASSIFICATION = NOT_PIT_SAFE
ADMISSION_STATUS = NOT_ADMITTED
APPROVED_VALUE_MODEL_SESSIONS = 0
RULE_REGISTRATION = RETROSPECTIVE_RESEARCH_EXTENSION
WALK_FORWARD = NOT_RUN
action = no_order
```

严格 `STRICT_CONTEMPORANEOUS_REPLAY` 不能成立。当前仓库可以复现一个事后登记的 experimental DCF/range experiment，但这不是当时规则的同期重放，也没有 approved historical value model。

## 已确认的证据

- 20-session 窗口在观察结果之前登记，并绑定了 `cninfo:63720184` 的年度输入。
- 2013 年度输入的 `available_at` 早于窗口第一日；窗口内没有已审现金行动。
- 全历史 admission audit 覆盖 2,674 个 session，`approved_sessions=0`。
- 官方全收益指数在中证来源中存在历史点位，但历史版本/修订和现金/费用口径未获 PIT 证明。
- `VirtualAccount` 已实现下一session开盘、T+1、100 股、现金、分红/送转和日期费用的研究账本机制。
- 现有 2015-2025 range experiment 明确 `strategy_backtest_complete=false`、`simulation_eligible=false`、`trade_approved=false`。

## 当前阻断

| 维度 | 状态 | 原因 |
| --- | --- | --- |
| Facts | `UNSUPPORTED` | 2012 comparative NWC 的 notes payable 等模型必需事实未闭合 |
| Assumptions | `UNSUPPORTED` | 没有当时批准的假设集 |
| Valuation | `UNSUPPORTED` | approved historical value model sessions 为 0 |
| Quote | `UNSUPPORTED` | 历史行情的修订/版本 PIT 未证明 |
| Corporate actions | `UNSUPPORTED` | 投资者税费、权益确认和股本分母桥未闭合 |
| Fees | `UNSUPPORTED` | 2015-08 前沪市费用基础不完整 |
| Execution | `UNSUPPORTED` | 日线无法证明排队、容量、停牌和涨跌停实际成交 |
| Portfolio | `UNSUPPORTED` | 没有冻结的历史组合上下文 |
| Benchmark | `UNSUPPORTED` | 历史版本和 total-return/现金/税费口径未对齐 |
| Universe | `UNSUPPORTED` | 单一事后选择证券，survivorship 未控制 |

## 现有实验的准确名称

`runtime/strategy-validation/moutai-historical-range-experiment-*` 可以称为：

```text
RETROSPECTIVE_RESEARCH_RANGE_EXPERIMENT
```

不能称为：

```text
VALIDATED STRATEGY BACKTEST
REAL HISTORICAL PERFORMANCE
BUY SIGNAL
PRODUCTION AUTHORIZATION
```

## 重开条件

只有出现以下全部或足以消除对应阻断的替代证据，才重新运行 admission：

1. 决策日之前可独立核验的规则登记证据；
2. approved historical value model 和 assumption set；
3. 修订安全的行情、公司行动、税费、执行和基准链；
4. 可审计的 PIT Universe/selection rule 和 survivorship 处理；
5. 冻结的研究组合上下文；
6. 所有输出仍保持 `action=no_order`。

在此之前，范围继续限定为工程合同、反例和证据审计，不发布策略绩效结论。
