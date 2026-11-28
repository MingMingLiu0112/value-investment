---
name: vi-web-acceptance
description: 验收 value-investment 的现有 Windows 8001 Web、G1 公司研究和 W1 模块工作台。用于用户实机操作、发布身份、API/UI 一致性和回退；不授权部署。
---

# G1/W1：从真实操作证明交付

1. 先对比目标提交、工作树、构建产物、运行版本和行为配置。入口以 [CLI 目录](../../../config/current-cli-entrypoints-v2.json) 为准；本项目正式本地 Web 默认用 8001，不因方便另造页面、状态库或端口。区分 API 自检、同 SHA CI、Windows 浏览器实机；`DIRTY` 或 `MISMATCH` 必须显式记录。未接入 Windows 时，只报能亲自核验的内容和项目记录。
2. 用既有入口按“用户动作 → 后端响应 → 页面证据 → 刷新结果”验收。典型路线：`/strategy/value` 选公司 → 查模型适用与公司事实 → 打开准确研究任务 → 查三情景和来源，或实质拒绝 → 查 F2 五维及未放行状态 → 刷新同一任务与结果。按任务范围选择实际操作；不为验证刷新另开付费任务。
3. 用 `/project` 展示当前模块目录的独立输入、流程和输出，列未完成缺口、拒绝理由、来源及验收办法；不同阶段或个股的案例放证据区，不用历史样本替代当前模块通过。金额、模型状态、事件与交易资格由后端产出，UI 不进行二次计算；保留未知与可定位原因。
4. 回执记前后端与运行身份、命令/环境、关联输入和结果版本、实际动作、状态和未测项。只读复核不写注册；若明确授权恢复，先备份并验证受保护来源与指针，隔离演练且用既有发布流程。Excel 是兼容/历史路径，不能以候选文件替换正式入口或覆盖手工记录。

验收分开报：代码/定向测试、分支 CI、Windows 行为、业务研究门、人工验收。HTTP 200 或 CI 绿灯不证明用户能操作，更不证明投资批准，`action=no_order`。

入口：[进度模块目录](../../../web/src/config/strategyArchitecture.v1.ts) · [运行身份 API](../../../src/value_investment_agent/presentation/web_api/runtime_identity.py) · [Web 验收](../../../docs/current/web-first-full-product-acceptance.md) · [恢复记录](../../../docs/current/closure-runtime-and-recovery.md)。
