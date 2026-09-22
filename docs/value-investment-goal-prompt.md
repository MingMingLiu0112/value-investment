# 目标模式启动入口

更新：2026-09-22。本文件仅启动当前阶段，不再叠加长期工作包。
仓库：`D:/GPTProject/value-investment`。文档权威见 [AGENTS.md](../AGENTS.md)。
下列文本可直接作为目标模式的目标：

```text
在 D:\GPTProject\value-investment 工作。先读取 AGENTS.md、docs/current-stage-goal.md 和 docs/execution-status.md，再按其中引用的 north-star.md、architecture.md、research-methodology.md、data-and-evidence-policy.md 执行。

本次唯一目标是完成 C3-RESEARCH-PLATFORM-FOUNDATION：把三家公司、runtime JSON 和多个专用脚本的研究 MVP，升级为未来 20-50 家固定样本可复用的研究后台基础。继承 C0/C1/C2 冻结成果，但不得重复已通过阶段。

先建立 append-only、不可变、可版本化、可 Hash 校验的通用 Research Artifact 持久化合同与独立 SQL migration；旧 valuation_results 混存价格和信号，保留为历史实验结构，不复用为新语义。随后实现 Repository，Domain 不导入 psycopg，由 Repository 完成 canonical JSON 与 PostgreSQL 转换。只允许 disposable/local/test PostgreSQL 和 CI 一次性实例，绝不连接 .env 中的生产数据库、修改旧表或部署 migration。

建立受控 importer/replay，将当前冻结的 600519、000333、601088 核心 artifact 导入测试 PostgreSQL并生成可审计 parity report；不存在则记 NOT_AVAILABLE，不得伪造。建立显式 ResearchRunSpec 驱动的 Application Runner，profile、model、facts、assumptions、distribution、quote 均显式输入，禁止 symbol if/else。Runner 按身份与版本校验、ResearchProfile、ValuationRouter、已注册模型、估值、有效性、价格桥接、吸引力、分配研究、CurrentResearchStatus、持久化编排；NOT_READY 只阻断依赖它的结论，身份/evidence/schema 损坏才 fail-closed。

将现有三种估值模型接入同一 registry/factory，并把 scripts/review_fixed_sample_admission.py 的三公司硬编码 policy 迁入版本化 manifest。建立带 run_id、时点和 rule_version 的 Batch Contract，单公司失败隔离，重复运行幂等。CI 保留离线 Core Gate，并增加 disposable PostgreSQL integration；全量历史测试不再作为未解释的 83% 中止状态证据。

三公司 E2E 必须保持冻结语义：600519 quality_compounder/conditional/low/production unavailable/cash partial；000333 mature_manufacturing/not_ready/cash partial-or-unknown；601088 cyclical_cash_return/not_ready/current != normalized dividend/cash partial-or-unknown。所有输出 no_order。审查 Excel 只是 Presentation，但本轮不重写 Excel。

不得新增第四家真实公司、扩全市场、Web、新金融模型、复杂 ShareholderYield、自动交易、券商下单或仓位算法；不调估值参数、不改原 Excel、生产数据库、计划任务或服务器 PTA 服务。按 W1-W12 连续完成并按 C3.1-C3.6 分阶段提交，不因 W1/W2 结束提前停止。全部完成后更新 execution-status、将 current-stage-goal 标记为 C3 PASSED_FOR_FREEZE，给出 Expansion Readiness Verdict，只提一个下一阶段建议后停止，不自动扩真实股票样本。
```

当前任务完整定义在 [current-stage-goal.md](current-stage-goal.md)；实际进度在 [execution-status.md](execution-status.md)。
本次文档合并记录在 [审查与治理报告](project-goal-consolidation-20260922.md)。
原启动文档已按字节归档：[2026-09-22 合并前原文](archive/goal-consolidation-20260922/value-investment-goal-prompt.md)，仅供追溯。
