# A股价值投资 Agent：当前进度审查与“初步可用”路线执行手册

**版本**：v1.0  
**日期**：2026-09-23  
**仓库**：`MingMingLiu0112/value-investment`  
**审查基线 HEAD**：`60c9de0128f46ee19f3ca0de211049a1aeb47f04`  
**最新提交**：`Build post-M1 review receipts and register core gates`

---

# 0. 本手册目的

本手册站在最终投资使用者视角，而不是单纯站在软件开发视角。

目标不是继续增加更多类、测试和脚本，而是明确：

> 当前系统究竟做到什么程度、离“能够实际辅助价值投资”还差什么、下一步应该按什么顺序开发，以及达到什么条件以后才适合开始真正依赖它。

最终系统目标：

```text
全A股
↓
自动分通道筛选
↓
候选池
↓
深度研究
↓
重点关注池
↓
价值/股息/风险研究
↓
BUY / ADD / HOLD / REDUCE / EXIT 人工复核信号
↓
仓位与组合约束
↓
每日事件跟踪
↓
买卖逻辑一致性
↓
用户最终决策
```

系统必须帮助用户真正理解：

```text
为什么买？
为什么加仓？
为什么继续持有？
什么条件下停止加仓？
为什么减仓？
为什么卖出？
哪一条原始买入逻辑已经发生变化？
```

系统不自动下单。

---

# 1. 当前版本审查结论

截至：

```text
HEAD = 60c9de0
```

最新 GitHub Core Research Gates：

```text
SUCCESS
```

M1 之后已经完成三次提交：

```text
decbd9e  Add post-M1 human review and decision contracts
62e22e5  Integrate post-M1 gates into research application
60c9de0  Build post-M1 review receipts and register core gates
```

本轮相对 `cbec189`：

```text
23 files changed
+6716
-9
```

说明本轮工作已经真正进入 Core，而不是只修改文档。

---

# 2. 当前已经具备的能力

## 2.1 工程基础

当前已经具备：

```text
Evidence
Facts
Assumptions
ResearchProfile
ResearchCase
ResearchGate
ValuationRouter
ValuationModel
ValuationResult
ModelValidity
QuoteSnapshot
PriceBridge
PriceAttractiveness
Distribution / Dividend
Research Artifact Repository
Application Runner
Batch Contract
PostgreSQL test persistence
Excel presentation
```

这一层已经比较完整。

## 2.2 M1 真实研究工作台

M1 已完成：

```text
20家真实样本预登记
6家 READABLE 深研档案
3家公司真实条件估值
真实 Quote
真实 Dividend lifecycle
真实公告扫描
PIT replay
PostgreSQL cold replay
42页 Excel
```

因此目前系统已经不是“纯架构原型”。

它已经能够：

> 对手工选定的一家公司进行有证据、有假设、有估值、有反证、有事件边界的研究。

## 2.3 人工 G3 已正式进入领域模型

新增：

```text
HumanResearchApprovalReceipt
```

以前：

```text
模型算出 Bear/Base/Bull
≈
容易被误认为模型通过
```

现在：

```text
ValuationResult
↓
HumanResearchApprovalReceipt
↓
是否允许继续价格研究
```

并且 approval 绑定：

```text
Valuation Hash
ResearchCase Hash
Facts Hash
Assumptions Hash
Model Version
```

依赖变化后旧批准不会自动继承。

这是正确方向。

## 2.4 事件材料性已经和标题扫描分离

新增：

```text
EventMaterialityDecision
EventMaterialityReview
```

当前支持：

```text
NOT_MATERIAL
MATERIAL_SUPPORTING_EVIDENCE
MATERIAL_ALREADY_INCORPORATED
MATERIAL_REQUIRES_RECALCULATION
MATERIAL_RISK_MONITOR
DUPLICATE_OR_DERIVED
REQUIRES_DECOMPOSITION
```

现在系统已经开始区分：

```text
“发现了公告”
```

和：

```text
“这个公告会不会改变投资模型”
```

## 2.5 决策前资格门已经建立

新增：

```text
PreDecisionEligibility
```

正向决策前现在至少要求：

```text
Research Gate
Human G3
Event Review
ModelValidity
PriceBridge
PriceAttractiveness policy
```

没有有效 G3 或有未处理重大事件：

```text
NOT_ELIGIBLE
```

