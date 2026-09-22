# 目标模式启动入口

更新：2026-09-22。本文件仅启动当前阶段，不再叠加长期工作包。
仓库：`D:/GPTProject/value-investment`。文档权威见 [AGENTS.md](../AGENTS.md)。
下列文本可直接作为目标模式的目标：

```text
在 D:\GPTProject\value-investment 工作。先读取 AGENTS.md、docs/current-stage-goal.md 和 docs/execution-status.md，再按其中引用的 north-star.md、architecture.md、research-methodology.md、data-and-evidence-policy.md 执行。

本次唯一目标是完成 C0-PRICE-BRIDGE-INTEGRITY：修复并验证研究价格桥接的证券身份、估值快照/模型版本、报价证据和有效时点合同，使错误混配不能返回 READY 或价格吸引力结论。严格按 current-stage-goal.md 的范围、验收标准和停止条件执行。

从实际 Git HEAD、工作树和相关测试开始，继承三公司冻结成果。先复现审查中的跨公司 ModelValidity / 空报价证据问题，再以最小改动修复正常调用、JSON 恢复及下游聚合。使用现有快照和离线 fixture 验证，外部行情等待只影响 Production Validation。

保留茅台条件估值参数、美的/神华未就绪边界、原 Excel 和历史证据。不要新增公司、专用证据脚本、全市场、Web、股息引擎、模拟/交易功能，不迁生产库、不改计划任务或服务器 PTA 服务。

按验收标准完成测试与回归，将实际结果、证据、剩余风险和一个建议后续任务更新到 docs/execution-status.md。工程通过、研究完成、估值完成、股息研究完成、生产数据就绪和价格评估就绪分别汇报，不用测试通过宣称投资有效或实盘就绪。

完成 C0 后停止并交付，不自动推进路线图。若发现阻碍 C0 的真实设计问题，先给出有界论证并继续可独立完成部分；不得等待自然时间或无限补证。长期始终服务资本增值与可持续股息现金回报，由用户作最终决策。
```

当前任务完整定义在 [current-stage-goal.md](current-stage-goal.md)；实际进度在 [execution-status.md](execution-status.md)。
本次文档合并记录在 [审查与治理报告](project-goal-consolidation-20260922.md)。
原启动文档已按字节归档：[2026-09-22 合并前原文](archive/goal-consolidation-20260922/value-investment-goal-prompt.md)，仅供追溯。

