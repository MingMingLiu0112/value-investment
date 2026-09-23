# 目标模式启动入口

更新：2026-09-23。`M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 已按 [current-stage-goal.md](current-stage-goal.md) 完成机器验收；当前没有自动启动的下一目标。M2 须由用户单独授权并先复核 M1 收口。
完整长期路线见 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md)，执行范围见 [current-stage-goal.md](current-stage-goal.md)。
下列文本是已退役的 M1 历史启动文本，仅用于记录原任务口径，不再重复执行。

```text
在 D:\GPTProject\value-investment 执行长期目标 M1-FIXED-SAMPLE-RESEARCH-WORKBENCH。

先读取 AGENTS.md、LONG-TERM-GOAL.md，以及 docs/north-star.md、docs/architecture.md、docs/research-methodology.md、docs/current-stage-goal.md、docs/data-and-evidence-policy.md、docs/execution-status.md。以 current-stage-goal.md 的 M1 为唯一范围，长期路线用于理解依赖，不授权自动开发 M2-M6。

先核查真实 Git HEAD、未提交改动、GitHub CI、测试、原 Excel 与 runtime 基线，继承并保护 Stage A/P0/P0.5/三公司 MVP/C0-C3，不重建已冻结成果，也不只相信 PASSED。

持续完成 M1 的可信输入与PIT/版本修复、原三公司回归、20家预登记样本分批入组、至少6家真实深研、跨至少2种适用模型的至少3家有界情景估值和反向估值、至少2家实质股息可持续性研究、当前有效报价桥接、隔离PostgreSQL冷启动replay，以及共同Application结果到原WPS Excel的安全发布。以文档具体数量和质量双门为准，不只完成一个adapter，不以20家全部占位/缺失或测试数量宣称完成。

保留Facts/Assumptions、Intrinsic Value/Market Price、Engineering/Research/Current Data各自边界；所有关键结论可追溯，保留最强反证、Thesis Breaker、Confidence和拒绝原因。新增公司复用共同流程，禁止复制专用流水线。规则自行调查论证并预登记，不为了估值或交易调参数。

外部数据未到不阻塞独立工程；真实数据、人工复核或发布验收未通过时保持PARTIAL或PENDING，不宣称达成。每批先交付可读研究增量，并客观审查下一批是否合理。

全程no_order，不开发买卖/仓位/全市场/Web/新金融行业模型，不连接或迁移生产数据库，不改生产计划任务和PTA服务。保护原Excel人工区与历史，先候选校验、源Hash守卫及回退，再按政策原子发布。代码和schema可版本化，密钥、个人持仓、生产dump、未授权原件不得公开。

完成M1全部验收后更新docs/execution-status.md，报告已提交与未提交状态、各类证据、用户可用成果、剩余限制和下一阶段合理性，然后停止。不要自动进入M2，不把工程通过称为实盘就绪。
```

C0-C3与原文档历史见execution-status及Git历史。此入口不创建第二条路线，不创建计划任务，不授权生产操作。
