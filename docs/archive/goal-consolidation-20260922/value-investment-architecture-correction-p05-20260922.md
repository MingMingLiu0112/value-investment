# A股价值投资 Agent：第二轮架构纠偏与三公司收敛执行目标（Codex 立即执行版）

> 版本：v1.0  
> 日期：2026-09-22  
> 仓库：`MingMingLiu0112/value-investment`  
> 当前基线提交：`8729923c3f9d0e7d06cfb905adf63a90c863c72f`  
> 建议保存路径：`docs/value-investment-architecture-correction-p05-20260922.md`
>
> 本文件是继 `docs/value-investment-architecture-correction-20260921.md` 之后的第二轮架构纠偏。
>
> 第一轮 P0 已基本完成：
>
> - `ValuationResult` 与当前价格已拆分；
> - `ModelValidity` 已建立；
> - `PriceBridgeResult` 已建立；
> - `ResearchGate` 已拆分为 G0/G1/G2/G3；
> - `ResearchProfile` 已建立；
> - `ValuationRouter` 已建立；
> - `CurrentResearchStatus` 已建立；
> - 600519 / 000333 / 601088 三家公司已经进入统一研究与估值工程路径。
>
> 当前新的主要风险已经变化：
>
> 1. `ResearchGate` 与 `CurrentResearchStatus` 对“估值具备研究吸引力”的语义仍然过早；
> 2. 系统过度要求“未来估值输入必须是事实”，导致 Facts / Assumptions 边界不清；
> 3. 对小额不可拆分项目缺少 Materiality 判断，导致大量无止境证据追踪；
> 4. 三家公司专用脚本数量快速膨胀，出现“证据考古 / 单公司工程化过深”风险；
> 5. Moutai execution / historical / simulation 工作开始重新占用当前主线资源；
> 6. 当前三公司还没有形成完全一致的“研究 → 估值 → 价格吸引力”闭环。
>
> **执行优先级：先完成本文件 P0.5，再继续补三公司研究级估值；在三公司收敛前，不新增第四家公司。**

---

# 1. 本轮总目标

把当前架构从：

```text
ResearchGate
↓
ValuationResult
↓
PriceBridge
↓
CurrentResearchStatus
```

升级为：

```text
Evidence
↓
FinancialFacts
↓
ResearchCase
↓
ResearchGate
↓
ValuationAssumptionSet
↓
ValuationModel
↓
ValuationResult
↓
ModelValidity
↓
PriceBridgeResult
↓
PriceAttractivenessAssessment
↓
CurrentResearchStatus
↓
Excel
```

最终明确四个完全不同的问题：

```text
ResearchGate
回答：研究本身是否完整？

ValuationResult
回答：在当前假设下企业价值是多少？

PriceBridgeResult
回答：当前市场价格与估值之间是什么关系？

PriceAttractivenessAssessment
回答：在当前 ResearchProfile、估值置信度和下行风险下，
当前价格是否值得提高研究优先级？
```

禁止继续把以上四个问题混在同一个状态中。

---

# 2. P0.5-1：修正“估值具备研究吸引力”的语义

## 当前问题

当前 `ResearchGate` 在以下四门通过时：

```text
G0 Evidence
G1 Financial
G2 Thesis
G3 Valuation
```

可能直接输出：

```text
估值具备研究吸引力
```

但此时 `PriceBridge` 可能仍然是：

```text
PENDING_EXTERNAL_DATA
```

这在语义上不成立。

因为：

> 没有当前价格，就无法判断“价格是否具备研究吸引力”。

## 必须修改的原则

`ResearchGate` 永久不得输出以下价格相关结论：

```text
价格缺乏吸引力
等待更有吸引力的价格
估值具备研究吸引力
```

这些结论只能在 `PriceBridgeResult` 形成以后，由独立 `PriceAttractivenessAssessment` 计算。

---

# 3. ResearchGate 新职责

`ResearchGate` 只回答研究本身是否准备好进入估值 / 价格比较。

建议结论改为：

```text
数据不足
研究未完成
估值未就绪
研究未通过
研究与估值已就绪
```

建议内部状态：

```text
RESEARCH_READY_FOR_PRICE_ASSESSMENT
```

