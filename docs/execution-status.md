# 当前执行状态

更新：2026-09-22。本文只记录事实，不制定新任务。唯一活动任务见 [current-stage-goal.md](current-stage-goal.md)。

## C0 已冻结

C0-PRICE-BRIDGE-INTEGRITY：`PASSED_FOR_FREEZE`。

- 提交：`df4d343 C0-price-bridge-integrity`。
- 新增 `QuoteSnapshot` 与显式 `bridge_with_quote()`；收紧 ModelValidity、PriceBridgeResult、JSON 恢复和下游聚合。
- `current_research_status_from_payloads()` 不再用估值 symbol 覆盖冲突身份。
- 定向回归 47 项、Core Gate 102 项通过；旧 runtime 合同显式重验，茅台 READY 恢复不静默洗掉冲突。
- 三公司 runtime Hash 与原 Excel Hash 未变。

C0 只修复共享工程合同，不表示研究、估值、股息能力、生产数据或价格判断已经完成。

## C1 验收基线

- C1 开始 HEAD：`df4d343726f0d49fd5570e30b075cc46faf859d0`，工作树干净。
- 未连接服务器、生产数据库或定时任务；未重做原始财报、行情或重大事项审计。
- 目标：固定样本准入协议与公共编排审查。

## C1 验收结果

C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/fixed_sample_admission.py`，显式区分研究样本准入证据与估值推进证据。
- 新增 `FixedSampleAdmissionPolicy`、`FixedSampleCompanyAdmission` 和 `FixedSampleAdmissionReview`。
- 公共入口 `review_fixed_sample()` 对每家公司复用 ResearchGate、ValuationResult、ModelValidity、PriceBridge 和 CurrentResearchStatus 合同；不按 symbol 猜测 profile。
- 三家公司输出：

| 公司 | 编排合同 | 研究样本 | 有界价值 | 生产估值 | 显式决策 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | REUSABLE | ADMITTED_FOR_RESEARCH | CONDITIONAL | NOT_AVAILABLE | CONTINUE_CONDITIONAL_MODEL |
| 000333 美的集团 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | RESOLVE_MODEL_INPUTS |
| 601088 中国神华 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | PAUSE_PRODUCTION_VALUATION |

- 汇总状态：`engineering_orchestration_status=REUSABLE`，`production_valuation_available=false`。
- 所有记录均为 `human_confirmation_required=true`、`action=no_order`；不含仓位、订单、目标权重或实盘指令。
- 新增本地审查命令：`python scripts/review_fixed_sample_admission.py`。命令读取四个冻结指针，验证 Hash 后生成带 script/evidence Hash 的审查产物和 latest 指针。

验证证据：

- 新增防回归：`10 passed`，覆盖显式政策、条件估值不升级、空情景、缺研究证据拒绝、身份冲突、profile/model 类型失配、公共编排、序列化和三公司冻结回归。
- 更新后的 Core Gate：`112 passed`。
- 全量测试：`1901 passed, 1 skipped, 5 failed, 18 warnings`。5 个失败均是旧验收测试硬编码茅台报价日 `2026-09-21`；后台日更在 C1 验证期间将 current 指针推进到 `2026-09-22`。本轮未改历史验收测试或回退 runtime 日更产物。
- `compileall` 通过；`git diff --check` 通过。
- 美的、神华及研究卡 Hash 与冻结记录一致；茅台 current 已被后台日更推进，Hash 为 `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`。原 WPS 工作簿 Hash 仍为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`。
- 未改动估值参数、原 Excel、生产数据库、计划任务或服务器服务。

## 阶段语义

三公司统一工程/Excel MVP、C0 和 C1 均通过冻结。C1 的 `REUSABLE` 表示共享审查入口可用，不表示任何公司生产估值或现金回报结论可用。

