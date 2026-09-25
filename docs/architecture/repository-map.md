# Repository Map

更新：2026-09-25。此表用于快速定位，不是权限边界。完整合同见
[repository-architecture.md](repository-architecture.md) 和 [architecture.md](../architecture.md)。

| Module / Area | Layer | Status | Public Entry | Replacement / Note |
| --- | --- | --- | --- | --- |
| `src/value_investment_agent/research_*` | Research Domain / Application | Active | CLI / replay scripts | 逐步拆到 `domain/research`、`application/research` |
| `src/value_investment_agent/valuation*`、`price_bridge.py`、`model_validity.py` | Valuation Domain | Active | Application | 公式冻结，只做边界迁移 |
| `src/value_investment_agent/investment_decision.py` | Decision Domain | Active | Decision application / workbook | 暂缓拆分，先确认职责 |
| `src/value_investment_agent/m3_*` | Decision Application / Presentation | Active | M3 scripts | Presentation adapter 与 domain 分开 |
| `src/value_investment_agent/portfolio_*`、`position_guidance.py` | Portfolio Domain | Active | private/synthetic application | 私人数据不得入库或公开 |
| `src/value_investment_agent/m5_*` | Event Domain / Application / Operations | Active | M5 scripts | 事件事实、材料性、运营编排分层 |
| `src/value_investment_agent/m6_*` | Operations | Active offline only | M6 preflight/control CLI | 生产授权仍未授予 |
| `src/value_investment_agent/m7_daily_workbench.py` | Presentation / Operations | Active candidate | M7 trial pointer | 只读候选，不是正式原表 |
| `src/value_investment_agent/historical_validation.py` | Historical Validation Domain | Provenance-frozen | admission scripts | receipt-bound byte-for-byte；不得移动或改写 |
| `src/value_investment_agent/application/historical_validation/` | Historical Validation Application | Active | `scripts/audit_historical_validation_receipt.py` | 只读 receipt audit；不替代冻结的 admission contract |
| `src/value_investment_agent/db.py` | Infrastructure / Database | Active | CLI / application | PostgreSQL 结构化事实底座 |
| `src/value_investment_agent/backup*.py`、`m6_*recovery*` | Infrastructure / Operations | Active offline | ops scripts | 真实恢复演练仍需隔离环境 |
| `src/value_investment_agent/excel_report.py`、`workbook_simple_overview.py` | Presentation / Excel | Legacy active | publication scripts | 新代码使用 Product Read Model |
| `scripts/*.py` | Tooling | Mixed | CLI | 新脚本只做 parse/load/invoke/print/exit |
| `config/` | Configuration / Pointers | Active | scripts / tests | 一个职责一个 current pointer |
| `runtime/` | Local evidence / candidates | Ignored | config pointers | 不把运行时目录当源码层 |
| `docs/` | Governance / Methodology / History | Mixed | docs index / current files | 逐步分为 current/architecture/operations/archive |
| `tests/` | Verification | Active | pytest / CI | 新测试按目标层逐步落位 |

## Current Entries

```text
User-facing formal workbook: WORKBOOK_PATH
M7 read-only trial pointer: config/current-trial-workbook.json
Current goal: docs/current-stage-goal.md
Current execution status: docs/execution-status.md
Permanent boundaries: AGENTS.md
Architecture inventory: docs/architecture/repository-architecture.md
```

## Known Migration Risks

```text
hash- and path-bound receipts
runtime pointer paths
Excel candidate filenames embedded in tests/scripts
Windows and Linux path differences
legacy root imports
company-specific scripts that still import core modules
```

迁移前必须对目标文件执行 `git grep`、manifest/receipt 搜索和对应测试；任何被 receipt 以原路径
绑定的文件不能直接移动。
