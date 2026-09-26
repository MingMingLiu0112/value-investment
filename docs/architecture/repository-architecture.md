# Repository Architecture Inventory

更新：2026-09-26。本文是架构治理的事实清单和迁移方向，不是新的业务 Roadmap，也不改变
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
root *.xlsx                    = 29
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
| Domain / Research | `domain/research/gap_classification.py`、`research_profile.py`、`research_case.py`、`research_run_contract.py`、`human_research_approval.py`、`research_gate.py`；旧根路径为 shim；`fixed_sample_*` 仍待迁移 | 从纯规则、低消费者模块开始，旧路径保留兼容 shim |
| Domain / Valuation | `domain/valuation/confidence.py`，旧路径为 shim；`valuation_router.py`, `valuation_assumptions.py`, `price_bridge.py`, `model_validity.py` 仍待迁移 | 保留公式和行为，先迁纯规则，不修改模型 |
| Domain / Decision | `investment_decision.py`, `decision_read_model.py`, `pre_decision_eligibility.py` | 大文件先不拆，确认职责后再拆 |
| Domain / Portfolio | `portfolio_contracts.py`, `portfolio_risk.py`, `position_guidance.py`, `dividend_income_projection.py` | 私人数据边界保持不变 |
| Domain / Events | `event_materiality.py`, `m5_event_*.py` | 事件合同与运营编排分开 |
| Domain / Historical Validation | `historical_validation.py` 由冻结 receipt 按原路径和 SHA-256 绑定 | provenance-frozen，不移动、不改写；新的只读校验用例进入 `application/historical_validation/` |
| Application | `research_application.py`, `research_batch.py`, `research_e2e_replay.py` | 作为应用编排，不导入 Excel/DB 业务实现 |
| Infrastructure | `infrastructure/filings/pdf_text.py`、`infrastructure/evidence/evidence_tiering.py`、`infrastructure/backup/backup_snapshot.py`；`db.py`、`disclosures.py`、`market.py` 仍待迁移 | 保持 I/O、持久化、外部数据和密钥边界 |
| Presentation | `presentation/excel/product_workbench.py`、`presentation/read_models/product_workbench.py`、`presentation/read_models/research_read_model.py`；`excel_report.py`、`workbook_simple_overview.py` 仍为核心 legacy 实现 | 只消费 Product Read Model / typed result，不重算投资结论；M7 五页用户界面不得展示 M2-M6 导航或执行语义 |
| Operations | `operations/authorization/m6_authorization_artifacts.py`；其余 `m6_*.py` 仍待迁移 | M6 运行控制、M7 展示发布分开 |
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

M7 用户产品面固定为五页：

```text
今日 / 机会 / 公司 / 我的组合 / 事件
```

`系统/审计` 只作为次级页面。M2-M6 是后台阶段，不得成为用户导航。Product Read Model
必须由 Application 层把已决定的 M2-M6 输出映射成用户语言；Presentation 层不得读取多个
runtime manifest 后自行拼装、重算或升级投资状态。没有真实私人组合时，候选工作簿只能显示
“尚未接入真实组合”，不得把 M4 模拟数字当作个人结论。

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
RECEIPT_AUDIT_APPLICATION_MIGRATION = historical_validation
HISTORICAL_VALIDATION_DOMAIN_MIGRATION = BLOCKED_BY_FROZEN_RECEIPT_HASH
FIRST_SAFE_DOMAIN_MIGRATION = gap_classification + research_profile
SECOND_SAFE_DOMAIN_MIGRATION = valuation_confidence
ROOT_ARTIFACT_CLUTTER = LOGICALLY_REDUCED
ROOT_ARTIFACT_PHYSICAL_BATCH_2 = NO_SAFE_MOVE
CURRENT_ARTIFACT_ENTRY = config/current-trial-workbook.json
DOCS_CURRENT_ENTRY = FUNCTIONAL
DOCS_CURRENT_VS_ARCHIVE = OPERATIONALLY_CLEAR
SCRIPT_INVENTORY = COMPLETE
CURRENT_SUPPORTED_CLIS = 51 (15 product + 36 engineering; all 43 v1 paths preserved)
M7_PRODUCT_READ_MODEL = READY
M7_PRODUCT_UX_CANDIDATE = READY (runtime candidate; canonical pointer unchanged)
ADV_P1_003_004 = CLOSED_WITH_TRUST_ROOT_RESIDUAL
M4_SYNTHETIC_ONBOARDING_REHEARSAL = COMPLETED
SCRIPT_ROOT_PYTHON_BASELINE = 528
PRESENTATION_DIRECTORY = ACTIVE
OPERATIONS_DIRECTORY = ACTIVE
INFRASTRUCTURE_DIRECTORY = ACTIVE
COMPATIBILITY_SHIMS = REGISTERED
COMPANY_SPECIFIC_TOOLING = CLASSIFIED
NEW_CODE_ROOT_GROWTH = BLOCKED
CORE_BEHAVIOR_CHANGED = false
action = no_order
```

Phase 2 的根 artifact 审计结论是：当前 58 个根 artifact 均被 canonical、pointer、
manifest、receipt、静态消费者或未跟踪本地证据绑定，因此没有可证明安全的物理移动批次。
当前通过 `artifacts/current/artifact-registry-v1.json` 提供逻辑导航，而不是为了降低目录数量
破坏 Hash 证据。物理根工作簿仍为 29 个。

当前脚本分类入口为 `config/current-cli-entrypoints-v2.json`（15 个产品入口、36 个工程入口，
51 个唯一路径；v1 的 43 个路径保留兼容）和 `docs/architecture/script-inventory-v1.json`
（完整机器可读清单）。`config/current-cli-entrypoints-v1.json` 继续作为兼容哈希基线，不新增
v1 条目。`scripts/` 根层默认不再
增长，诊断、历史验证和公司 case 开始进入明确子目录；旧实现通过已登记 shim 保留路径兼容。

`src/value_investment_agent/historical_validation.py` 不是普通的 legacy module。现有历史验证
receipt 将路径 `src/value_investment_agent/historical_validation.py` 和 SHA-256
`806d890817611000a588c9ee76ee00cc18a2529d5e1ee9769c092cc00452c5ba` 一起纳入不可变
input manifest。将该文件改成 shim 会使旧 receipt 无法复验。因此它必须保持原字节，任何
新行为必须通过新的 v2 admission/receipt 链建立，而不是原地迁移。

每批迁移必须满足：

```text
INCREMENTAL_REFACTOR_ONLY
BEHAVIOR_PRESERVING
TEST_GATED
ROLLBACKABLE
```

禁止把重构与估值公式、投资门槛、数据库 schema 语义或决策状态修改混在同一提交。