Excel 可显示中文“研究与估值已就绪”。

## ResearchGate 必须继续检查

### G0 Evidence

- 事实是否有 evidence_refs；
- 是否 quarantine；
- 是否有关键数据冲突；
- 是否完成可追溯验证。

### G1 Financial

- 当前 ResearchProfile 要求的最低财务事实是否满足；
- 财务口径是否明确；
- 关键输入是否可复算。

### G2 Thesis

- thesis；
- return_driver；
- mispricing_hypothesis；
- positives；
- counter_evidence；
- thesis_breakers；
- next_events。

### G3 Valuation

- 适用模型是否明确；
- 估值是否已经形成；
- 估值状态是否允许进入价格比较；
- confidence 是否有效；
- blockers 是否为空或允许进入下一层。

---

# 4. P0.5-2：新增 PriceAttractivenessAssessment

新增建议文件：

`src/value_investment_agent/price_attractiveness.py`

建议对象：

```python
@dataclass(frozen=True)
class PriceAttractivenessAssessment:
    symbol: str
    profile_id: str
    status: str
    margin_to_bear: Decimal | None
    margin_to_base: Decimal | None
    downside_reference: Decimal | None
    upside_reference: Decimal | None
    confidence: str
    reasons: list[str]
    blockers: list[str]
    evidence_refs: list[dict]
```

## 状态建议

```text
NOT_ASSESSABLE
PRICE_NOT_ATTRACTIVE
WAITING_FOR_BETTER_PRICE
KEY_OBSERVATION
RESEARCH_ATTRACTIVE
```

中文展示：

```text
不可判断价格吸引力
价格缺乏吸引力
等待更有吸引力的价格
重点观察
估值具备研究吸引力
```

---

# 5. PriceAttractiveness 必须依赖 READY PriceBridge

如果：

```text
PriceBridgeResult.bridge_status != READY
```

则：

```text
PriceAttractivenessAssessment.status = NOT_ASSESSABLE
```

例如：

```text
PENDING_EXTERNAL_DATA
STALE_MODEL
INVALID
```

都不得产生：

```text
估值具备研究吸引力
```

---

# 6. 禁止重新引入统一 30% 安全边际

禁止：

```python
if margin_to_base >= 0.30:
    return RESEARCH_ATTRACTIVE
```

也禁止：

```text
全行业统一安全边际阈值
```

PriceAttractiveness 必须：

```text
ResearchProfile-aware
```

---

# 7. 第一版 PriceAttractiveness 不要求复杂自动决策

本轮只做最小可扩展合同。

可以先支持：

```text
quality_compounder
mature_manufacturing
cyclical_cash_return
```

但原则上允许第一版保守返回：

```text
KEY_OBSERVATION
```

而不是为了产生：

```text
RESEARCH_ATTRACTIVE
```

强行设计未经验证阈值。

---

# 8. 第一版 Profile-aware 价格判断建议

## quality_compounder

观察：

```text
margin_to_base
margin_to_bear
confidence
```

若：

- confidence = LOW；
- 或 Bear 下行风险过高；

不得进入：

```text
RESEARCH_ATTRACTIVE
```

## mature_manufacturing

观察：

```text
margin_to_base
margin_to_bear
FCFF confidence
```

本轮在真实 Midea FCFF 尚未形成前：

```text
NOT_ASSESSABLE
```

## cyclical_cash_return

价格判断必须基于：

```text
normalized cyclical value
```

不能基于：

```text
current-year PE
current-year earnings
```

本轮 Shenhua 估值未形成前：

```text
NOT_ASSESSABLE
```

---

# 9. CurrentResearchStatus 必须重新组合

目标：

```text
ResearchGate
+
ValuationResult
+
PriceBridgeResult
+
PriceAttractivenessAssessment
↓
CurrentResearchStatus
```

CurrentResearchStatus 不再自行决定 margin 阈值。

它只做：

> 已有研究对象的状态聚合与展示。

---

# 10. 修正当前测试中的错误语义

当前类似以下行为必须删除：

```text
PriceBridge = PENDING_EXTERNAL_DATA
但
ResearchConclusion = 估值具备研究吸引力
```

新增测试：

