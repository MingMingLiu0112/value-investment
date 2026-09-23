# A股价值投资 Agent：M1 后人工复核纠偏与 M3/M5 决策门升级（Codex 可执行版）

**版本**：v1.0
**日期**：2026-09-23
**仓库**：`MingMingLiu0112/value-investment`
**执行基线**：`cbec189f38dc489105eae7f18ba2535ba95478d8`
**基线提交**：`Close M1 workbench and defer decision-stage reviews`

---

# 0. 本文性质

本文不是新的 North Star，不替代 `AGENTS.md`、`LONG-TERM-GOAL.md`、`docs/architecture.md` 或 `docs/current-stage-goal.md`。

本文的作用是：

> 将 M1 结束后已经完成的一轮人工投资研究复核，转换成可追溯、可编码、可测试、可进入 M3/M5 的正式执行输入。

本轮必须保留以下边界：

- **M1 保持 DONE，不重新打开 M1 验收。**
- 不修改 M1 冻结收据、Hash、历史估值包来“凑通过”。
- 不把 G3 批准解释为买入信号。
- 不把 PriceBridge READY 解释为价格吸引力。
- 不把 Bear/Base/Bull 解释为目标价。
- 不把高股息率解释为买入理由。
- 不产生真实订单。
- 不改变现有 `action=no_order` 边界。
- 所有新的人工批准、事件判断和重估必须通过**新版本 append-only artifact / receipt** 表达。
- 不允许用 `symbol == "000651"` 等分支把本轮规则写死到 Core；公司差异通过数据包、review receipt、profile、policy 表达。

---

# 1. 本轮总目标

将当前：

```text
M1 Research Workbench
    ↓
conditional_research_only
    ↓
G3 / Event Materiality deferred
```

推进为：

```text
ValuationResult
    ↓
HumanResearchApprovalReceipt
    ↓
EventMaterialityReview
    ↓
ModelValidity
    ↓
PriceBridge
    ↓
PreDecisionEligibility
```

使系统能够准确区分：

```text
模型能算
≠
模型值得信任

模型值得研究
≠
价格值得研究

价格值得研究
≠
可以买入
```

本轮重点不是继续增加更多公司，而是把“人工投资判断”正式建模，避免未来 M3/M5 继续依赖 Markdown 中一句“批准/不批准”。

---

# 2. 人工复核正式结论

以下结论视为本轮由投资研究负责人提供的正式人工研究输入。

## 2.1 格力电器 `000651`

### G3 结论

```text
REJECTED_NEEDS_REWORK
```

### 解释

保留：

```text
profile = mature_manufacturing
model = FCFF
```

但**当前 G3 不批准**。

不是因为 FCFF 方法错误，而是当前 Equity Bridge 中大量非经营金融资产、现金和长期金融资产直接进入股东价值，而这一部分恰好仍存在：

- 财务公司范围未充分拆分；
- 受限现金未充分拆分；
- 法人层级可分配现金未确认；
- 金融资产真实可回收价值未做 haircut；
- 关联/子公司资金往来可能影响可实现价值；
- 当前约束下无法证明所有账面金融资产都可以接近 100% 转化为普通股股东可获得价值。

当前模型的非经营性资产桥接对 Bear/Base/Bull 的贡献过大，因此：

> **当前估值区间可以继续作为研究算术存在，但不得作为人工批准的研究估值包络。**

### 当前允许状态

```text
ValuationResult = conditional_research_only
HumanResearchApproval = REJECTED_NEEDS_REWORK
PriceAttractiveness = NOT_ASSESSABLE
DecisionEligibility = NOT_ELIGIBLE
action = no_order
```

---

## 2.2 华域汽车 `600741`

### G3 结论

```text
REJECTED_NEEDS_REWORK
```

但属于：

```text
PRIORITY_FOR_FAST_REREVIEW
```

### 解释

FCFF 方法与成熟汽车零部件制造商的经济特征基本匹配，可以继续保留。

当前主要问题不是整个模型不可用，而是：

- non-operating assets 对股东价值贡献较高；
- 上汽财务公司存款安全性证据只能支持其中一部分资产；
- 不能由财务公司风险评估直接推出全部金融资产按账面 100% 可实现；
- WACC 仍是 generic proxy；
- ROIC / incremental ROIC 未验证；
- 客户集中度、整车降价和供应商价格传导尚未量化到 EBIT / Margin / Working Capital；
- 2026H1 当前利润下降需要继续进入正常化假设。

### 当前允许状态

```text
ValuationResult = conditional_research_only
HumanResearchApproval = REJECTED_NEEDS_REWORK
review_priority = HIGH
PriceAttractiveness = NOT_ASSESSABLE
DecisionEligibility = NOT_ELIGIBLE
action = no_order
```

