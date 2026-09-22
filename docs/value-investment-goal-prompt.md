# 目标模式启动入口

更新：2026-09-22。本文件仅启动当前阶段，不再叠加长期工作包。
仓库：`D:/GPTProject/value-investment`。文档权威见 [AGENTS.md](../AGENTS.md)。
下列文本可直接作为目标模式的目标：

```text
在 D:\GPTProject\value-investment 工作。先读取 AGENTS.md、docs/current-stage-goal.md 和 docs/execution-status.md，再按其中引用的 north-star.md、architecture.md、research-methodology.md、data-and-evidence-policy.md 执行。

本次唯一目标是完成 C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT：建立最小、可复用、画像感知的 Distribution / Dividend 研究合同，并把历史验收测试从滚动的 runtime 指针改为冻结快照。三家公司复用同一合同，允许显式 PARTIAL / UNKNOWN，但任何结果都不能生成订单或自动升级生产估值。

从实际 Git HEAD、工作树和相关测试开始，继承 C0 价格桥接和 C1 固定样本准入成果。新增 DividendRecord、DividendHistory、DistributionCapacity、DividendSustainabilityAssessment、DividendYieldSnapshot 和 DividendResearchResult，严格执行时点、身份、币种、股份口径和证据引用校验。当前价格只进入 DividendYieldSnapshot，不进入分配能力或可持续性。

用同一公共入口把三家公司 typed 现金回报结果接入 FixedSampleCompanyAdmission。历史分红只是事实，不是未来承诺；高当前收益率不得升级可持续性，UNKNOWN 是合法 fail-closed 状态。审查命令继续输出 REUSABLE、production_valuation_available=false、human_confirmation_required=true 和 action=no_order。

旧茅台估值与三公司验收测试改为读取冻结的 2026-09-21 快照并校验固定 Hash，不再读取 rolling current/latest。新增测试加入 Core Gate，且覆盖完全离线的三画像合同。

不得新增公司、全市场、Web、完整股息引擎、ShareholderYield、模拟交易或券商逻辑；不调整估值参数、原 Excel、生产数据库、计划任务或服务器 PTA 服务。按验收标准完成测试与回归，将实际结果、证据、剩余风险和一个建议后续任务更新到 docs/execution-status.md。

完成 C2 后停止并交付，不自动推进路线图。若发现阻碍 C2 的真实设计问题，先给出有界论证并继续可独立完成部分；不得等待自然时间或无限补证。长期始终服务资本增值与可持续股息现金回报，由用户作最终决策。
```

当前任务完整定义在 [current-stage-goal.md](current-stage-goal.md)；实际进度在 [execution-status.md](execution-status.md)。
本次文档合并记录在 [审查与治理报告](project-goal-consolidation-20260922.md)。
原启动文档已按字节归档：[2026-09-22 合并前原文](archive/goal-consolidation-20260922/value-investment-goal-prompt.md)，仅供追溯。