```text
ResearchGate = READY
Valuation = approved_research_only
PriceBridge = PENDING_EXTERNAL_DATA

=> PriceAttractiveness = NOT_ASSESSABLE
=> CurrentResearchStatus 不得为 估值具备研究吸引力
```

---

# 11. P0.5-3：正式拆分 Facts 与 Assumptions

这是当前第二个最高优先级问题。

当前系统已经非常擅长：

```text
证明历史事实
```

但价值投资估值还必须允许：

```text
有证据基础的未来假设
```

不能要求：

> 未来收入、未来煤价、未来ROIC、未来WACC 都必须来自已披露事实。

这是不可能的。

---

# 12. 定义两层

## FinancialFacts

回答：

> 已经发生了什么？

必须：

```text
严格
可追溯
可复算
point-in-time
```

例如：

```text
2025 EBIT
2025 CapEx
2025 Revenue
2025 Cash
2025 Debt
Current Shares
Historical Coal Price
Historical Unit Cost
```

## ValuationAssumptions

回答：

> 对未来采用什么假设？

允许：

```text
估计
区间
情景
合理归一化
```

但必须：

```text
有依据
有理由
有来源
有敏感性
有 confidence
```

---

# 13. 新增 ValuationAssumption

建议文件：

`src/value_investment_agent/valuation_assumptions.py`

建议：

```python
@dataclass(frozen=True)
class ValuationAssumption:
    name: str
    unit: str
    bear: Decimal | str | None
    base: Decimal | str | None
    bull: Decimal | str | None
    basis: str
    rationale: str
    as_of: date
    confidence: str
    sensitivity: str
    evidence_refs: list[dict]
    blockers: list[str]
```

---

# 14. 新增 ValuationAssumptionSet

建议：

```python
@dataclass(frozen=True)
class ValuationAssumptionSet:
    symbol: str
    profile_id: str
    model_type: str
    as_of: date
    assumptions: list[ValuationAssumption]
    status: str
    blockers: list[str]
    evidence_refs: list[dict]
```

状态：

```text
READY
PARTIAL
NOT_READY
INVALID
```

---

# 15. 每个假设必须回答

例如：

```text
normalized_coal_price
```

必须能解释：

```text
Bear:
为什么是550？

Base:
为什么是700？

Bull:
为什么是850？

Basis:
历史价格 + 供需区间 + 成本支撑

Evidence:
哪些来源？

Confidence:
低/中/高

Sensitivity:
高/中/低
```

---

# 16. 估值模型不能自己藏假设

禁止：

```python
growth = 0.05
wacc = 0.09
terminal_growth = 0.02
```

无证据、无假设对象直接写死在模型内部。

长期要求：

```text
ValuationAssumptionSet
↓
ValuationModel
```

模型负责数学。

假设层负责人类 / Agent 对未来的研究判断。

---

# 17. Moutai 迁移原则

当前 Moutai 已经存在：

```text
growth
payout
fade
terminal growth
cost of equity
```

本轮不要重做其估值数学。

只需要：

> 把现有已命名假设逐步映射到统一 ValuationAssumptionSet。

不要重新调整参数。

---

# 18. Midea 迁移原则

当前 Midea 大量时间用于寻找：

```text
完整工业 EBIT
完整金融业务剥离
完整净债务
```

下一步应该开始判断：

> 哪些是必须精确事实，哪些可以通过重大性判断后形成合理假设？

不要继续无限追求“完美拆分”。

---

# 19. Shenhua 迁移原则

当前已经拥有：

```text
2014-2025
煤价
销量
成本
运输
电力
资源
```

大量历史研究。

下一步不应该继续无限寻找：

```text
所有年份完整一手原始来源
每条运输路线精确成本
每家子公司税费分配
```

而应该开始形成：

```text
normalized_price assumptions
normalized_unit_cost assumptions
maintenance_capex assumptions
normalized_volume assumptions
resource_life assumptions
```

并明确：

```text
事实支持范围
假设区间
Confidence
Sensitivity
```

---

# 20. P0.5-4：新增 Materiality Assessment

当前系统最大的问题之一：

```text
存在小额未知
↓
整个估值永久阻断
```

这是过于严格。

Fail-closed 不等于：

> 所有数据必须100%确定。

---

# 21. 新增 ScopeMaterialityAssessment