这是未来 BUY / ADD Review 的正确基础。

---

# 3. 当前三家公司最新真实状态

## 格力 `000651`

当前：

```text
Human Approval = REJECTED_NEEDS_REWORK
ModelValidity = STALE
DecisionEligibility = NOT_ELIGIBLE
PriceAttractiveness = NOT_ASSESSABLE
```

这是正确结果。

主要原因：

```text
金融资产/财务公司/受限现金
法人层级可分配现金
关联/子公司往来
Bridge recoverability
```

仍未真正拆清。

## 华域 `600741`

当前：

```text
Human Approval = REJECTED_NEEDS_REWORK
Review Priority = HIGH
ModelValidity = VALID
DecisionEligibility = NOT_ELIGIBLE
PriceAttractiveness = NOT_ASSESSABLE
```

它是当前最适合快速完成第二轮 G3 的对象。

## 伊利 `600887`

当前：

```text
Human Approval = APPROVED_CONDITIONAL_LOW_CONFIDENCE
ModelValidity = STALE
DecisionEligibility = NOT_ELIGIBLE
PriceAttractiveness = NOT_ASSESSABLE
```

条件批准只意味着：

> 剩余收益模型可以继续作为低置信度研究工具。

并不表示：

```text
BUY
```

主要未完成：

```text
Cost of Equity sensitivity
Retention / Dividend consistency
Normalized ROE
Impairment classification
Buyback monitoring
```

---

# 4. 当前版本效果评价

从最终用户角度，当前成熟度应定义为：

| 层级 | 能力 | 当前状态 |
|---|---|---|
| L0 | 工程基础设施 | HEALTHY |
| L1 | 单公司研究工作台 | BASICALLY_READY |
| L2 | 主动机会发现 | NOT_STARTED |
| L3 | 可解释投资决策支持 | NOT_STARTED，只有前置门 |
| L4 | 组合与仓位 | NOT_STARTED |
| L5 | 每日持续监控 | NOT_STARTED |
| L6 | 有限真实使用 | NOT_READY |

因此：

> 当前已经可以帮助“研究一家公司”，但还不能可靠帮助“从市场找公司”，更不能直接依赖它决定真实买卖和仓位。

---

# 5. 当前最需要警惕的新技术债

## P0-1：`build_m1_post_review_receipts.py` 不能继续演化为投资规则引擎

当前文件约 1100 行。

其中存在：

```text
DECISION_SPECS
APPROVAL_SPECS
BRIDGE_SPECS
```

并写入公司级规则。

例如：

```text
000651
cash_and_liquid_financial_assets
haircut = 45% / 30% / 20%
```

以及：

```text
600741
haircut = 30% / 20% / 10%
```

这些数字当前没有修改 M1 冻结估值，只作为：

```text
research_arithmetic_only
```

所以暂时没有污染正式估值。

但这是一个重要警报：

> **未来绝不能让临时脚本中的人工数值变成正式 valuation assumption。**

---

# 6. 对该脚本的处理要求

立即把：

```text
scripts/build_m1_post_review_receipts.py
```

定位为：

```text
ONE_OFF_REVIEW_RECEIPT_GENERATOR
```

而不是 Core Engine。

要求：

1. 不允许 M2/M3/M4 调用其中的 `BRIDGE_SPECS` 作为投资参数；
2. haircut 必须显式标记 `stress_test_only=true`；
3. 任何未来进入正式估值的 haircut 必须来自：
   - 官方事实；
   - Versioned ValuationAssumption；
   - 有 basis/rationale/evidence/confidence 的人工假设；
4. 将公司级人工判断逐步迁移为 versioned receipt/config artifact，而不是继续增加 Python `if symbol`；
5. 本脚本完成历史复核后进入 maintenance-only 状态。

---

# 7. P0-2：当前 Bridge Review 仍不是真正重估

目前：

```text
BridgeContributionAssessment
```

已经建立，这是好事。

但当前脚本做的是：

```text
冻结旧估值
-
原旧 Bridge
=
倒推出 Operating Value

然后
+
新的 haircut bridge
```

用于展示研究敏感性。

这只能称作：

```text
Bridge Stress Review
```

不能称作：

```text
New Approved Valuation
```

真正 G3 v2 必须重新：

```text
Facts
+
Assumptions
+
Bridge
↓
ValuationModel
↓
new ValuationResult
↓
new HumanApproval
```

