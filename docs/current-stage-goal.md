# 当前阶段：研究平台基础

更新：2026-09-22。唯一活动长程工程任务：`C3-RESEARCH-PLATFORM-FOUNDATION`。
执行入口为 [value-investment-goal-prompt.md](value-investment-goal-prompt.md)；证据基线见 [execution-status.md](execution-status.md)。

## 已通过并冻结

- Stage A、P0/P0.5、三公司统一工程/Excel MVP 已冻结。
- C0-PRICE-BRIDGE-INTEGRITY、C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION、C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT 已通过并冻结。
- 已冻结不代表任何公司生产估值、股息可持续性或现金回报结论完成。

## C3 目标

把当前“三家公司 + runtime JSON + 多个专用脚本”的研究 MVP，升级为未来 20-50 家固定样本可复用的研究后台基础。责任边界固定为：

```text
Evidence / Facts / Assumptions
        ↓
ResearchProfile -> ResearchRunSpec / Manifest
        ↓
Application Research Runner
        ↓
ValuationRouter + Model Registry
        ↓
Valuation / Distribution / Price / Status
        ↓
Immutable Research Artifacts -> Repository -> PostgreSQL
        ↓
Excel / Future Web
```

Domain 不依赖 Excel、PostgreSQL、HTTP；Application 负责编排；Repository 负责持久化；Excel 只做 Presentation。Runtime JSON 从当前主要状态载体降级为可追溯快照与兼容出口，PostgreSQL 成为长期结构化状态底座。

## Workstreams

### W1 治理与冻结状态校准

修正 `AGENTS.md`、`docs/current-stage-goal.md`、`docs/execution-status.md`、`docs/architecture.md`、`docs/value-investment-goal-prompt.md`。C2 不再 active，当前唯一阶段切到 C3；清除 C0 已修复但仍被写成当前缺口的旧描述；不重写 North Star，不新增平行 Goal 文档。

### W2 Research Artifact 持久化合同

审计 `src/value_investment_agent/db.py`、`sql/001_init.sql`、`sql/server-schema-20260921.sql`、runtime JSON 和旧 `valuation_results`。旧表混存 `current_price / fair_value / safety_margin / build_signal / target_weight`，属于历史实验结构，不复用为新语义。

新增独立 SQL migration，采用少量通用 append-only 表。至少保存 artifact identity、scope/security identity、`artifact_type`、`schema_version`、`as_of / available_at`、canonical payload、`payload_sha256`、evidence references、run identity、`created_at`，并有不可变 snapshot 与 latest head 分离的指针。

### W3 Repository Layer

实现 `ResearchArtifactRepository` 与 `PostgresResearchArtifactRepository`：保存不可变 artifact、按 id/hash 加载、按 scope+type 取 latest、列版本、验证 Hash。Domain dataclass 不导入 `psycopg`；Repository 负责 canonical JSON 与 PostgreSQL 转换。核心对象必须完成 object -> JSON -> DB -> object -> JSON 的 round-trip，并证明语义相等与 Hash 完整。malformed、identity conflict、未知 schema version 均 fail-closed。

### W4 三公司 Runtime -> PostgreSQL 可复现迁移

建立受控 importer/replay，把 600519、000333、601088 当前冻结的核心 artifact 导入 disposable/local/test PostgreSQL；不删除 runtime JSON。已有 artifact 至少覆盖 ResearchCase、ValuationResult、ModelValidity、PriceBridge、DividendResearchResult、CurrentResearchStatus/admission；缺失项记 `NOT_AVAILABLE`，不伪造。生成 source path/source sha256/database id/database payload sha256/restored semantic status 的 parity report。

### W5 Application Research Runner

建立 `ResearchApplicationService`、`run_company_research()`、`review_company_research()` 或等价入口。输入是显式 `ResearchRunSpec`，不得按 symbol 猜逻辑。Runner 按 load -> identity/version validation -> profile -> router -> model -> valuation -> validity -> price bridge -> attractiveness -> distribution -> current status -> persist 编排。单步 `NOT_READY` 只阻断依赖它的结论；identity/schema/evidence integrity/unsupported contract 才可 fail-closed。

### W6 Valuation Model Registry

将现有 `residual_income_or_equity_value`、`FCFF`、`cyclical_normalized` 接入显式 registry/factory，表达 profile -> allowed models、model_type -> builder、model_type -> required input contract。禁止 symbol if/else；不新增银行、保险、地产等模型；统一接口，不统一经济假设。

### W7 版本化 Fixed Sample Manifest

