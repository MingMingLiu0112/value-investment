# 目标模式启动入口

更新：2026-09-22。本文件仅启动当前阶段，不再叠加长期工作包。当前 C3 已 `PASSED_FOR_FREEZE`，请先读取 [current-stage-goal.md](current-stage-goal.md) 中的下一阶段唯一建议，不要重新执行已完成 C3。
仓库：`D:/GPTProject/value-investment`。文档权威见 [AGENTS.md](../AGENTS.md)。
下列文本可直接作为目标模式的目标：

```text
在 D:\GPTProject\value-investment 工作。先读取 AGENTS.md、docs/current-stage-goal.md 和 docs/execution-status.md，再按其中引用的 north-star.md、architecture.md、research-methodology.md、data-and-evidence-policy.md 执行。

C0、C1、C2、C3 已通过并冻结，不重复执行。C3 已建立 append-only Research Artifact 存储、Repository、三公司 Runtime -> PostgreSQL importer、显式 ResearchRunSpec Application Runner、ValuationRouter/Model Registry、版本化 Fixed Sample Manifest、Batch Contract、离线 Core + disposable PostgreSQL CI，并完成三公司 E2E replay 与 Expansion Readiness Review。

当前唯一后续建议是 C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER：移除 replay 中的茅台 symbol 专用输入分支，建立 versioned per-company input descriptor，再以离线 fixture 和 disposable PostgreSQL replay 验收。未获用户明确授权前，不开始 C4、不新增第四家真实公司、不扩 20-50 家样本。

所有研究结果继续 no_order；不自动交易、不改估值参数、不连接或迁移生产数据库、不改旧 valuation_results 语义、不改原 Excel、生产计划任务或服务器 PTA 服务。若继续后续任务，每次先核对真实 HEAD、测试、GitHub CI 和 execution-status，不把文档中的 PASSED 当作未经验证的完成。
```

当前任务完整定义在 [current-stage-goal.md](current-stage-goal.md)；实际进度在 [execution-status.md](execution-status.md)。
本次文档合并记录在 [审查与治理报告](project-goal-consolidation-20260922.md)。
原启动文档已按字节归档：[2026-09-22 合并前原文](archive/goal-consolidation-20260922/value-investment-goal-prompt.md)，仅供追溯。