不能只在旧结果后面加一个 haircut 表。

---

# 8. P0-3：全量测试仍有 1 个历史失败

当前记录：

```text
2107 passed
6 skipped
1 failed
```

唯一失败：

```text
Moutai old daily_simulation_policy_implemented runtime pointer assertion
```

即使与本轮无关，也建议在启动 M2 前解决。

原因：

> 从 M2 开始全市场批量运行后，如果主分支长期允许“已知1失败”，未来真正的新失败很容易被掩盖。

要求：

```text
Full offline test suite
=
0 unexpected failures
```

如果确实是历史废弃契约：

显式：

```text
retire / rewrite / quarantine
```

不要长期留红。

---

# 9. P0-4：`current-stage-goal.md` 需要正式从 M1 切换

目前文件仍是：

```text
M1-FIXED-SAMPLE-RESEARCH-WORKBENCH
状态 DONE
```

且没有 active milestone。

在开始新开发前：

```text
M1 保持历史 DONE
```

然后用户正式授权：

```text
M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY
```

成为唯一活动目标。

不要继续往 M1 文件下面堆新功能。

---

# 10. 我的总体建议

现在不要继续把主要精力花在：

```text
格力
华域
伊利
```

三家公司无限精修。

它们已经完成了当前阶段最重要的任务：

> 暴露系统真实研究中的问题。

下一步真正影响产品可用性的，不是把三家公司全部批准，而是：

```text
整个A股
↓
系统能不能找到值得研究的公司？
```

因此建议正式进入 M2。

但在启动 M2 前先完成一个很短的：

```text
POST-M1-STABILIZATION
```

---

# 11. 阶段 A：POST-M1-STABILIZATION

## Goal

冻结上一轮人工复核能力，消除会污染下一阶段的技术债。

## Tasks

### A1
修复或正式退休唯一全量测试失败。

### A2
将 `build_m1_post_review_receipts.py` 标记为一次性复核工具。

增加防误用测试：

```text
M2/M3 production path
must not import
build_m1_post_review_receipts
```

### A3
所有临时 haircut 标记：

```text
stress_test_only
not_valuation_input
not_price_assessment_input
```

### A4
检查 Core 是否存在新：

```text
symbol == 000651
symbol == 600741
symbol == 600887
```

投资逻辑。

公司特例只允许存在：

```text
provider adapter
review receipt generator
versioned config
```

不允许进入：

```text
ResearchGate
ValuationRouter
PriceAttractiveness
Decision
Portfolio
```

### A5
更新 Authority：

```text
current-stage-goal.md
→ M2
```

### Acceptance

```text
Full offline tests = green
Core CI = green
M1 frozen hashes = unchanged
No production changes
```

完成后立即进入 M2。

---

# 12. 阶段 B：M2 Multi-Channel Opportunity Discovery

这是接下来真正最重要的产品阶段。

目标：

> 系统从“你给我股票，我研究”升级为“系统主动从 A 股找到值得你研究的股票”。

---

# 13. M2 的最终产品形态

```text
A股全市场
↓
UniverseSnapshot
↓
Data Health
↓
Multi-Channel Cheap Screening
↓
Candidate Pool
↓
Research Priority
↓
Supported Profile Routing
↓
Deep Research Queue
```

---

# 14. M2 必须先废除“单一 PE/PB 选股”

目前：

```text
market.py
```

依旧存在 legacy：

```text
PE <= 25
PB <= 3
Market Cap >= 5bn
```

它可以保留用于：

```text
baseline comparison
```

但必须明确：

```text
LEGACY_VALUE_SCREEN
```

不得作为最终候选排序依据。

---

# 15. M2 建立四个筛选通道

## Quality Channel

关注：

```text
ROIC / ROE
现金转换
利润稳定
毛利/净利稳定
资本强度
负债
再投资
```

目的：发现长期高质量企业。

## Dividend / Cash Return Channel

关注：

```text
Current Dividend Yield
Dividend History
DPS Growth
Payout
FCF Coverage
Debt
Capital Intensity
Distribution Stability
```

必须避免：

```text
高股息 = 好公司
```

周期高点和股价暴跌必须可识别。

## Value Channel

关注：

```text
FCF Yield
EV/EBIT
Normalized Earnings Yield
PB / ROE relationship
Balance Sheet
```

不是简单：

```text
PE低
```