华域完成本文件指定的小范围修正后，应成为三家公司中优先重新提交 G3 的对象。

---

## 2.3 伊利股份 `600887`

### G3 结论

```text
APPROVED_CONDITIONAL_LOW_CONFIDENCE
```

### 解释

当前 `quality_compounder -> residual_income_or_equity_value` 的经济模型与企业结构基本匹配。

人工批准的含义仅为：

> 当前剩余收益模型可作为低置信度、条件性的研究包络继续使用。

不代表：

- 当前股价有吸引力；
- Bull 值是目标价；
- 可以买入；
- 可以产生仓位。

当前仍有重要条件：

- Cost of Equity 使用 generic beta=1，必须补 sensitivity；
- Retention 与 Dividend Policy 当前相互独立，必须建立一致性；
- 资产减值与利润下降必须进入 normalized ROE；
- ROIC / incremental ROIC 仍缺；
- 回购/注销对未来股数和现金的影响只能在实际发生后进入事实层。

### 当前允许状态

```text
HumanResearchApproval = APPROVED_CONDITIONAL_LOW_CONFIDENCE
research_use = ALLOWED
positive_price_decision = NOT_ALLOWED_UNTIL_CONDITIONS_RESOLVED
PriceAttractiveness = NOT_ASSESSABLE
action = no_order
```

不得因为本次 G3 条件批准直接把：

```text
PriceAttractiveness
```

从 `NOT_ASSESSABLE` 改成正向状态。

---

# 3. 必须新增正式 Human Research Approval Contract

不要继续让 G3 依赖：

```text
ResearchCase.valuation_status
```

中的人工字符串。

新增独立领域对象，建议：

```text
src/value_investment_agent/human_research_approval.py
```

建议 dataclass：

```python
HumanResearchApprovalReceipt
```

至少包含：

```text
approval_id
symbol
security_id
profile_id

valuation_artifact_id
valuation_artifact_sha256
valuation_model_id
valuation_model_version

research_case_id / hash
assumption_set_id / hash
facts_artifact_id / hash

reviewed_at
review_as_of

reviewer_type
decision

conditions
remaining_blockers
required_followups
reopen_triggers

evidence_refs

decision_version
created_at
action = no_order
```

---

# 4. G3 状态重新定义

不要只有：

```text
approved = true / false
```

至少支持：

```text
PENDING_HUMAN_REVIEW

REJECTED_NEEDS_REWORK

APPROVED_CONDITIONAL_LOW_CONFIDENCE

APPROVED_RESEARCH_ONLY

SUPERSEDED
```

语义：

## PENDING_HUMAN_REVIEW

尚无人工判断。

## REJECTED_NEEDS_REWORK

当前模型/事实/假设中存在足以影响估值可信性的重大未解决问题。

模型可以保存，但：

```text
G3 = fail
PriceAttractiveness = NOT_ASSESSABLE
```

## APPROVED_CONDITIONAL_LOW_CONFIDENCE

模型结构合理、范围可用于研究，但仍存在重要低置信度假设。

允许：

```text
研究
敏感性
反向估值
比较
```

但是否允许进入价格吸引力判断，应由 receipt 中显式字段控制，例如：

```text
price_assessment_eligible = false
```

不得仅凭 status 名称推断。

## APPROVED_RESEARCH_ONLY

模型基础已达到人工研究批准，但仍不等于 BUY。

## SUPERSEDED

该批准对应的估值 artifact 已被新版本替换。

---

# 5. Approval Receipt 必须绑定具体 artifact

这是硬约束。

G3 不能批准：

```text
symbol = 600887
```

而必须批准：

```text
600887
+
specific valuation artifact hash
+
specific facts hash
+
specific assumption hash
```

如果任一关键依赖变化：

```text
facts changed
assumptions changed
model version changed
material event changed
valuation payload changed
```

则旧 receipt 不能自动继续有效。

至少测试：

```text
approval_receipt.valuation_artifact_sha256
==
current_valuation.sha256
```

不相等：

```text
approval = SUPERSEDED / STALE
```

不得静默继承。

---

# 6. 新增 Event Materiality Decision Contract

当前 `event_scan.py` 的职责应该保持：

> 机器发现公告、去重、初步候选分类。

不要让扫描器直接变成最终材料性裁判。

建议新增：

```text
src/value_investment_agent/event_materiality.py
```

建立：

```python
EventMaterialityDecision
```

至少字段：

