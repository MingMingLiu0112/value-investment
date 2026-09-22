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
- 通用多模型运行器、持久化注册表和最小现金回报研究合同仍需在扩样本前补齐。
- 全市场漏斗、Web 前端和券商接入均未实现，不属于 C1 回归范围。

## 唯一建议后续任务

`NEXT TASK: 通用入口、持久化与最小现金回报研究合同`。目标是在把固定样本从 3 家扩展到 20--50 家之前，先收敛通用多模型运行入口、PostgreSQL 写入/恢复合同和最小 Distribution/DividendSustainability 合同；不改现有估值参数，不连接自动交易。

当前 C1 已完成，停止本阶段目标运行，不自动开始下一任务。
