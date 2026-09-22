# 架构合同

生效：2026-09-22。合并原 P0、P0.5 与长期漏斗合同；现状见 [execution-status.md](execution-status.md)，当前开发范围见 [current-stage-goal.md](current-stage-goal.md)。
本文区分必须满足的合同与尚未实现的设计。写入本文不代表代码、数据库或生产服务已完成。

## 分层与依赖

```text
Raw Source -> Evidence -> Validated Facts -> Profile-specific FinancialFacts
ResearchProfile + Facts -> ResearchCase -> G0 Evidence / G1 Financial / G2 Thesis
Facts + ValuationAssumptionSet + Applicability -> ValuationRouter -> ValuationModel
ValuationModel -> ValuationResult -> G3 Valuation -> ResearchGate completion

Facts + Capital Allocation + Distribution History
  -> DistributionCapacity -> DividendSustainability

ValuationResult + ModelValidity + QuoteSnapshot -> PriceBridgeResult
Distribution Data + QuoteSnapshot -> DividendYieldSnapshot

ResearchGate + ValuationResult + PriceBridgeResult
  + applicable DividendSustainability / DividendYieldSnapshot
  -> PriceAttractivenessAssessment -> CurrentResearchStatus
  -> Funnel State -> Event Monitoring -> Excel / Future Web -> Human Decision
```

这是依赖关系，不是强制按字段串行执行的全局流水线。G3 消费估值就绪度，不能让“完整 ResearchGate 先通过”反过来阻止估值产生，形成循环依赖。
股息域尚未开发，未来只按 Profile 与研究路径使用；非股息路径不因缺股息评分被机械阻断。

Domain Engine 不读取 Excel、网络或数据库；Application 负责编排、读取和保存；Provider / Repository / Publisher 负责 I/O。
现有模块渐进整理，不为目录美观大搬迁。未来 FastAPI / Web 调用同一 Application 服务。

## 核心职责

| 对象 | 负责 | 不负责 |
| --- | --- | --- |
| ResearchProfile | 行业、商业模式、投资路径、生命周期、资本结构、必要指标和模型适配 | 按股票代码自动决定模型 |
| FinancialFacts | 有版本的事实、期间、主体、单位、可用时点与证据 | 把 WACC、增长、正常化利润等未来判断冒充披露事实 |
| ResearchCase | thesis、return_driver、mispricing_hypothesis、positives、counter_evidence、thesis_breakers、next_events | 订单、仓位、唯一总分 |
| ResearchGate | G0-G3 的研究/估值完成状态；G2 实质检查论点、反证、失效条件、下一事件及证据 | 价格吸引力结论；旧 G4 仅作聚合语义，不再新增第五个前置门 |
| ValuationAssumptionSet | Bear/Base/Bull、basis、rationale、evidence、confidence、sensitivity、版本和适用时点 | 隐藏假设或反向拟合股价 |
| Materiality | 量化暴露或有依据上下界、处理方式、影响结论 | LOW 自动解除 MODEL_NOT_APPLICABLE |
| ValuationRouter | 根据 Profile 选择已注册且经济适用的模型与 Facts 合同 | 所有公司默认 FCFF；为得到数值自动换模型 |
| ValuationResult | bear/base/bull、confidence、assumptions、sensitivities、evidence、blockers、版本及日期 | current_price、margin、交易信号 |
| ModelValidity | 特定模型版本到目标时点的重大事件复核、有效窗口和失效原因 | 用任意 VALID 标签替代模型身份与事件证据 |
| PriceBridgeResult | 合法模型与具体报价的日期、价格、相对情景边际及状态 | 重新估值、清空无行情时的已有估值 |
| PriceAttractivenessAssessment | 已完成研究与合法价格桥接后的 Profile-aware 价格研究 | ResearchGate 结论改名；自动买卖 |
| CurrentResearchStatus | 汇总各维度状态、原因和证据供展示 | 从 display_text 推导业务状态 |

当前已有三种 Profile、Router、FCFF/剩余收益/周期算术接口。FCFF 的 FinancialFacts 类型仍为模型专用合同，不宣称全行业统一事实字典已完成。
允许不同模型使用不同事实 schema；金融、保险、NAV 等在未注册前明确 UNSUPPORTED。CycleProfile 当前只是有限画像信息，MarketContext 和完整事件引擎仍为设计。

## 身份、版本与时点硬约束

每次研究结果与桥接必须可绑定 security identity、模型/估值快照 identity、模型版本、事实/假设版本、信息可用时点和证据 Hash。
具体采用现有不可变快照 Hash 或最小引用对象，不为一个校验任务创建全新实体体系。