```text
event_decision_id

symbol
announcement_id
title
published_at

source_ref
source_sha256

machine_candidate_reason

human_decision
affected_domains
affected_fact_fields
affected_assumptions
affected_artifacts

requires_recalculation
requires_model_stale
requires_followup

supersedes_event_id
event_cluster_id

reviewed_at
reviewer_type
review_notes

decision_version
action = no_order
```

---

# 7. Event Materiality 不再只用 true / false

支持：

```text
NOT_MATERIAL

MATERIAL_SUPPORTING_EVIDENCE

MATERIAL_ALREADY_INCORPORATED

MATERIAL_REQUIRES_RECALCULATION

MATERIAL_RISK_MONITOR

DUPLICATE_OR_DERIVED

REQUIRES_DECOMPOSITION
```

## NOT_MATERIAL

不影响当前 Facts / Assumptions / ModelValidity。

## MATERIAL_SUPPORTING_EVIDENCE

对现有判断提供新的支持，但不改变输入。

例如某项风险评估增强金融资产安全性证据。

## MATERIAL_ALREADY_INCORPORATED

事件重要，但当前模型使用的 Facts / Assumptions 已经包含该信息。

不得重复把模型打成 STALE。

## MATERIAL_REQUIRES_RECALCULATION

事件影响关键事实、假设、股数、现金、资本配置或估值。

必须：

```text
ModelValidity -> STALE
```

直到新 artifact 完成。

## MATERIAL_RISK_MONITOR

当前不足以要求立即重算，但属于必须持续跟踪的风险/资本配置事件。

## DUPLICATE_OR_DERIVED

摘要、债权人通知、前十名股东等由主事件派生。

必须关联主 `event_cluster_id`，避免重复触发。

## REQUIRES_DECOMPOSITION

单份公告包含多个事实，其中部分可能重要。

不得直接写成“不重要”。

---

# 8. 24 条公告人工分类结果

以下分类作为本轮初始人工复核输入。

Codex 在落库前必须：

1. 绑定对应原 PDF SHA；
2. 确认 announcement ID 与原 packet 一致；
3. 如果 PDF 内容与以下人工结论存在明显事实冲突，停止该条写入并报告；
4. 不得自行把“不确定”强改为 NOT_MATERIAL。

---

## 8.1 格力电器 `000651`

### `1225542476` 回购进展

```text
MATERIAL_RISK_MONITOR
```

理由：

- 回购/注销属于重要资本配置；
- 当前“进展公告”本身不一定意味着立即重算；
- 实际回购金额、注销股数、现金支出达到模型重要性阈值后再更新 Facts / Shares。

建立 Event Cluster：

```text
GREE_BUYBACK_2026
```

---

### `1225515009` “质量回报双提升”行动方案进展

```text
NOT_MATERIAL
```

除非正文存在新的量化资本配置承诺或正式财务目标。

若发现具体新承诺：

```text
REQUIRES_DECOMPOSITION
```

---

### `1225515008` 会计政策变更

```text
NOT_MATERIAL
```

前提：

正文确认不对主要资产、负债、权益、收入、利润产生重大影响。

保留 PDF 与 review note。

---

### `1225515007` 子公司之间提供担保

```text
MATERIAL_RISK_MONITOR
```

当前不直接调整 FCFF。

进入：

```text
balance_sheet_risk
capital_allocation
```

监控。

如果担保金额、逾期、代偿或风险敞口达到实质性：

```text
MATERIAL_REQUIRES_RECALCULATION
```

---

### `1225515005` 非经营性资金占用及其他关联资金往来

```text
MATERIAL_REQUIRES_RECALCULATION
```

这是格力本轮最重要的事件之一。

它直接影响：

```text
cash recoverability
legal entity cash availability
related-party receivables
non-operating asset bridge
```

当前 G3 拒绝与该问题直接相关。

---

### `1225515004` 2026H1 半年报

```text
MATERIAL_ALREADY_INCORPORATED
```

重要，但已经作为当前模型最新 Facts 来源。

不得因为“重大”再次重复 STALE。

---

### `1225515003` 2026H1 摘要

```text
DUPLICATE_OR_DERIVED
```

主事件：

```text
1225515004
```

---

## 8.2 华域汽车 `600741`

### `1225516580` 上汽财务公司风险评估报告

```text
MATERIAL_SUPPORTING_EVIDENCE
```

作用：

- 支持财务公司存款的安全/流动性判断；
- 不能推广为全部 non-operating assets 100% 可实现。

写入：

```text
bridge_evidence
financial_company_risk
```

---

### `1225516573` 2026H1 半年报

```text
MATERIAL_ALREADY_INCORPORATED
```

---

### `1225516560` 重大信息内部报告制度

