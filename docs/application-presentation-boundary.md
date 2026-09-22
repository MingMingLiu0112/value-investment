# Application / Presentation Boundary Review

更新：2026-09-22。范围：C3 W11。结论：`PASSED_WITH_RECORDED_TECH_DEBT`。

## 结论

新 Application 层已经产生独立 typed result 与 JSON 收据，Domain 和 Application 不依赖 Excel、PostgreSQL schema 或单元格业务逻辑。现有 Excel publisher 仍是旧 runtime JSON 展示层，尚未切换到新 Application 输出；这记录为技术债，不在本轮重写。

## 依赖证据

### Domain / Application

- `src/value_investment_agent/research_artifacts.py` 明确不导入 database、HTTP 或 Excel。
- `research_application.py`、`research_batch.py`、`research_e2e_replay.py` 不导入 `openpyxl`、`psycopg` 或旧 `valuation_results` schema。
- `research_application.py` 输出 `CompanyResearchRunOutcome`，其中 route、gate、valuation、model validity、price bridge、distribution 和 current status 都是 typed domain 对象。
- `ThreeCompanyReplayResult.as_policy()` 输出独立 JSON；`scripts/run_three_company_research_replay.py` 已验证可生成 193KB 可审计收据，顶层固定为 `no_order`。

### Presentation

- `excel_report.py` 与 `workbook_simple_overview.py` 不导入 `psycopg`、`valuation_models` 或 `research_artifact_repository`。
- 它们读取 pinned runtime evidence 和 display 合同，只承担展示；模型数值和数据库持久化仍在 Application/Domain 边界以内。
- 现有 publisher 未读取新 Application result，因此新结果与 Excel 之间仍缺少一个 presentation adapter。

## 技术债

1. 旧 `excel_report.py`、`workbook_simple_overview.py` 体积较大，并保留大量茅台专用展示逻辑。
2. 新 `ThreeCompanyReplayResult.as_policy()` 尚未接入 Excel。
3. 未来切换 Excel 或 Web 时，应由 adapter 只消费 typed Application result / artifact JSON，不直接查询 PostgreSQL 或重算估值。

## 本轮验证

- Offline Core Gate：`176 passed`。
- 本地真实 frozen runtime replay 命令：`all_semantics_matched=True`、`action=no_order`。
- PostgreSQL integration 无本机 disposable DSN，本地 `4 skipped`；GitHub CI 已保留 disposable PostgreSQL job。
