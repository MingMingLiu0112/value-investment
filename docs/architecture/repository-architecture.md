# Repository Architecture Inventory

更新：2026-09-25。本文是架构治理的事实清单和迁移方向，不是新的业务 Roadmap，也不改变
任何估值、研究门槛、数据库语义或 `action=no_order`。

## 当前基线

当前包名保持不变：

```text
src/value_investment_agent/
```

盘点时约有：

```text
src/value_investment_agent/*.py = 199
scripts/*                      = 546
tests/*.py                     = 455
docs/*                         = 191
root *.xlsx                    = 35
```

这不是“文件数量必须下降”的目标，而是说明根层职责已经过度集中。当前冻结的正式入口仍是：

```text
README.md
config/current-trial-workbook.json
WORKBOOK_PATH 指向的 WPS 正式工作簿
```

M7 只读试用候选由 `config/current-trial-workbook.json` 固定；正式 WPS 工作簿仍在用户
配置路径。两者都没有被本次架构治理替换。

## 目标分层

以下是逐步收敛方向，不要求一次性移动全部旧文件：

```text
src/value_investment_agent/
  domain/
    research/
    valuation/
    decision/
    portfolio/
    events/
    market/
    historical_validation/

  application/
    discovery/
    research/
    decision/
    portfolio/
    monitoring/
    historical_validation/

  infrastructure/
    database/
    evidence/
    market_data/
    filings/
    backup/
    security/

  presentation/
    excel/
    read_models/

  operations/
    shadow/
    recovery/
    health/
    authorization/
```

依赖方向：

```text
Domain <- Application <- Presentation / Operations / Scripts
Application -> Infrastructure interfaces / adapters

Domain must not import:
  presentation, operations, scripts, Excel, network clients, database drivers, test fixtures
```

现有根层模块通过 compatibility shim 渐进迁移，不进行一次性大搬家。旧 import 路径可以短期
保留，但新代码必须写入目标层；shim 只转发，不复制业务逻辑。

## 当前职责归类

| 层 | 当前代表模块 | 迁移策略 |
| --- | --- | --- |
| Domain / Research | `research_gate.py`, `research_case.py`, `research_profile.py`, `fixed_sample_*` | 逐步移入 `domain/research/`，先迁移消费者少的新模块 |
| Domain / Valuation | `valuation_router.py`, `valuation_assumptions.py`, `price_bridge.py`, `model_validity.py` | 保留公式和行为，先建边界，不修改模型 |
| Domain / Decision | `investment_decision.py`, `decision_read_model.py`, `pre_decision_eligibility.py` | 大文件先不拆，确认职责后再拆 |
| Domain / Portfolio | `portfolio_contracts.py`, `portfolio_risk.py`, `position_guidance.py`, `dividend_income_projection.py` | 私人数据边界保持不变 |
| Domain / Events | `event_materiality.py`, `m5_event_*.py` | 事件合同与运营编排分开 |
| Domain / Historical Validation | `domain/historical_validation/admission.py`；旧 `historical_validation.py` 为 shim | 已开始边界迁移，统一 admission/PIT/replay 边界 |
| Application | `research_application.py`, `research_batch.py`, `research_e2e_replay.py` | 作为应用编排，不导入 Excel/DB 业务实现 |
| Infrastructure | `db.py`, `disclosures.py`, `market.py`, `backup*.py`, `private_portfolio_intake.py` | 保持 I/O、持久化、外部数据和密钥边界 |
| Presentation | `excel_report.py`, `workbook_simple_overview.py`, `*_workbook.py` | 只消费 Product Read Model / typed result，不重算投资结论 |
| Operations | `m6_*.py`, `m7_daily_workbench.py` 的发布入口 | M6 运行控制、M7 展示发布分开 |
| Compatibility / Legacy | 根层旧模块和 `scripts/*` wrapper | 只保留迁移期 shim，不再增长 |

## 公司特定代码边界

公司代码不得进入核心 Domain 分支。`moutai`、`600519`、`midea`、`000333`、`shenhua`、
`601088`、`gree`、`yili`、`huayu` 等名称可以出现在：

```text
research case evidence
issuer-specific parser / adapter
historical replay input
one-off research tool
Human review packet
```

不得出现在：

```text
通用 ResearchProfile / ValuationRouter / PriceBridge / Portfolio 决策分支
```

需要继续扫描 `if symbol == ...`、symbol allowlist 和公司名硬编码；合法 issuer adapter 必须
有明确接口、证据输入和退出计划。

## Historical Validation 边界

历史验证统一围绕以下职责收敛：

```text
HistoricalValidationAdmission
ProcessReplay
DecisionReplay
PortfolioReplay
WalkForward
ExecutionModel
```

公司历史脚本只提供 case input / evidence adapter，不应复制 replay engine。第一案例当前仍是：

```text
600519 = NOT_PIT_SAFE / NOT_ADMITTED
approved_value_model_sessions = 0
walk_forward = NOT_RUN
action = no_order
```

## Presentation 边界

Excel 和未来 Web 必须消费同一个 Product Read Model：

```text
Domain -> Application -> Product Read Model -> Excel Renderer / Future Web
```

Excel renderer 不重新做：

```text
投资判断
估值计算
材料性判断
组合判断
目标仓位计算
```

## Artifact 边界

目标目录：

```text
artifacts/
  current/
  archive/
```

规则：

```text
canonical workbook / current pointer / receipt-bound artifact 不得为目录美观而移动
可重复生成且无签收价值的 candidate 可归档或删除
历史 research / review / incident 证据优先 archive
```

当前正式工作簿仍由 `WORKBOOK_PATH` 和 `config/current-trial-workbook.json` 定位；在迁移完成
前，不建立第二个互相竞争的正式入口。

## 迁移状态

```text
TARGET_ARCHITECTURE_DEFINED = true
NEW_CODE_PLACEMENT_RULES = ACTIVE
FIRST_DOMAIN_MIGRATION = historical_validation
ROOT_ARTIFACT_CLUTTER = INVENTORY_IN_PROGRESS
CURRENT_ARTIFACT_ENTRY = config/current-trial-workbook.json
DOCS_CURRENT_VS_ARCHIVE = INVENTORY_IN_PROGRESS
CORE_BEHAVIOR_CHANGED = false
action = no_order
```

每批迁移必须满足：

```text
INCREMENTAL_REFACTOR_ONLY
BEHAVIOR_PRESERVING
TEST_GATED
ROLLBACKABLE
```

禁止把重构与估值公式、投资门槛、数据库 schema 语义或决策状态修改混在同一提交。