```text
NOT_MATERIAL
```

除非正文包含会改变经济权利或资本结构的实质性变化。

---

### `1225516550` 2026H1 摘要

```text
DUPLICATE_OR_DERIVED
```

主事件：

```text
1225516573
```

---

## 8.3 伊利股份 `600887`

### `1225568022` 回购报告书

```text
MATERIAL_RISK_MONITOR
```

资本配置重要。

暂不直接修改 ordinary shares。

只有实际回购并注销/完成资本变更后，新的股数才能进入 Facts。

建立 Event Cluster：

```text
YILI_BUYBACK_2026
```

---

### `1225568017` 回购股份减少注册资本通知债权人

```text
DUPLICATE_OR_DERIVED
```

归属：

```text
YILI_BUYBACK_2026
```

---

### `1225559652` 为控股子公司提供担保进展

```text
MATERIAL_RISK_MONITOR
```

进入：

```text
balance_sheet_risk
distribution_sustainability
```

当前不机械重算估值。

出现：

```text
逾期
代偿
大幅新增风险敞口
```

时升级。

---

### `1225559649` 回购事项前十名股东持股情况

```text
NOT_MATERIAL
```

归属于回购信息披露流程。

---

### `1225547701` 2023 年持股计划持有人会议

```text
NOT_MATERIAL
```

如仅为计划管理事项。

若涉及重大新发行/稀释：

```text
REQUIRES_DECOMPOSITION
```

---

### `1225547678` 长期服务计划持有人会议

```text
NOT_MATERIAL
```

同样保留稀释检查。

---

### `1225536213` 回购事项前十名股东持股情况

```text
NOT_MATERIAL
```

---

### `1225511505` 2026H1 摘要

```text
DUPLICATE_OR_DERIVED
```

主事件：

```text
1225511409
```

---

### `1225511493` 计提资产减值准备

```text
MATERIAL_REQUIRES_RECALCULATION
```

原因：

当前模型虽然已经看到 H1 ROE/利润下滑，但还需要明确：

```text
reported ROE
vs
normalized ROE
```

并判断减值属于：

```text
一次性资产清理
or
并购资本配置失败
or
业务长期盈利能力恶化
```

必须更新：

```text
normalized ROE review
capital allocation assessment
counter evidence
thesis breaker monitoring
```

---

### `1225511474` 募集资金存放、管理与实际使用

```text
REQUIRES_DECOMPOSITION
```

检查：

```text
unused funds
project delay
changed use
return on reinvestment
```

如果无重大偏离：

```text
NOT_MATERIAL
```

如存在大额项目延期/用途变化：

```text
MATERIAL_RISK_MONITOR
or
MATERIAL_REQUIRES_RECALCULATION
```

---

### `1225511473` 8/27 回购方案

```text
DUPLICATE_OR_DERIVED
```

作为：

```text
YILI_BUYBACK_2026
```

主事件的早期版本。

最新主版本以正式回购报告书为准，但历史 PIT 不得删除。

---

### `1225511470` 2026H1 经营数据

```text
MATERIAL_ALREADY_INCORPORATED
```

用于：

```text
BusinessQuality
Thesis
product/channel mix
```

---

### `1225511409` 2026H1 半年报

```text
MATERIAL_ALREADY_INCORPORATED
```

---

# 9. ModelValidity 与 EventMateriality 的新关系

修改 `model_validity.py` / Application 聚合逻辑时遵守：

```text
NOT_MATERIAL
→ validity unaffected

MATERIAL_SUPPORTING_EVIDENCE
→ validity unaffected
→ can update confidence/evidence only through new versioned artifact

MATERIAL_ALREADY_INCORPORATED
→ validity remains valid if event evidence/hash is already bound to current input package

MATERIAL_REQUIRES_RECALCULATION
→ STALE

MATERIAL_RISK_MONITOR
→ validity may remain VALID
→ review_due = true / monitored risk

DUPLICATE_OR_DERIVED
→ no independent invalidation

REQUIRES_DECOMPOSITION
→ decision eligibility blocked until decomposed
```

不要再使用：

```text
标题出现“回购”
→ STALE
```

这种机械规则。

也不要：

```text
machine scan no confirmed event
→ COMPLETE_NO_MATERIAL_EVENT
```

自动解释为正式材料性完成。

---

# 10. 决策前必须增加 PreDecision Eligibility Gate

即使完整 M5 Event Engine 尚未完成，M3 的任何正向价格/交易复核之前必须要求：

```text
HumanResearchApprovalReceipt valid
+
material event review current through decision_as_of
```

建议新增：

```python
PreDecisionEligibility
```