## Cyclical Channel

关注：

```text
Current vs Normalized Earnings
Current Margin vs Historical Mid-cycle
Commodity / Cost Context
Balance Sheet
Dividend Normalization
```

必须防止：

```text
周期顶点低PE
→ 价值股
```

---

# 16. M2 不做全市场 DCF

正确成本结构：

```text
4000+家公司
↓
Cheap Screen
↓
数百候选
↓
更昂贵财务研究
↓
几十研究对象
↓
少量深度估值
```

禁止：

```text
4000家公司全部跑 Bear/Base/Bull
```

---

# 17. M2 建立 Candidate Reason

每个 Candidate 必须回答：

```text
Why selected?
Which channel?
Which metrics?
Which evidence?
Which data is missing?
Which profile may apply?
```

而不是：

```text
Score = 83
```

---

# 18. M2 建立 Research Priority

建议至少考虑：

```text
Business Quality
Financial Quality
Evidence Completeness
Valuation Readiness
Dividend Quality
Price Context
Uncertainty
Next Important Event
```

但不要制造单一万能分数。

可以使用：

```text
Priority Tier
+
Reasons
```

---

# 19. M2 Dashboard / Excel 板卡

完成 M2 后，Excel 至少增加/更新：

```text
全市场覆盖
Quality 候选
Dividend 候选
Value 候选
Cyclical 候选
Candidate Pool
新进入候选
移出候选
待深研
```

每家公司显示：

```text
Why Now
Channel
Evidence Date
Data Status
Profile Status
```

---

# 20. M2 Acceptance

M2 不能因为创建了 Channel class 就通过。

必须完成一次真实全市场：

```text
run-once
```

至少证明：

1. 全市场 Universe 分母完整；
2. 4 通道真实运行；
3. 缺失数据不会默认为0；
4. 银行/保险等不支持行业不会误套模型；
5. 每个候选都有进入原因；
6. 无候选是合法结果；
7. 至少从“系统主动发现”的公司里形成 3 份实质研究/否决报告；
8. PIT / rule version 可重放；
9. Legacy PE/PB 与新通道 shadow 对比；
10. Excel 能直接看到候选变化。

M2 完成后：

> 系统首次具备“主动找股票”的能力。

---

# 21. 阶段 C：M3 Explainable Decision Support

M2 解决：

```text
研究谁？
```

M3 解决：

```text
为什么买？
为什么不买？
为什么拿？
为什么卖？
```

---

# 22. M3 必须建立 Decision State

建议：

```text
INSUFFICIENT_RESEARCH
RESEARCH_CANDIDATE
WATCH
WAIT_FOR_PRICE
MANUAL_BUY_REVIEW
MANUAL_ADD_REVIEW
HOLD
MANUAL_REDUCE_REVIEW
MANUAL_EXIT_REVIEW
```

注意：

这些是 Human Review Signal，不是自动订单。

---

# 23. BUY_REVIEW 前置条件

至少：

```text
ResearchGate Ready
G3 Valid
Event Review Current
Valuation Usable
ModelValidity VALID
PriceBridge READY
PriceAttractiveness Assessable
No Thesis Breaker
Minimum confidence satisfied
PortfolioPreconditions present
```

缺一项：

```text
WAIT / RESEARCH
```

---

# 24. 必须生成 Buy Logic Card

每个：

```text
MANUAL_BUY_REVIEW
```

必须解释：

```text
为什么现在关注？
公司如何赚钱？
竞争优势？
核心回报来源？
市场可能错在哪里？
Bear/Base/Bull？
当前价格？
最大风险？
最强反证？
Thesis Breaker？
股息情况？
未来跟踪什么？
什么情况下不买？
```

目标：

> 用户阅读后可以不用看“BUY”两个字，也能自己解释为什么考虑买。

---

# 25. Entry Thesis Snapshot

当用户真的决定买入时，必须冻结：

```text
Entry Date
Entry Price
Research Version
Valuation Version
Thesis
Return Drivers
Mispricing
Bear/Base/Bull
Confidence
Dividend Thesis
Counter Evidence
Thesis Breakers
Reasons to Add
Reasons Not to Add
Reasons to Reduce
Reasons to Exit
```

没有 Entry Thesis，未来不允许系统假装知道为什么当初买。

---

# 26. ADD Review

不能：

```text
跌20%
→ 加仓
```