把 `scripts/review_fixed_sample_admission.py` 中的三公司硬编码 policy 迁入版本化 manifest。至少记录 symbol、name、profile_id、primary model、distribution profile/status、admission state、required evidence、explicit decision、version；不得含自动买卖、仓位、目标权重。三公司输出必须与冻结基线一致。

### W8 Batch Contract

建立 `ResearchBatchSpec` / `BatchRunResult` 或等价接口。单公司失败隔离，独立状态与 blocker；unsupported profile 输出 UNSUPPORTED，missing data 输出 GapClassification；批次有 run_id/started_at/finished_at/rule_version；支持幂等重复运行和只重跑变化公司。用三公司和 synthetic fixtures 验证，不新增几十家真实公司。

### W9 测试与 CI 平台化

保留 Core Research Gates，不新建重复 CI。补充完全离线的 Offline Core 与 GitHub Actions disposable PostgreSQL integration，验证 migration、repository save/load、Hash、round-trip、三公司 replay。不得连接生产服务器。明确 Core CI proves what、Postgres Integration proves what、External validation does NOT prove。

### W10 三公司 End-to-End Replay

通过 Manifest + Application Runner + Repository + PostgreSQL 重放三公司，保持：

| 公司 | 约束 |
| --- | --- |
| 600519 | quality_compounder / conditional / low / production unavailable / cash partial / no_order |
| 000333 | mature_manufacturing / not_ready / cash partial-or-unknown / no_order |
| 601088 | cyclical_cash_return / not_ready / current != normalized dividend / cash partial-or-unknown / no_order |

禁止为让 E2E 变绿修改投资参数。

### W11 Application / Presentation Boundary

审查 Excel publisher 但不重写 Excel。确认新 Application service 输出独立 JSON/typed result；Excel 消费 Application Result，不直接知道 PostgreSQL schema、模型内部或单元格业务逻辑。旧巨大 publisher 可作为技术债记录。

### W12 Expansion Readiness Review

完成 `20-50 FIXED SAMPLE EXPANSION READINESS REVIEW`，逐项回答新增公司成本、manifest 入组、unsupported profile、三模型同一入口、Distribution 同一入口、artifact 持久化/恢复、runtime/PostgreSQL parity、Excel boundary、batch isolation 和是否可安全扩样本。最终只输出 `READY_FOR_FIXED_SAMPLE_EXPANSION` 或 `NOT_READY` 与真实原因，不强行写 READY。

## Acceptance Criteria

1. C2 已正确冻结，权威文档同步。
2. 新 Research Artifact 存储不复用旧混合语义 `valuation_results`。
3. 新 artifact append-only、可版本化、可 Hash 校验。
4. Repository round-trip 语义相等且 Hash 完整。
5. 三公司 frozen runtime 可迁入 disposable PostgreSQL 并恢复，parity 可审计。
6. 通用 Application Runner 处理三种现有 Profile，模型选择不依赖 symbol。
7. Fixed Sample policy 已迁入版本化 manifest。
8. Batch Runner 隔离单公司失败，Distribution 进入同一 pipeline。
9. GitHub CI 同时包含稳定 Core 与 disposable PostgreSQL integration。
10. 三公司 E2E 研究语义与冻结基线一致。
11. Excel 未成为 Domain 依赖，所有研究结果仍为 `no_order`。
12. 未修改生产 DB、Web、自动交易或服务器 PTA 服务。
13. Expansion Readiness Review 给出真实 verdict。

## 数据库安全边界

只允许 migration SQL、repository code、local/test PostgreSQL、CI disposable PostgreSQL、schema compatibility audit 和 import/replay tools。禁止自动 ssh 到生产服务器、ALTER 生产数据库、DROP/DELETE 生产表或覆盖生产数据。任何未来生产 migration 必须作为独立、人工确认阶段执行。

## Forbidden Changes

不得新增第四家真实研究公司、正式扩到 20-50 家、全市场 Funnel、Web/FastAPI、银行/保险新估值模型、复杂 ShareholderYield、自动交易、券商下单、仓位算法；不得重新调茅台估值、降低美的/神华证据标准、删除旧生产表、修改生产 PostgreSQL、修改服务器计划任务或破坏 PTA 服务。

## 执行纪律

这是连续长程目标，完成 W1/W2 后必须继续，直到 C3 全部验收或出现不可逆生产风险、核心架构冲突、无法恢复的数据完整性问题。外部数据暂不可得标记 `PENDING_EXTERNAL_DATA`，不阻塞无关工程任务；真实公司仍无法估值时保持 `NOT_READY`，继续平台化。

全部完成后更新 `docs/execution-status.md`，将本文件标记为 C3 `PASSED_FOR_FREEZE`，给出 Expansion Readiness Verdict，只提一个下一阶段建议后停止，不自动扩真实股票样本。