或放入未来 `InvestmentDecisionReview` 前置检查。

至少验证：

```text
G3 approval valid for current valuation hash

no unresolved MATERIAL_REQUIRES_RECALCULATION

no unresolved REQUIRES_DECOMPOSITION

event_review_watermark >= decision_as_of required watermark

ModelValidity != STALE / INVALID

PriceBridge == READY
```

否则：

```text
WAIT / RESEARCH
```

不得：

```text
BUY_REVIEW
ADD_REVIEW
```

---

# 11. “未经审计半年报”规则调整

当前多个 ResearchCase 把：

```text
H1 2026 interim report is unaudited
```

作为 blocker。

这需要重新分级。

默认规则：

```text
合法法定半年报
+
来源 verified
+
无已知更正/冲突
```

应作为：

```text
CONFIDENCE_MODIFIER
```

而不是自动：

```text
HARD_BLOCKER
```

只有以下情况才升级：

```text
reported data conflict
subsequent correction
scope mismatch
audit qualification related evidence
material accounting uncertainty
```

实现时不要删除原历史 blocker。

生成新版本 ResearchCase / ReviewResult 说明：

```text
previous classification = blocker
new classification = confidence_modifier
reason = policy correction
```

保留版本链。

---

# 12. 新增 Bridge Contribution Review

这是本轮非常重要的通用能力。

建议新增：

```text
src/value_investment_agent/valuation_bridge_review.py
```

定义：

```python
BridgeContributionAssessment
```

至少输出：

```text
symbol
valuation_scenario

operating_enterprise_value

gross_non_operating_assets
debt
minority_interest
other_claims

net_equity_bridge

net_bridge_per_share

total_equity_value
total_value_per_share

bridge_share_of_equity_value

bridge_components

confidence
blockers
evidence_refs
```

目的：

让用户能一眼看到：

```text
公司经营业务值多少
+
账外/非经营资产值多少
-
债务/少数股东
=
最终股东价值
```

---

# 13. Bridge Component 必须支持 haircut

不要继续默认：

```text
所有 non-operating asset = 100% book value
```

建议：

```python
BridgeComponentAssessment
```

字段：

```text
name
book_value

legal_availability
liquidity
recoverability

bear_haircut
base_haircut
bull_haircut

bear_recoverable_value
base_recoverable_value
bull_recoverable_value

basis
confidence
evidence_refs
blockers
```

haircut 不得凭空硬编码。

来源必须是：

```text
official evidence
materiality judgment
explicit conservative assumption
```

未知：

```text
UNKNOWN
```

不得默认 100%。

---

# 14. 格力专项调整

不要修改：

```text
config/m1-valuation-packages-v1/000651-fcff.json
```

历史文件。

创建：

```text
000651 ... v2
```

或相同 append-only version mechanism。

必须完成：

## GREE-1：Bridge 拆分

至少拆：

```text
unrestricted cash

restricted cash

finance-company assets

debt / certificates / highly liquid financial investments

long-term equity investments

other financial assets

related-party / subsidiary receivables

investment property

interest-bearing debt

minority interest
```

---

## GREE-2：资金往来材料性

将公告：

```text
1225515005
```

绑定到 Bridge Review。

回答：

```text
哪些资产不能按100%实现？
哪些是经营周转？
哪些是关联/子公司资金？
哪些存在法人与合并口径差异？
```

---

## GREE-3：Bridge Haircut Scenarios

重算：

```text
Bear
Base
Bull
```

各自独立 Bridge。

禁止继续三种情景完全复用同一巨额 non-operating asset value。

---

## GREE-4：WACC sensitivity

当前 8.5% generic WACC 保留为旧包输入。

新包必须增加敏感性。

不要为了过 G3 随便制造 issuer beta。

如果仍没有公司特定 beta/credit spread：

```text
confidence = low
```

并运行合理 bounded sensitivity。

---

## GREE-5：ROIC

计算至少：

```text
historical ROIC proxy
incremental ROIC proxy
```

如果无法可靠拆出：

明确：

```text
NOT_VERIFIED
```

不要伪造。

---

## GREE-6：重新提交 G3

只有当：

```text
Bridge uncertainty no longer dominates valuation conclusion
```

时才重新申请。

否则继续：

```text
REJECTED_NEEDS_REWORK
```

---

# 15. 华域专项调整

创建新的 v2 research/valuation artifact，不覆盖原 M1。

## HUAYU-1：Bridge 拆分

区分：

```text
cash
SAIC Finance deposits
debt investments
long-term equity investments
other financial assets
investment property
debt
minority
```

---

## HUAYU-2：财务公司证据

公告：