建议文件：

`src/value_investment_agent/materiality.py`

建议：

```python
@dataclass(frozen=True)
class ScopeMaterialityAssessment:
    symbol: str
    issue_id: str
    metric: str
    estimated_exposure_ratio: Decimal | None
    downside_impact: Decimal | None
    upside_impact: Decimal | None
    materiality: str
    treatment: str
    rationale: str
    evidence_refs: list[dict]
    blockers: list[str]
```

---

# 22. Materiality 状态

建议：

```text
IMMATERIAL
LOW
MEDIUM
HIGH
UNKNOWN
```

---

# 23. Materiality Treatment

例如：

```text
IGNORE_WITH_DISCLOSURE
MODEL_AS_RANGE
SCENARIO_STRESS
BLOCK_MODEL
REQUIRE_MORE_EVIDENCE
```

---

# 24. Materiality 不能成为随意放宽数据标准的工具

必须禁止：

```text
不知道
→
假设不重要
```

只有具备：

```text
可量化暴露
或
合理上下界
```

才允许判断：

```text
IMMATERIAL / LOW
```

如果无法判断：

```text
UNKNOWN
```

仍 fail-closed。

---

# 25. Midea 应优先作为 Materiality 首例

当前财务公司已经有候选规模：

```text
利润约占归母利润 0.93%
权益约占归母权益 3.52%
```

本轮可以建立：

```text
MideaFinanceBusinessMateriality
```

但不要直接解锁 FCFF。

只做：

```text
这个不可拆分范围是否属于 LOW / MEDIUM / HIGH？
```

并做极端上下界测试。

---

# 26. Materiality 不得取代模型适用性

即使某项目 Materiality = LOW，

也不能自动：

```text
MODEL_NOT_APPLICABLE
↓
SUPPORTED
```

它只能作为：

```text
ValuationApplicability
```

的一个输入。

---

# 27. P0.5-5：冻结新的 company-specific 脚本扩张

当前最近一次提交：

```text
142 files changed
18k+ additions
```

已有大量：

```text
moutai_*
midea_*
shenhua_*
```

脚本。

从现在开始：

> 新增公司专用脚本必须满足严格条件。

---

# 28. 允许新增 company-specific 脚本的条件

只有满足至少一项：

```text
1. 某公司独有的一手数据解析
2. 某公司独有的法律/披露结构
3. 无法合理抽象成通用 Provider / Evidence / Assumption 接口
4. 是临时迁移 adapter，并明确未来归并方向
```

否则：

```text
优先新增通用模块
```

---

# 29. 禁止继续出现

```text
build_shenhua_xxx_22.py
build_midea_xxx_12.py
```

只因为：

> 又发现一个数据缺口。

优先判断：

```text
这个缺口属于：
Fact？
Assumption？
Materiality？
Model applicability？
```

再选择通用层解决。

---

# 30. P0.5-6：冻结 Moutai execution / R1 / historical 扩展

在三公司研究级闭环完成之前：

禁止继续新增：

```text
Moutai execution feature
Moutai historical capital cost
Moutai R1 refinement
Moutai paper strategy logic
Moutai execution policy enhancement
```

允许：

```text
Bug fix
Regression fix
Security / data integrity fix
```

---

# 31. 原因

当前产品主线：

```text
Research Operating System
```

不是：

```text
Moutai trading simulator
```

必须先完成：

```text
三种公司
→ 三种研究路径
→ 三种估值路径
→ 同一价格吸引力框架
```

---

# 32. P0.5-7：统一三公司最终闭环

本轮完成以后，三家公司必须最终都能进入同一流程：

```text
ResearchCase
↓
ResearchProfile
↓
ResearchGate
↓
ValuationAssumptionSet
↓
ValuationRouter
↓
ValuationModel
↓
ValuationResult
↓
ModelValidity
↓
PriceBridgeResult
↓
PriceAttractivenessAssessment
↓
CurrentResearchStatus
↓
Excel
```

---

# 33. 三公司当前目标状态

## 600519

要求：

```text
ResearchCase = READY
Profile = quality_compounder
Valuation = conditional research result
Assumptions = migrated to unified structure
ModelValidity = VALID / explicit
PriceBridge = READY / explicit
PriceAttractiveness = assessable
CurrentResearchStatus = no trade signal
```