| 维度 | 600519 贵州茅台 | 000333 美的集团 | 601088 中国神华 |
| --- | --- | --- | --- |
| Engineering Complete | READY：研究、估值和 C0/C1 共享合同可用 | READY：FCFF 算术与拒绝边界 | READY：周期算术与拒绝边界 |
| Research Complete | PARTIAL：商业/财务材料与论点存在，G3 未通过 | PARTIAL：事实范围 MODEL_NOT_APPLICABLE | PARTIAL：正常化假设和财务门未通过 |
| Valuation Complete | PARTIAL：低置信度 conditional_research_only | NOT_READY：无三情景值 | NOT_READY：无三情景值 |
| Dividend Research Complete | PARTIAL：有历史分红及分配交叉检查 | PARTIAL：有历史派息与部分财务材料 | PARTIAL：有派息与周期候选材料 |
| Production Data Ready | 2026-09-21 快照 READY；未验证 09-22 当前生产 | PENDING_EXTERNAL_DATA，并存模型适用性问题 | PENDING_EXTERNAL_DATA，并存未注册假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE：低置信度及研究门限制 | NOT_ASSESSABLE | NOT_ASSESSABLE |

三家公司完整 DividendSustainability 评估均未完成。

## 当前可追溯产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司研究卡 | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 茅台条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`（后台日更推进） |
| 美的未就绪结果 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 神华未就绪结果 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |
| 固定样本审查 | `runtime/fixed-sample-admission-review-latest.json` | `1dfe78e330ee45242d71a59a6888774408166fc215ca866816e4aefd6e535b4f` |

茅台估值日期为 2026-09-21，报价日已由后台日更推进到 2026-09-22；条件情景 403.44 / 478.43 / 571.25 元每股。此处仅描述研究模型，不是当前合理价或投资建议。美的、神华载荷日期为 2025-12-31，不能称作今日估值。

## 剩余风险与边界

- C1 是工程与准入协议验证，不替代生产行情、公告、重大事项或人工研究复核；当前价格评估仍为 NOT_ASSESSABLE。
- 后台日更会推进 current 指针；硬编码具体报价日的旧测试在日更后可能暂时失败，需在后续任务中把 current 回归改为对冻结快照的显式版本测试。
- 三家公司政策目前由 `scripts/review_fixed_sample_admission.py` 显式登记，属于受控 adapter；新增公司必须新增政策与证据，不能自动推断。
- 研究准入证据目前验证的是结构与 Hash 可追溯性，不是重新证明财务事实或论点内容正确。
- 固定样本协议尚未迁移到 PostgreSQL；runtime JSON 仍为当前可追溯中间产物。
- 通用多模型运行器与持久化注册表仍需在扩样本前补齐；最小现金回报研究合同由 C2 完成。
- 全市场漏斗、Web 前端和券商接入均未实现，不属于 C1 回归范围。

## C2 验收基线

- C2 开始 HEAD：`357e080b69edfe135eaabcd5d31dc7331e05b9d3`，即 C1 提交 `C1-fixed-sample-admission-orchestration`。
- 未连接服务器、生产数据库或定时任务；未改动估值参数、原 Excel、计划任务或服务器 PTA 服务。

## C2 验收结果