```text
1225516580
```

作为：

```text
MATERIAL_SUPPORTING_EVIDENCE
```

仅提升对应财务公司存款项的 confidence。

禁止扩张到全部金融资产。

---

## HUAYU-3：Haircut sensitivity

至少证明：

> 即使部分 non-operating assets 按保守折价，模型是否仍保持同一研究结论方向。

不要要求结果必须便宜。

如果结论高度依赖 100% book value：

G3 继续拒绝。

---

## HUAYU-4：经营风险映射

把：

```text
customer concentration
OEM price pressure
external customer expansion
```

至少映射到：

```text
EBIT
margin
working capital
```

的 Bear/Base/Bull rationale。

不要求制造复杂行业模型，但禁止只停留在文字。

---

## HUAYU-5：WACC / ROIC sensitivity

同格力。

---

## HUAYU-6：Fast Re-review

华域修正后优先进入重新 G3。

如果：

```text
model direction robust
+
bridge no longer dominates unfairly
+
remaining assumptions explicitly low confidence
```

可以批准：

```text
APPROVED_CONDITIONAL_LOW_CONFIDENCE
```

但不能自动。

---

# 16. 伊利专项调整

原 M1 估值不覆盖。

新增 v2。

当前 Human Approval Receipt 先记录：

```text
APPROVED_CONDITIONAL_LOW_CONFIDENCE
```

绑定当前 artifact hash。

---

## YILI-1：Cost of Equity sensitivity

当前：

```text
8%
```

不能继续作为 Bear/Base/Bull 唯一折现率而不做敏感性。

构建：

```text
cost_of_equity sensitivity
```

但不要伪造 issuer beta。

---

## YILI-2：Retention / Dividend Consistency

当前：

```text
retention = 30%
```

同时存在高现金派息政策。

必须建立一致关系：

```text
earnings
↓
distribution
↓
retention
↓
book equity growth
↓
future ROE / residual income
```

至少确保：

```text
retention assumption
+
dividend policy
+
book-value growth
```

不会互相矛盾。

---

## YILI-3：Impairment-normalized ROE

公告：

```text
1225511493
```

必须建立：

```text
reported ROE
normalized ROE range
```

不允许简单把减值全部加回。

需要判断：

```text
one-off cleanup
vs
recurring capital allocation failure
```

如果无法确定：

用 Bear/Base/Bull 或 uncertainty range。

---

## YILI-4：回购

建立：

```text
YILI_BUYBACK_2026
```

事件集。

当前不得直接减少普通股股数。

只有：

```text
actual repurchase
+
cancellation / registered capital change
```

形成可验证事实后，才更新 shares。

同时监控现金使用。

---

## YILI-5：Price Assessment

即使 G3 已条件批准：

完成：

```text
Cost of Equity sensitivity
Retention consistency
Normalized ROE
Materiality decisions
```

前保持：

```text
PriceAttractiveness = NOT_ASSESSABLE
```

完成后才允许 PriceAttractivenessPolicy 正常工作。

不得硬编码结果。

---

# 17. G3 不应该和 PriceAttractiveness 混在一起

必须保持：

```text
Human G3 Approval
=
“这个模型能否作为研究估值使用？”
```

而：

```text
PriceAttractiveness
=
“当前市场价格相对已批准研究价值是否具有研究吸引力？”
```

顺序：

```text
Valuation
↓
HumanResearchApproval
↓
ModelValidity
↓
PriceBridge
↓
PriceAttractiveness
```

没有有效 G3 approval：

```text
PriceAttractiveness = NOT_ASSESSABLE
```

---

# 18. 决策层未来硬规则

立即写入 Architecture / Methodology：

任何未来：

```text
MANUAL_BUY_REVIEW
MANUAL_ADD_REVIEW
```

必须同时满足：

```text
G0-G2 ready
G3 approval valid
ModelValidity valid
EventMateriality current
PriceBridge ready
PriceAttractiveness policy assessable
No confirmed Thesis Breaker
Portfolio Preconditions present
```

缺任何核心项：

```text
WAIT / RESEARCH
```

不得生成正向买入复核。

---

# 19. Excel / Presentation 调整

M1 原 42 页工作簿不作为本轮历史冻结对象修改来源。

如果需要发布新版本：

必须使用现有原子 publisher / Hash 保护机制。

建议在未来 M3 页面加入：

## Valuation Review

显示：

```text
G3 Status

Review Date

Valuation Artifact Hash

Remaining Conditions

Price Assessment Eligible?
```

---

## Bridge Contribution

显示：

```text
Operating Value
Non-operating Asset Bridge
Debt
Minority
Net Bridge
Bridge % of Equity Value
```

