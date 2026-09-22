# 当前阶段：最小现金回报研究合同

更新：2026-09-22。唯一活动工程任务：`C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT`。
执行入口为 [value-investment-goal-prompt.md](value-investment-goal-prompt.md)；证据基线见 [execution-status.md](execution-status.md)。

## 已通过并冻结

- Stage A、P0/P0.5、三公司统一工程/Excel MVP 已冻结。
- C0-PRICE-BRIDGE-INTEGRITY 已通过：共享价格桥接的证券、估值快照、模型有效性、报价证据、时点和反序列化身份合同已收紧。
- C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION 已通过：三家公司按同一固定样本准入入口审查，`REUSABLE` 与 `production_valuation_available=false` 严格分开。
- C0/C1 通过不表示任何公司生产估值、股息可持续性或现金回报结论已经完成。

## NEXT TASK

Goal：建立最小、可复用、画像感知的 Distribution / Dividend 研究合同；三家公司复用同一合同，允许显式 `PARTIAL` / `UNKNOWN`。历史验收测试不得继续依赖会滚动的 `*-latest.json` 指针。

### 合同定义

1. `DividendRecord` 区分 proposed、approved、paid 三种事实，保存公告、批准、除息、支付和信息可用时点；状态不能互相混写，未来信息不能进入历史。
2. `DividendHistory` 只保存已核验的历史分红事实，不保存未来派息预测；同一证券、时点和 fiscal/type 身份必须一致。
3. `DistributionCapacity` 只描述盈利、经营现金流、必要再投资、债务与受限现金等价格无关的分配能力，并按 ResearchProfile 表达。`READY` 必须有三情景值、已知置信度和证据，否则不得放行。
4. `DividendSustainabilityAssessment` 使用 HIGH / MEDIUM / LOW / UNKNOWN；`UNKNOWN` 是合法 fail-closed 结果，已知结论必须有理由、证据和已知置信度。
5. `DividendYieldSnapshot` 是价格层对象，只在合法且同证券的 `QuoteSnapshot` 上形成；股息 basis、known_at、quote date、币种和股份口径明确，当前收益率与周期正常化收益率不能互相替代。
6. `DividendResearchResult` 只输出 `action=no_order`，可由 C1 `FixedSampleCompanyAdmission` 直接消费，并与 valuation 的 symbol/profile 强一致。
7. 三家公司可按同一合同进入审查；历史有记录不等于可持续性通过，高当前收益率不得升级可持续性，缺数据只阻断相关投资结论。

### 本轮范围

- 新增 `src/value_investment_agent/distribution.py`，实现最小股息领域对象和类型化结果。
- C1 审查入口接受可选 `cash_return_result`，保留旧的手工 status/explanation 兼容路径。
- `scripts/review_fixed_sample_admission.py` 用同一合同读取三公司已审查分红注册表、冻结估值与研究载荷，输出三公司 typed 结果。
- 旧茅台估值与三公司验收测试改为读取冻结的 `2026-09-21` 快照和固定 Hash，不再依赖每日滚动的 current pointer。
- Core Gate 增加 `tests/test_distribution.py`；另增一个完全离线的三画像 typed 合同测试。

### Acceptance Criteria

1. 分红生命周期、时点、身份、币种、股份口径和历史事实边界均有防回归测试。
2. 分配能力不依赖市场价格；READY 或已知可持续性不能携带 UNKNOWN 置信度。
3. 高收益率、历史派息或周期当前收益率均不会自动升级可持续性或生产估值。
4. 三家公司以同一公共入口输出各自画像下的 typed 结果，预期均为 `PARTIAL`，不因 `UNKNOWN` 被当作工程失败。
5. 汇总仍为 `engineering_orchestration_status=REUSABLE`、`production_valuation_available=false`、`human_confirmation_required=true`、`action=no_order`。
6. 本地审查命令成功生成带 script/evidence Hash 的审查产物；序列化结果不含仓位、订单、目标权重或实盘指令。
7. 历史验收测试不再读取滚动 `current/latest` 指针；冻结快照 Hash 被显式校验。
8. Core Gate 在离线 fixture 上通过；三公司冻结 payload 回归单独通过。

### Forbidden Changes

不得新增第四家公司、扩全市场、实现完整股息引擎/ShareholderYield、Web、模拟交易或券商接入；不得调整估值参数、价格阈值、仓位规则、原 Excel、生产数据库、计划任务或服务器 PTA 服务。
不复制公司股息流水线，不把历史派息写成未来承诺，不为让任何公司达到可用而修饰 fixture。

## 停止条件与后续路线

本任务完成并验证后停止目标运行，交付可复现证据、实际 diff 和审查产物指针；不自动开始下一阶段。

候选后续顺序（尚未授权开发）：把最小 Distribution 合同迁移到 PostgreSQL -> 固定样本从 3 家分批扩展到 20--50 家 -> 完整股息可持续性与 ShareholderYield。未明确授权前不得自动恢复旧 P1/P2/P3、R1/R2、6--10 家或“继续三公司冻结”。