C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/distribution.py`：`DividendRecord`、`DividendHistory`、`DistributionCapacity`、`DividendSustainabilityAssessment`、`DividendYieldSnapshot`、`DividendResearchResult` 与两个合法 yield 构建函数。
- `DividendRecord` 强制区分 proposed / approved / paid，并校验公告、批准、除息、支付和 known_at 的时序；`DividendHistory` 只接受 known_at 不晚于 as_of 的事实。
- `DistributionCapacity` 与 `DividendSustainabilityAssessment` 不依赖价格，按 ResearchProfile 识别；READY 能力及已知可持续性均不允许 UNKNOWN 置信度。
- `DividendYieldSnapshot` 只接受同证券 verified close quote，并强制 DPS / price / yield 可复算；当前收益率与周期正常化收益率是不同对象。
- `FixedSampleCompanyAdmission` 和公共入口 `review_fixed_sample()` 接受可选 typed `cash_return_result`，同时保留旧手工 status/explanation 兼容路径。
- `scripts/review_fixed_sample_admission.py` 使用同一合同读取已审查现金分配注册表和冻结研究/估值载荷，为三家公司生成 typed 结果。
- 旧茅台估值与三公司验收测试改为读取冻结的 2026-09-21 快照并校验固定 Hash，不再依赖 rolling current/latest 指针；干净 checkout 中这些冻结 runtime 快照缺失时显式 skip，不误报为当前生产失败。

三公司 typed 现金回报状态：

| 公司 | 历史分红 | 分配能力 | 可持续性 | Yield 快照 | 现金回报研究 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | PARTIAL | PARTIAL | UNKNOWN | 1 | PARTIAL |
| 000333 美的集团 | PARTIAL | UNKNOWN | UNKNOWN | 0 | PARTIAL |
| 601088 中国神华 | PARTIAL | UNKNOWN | UNKNOWN | 2 | PARTIAL |

三家公司均仍是研究状态；有历史派息不等于分红可持续性或现金回报能力完成。公共审查保持 `REUSABLE`、`production_valuation_available=false`、`human_confirmation_required=true`、`action=no_order`。

验证证据：

- Core Gate 同款离线清单：`124 passed`。
- 冻结历史验收：`tests/test_moutai_valuation_export.py` + `tests/test_three_company_unified_acceptance.py`：`9 passed`。
- Distribution + 固定样本 + 价格桥接 + quote 定向回归：`74 passed`。
- 新离线三画像 typed 合同测试覆盖 600519 / 000333 / 601088 的 quality_compounder / mature_manufacturing / cyclical_cash_return，确认三公司复用同一合同且均为 PARTIAL。
- 审查命令成功生成：`runtime/fixed-sample-admission-review-20260922T101442190293Z`，evidence SHA-256 `022cfd2f501a358ff843799ec227a832d5a23a370cbd3238f238f93f2f4ed0d0`。
- `compileall` 与 `git diff --check` 通过。
- 全量历史测试尝试运行至约 83% 后停在旧网络/外部 fixture 路径，未作为 C2 验收依据；C2 只冻结上述离线 Core Gate 和定向回归证据。

## 剩余风险与边界

- 本任务是共享领域合同和 fail-closed 类型验证，不是三家公司的股息可持续性研究、生产数据核验或未来派息承诺。
- 现金分配注册表目前是受控 JSON adapter；茅台 fiscal attribution、提案/批准日期、税费和结算时点仍列为显式 blocker。
- Distribution 对象尚未迁移到 PostgreSQL；runtime JSON 仍是当前可追溯中间产物。
- ShareholderYield、完整 distribution_profile、行业阈值和回购/稀释口径未实现，不属于 C2。

## C3 验收基线

- C3 开始 HEAD：`d658b92 C2-minimal-distribution-research-contract`；工作树开始时的改动仅包含 C3 的 W1 治理校准。
- C2 的唯一建议后续任务“最小 Distribution 合同迁移到 PostgreSQL”已被 C3 吸收，但 C3 范围扩大到通用 Research Artifact 合同、Repository、Runner、Registry、Manifest、Batch、CI 与三公司 E2E。
- 数据库安全边界：`.env` 中的生产 `DATABASE_URL` 在本阶段不得连接；只使用 disposable/local/test PostgreSQL 或 GitHub CI 一次性实例。

## C3 验收结果

C3-RESEARCH-PLATFORM-FOUNDATION：`PASSED_FOR_FREEZE`。

提交序列：

```text
7903933 C3.1 governance and research artifact contract
6eee08e C3.2 repository and typed artifact round-trip
a89e269 C3.3 frozen runtime parity importer
b787b3e C3.4 profile-driven application research runner
365d845 C3.5 explicit valuation model registry contract
2bfe065 C3.6 versioned fixed sample policy manifest
33590bb C3.7 failure-isolated research batch contract
9d9231b C3.8 offline core and disposable postgres CI
13c5b03 C3.10 three-company frozen replay receipt
412564a C3.11 presentation boundary and expansion verdict
957243f C3.12 isolate postgres CI from ignored runtime data
fc49ab7 C3.13 align postgres import assertion with review scope
```

W1-W12 结果：

- W2-W3：新增 `sql/20260922_research_artifacts.sql`、`research_artifacts.py`、`research_artifact_codecs.py` 和 `research_artifact_repository.py`。新表 append-only，与旧混合语义 `valuation_results` 分离；round-trip、版本 head、Hash 与 fail-closed 均有测试。
- W4：`research_runtime_import.py` 把三公司 frozen runtime 核心 artifact 迁入 repository，输出 source path、source/database SHA-256 和 restored semantic status；缺失 `model_validity` 显式记为缺失，不伪造。
- W5：`research_application.py` 使用显式 `ResearchRunSpec`，按 Profile -> Router -> Model -> Validity -> PriceBridge -> Distribution -> CurrentStatus -> Repository 编排，不按 symbol 猜模型。
- W6：`valuation_router.py` 已表达三种 Profile 与三种模型/Facts 合同；未知 profile 为 `UNSUPPORTED`。
- W7：三公司 admission policy 迁入 `config/fixed-sample-manifest.json`，禁止交易键，loader 做 schema 与 profile/model 校验。
- W8：`research_batch.py` 隔离单公司 GAP/FAILED/UNSUPPORTED，支持 run_id、rule_version、时点和幂等输入 fingerprint。
- W9：GitHub Core Gate 保持离线，另增加 disposable PostgreSQL job；本地未使用生产 DSN。
- W10：`research_e2e_replay.py` 完成三公司 Manifest -> ResearchRunSpec -> Application -> Repository -> Batch replay。真实 frozen runtime 结果为 `all_semantics_matched=True`、`action=no_order`。新增命令行 `python scripts/run_three_company_research_replay.py`，输出独立 JSON 审计收据。
- W11：Application/Presentation 边界审查通过并记录技术债，见 [application-presentation-boundary.md](application-presentation-boundary.md)。Domain/Application 不依赖 Excel 或 PostgreSQL schema；旧 Excel publisher 尚未切换到新 Application result。
- W12：Expansion Readiness Verdict 为 `NOT_READY`，原因见 [fixed-sample-expansion-readiness-review.md](fixed-sample-expansion-readiness-review.md)。核心 pipeline 可复用，但缺少 manifest-driven facts/assumptions/quote input adapter，且 replay adapter 仍含茅台 symbol 专用分支。

验证证据：

- Offline Core Gate 全清单：`176 passed`。
- 新增三公司 replay 自包含 fixture：三种 Profile、三种模型、`no_order`、美的/神华 `not_ready`、神华 current/normalized yield 区分和 Hash 篡改 fail-closed。
- PostgreSQL integration 在本机无 disposable DSN，`4 skipped`；GitHub CI 中由一次性 PostgreSQL service 验证 migration、repository round-trip、frozen runtime import 和三公司 replay。最终验收运行 `35727542158` 的离线 Core 与 disposable PostgreSQL job 均为 success。
- 本机真实 frozen runtime 命令验证：`all_semantics_matched=True`、`action=no_order`、收据约 193KB。
- `compileall` 与 `git diff --check` 通过。
- 未连接生产数据库、未修改旧 `valuation_results`、未改动原 Excel、未调整估值参数、未触碰服务器 PTA 项目或计划任务。

## 当前建议后续任务

```text
NEXT TASK: C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER
```

先移除三公司 replay 中的茅台 symbol 专用分支，建立 versioned per-company input descriptor，再以离线 fixture 和 disposable PostgreSQL replay 验收。验收前不新增第四家真实公司，也不自动扩样本。