并按 Bear/Base/Bull 展示。

---

## Event Materiality

显示：

```text
Event
Machine Candidate
Human Decision
Already Incorporated?
Requires Recalc?
Monitor?
```

---

## 人工批准边界

醒目标注：

```text
G3 APPROVED
≠
BUY
```

---

# 20. 不要把所有公告交给用户逐条人工读

本轮有 24 条是人工复核样本。

未来 M5 设计必须逐步做到：

```text
Machine discovery
↓
duplicate clustering
↓
rule triage
↓
document content analysis
↓
materiality candidate
↓
human only for material / ambiguous cases
```

目标：

用户未来只审：

```text
少量真正可能改变投资逻辑的事项
```

而不是每天手工读几十份程序性公告。

---

# 21. Tests

至少新增：

```text
tests/test_human_research_approval.py
tests/test_event_materiality.py
tests/test_valuation_bridge_review.py
```

并修改必要的：

```text
tests/test_research_gate.py
tests/test_model_validity.py
tests/test_price_attractiveness.py
tests/test_event_scan.py
tests/test_current_research_status.py
```

---

# 22. Human Approval Tests

必须覆盖：

1. 无 receipt → G3 不通过；
2. `REJECTED_NEEDS_REWORK` → PriceAttractiveness NOT_ASSESSABLE；
3. approval hash 与 valuation hash 不一致 → approval STALE/SUPERSEDED；
4. 新 assumption artifact 出现 → 旧 approval 不自动继承；
5. APPROVED_CONDITIONAL_LOW_CONFIDENCE 可以保留研究，但可通过字段禁止价格判断；
6. approval 不能生成 `action != no_order`；
7. symbol/security/model identity conflict fail-closed。

---

# 23. Event Materiality Tests

覆盖：

```text
NOT_MATERIAL
```

不 stale。

```text
MATERIAL_ALREADY_INCORPORATED
```

如果已绑定当前 Facts，不 stale。

```text
MATERIAL_REQUIRES_RECALCULATION
```

必须 stale。

```text
MATERIAL_RISK_MONITOR
```

不必 stale，但生成 monitor/review_due。

```text
DUPLICATE_OR_DERIVED
```

不得重复触发。

```text
REQUIRES_DECOMPOSITION
```

阻断 Decision Eligibility。

---

# 24. Bridge Review Tests

至少：

- bridge arithmetic 可复算；
- per-share contribution 正确；
- haircut 不能超出合法范围；
- UNKNOWN recoverability 不得默认为 100%；
- bridge % 过高本身不自动 fail，但必须可见；
- identity / currency / share basis 冲突 fail-closed；
- Bear/Base/Bull 允许不同 haircut；
- 原 ValuationResult 不被修改。

---

# 25. Interim Report Policy Tests

验证：

```text
unaudited interim report
```

默认只影响：

```text
confidence
```

不自动成为 hard blocker。

但：

```text
conflict / correction / scope mismatch
```

可以升级。

---

# 26. 回归约束

必须证明：

```text
M1 original artifacts unchanged
M1 receipts unchanged
M1 DONE remains
C0-C3 frozen semantics unchanged
action=no_order remains
```

新增：

```text
human approval receipt
event materiality receipt
v2 valuation/research artifacts
```

不得覆盖旧版本。

---

# 27. 建议 Commit 顺序

不要一个巨型 commit。

## Commit 1

```text
HumanResearchApproval contract + tests
```

## Commit 2

```text
EventMaterialityDecision contract + 24-event review receipts
```

## Commit 3

```text
BridgeContribution generic domain + tests
```

## Commit 4

```text
Gree v2 bridge review + G3 remains rejected
```

## Commit 5

```text
Huayu v2 bridge/sensitivity + fast G3 rereview package
```

## Commit 6

```text
Yili conditional approval + cost-of-equity/retention/normalized-ROE review
```

## Commit 7

```text
ResearchGate / ModelValidity / PriceAttractiveness integration
```

## Commit 8

```text
Docs + presentation/read-model updates + full regression
```

如实际修改较小可合并相邻 commit，但不得把所有内容塞进单一超大 commit。

---

# 28. 执行顺序

Codex 按以下顺序执行：

```text
1. git status / HEAD / dirty tree audit
2. 读取本文与权威目标
3. 冻结 M1 历史 artifact/hash
4. 实现 HumanResearchApproval
5. 实现 EventMaterialityDecision
6. 写入本轮人工 review receipt
7. 实现 BridgeContribution
8. 格力 v2
9. 华域 v2
10. 伊利 v2
11. 集成 Gate / Validity / PriceAttractiveness
12. 更新 Read Model / Excel展示（如安全）
13. 定向测试
14. Core CI
15. 适当的全量/集成回归
16. 更新 execution-status
17. 报告结果
```