必须：

```text
Price down
+
Intrinsic Value intact
+
Thesis intact
+
Confidence intact/improved
+
Portfolio capacity available
```

才允许：

```text
MANUAL_ADD_REVIEW
```

---

# 27. EXIT Review

卖出必须回到：

```text
EntryThesisSnapshot
```

检查：

```text
Original Thesis
vs
Current Evidence
```

卖出至少分：

```text
THESIS_BROKEN
INTRINSIC_VALUE_IMPAIRED
EXTREME_OVERVALUATION
PORTFOLIO_RISK
OPPORTUNITY_COST
```

不能因为：

```text
涨了30%
or
跌了20%
```

机械卖出。

---

# 28. M3 Acceptance

至少：

1. 真实公司产生 Decision Card；
2. BUY / ADD / HOLD / REDUCE / EXIT 都有拒绝反例；
3. 至少一条完整 `Entry -> New Evidence -> Consistency -> Reduce/Exit` 历史 replay；
4. 每个决定都能回溯 Evidence Bundle；
5. 至少 3 张 Logic Card 经用户阅读；
6. 用户能够复述 `为什么买、什么情况下错、为什么卖`；
7. 无任何自动订单。

完成 M3 后：

> 系统才开始“初步指导交易决策”。

---

# 29. 阶段 D：M4 Portfolio / Position Guidance

M3 解决单股。

M4 解决：

```text
即使这家公司值得买，
我该买多少？
```

---

# 30. 用户必须提供 Investor Policy Statement

真实仓位建议前必须由用户明确：

```text
总投资资金
最低现金比例
单股最大仓位
行业最大仓位
周期股最大暴露
高股息资产目标
流动性需求
投资期限
是否允许集中投资
```

系统不能自行猜风险偏好。

---

# 31. Position Guidance

建议层级：

```text
ZERO
WATCH_ONLY
STARTER
NORMAL
ADD_ALLOWED
MAX_CAPACITY
STOP_ADDING
REDUCE_REVIEW
EXIT_REVIEW
```

不要直接给出伪精确比例，除非未来已有明确规则和可复算约束。

---

# 32. 仓位考虑因素

至少：

```text
Business Quality
Research Confidence
Valuation Confidence
Downside
Price Attractiveness
Dividend Sustainability
Thesis Strength
Single-name concentration
Industry concentration
Common risk
Existing position
Cash reserve
```

---

# 33. 股息组合视图

用户有长期现金分红目标，因此必须显示：

```text
Current Annual Dividend
Forward Declared Dividend
Normalized Dividend
Yield on Cost
Dividend Concentration
Dividend Sustainability Distribution
```

特别股息不能年化。

---

# 34. M4 Acceptance

至少：

1. 用户提供一份真实但私有 PortfolioSnapshot；
2. 总资产/现金/持仓可对账；
3. 私有数据不进公开 GitHub；
4. Starter/Normal/Max/Stop Adding 有明确规则；
5. 全现金、集中、分散三种反例测试；
6. 组合现金预算不会重复使用；
7. 股息收入 current/forward/normalized 分开；
8. 不连接券商自动下单。

完成 M4 后：

> 系统可以初步告诉用户“是否值得加仓、仓位是否过高、是否应该停止新增”。

---

# 35. 阶段 E：M5 Event-Driven Daily Monitoring

这是系统真正变成“日常工具”的关键阶段。

每天：

```text
行情
公告
财报
分红
回购
担保
资本结构
重大经营变化
```

进入：

```text
Change Detection
↓
Materiality
↓
Dependency Invalidation
↓
Bounded Recalculation
↓
Decision Review
```

---

# 36. 不允许每天全量深研

正确：

```text
New Event
↓
Affected Companies
↓
Affected Artifacts
↓
Only Recalculate Dependencies
```

---

# 37. 每日输出

最终每天只应该显示：

```text
新增候选
退出候选
进入重点关注
BUY Review
ADD Review
HOLD Review
REDUCE Review
EXIT Review
Thesis Risk
Dividend Risk
Data/Source Failure
```

全部为 0 完全合法。

---

# 38. 静默是产品能力

理想状态：

```text
今天没有重要变化
```

系统保持安静。

不要为了“每天有内容”制造消息。

---

# 39. M5 Acceptance

至少验证：