不得重估参数。

## 000333

要求：

```text
ResearchCase = READY
Profile = mature_manufacturing
FCFF engineering = READY
Facts = explicit
Assumptions = explicit
Materiality = explicit
Production valuation = may remain NOT_READY if truly unresolved
```

如果无法完成 FCFF：

允许：

```text
VALUATION_NOT_READY
```

但必须明确：

```text
剩余阻断是事实问题
还是假设问题
还是重大性问题
还是模型适用性问题
```

不能继续统称：

```text
数据缺失
```

## 601088

要求：

```text
ResearchCase = READY
Profile = cyclical_cash_return
Cyclical engine = READY
Historical evidence = sufficient
ValuationAssumptionSet = formed
Normalized scenario logic = formed
```

目标是：

> 从“证据收集”进入“合理正常化假设”。

不要继续无限扩展历史考古。

---

# 34. P0.5-8：新增 Gap Classification

为了防止所有 blocker 都变成：

```text
继续找数据
```

新增统一 blocker 分类。

建议：

```text
FACT_MISSING
FACT_CONFLICT
ASSUMPTION_MISSING
ASSUMPTION_LOW_CONFIDENCE
MATERIALITY_UNKNOWN
MODEL_NOT_APPLICABLE
MODEL_NOT_REGISTERED
PRICE_DATA_PENDING
MODEL_STALE
THESIS_INCOMPLETE
```

---

# 35. 每一个 blocker 都必须属于一类

禁止：

```text
blocker = "还需要更多数据"
```

必须具体：

```text
type:
ASSUMPTION_MISSING

field:
normalized_coal_price

reason:
historical evidence exists but bear/base/bull assumption not yet registered
```

---

# 36. Codex 遇到 blocker 后必须按类型推进

```text
FACT_MISSING
→ 找一手事实

ASSUMPTION_MISSING
→ 形成假设范围

MATERIALITY_UNKNOWN
→ 做重大性分析

MODEL_NOT_APPLICABLE
→ 换模型 / 调整范围

PRICE_DATA_PENDING
→ 等待生产数据，不阻塞工程
```

---

# 37. P0.5-9：Excel 展示调整

Excel 不需要新增大量 sheet。

继续使用现有：

```text
00_首页Dashboard
00_公司总览
09_公司研究
04_估值跟踪
21_决策验证
18_指标证据
```

---

# 38. 公司卡增加三项即可

建议增加：

```text
假设状态
价格吸引力状态
主要未解决问题类型
```

例如：

```text
贵州茅台

研究状态：
研究与估值已就绪

估值状态：
conditional_research_only

假设状态：
READY

价格桥接：
READY

价格吸引力：
价格缺乏吸引力 / 重点观察

主要阻断：
估值置信度低
```

---

# 39. Midea 示例

```text
美的集团

研究状态：
研究已完成

估值状态：
VALUATION_NOT_READY

假设状态：
PARTIAL

Materiality：
财务公司影响待评估

价格吸引力：
不可判断

主要阻断：
MODEL_APPLICABILITY / MATERIALITY
```

---

# 40. Shenhua 示例

```text
中国神华

研究状态：
研究已完成

估值状态：
VALUATION_NOT_READY

假设状态：
PARTIAL

价格吸引力：
不可判断

主要阻断：
ASSUMPTION_MISSING
```

---

# 41. 不要把 Excel 继续做成事实数据库

核心对象：

```text
Facts
Assumptions
Materiality
Valuation
PriceAttractiveness
```

都必须先存在于：

```text
Python / JSON / Database-compatible structures
```

Excel 只负责展示。

---

# 42. P0.5-10：CI 增加新的 Core Gate

更新：

`.github/workflows/core-research-gates.yml`

至少加入：

```text
test_price_attractiveness.py
test_valuation_assumptions.py
test_materiality.py
```

以及必要：

```text
test_current_research_status.py
```

---

# 43. 不要求 CI 跑所有 1800+ tests

当前 CI 保持：

```text
Core Contract Tests
```

即可。

建议未来：

```text
push/PR:
core tests

manual/nightly:
full pytest
```

---

# 44. 提交粒度约束