---

# 29. 禁止事项

本轮禁止：

- 重开 M1；
- 把 M1 DONE 改回 IN_PROGRESS；
- 修改 M1 冻结数字凑通过；
- 删除原 G3 未批准记录；
- 直接把格力 83.25、华域 33.75、伊利 17.02 当合理价值；
- 根据当前股价倒推参数；
- 为了让格力“便宜”而调高金融资产可实现价值；
- 为了让伊利“通过”而调高 ROE；
- 为了让华域“通过”而忽略客户/周期风险；
- 把所有 24 条公告标记“不重要”；
- 把所有标题带“回购/担保/减值”的公告机械 STALE；
- 新增第四个本轮 G3 公司；
- 启动 M2 全市场正式漏斗；
- 自动交易；
- 仓位算法；
- Broker API；
- 生产 PostgreSQL migration；
- 生产 scheduler 修改；
- Web 前端大开发。

---

# 30. 验收标准

本轮只有满足以下条件才允许完成：

1. M1 历史冻结结果完全不变；
2. 三家公司都存在版本化 HumanResearchApprovalReceipt；
3. 格力正式记录 `REJECTED_NEEDS_REWORK`；
4. 华域正式记录 `REJECTED_NEEDS_REWORK + PRIORITY_FOR_FAST_REREVIEW`；
5. 伊利正式记录 `APPROVED_CONDITIONAL_LOW_CONFIDENCE`；
6. Approval 与具体 valuation/facts/assumptions Hash 绑定；
7. Approval 失配能够自动失效；
8. 24 条公告都有正式 EventMaterialityDecision；
9. duplicate/derived 公告不会重复触发；
10. `MATERIAL_REQUIRES_RECALCULATION` 会让模型 STALE；
11. `MATERIAL_ALREADY_INCORPORATED` 不会无意义重复 STALE；
12. 格力 non-operating bridge 已拆分并有 haircut；
13. 华域 bridge 已拆分并有 sensitivity；
14. 伊利完成 Cost of Equity sensitivity；
15. 伊利 Retention 与 Dividend policy 建立一致性；
16. 伊利 impairment 已进入 normalized ROE review；
17. 未经审计半年报默认从 hard blocker 调整为 confidence modifier；
18. PriceAttractiveness 不能绕过 Human G3；
19. BUY/ADD 前置合同要求 G3 + Current Event Review；
20. 所有状态继续 `action=no_order`；
21. 定向测试、Core Gate 和适用 CI 全绿；
22. 无生产数据库/下单/服务器高风险修改。

---

# 31. 本轮完成后应得到的真实状态

理想结果不是：

```text
三家公司全部 APPROVED
```

而是：

```text
格力：
模型存在
但 bridge 风险尚大
→ 不批准

华域：
模型基本合理
→ 修正后快速复审

伊利：
模型可作为低置信度研究工具
→ 条件批准
→ 暂不进入价格结论
```

系统因此第一次真正具备：

> **“不是所有模型算出来都一样可信”**

的研究纪律。

---

# 32. 本轮完成后报告格式

Codex 最终只需报告：

```text
HEAD

M1 frozen integrity
PASS / FAIL

Human Approval:
000651 =
600741 =
600887 =

Event Materiality:
NOT_MATERIAL =
SUPPORTING =
ALREADY_INCORPORATED =
REQUIRES_RECALCULATION =
RISK_MONITOR =
DUPLICATE =
REQUIRES_DECOMPOSITION =

Gree:
bridge review status
remaining blocker

Huayu:
bridge/sensitivity status
G3 rereview status

Yili:
approval status
condition resolution status

Gate/Validity/Price integration:
PASS / FAIL

Tests:
...

Production changes:
NONE / explain

NEXT TASK:
one only
```

---

# 33. 最终原则

本轮的最终目的不是让更多股票显示“通过”。

而是建立以下投资纪律：

```text
模型有数值
↓
检查这些价值来自哪里

价值来自现金/金融资产
↓
确认这些资产是否真的属于普通股股东

出现新公告
↓
判断它是否改变事实/假设/模型

人工批准模型
↓
才允许研究价格

价格便宜
↓
仍然不是买入

买入复核
↓
必须建立在可追溯事实、假设、估值、事件和人工研究批准之上
```

只有这样，后续 M3 的 BUY/ADD/HOLD/REDUCE/EXIT Review 才不会变成一个披着价值投资外衣的机械信号系统。
