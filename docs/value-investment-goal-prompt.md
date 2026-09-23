# 目标模式启动入口

更新：2026-09-23。`M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 已完成并冻结；
用户已复核 [m2-current-progress-review-20260923.md](m2-current-progress-review-20260923.md)，
当前唯一活动目标为 [current-stage-goal.md](current-stage-goal.md) 中的
`M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`。完整长期路线见
[LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md)，但不得自动开发 M3-M6。

```text
在 D:\GPTProject\value-investment 执行长期目标 M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY。

先读取 AGENTS.md、LONG-TERM-GOAL.md，以及 docs/north-star.md、docs/architecture.md、docs/research-methodology.md、docs/current-stage-goal.md、docs/data-and-evidence-policy.md、docs/execution-status.md。以 current-stage-goal.md 的 M2 为唯一范围，不把长期路线当成并行任务队列。

先核查真实 Git HEAD、未提交改动、CI、测试、已产生的 M2 runtime 收据、原 WPS Excel 与证据清单，继承并保护 POST-M1 稳定化结果。不得因已有一次 JSON run-once 就宣布 M2 完成；继续用真实全市场数据补足尚未达到的验收项。

维持四个筛选通道和候选池，但所有候选只进入深研队列；缺失不得默认为 0，银行/保险/券商等不支持画像必须隔离，Legacy PE/PB 只作 shadow 对比。每条候选保留进入原因、证据日期、数据状态和画像状态。

从新发现候选中有界形成至少 3 份实质研究或否决报告，禁止为凑数量复制 symbol 专用流水线。报告必须记录来源、可用时点、反证和拒绝/研究结论；仍不能从研究状态生成 BUY、ADD、仓位或订单。

保持全程 no_order，不开发 M3 决策门、组合/仓位、Web、金融行业新模型、券商接口，不连接生产 PostgreSQL，不改计划任务，不触碰服务器 PTA/Web App 或原 WPS 人工工作簿。

完成 M2 全部验收后更新 execution-status.md，报告用户可见 Excel、真实数据覆盖、已知缺口、测试与下一阶段合理性，然后停止；不得自动进入 M3，也不把机会发现称为投资就绪。
```

C0-C3与原文档历史见execution-status及Git历史。此入口不创建第二条路线，不创建计划任务，不授权生产操作。