禁止再次一个 commit：

```text
142 files
18k+ lines
```

本轮至少拆成：

```text
Commit 1:
PriceAttractiveness + ResearchGate semantic correction

Commit 2:
ValuationAssumptions

Commit 3:
Materiality + Midea first case

Commit 4:
Three-company adapters + Excel

Commit 5:
Tests / CI / docs
```

如果实际修改较小，可以合并，但：

> 每个 commit 必须只有一个可解释的主要意图。

---

# 45. 本轮不做

明确禁止：

```text
新增第四家公司
全市场筛选
Web前端
银行估值
保险估值
地产NAV
复杂CycleAnalyzer
市场情绪系统
真实交易
券商API
新的仓位算法
新的Moutai execution功能
新的历史策略回测扩展
```

---

# 46. P0.5 验收标准

全部满足后才允许继续三公司生产估值收敛。

## ResearchGate

- [x] 不再输出价格相关结论
- [x] 新增 READY_FOR_PRICE_ASSESSMENT 或等价状态
- [x] PENDING quote 不影响研究完成状态

## PriceAttractiveness

- [x] 新增独立对象
- [x] 无 READY PriceBridge 时不得输出 research attractive
- [x] 真正使用 margin_to_base / margin_to_bear
- [x] 不使用统一30%
- [x] 支持 Profile-aware 扩展

## Assumptions

- [x] 新增 ValuationAssumption
- [x] 新增 ValuationAssumptionSet
- [x] Facts 与 Assumptions 明确分离
- [x] 假设必须有 basis / rationale / evidence / confidence / sensitivity
- [x] 不允许模型内部隐藏关键经济假设

## Materiality

- [x] 新增 Materiality contract
- [x] UNKNOWN 继续 fail-closed
- [x] LOW/IMMATERIAL 必须有量化证据
- [x] 不得自动解除 MODEL_NOT_APPLICABLE

## Three-company integration

- [x] Moutai 假设可以映射统一 AssumptionSet
- [x] Midea blocker 被明确分类
- [x] Shenhua 从“继续找历史事实”转向“形成正常化假设”
- [x] 三家公司共享同一 PriceAttractiveness 接口

## Excel

- [x] 展示 Research
- [x] 展示 Valuation
- [x] 展示 Assumption status
- [x] 展示 PriceBridge
- [x] 展示 PriceAttractiveness
- [x] 不新增买卖指令

## CI

- [x] 新核心测试进入 GitHub Actions
- [x] Core tests 可在 Linux Python 3.12 运行

---

# 47. P0.5 完成后的主线

完成后严格按：

```text
P0.5
↓
Midea 研究级估值收敛
↓
Shenhua 研究级正常化估值收敛
↓
三公司统一验收
↓
冻结三公司 MVP
↓
20-50家公司固定跨行业样本
```

---

# 48. 三公司统一验收必须回答

对每家公司：

```text
1. 公司怎么赚钱？
2. 核心回报来源是什么？
3. 最强竞争优势 / 经济驱动是什么？
4. 最强反证是什么？
5. Thesis Breaker 是什么？
6. 当前事实是什么？
7. 哪些是估值假设？
8. 主模型是什么？
9. 为什么这个模型适用？
10. Bear/Base/Bull 是什么？
11. Confidence 是什么？
12. 当前价格桥接状态是什么？
13. 当前价格吸引力是什么？
14. 最大不确定性是什么？
15. 下一次需要重新研究的事件是什么？
```

如果三家公司都能回答：

> 三公司研究 MVP 才算真正形成。

---

# 49. 对公司专用研究的 Stop Rule

以后公司研究必须有停止规则。

如果：

```text
继续收集某项证据
```

不能改变以下任何一项：

```text
Model applicability
Assumption range
Materiality
Confidence
Valuation output
Thesis
```

则默认：

```text
停止继续收集
```

除非：

```text
用户明确要求法证级审计
```

---

# 50. 价值投资研究不是审计竞赛

长期原则：

> 数据事实必须严格，但估值永远包含假设。

系统的价值不是：

```text
证明所有未知都不存在
```

而是：

```text
把事实、假设、不确定性、敏感性和风险分开管理
```

---

# 51. Codex 每轮必须先判断当前问题属于哪一层