```text
duplicate events
late events
corrected filing
data source failure
price-only movement
Thesis Breaker
Dividend change
buyback update
model stale
restart recovery
```

必须能够：

```text
不重复通知
不漏掉Critical
恢复后继续
```

---

# 40. 阶段 F：M6 Initial Assisted Use

M6 不再大量开发新策略。

主要验证：

> 系统是否真的能够每天稳定帮助用户。

---

# 41. M6 Shadow Mode

正式使用前建议至少：

```text
20个连续交易会话
```

Shadow。

期间系统产生：

```text
候选
研究
Decision Review
Position Guidance
Events
```

但不自动交易。

用户观察：

```text
是否漏事件？
是否误报？
是否给出错误价格？
是否理由看不懂？
是否频繁变化？
```

---

# 42. M6 最终准入

只有达到：

```text
INITIAL_ASSISTED_USE
```

才建议开始把它当作日常辅助系统。

仍然不是：

```text
AUTO_TRADING_READY
```

---

# 43. 从用户角度的“什么时候算可用”

## Level A：现在

### 可以
- 查看固定样本研究；
- 看三家公司研究边界；
- 查看证据；
- 看条件估值；
- 看股息研究；
- 作为辅助学习/研究工具。

### 不应该
- 根据系统直接买卖；
- 根据格力/华域条件估值直接判断便宜；
- 根据股息率直接买；
- 依赖它扫描全市场。

## Level B：M2 后

系统可以：

```text
全A股
→
自动找值得研究的公司
```

这时已经非常有实际价值。

## Level C：M3 + M4 后

系统可以初步：

```text
BUY Review
ADD Review
HOLD
REDUCE Review
EXIT Review
Position Guidance
```

并解释为什么。

这时可以开始：

> **有限度地辅助真实投资决策。**

仍应人工最终确认。

## Level D：M5 + M6 后

系统达到：

```text
每日自动筛选
持续跟踪
重大变化提醒
决策理由更新
仓位复核
股息跟踪
```

才真正接近最终产品目标。

---

# 44. 项目可用时间预估

以下是项目工程进度估算，不是收益承诺，也不是固定工期。

假设：

- 继续使用长时间 Codex Goal Run；
- 不同时开发 Web；
- 暂不增加银行/保险估值模型；
- 当前数据源基本可用；
- 用户可以在 M3/M4 提供必要人工确认；
- 不发生大型架构返工。

## 44.1 达到“自动筛重点关注公司”

需要：

```text
POST-M1 Stabilization
+
M2
```

预计：

> **约 1～2 周的集中开发/真实数据验收。**

主要不确定性不是代码，而是：

```text
全市场数据完整性
历史/PIT
四通道误筛检查
数据源限流
```

## 44.2 达到“初步辅助买入/加仓/持有/卖出判断”

需要：

```text
M2
+
M3
```

并建议至少接入 M4 的最小组合约束。

预计：

> **约 2～4 周可以进入第一版人工辅助投资阶段。**

这时目标不是“系统替你交易”，而是：

```text
系统给出值得复核的信号
+
完整理由
+
原始Thesis
+
风险
+
价格条件
```

你自己决定。

## 44.3 达到“仓位管理 + 每日跟踪”

需要：

```text
M4
+
M5
```

如果前面阶段顺利：

> **约 3～5 周可以形成工程上可运行的日常版本。**

但此时仍建议 Shadow。

## 44.4 达到“我认为可以开始长期依赖”的版本

M6 当前路线要求：

```text
至少20个连续交易会话 shadow
```

20 个交易会话本身通常需要约：

```text
4～5个自然周
```

因此即使开发很快，也不能靠一天跑很多测试替代真实时间观察。

综合考虑：

> **较现实的 `INITIAL_ASSISTED_USE` 时间窗口约为 6～10 周。**

如果 M2/M3/M4/M5 开发非常顺利：

```text
前2～4周
完成主要产品能力

随后4～5周
Shadow / 事件 / 数据稳定性验证
```

---

# 45. 哪些情况会明显拉长时间

以下任一项会增加周期：

```text
要求银行/保险马上进入正式估值
要求所有A股都有估值
生产数据源频繁失效
需要更换行情供应商
生产PostgreSQL迁移出现问题
要同时开发Web
要直接接券商
要做自动交易
要做完整历史回测调参
```

这些全部应该推迟。

---

# 46. 现在最合理的目标顺序

严格建议：

