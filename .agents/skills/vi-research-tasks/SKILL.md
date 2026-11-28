---
name: vi-research-tasks
description: 审查 value-investment 的 D1/G2 研究任务、预算和角色请求，区分重开、封存重算、发布重试及新付费任务。用于 API/UI 任务恢复、取消或重复计费问题，不授予模型消费权限。
---

# D1/G2：受限执行、封存、重试

- 先列操作类型：读取/重开旧任务、从已封存输入重算、仅重试发布、创建独立新研究。前三类不能暗中创建付费任务。用同一研究任务 ID、原候选及输入版本核对回退和刷新，不把新任务结果伪装成原任务后继。
- 任务输入冻结财务主体、候选、来源、时点、workflow/model、预算和前驱。调用前校验必需输入、前序角色、可用预算和执行授权。重复点击应复用同一操作或安全拒绝；仅在需要新证据且授权允许时才发新请求。
- 区分排队、执行、取消、结算、封存结果及发布状态。保存原始拒绝原因和已结算请求的绑定。HTTP 202 只证明排队；未封存不进入 E2/F1，单独发布重试不得再次调用模型；流程成功不等于估值通过。若失败发生在已付费之后，先离线重放已封存响应，明确新增调用数、已结算费用和未结算预留。
- 面向用户写清楚“点什么 → 发生什么 → 刷新后如何查 → 是否花费”。边界测试：缺输入未调用、重复操作不增费、旧任务刷新仍绑定原版本；覆盖错误任务号、错误前驱、响应校验失败和取消后的真实状态。

入口：[任务路由](../../../src/value_investment_agent/presentation/web_api/research_task_routes.py) · [执行测试](../../../tests/test_research_task_execution_v1.py) · [API 测试](../../../tests/web_api/test_research_tasks_api.py)。[PR #5 审阅快照的封存重算对照例](https://github.com/MingMingLiu0112/value-investment/blob/9bf691202f5cef8a9935d0b4bd8b670a8c9f68d8/docs/current/core-value-development-plan.md#L1218-L1279)是特定版本记录，不证明当前 Windows 实机。