执行任何新任务前，先分类：

```text
Evidence
Fact
Assumption
Materiality
Model
PriceBridge
PriceAttractiveness
Presentation
Execution
```

如果当前需求可以在通用层解决：

> 禁止优先新增 company-specific script。

---

# 52. 每轮固定汇报

```text
Engineering Status:

Current Data Status:

本轮解决的问题类型:
FACT / ASSUMPTION / MATERIALITY / MODEL / PRICE

本轮通用架构变化:

本轮公司适配变化:

测试:

新增 company-specific scripts:
数量 + 理由

当前 blockers:
最多5个，必须分类

下一唯一任务:

等待的 Production Validation:
```

---

# 53. 本轮第一执行任务

现在不要继续新增 Shenhua / Midea 证据脚本。

第一任务必须是：

```text
PriceAttractiveness semantic correction
```

具体：

1. 修改 ResearchGate，使其不再产生价格相关 conclusion；
2. 新增 `price_attractiveness.py`；
3. 修改 `CurrentResearchStatus`；
4. 修改测试：
   - PENDING_EXTERNAL_DATA 不得为 research attractive；
   - READY bridge 才允许进入价格吸引力评估；
5. 不修改 Moutai 估值参数；
6. 不修改交易执行；
7. 不修改仓位逻辑；
8. 测试通过后停止并汇报。

---

# 54. 第一任务验收语句

只有完成第53节后，允许写：

> **P0.5-1 已通过：研究完成状态与价格吸引力状态已经彻底分离；没有合法 PriceBridge 时，系统不再产生“估值具备研究吸引力”等价格相关研究结论。**

---

# 55. 第二执行任务

只有第一任务通过后：

```text
ValuationAssumptionSet
```

目标：

- 建立通用合同；
- Moutai 只做映射；
- Shenhua 建立第一版正常化假设；
- 不修改模型参数以匹配股价；
- 不继续扩历史证据。

---

# 56. 第三执行任务

随后：

```text
Materiality
```

目标：

- 先以 Midea 财务公司为第一案例；
- 不直接解锁模型；
- 形成通用 materiality contract；
- 明确 LOW / MEDIUM / HIGH / UNKNOWN 的证据要求。

---

# 57. 长期原则补充

在原 P0 六条原则基础上，增加：

> **7. Facts 与 Assumptions 永久分层。**

> **8. Fail-closed 不等于追求不存在的确定性；未知必须通过 Assumption、Sensitivity、Confidence 或 Materiality 显式管理。**

> **9. Price Attractiveness 必须在合法 PriceBridge 之后产生。**

> **10. 新公司优先复用 Profile / Router / Assumption / Materiality / PriceAttractiveness，不复制整套公司流水线。**

> **11. 单公司研究有停止规则；不能改变投资判断的重要信息不继续无限收集。**

> **12. 三公司 MVP 未冻结前，不扩第四家公司。**

---

# 58. 最终产品方向不变

最终仍然是：

```text
全市场
↓
多通道筛选
↓
候选
↓
深度研究
↓
ResearchCase
↓
Profile
↓
Facts
↓
Assumptions
↓
Valuation
↓
Reverse Valuation
↓
PriceBridge
↓
Price Attractiveness
↓
Event Monitoring
↓
少量高关注公司
↓
Excel / 未来 Web
↓
Human Decision
```

不是：

```text
自动买卖机器人
```

不是：

```text
无限证据审计系统
```

也不是：

```text
每家公司都必须有目标价
```

---

# 59. 最终成功标准

当前阶段真正成功，不是：

```text
脚本越来越多
测试越来越多
证据文件越来越多
```

而是：

> **三类不同 A 股公司都可以通过同一研究工作流，在明确区分事实、假设、重大性、模型、不确定性和市场价格的前提下形成可追溯的研究级价值判断，并且新增第四家公司时不需要复制一整套流水线。**

---

# 60. 本轮完成语句

只有第46节全部满足后，允许写：

> **P0.5 第二轮架构纠偏已通过：Research、Valuation、Assumption、Materiality、PriceBridge 与 PriceAttractiveness 已完成职责分离；系统停止以无限证据收集替代估值判断，三公司进入统一收敛阶段。**
