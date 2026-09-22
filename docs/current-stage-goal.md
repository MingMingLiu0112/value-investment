# 当前阶段：固定样本准入协议与公共编排审查

更新：2026-09-22。唯一活动工程任务：`C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION`。
执行入口为 [value-investment-goal-prompt.md](value-investment-goal-prompt.md)；证据基线见 [execution-status.md](execution-status.md)。

## 已通过并冻结

- Stage A、P0/P0.5、三公司统一工程/Excel MVP 已冻结。
- C0-PRICE-BRIDGE-INTEGRITY 已通过：共享价格桥接的证券、估值快照、模型有效性、报价证据、时点和反序列化身份合同已收紧。
- C0 通过不表示任何公司生产估值或股息可持续性已经完成。

## NEXT TASK

Goal：建立可复用的固定样本准入协议和公共编排入口，把“流程可复用”与“生产估值可用”严格分开；三家公司可按相同合同进入固定研究样本，但未完成的估值、价格和现金回报判断保持 fail-closed。

### 协议定义

1. 每次准入必须显式声明研究样本准入证据、经济画像与已注册模型路由、版本化 ResearchCase 和证据引用。
2. `FixedSampleCompanyAdmission` 同时记录：
   - `engineering_contract_reusable`
   - `research_sample_status`
   - `production_valuation_status`
   - `bounded_value_judgment`
   - `cash_return_status` 与解释
   - 显式模型继续、输入解决、暂停或替换/停止决策
   - 决策所需证据、阻断项、证据引用和人工确认边界。
3. 公共入口 `review_fixed_sample()` 必须覆盖显式传入的每一家公司，不得按证券代码猜测经济画像或估值模型。
4. 身份冲突、缺失估值 payload、未知 profile、坏价格桥接或未注册模型必须异常退出或返回明确拒绝状态；单家公司失败不得静默跳过。
5. `production_valuation_available` 仅在正式估值批准、合法模型状态、完整三情景和有效人工确认边界同时满足时为 true。
6. `conditional_research_only`、`not_ready`、空情景或缺失报价只能保留为研究状态，不能被解释为生产估值可用。
7. 所有输出必须为 `action=no_order`，不得生成仓位、订单、目标权重或实盘指令。

### 本轮范围

- 新增共享准入域合同与统一审查入口：`src/value_investment_agent/fixed_sample_admission.py`。
- 新增可审计本地命令：`scripts/review_fixed_sample_admission.py`，读取三公司冻结指针并生成带 Hash 的审查产物。
- 防回归测试覆盖直接构造、JSON 恢复、身份冲突、条件估值不升级、空情景和公共编排；新测试加入现有 Core Gate，不新建 CI。
- 更新 `current-stage-goal.md` 和 `execution-status.md`，不扩展路线图。

### Acceptance Criteria

1. 同一公共入口成功读取三家公司冻结 ResearchCase、ValuationResult、ModelValidity、PriceBridge 和下游状态，不新增公司适配流水线。
2. `engineering_orchestration_status` 与 `production_valuation_available` 独立；当前预期为 `REUSABLE` 与 `false`。
3. 茅台边界为 `CONDITIONAL`，美的和神华为 `NOT_AVAILABLE`；三家公司都不得因空估值或缺行情变成生产估值可用。
4. 每家公司有显式且可执行的决策与所需证据：继续条件模型、解决模型输入或暂停生产估值；不生成自动升级。
5. 身份/JSON 冲突、缺证据或未知 profile 被拒绝并可定位原因；正常失败不写入半成品指针。
6. 固定样本准入证据字段独立于估值推进证据字段，避免把“进入研究池”写成“模型已批准”。
7. 审查命令输出 `human_confirmation_required=true`、`action=no_order`，序列化结果不含交易、仓位或订单状态。
8. Core Gate 在离线 fixture 上通过；三公司冻结 payload 本地回归单列。diff 只含本任务必要改动。

### Forbidden Changes

不得新增第四家公司、扩全市场、实现新估值/股息引擎、调整估值/价格阈值或仓位、扩展模拟/历史策略、接券商、修改 WPS 原表、迁生产数据库、改计划任务或服务器服务。
不进行通用目录重构，不复制公司流水线，不放宽证据门禁，不为让公司达到生产可用而修饰 fixture。

## 停止条件与后续路线

本任务完成并验证后停止目标运行，交付可复现证据、实际 diff 和审查产物指针；不自动开始下一阶段。
真正的合同设计或兼容问题先做有界论证并报告受影响部分，不能无限补证。

候选后续顺序（尚未授权开发）：20--50 家范围/分批计划 -> 在允许扩样本前补齐通用入口、持久化与最小现金回报研究合同 -> 逐批验证 -> 扩大候选与事件运营。
固定样本协议完成后，后续任务须在节点评估后选定一个更新本文件。旧文档中的 P1/P2/P3、R1/R2、6--10 家或“继续三公司冻结”不自动恢复。