```text
POST-M1 Stabilization
↓
M2 Opportunity Discovery
↓
M3 Explainable Decisions
↓
M4 Portfolio Guidance
↓
M5 Daily Monitoring
↓
M6 Shadow / Initial Assisted Use
```

不要跳。

---

# 47. 下一阶段 Codex 的核心授权

现在应正式授权：

# `M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`

但在 M2 正式业务扩展前：

先自动完成本手册：

```text
POST-M1-STABILIZATION
```

全部 P0 项。

这是同一个 Goal Run 的前置工作，不需要另外浪费一个长期阶段。

---

# 48. Codex 执行纪律

每次开始：

```text
git status
branch
HEAD
dirty files
latest CI
```

不得覆盖用户无关改动。

每个工作包必须报告：

```text
Engineering Status
Research Status
Data Status
Tests
Real Data Validation
Known Blockers
Changed Files
Commit
```

不得因为：

```text
unit tests pass
```

就宣布 Milestone 完成。

必须满足：

```text
真实数据
真实公司
真实运行
可读输出
PIT
反例
Fail-closed
```

---

# 49. Commit 原则

建议：

```text
M2.0 Post-M1 stabilization
M2.1 Universe and channel contracts
M2.2 Quality + Dividend
M2.3 Value + Cyclical
M2.4 Candidate / priority / funnel
M2.5 Full-market run-once
M2.6 Excel dashboard + replay
M2.7 Acceptance + freeze
```

不要形成超大单一 commit。

---

# 50. 当前禁止事项

直到 M6 前都禁止：

```text
自动下单
券商API
自动仓位交易
杠杆
期权
追求回测最高收益
因为系统没有BUY而调低标准
银行/保险强套现有模型
所有A股全量DCF
复杂Web产品化
```

---

# 51. 用户需要参与的节点

## M2

用户只需：

```text
抽查候选是否“看起来有研究价值”
```

不需要逐条审批。

## M3

用户需要阅读至少：

```text
3张 Decision Logic Card
```

确认：

```text
我能理解为什么买
我知道什么情况下逻辑错误
```

## M4

用户必须提供真实：

```text
总资金
当前持仓
现金
仓位约束
风险偏好
股息目标
```

这些数据应保存在私有环境，不进入公开 Git。

## M6

用户需要判断：

```text
每天的提醒是否有用
是否太吵
是否漏重要事件
买卖理由是否一致
```

---

# 52. 最终产品验收问题

最终系统必须让我能够回答：

```text
今天哪些公司值得重点关注？

为什么？

哪些正在等待更好的价格？

哪些已经具备 BUY Review 条件？

我为什么考虑买它？

如果跌20%，为什么该加或不该加？

为什么继续持有？

什么事实会让我停止加仓？

什么事实会让我减仓？

卖出时，是估值原因还是原始Thesis已经破坏？

我的仓位是否太集中？

我的股息收入是否可持续？

今天有没有需要重新检查持仓的重要事件？
```

如果系统不能回答这些问题：

无论测试数量多少，都不能称为最终可用。

---

# 53. 本轮建议 Codex 最终输出

执行本手册后，每个大阶段都使用统一报告：

```text
HEAD:
Milestone:
Status:

PRODUCT CAPABILITY:
...

REAL DATA COVERAGE:
...

CURRENT USER-VISIBLE OUTPUT:
...

WHAT SYSTEM CAN NOW DO:
...

WHAT SYSTEM STILL CANNOT DO:
...

FAIL-CLOSED CASES:
...

TESTS:
...

KNOWN RISKS:
...

NEXT SINGLE MILESTONE:
...
```

---

# 54. 当前最终判断

当前项目不是失败，也不是“快做完了”。

更准确的状态是：

> **研究内核和安全门已经建立，单公司研究工作台初步成立；但真正决定用户体验的机会发现、决策解释、组合管理和持续监控仍在前面。**

当前最大的优势：

```text
架构边界越来越正确
Fail-closed越来越真实
研究事实开始接入真实公司
```

当前最大的风险：

```text
继续在单个公司和临时脚本上消耗时间
而迟迟没有做真正的 Opportunity Discovery
```

因此接下来应坚定进入：

```text
M2
```

让系统第一次真正回答：

> **“整个A股里，现在我应该看谁？”**

这是从“研究工程”走向“投资工具”的下一个真正里程碑。