合法价格桥接必须验证：
1. 估值、有效性检查、报价及下游载荷属于同一证券，且有效性检查对应同一模型快照。
2. 报价时点不早于模型可用时点，有效窗口和重大事件扫描覆盖到报价时点；跨日有效性有证据，不能机械要求同日。
3. 报价为已核验的对应交易会话和口径；正数、有限值、非空证据及快照身份齐全。
4. 使用对应估值计算边际，不接受别的模型计算出的 margin；反序列化不得用估值 symbol 覆写其他载荷的冲突 symbol。
5. 重大事件为 STALE，未知为 UNKNOWN；价格缺失为 PENDING_EXTERNAL_DATA。不可判断不构成价格不吸引，更不构成卖出。
6. READY 是通过合同验证后的结果，直接构造对象、JSON 恢复与正常函数路径都必须维持同样不变量。

C0 已通过并冻结上述身份与时点合同；该段旧“代码缺口”不再作为当前状态。新价格桥接仍必须保持这些不变量，不能被 C3 的 Repository/Application 层放宽。

## Dividend / Distribution Domain：最小合同已实现

`src/value_investment_agent/distribution.py` 已实现最小时点合同：`DividendRecord`、`DividendHistory`、`DistributionCapacity`、`DividendSustainabilityAssessment`、`DividendYieldSnapshot` 与 `DividendResearchResult`。当前只证明共享类型与 fail-closed 边界，不代表三家公司的股息研究已经完成。

| 对象 | 内容 | 是否依赖当前价格 |
| --- | --- | --- |
| DividendHistory / DividendPolicy | 每股金额、普通/特别分红、方案/批准/实施/支付状态、资本配置政策 | 否 |
| DistributionCapacity | 经营现金、必要再投资、债务、受限资金、子公司上划、普通股可分配范围及情景 | 否 |
| DividendSustainability | HIGH / MEDIUM / LOW / UNKNOWN、覆盖、稳定性、增长来源、周期压力、breaker | 否 |
| DividendYieldSnapshot | dividend_basis_period、basis_type、DPS、known_at、quote_date/time、price、currency/share_basis、yield、source refs | 是 |
| ShareholderYield | 现金分红、实际回购及稀释的明确口径 | 是，后续再做 |

ResearchProfile 未来可带 distribution_profile：growth_reinvestment / balanced / cash_return / cyclical_distribution / regulated_distribution。
可持续性阈值按经济特征登记，不共享一个机械 payout 或 FCF 阈值。DividendSustainability 是有条件判断，不保证分红兑现。
Distribution 与 Valuation 共用有身份的 Facts/Assumptions；分红、回购和终值不能重复计价。

## 漏斗与事件：后续设计

L0 身份/上市与数据覆盖；L1 多通道筛查；L2 初步论点与研究缺口；L3 深研/估值/股息能力；L4 高关注与变化跟踪。
每次升降级保存 old_state、new_state、reason、as_of、rule_version、actor、evidence_refs；不以一条总分抹掉否决项，不按名额填满 L4。
正式完整估值限 L3/L4；不支持的 Profile 保留覆盖与缺口，不调用默认 FCFF。

事件区分发生日、披露/可用日、抓取日；新财报、更正、资本动作、分红变化、重大并购、债务和经营变化只失效受影响依赖。
无实质变化保持安静；重复事件幂等，单公司失败不阻塞其他公司。MaterialEvent 类型已存在不代表完整 Event Engine 已上线。
MarketContext 未来只提供环境与研究解释，不直接修改内在价值或替代公司事实。

## 存储、展示与迁移

PostgreSQL 是长期结构化事实、身份/版本关系、状态和运行审计底座；Evidence/Snapshot 保存不可变原件与封存输入；runtime JSON 是当前 MVP 的可追溯中间产物，Excel 是展示和明确的人工作业入口。
现有旧 valuation_results 表仍混存价格与信号，不将它误认为新 ValuationResult 的数据库实现，也不因同名认定新领域对象仍含价格。

C3 已建立独立 append-only Research Artifact 存储，尚未迁移到生产 PostgreSQL；旧 `valuation_results` 保留为历史实验结构，不承载新语义。生产迁移必须作为未来独立、人工确认的阶段执行；当前只使用 disposable/local/test PostgreSQL 和 CI 一次性实例。
Excel publisher 目前仍有三公司 adapter，可作为技术债保留；同一财务计算不能复制到表内。人工研究输入须显式导入并审计，不能静默反向控制模型。

## 工程治理

新增公司专用脚本只允许独有的一手解析、法律/披露结构或有退出计划的迁移 adapter；复用计算、假设、重大性、价格判断优先放 Core。
历史 20/30/40% 规则只属于原版本实验；不进入新 Router、研究结论或通用仓位规则。
策略、模拟、账户与真实执行独立；研究结果无论是否 READY 均不授权订单。
