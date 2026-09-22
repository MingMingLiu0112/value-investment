# A股价值投资 Agent：Excel MVP 执行目标（Codex 短执行版）

> 版本：v3.0
> 日期：2026-09-22
> 仓库：`MingMingLiu0112/value-investment`
> 目标文件：`docs/value-investment-excel-mvp-goal.md`

## 1. 当前唯一目标
先完成 P0.5 职责分离与三公司收敛，再交付一个用户打开 Excel 就能实际使用的多公司价值投资研究版本。
当前固定三家公司：`600519 贵州茅台`、`000333 美的集团`、`601088 中国神华`。
用户打开 Excel 后，必须能回答：公司靠什么赚钱、财务怎么样、核心论点是什么、最强反证是什么、估值是否就绪、当前价格是否有研究吸引力、哪些事实会推翻结论、下一次关键事件是什么。其中“估值是否就绪”属于 ResearchGate，“价格是否有研究吸引力”只允许由独立 PriceAttractivenessAssessment 在合法 PriceBridge 之后回答。
本阶段定位：**可追溯的价值投资研究辅助系统**，不是自动交易、保证盈利或券商下单系统。

## 2. 与现有目标文档的关系
本文件负责当前阶段 P0.5 与 A/B 的范围、执行顺序和验收；`value-investment-goal-prompt.md` 是唯一启动入口，`value-investment-architecture-correction-p05-20260922.md` 规定当前 P0.5 的强制顺序，`value-investment-goal-framework-v2.md` 提供金融口径和后续验收约束。附件中的指令自本次合入起成为项目目标。
本文件不直接删除现有 `value-investment-goal-prompt.md` 的有效约束。
继续继承以下底线：一手披露优先、来源/Hash/日期可追溯、数据冲突不静默覆盖、quarantine 不进入正式估值、缺失值不填 0、历史数据遵守 point-in-time、WPS 原表发布保护、模拟与实盘隔离、R1/R2 独立验收。
若旧文档的短期顺序要求“继续只深挖茅台后才允许扩展”，与本文件冲突时，以本文件的 P0.5 与 Excel MVP 顺序为准。
R1 历史验证和 R2 实盘准入继续保留，但不作为 Excel MVP 的前置条件。

## 3. 不可突破的边界
证据、数据或模型关键门禁失败时，只能降级为：`数据不足`、`研究未完成`、`估值未就绪`、`需复评`。
不得为了产生结论而放宽门禁。
不得自动下单、生成真实订单、生成真实券商数量、将模板本金当真实本金、将研究状态直接映射成真实仓位。
估值区间是研究结果，不得写成“可直接照做”的强制交易价。
Excel MVP 通过不等于历史策略有效或实盘准入。
ResearchGate 不得输出价格相关结论；没有 `READY` PriceBridge 时，PriceAttractiveness 只能为 `NOT_ASSESSABLE`，不得输出“估值具备研究吸引力”。

## 4. 当前实施分三个阶段

### 阶段 P0.5：职责分离与三公司收敛
当前最高优先级。第一任务修正 ResearchGate 与价格吸引力语义并新增 `PriceAttractivenessAssessment`；第二任务建立通用 `ValuationAssumptionSet`，把茅台现有命名假设只做映射，神华开始形成正常化假设；第三任务建立通用 Materiality 合同，以美的财务公司为首例，不直接解锁 FCFF。P0.5 未通过前，不继续 B2/B3 的证据考古，不新增第四家公司，不继续 Moutai execution / historical / R1 扩展。当前按用户要求暂停新开发，只完成目标文档合入。

### 阶段 A：Excel MVP
先建立统一 `ResearchCase + ResearchGate + ValuationResult + ModelValidity + PriceBridgeResult`。
让 600519、000333、601088 都进入 Excel，并使用同一研究结构。
阶段 A 不要求三家公司全部完成正式估值；未完成模型的公司必须显示 `估值未就绪`，不能硬填价值区间。目标是证明系统能用同一骨架论证不同公司。

### 阶段 B：模型逐只完成
严格按顺序完成：
1. 600519：主模型 + bear/base/bull + 反向估值。
2. 000333：FCFF + bear/base/bull + 反向估值。
3. 601088：周期正常化模型 + bear/base/bull + 反向估值。
不得并行开发三套不成熟模型。

## 5. 阶段 A 只新增三个通用核心对象

### 5.1 ResearchCase
新增：`src/value_investment_agent/research_case.py`
最少字段：
```python
symbol
name
as_of
industry
investment_path
thesis
return_driver
mispricing_hypothesis
financial_summary
positives
counter_evidence
thesis_breakers
next_events
evidence_status
valuation_status
research_status
blockers
evidence_refs
```
要求：可 JSON 序列化；每次生成带 `run_id`；可供 Excel 导出；Excel 不得成为唯一事实来源。
`symbol`、`name`、`run_id`、生成时间、研究版本及 `as_of` 必填；行情日期、财报期、发布时间/可用时间独立记录，缺失须为 null 并给出原因。`evidence_refs` 必须存在，各事实和解释关联具体证据；空列表不算证据通过。不同日期可以并列展示，但不得冒充同一时点的新数据。

### 5.2 ResearchGate
新增：`src/value_investment_agent/research_gate.py`
职责：把已有事实、商业研究和估值状态转换为统一研究状态。
职责中明确排除：真实订单、股数、真实仓位、券商执行。

### 5.3 ValuationResult
新增：`src/value_investment_agent/valuation_models/base.py`
最少字段：
```python
symbol
model_type
valuation_date
bear_value
base_value
bull_value
current_price
margin_to_bear
margin_to_base
confidence
assumptions
sensitivities
evidence_refs
blockers
status
```
估值未完成时允许 `bear/base/bull = None`。`ValuationResult` 不保存当前价格或安全边际；它只描述
企业价值。市场价格与安全边际属于 `PriceBridgeResult`，行情未形成时显示
`PENDING_EXTERNAL_DATA`，不反向把已完成估值标为未就绪。

## 6. 阶段 A 的统一研究门禁

### G0 证据门
检查最新财报、核心事实、来源、自动验证、quarantine、数据日期，并单独记录
当前价格的数据状态。失败输出：`数据不足`。行情缺失只标记
`PENDING_EXTERNAL_DATA`，不清空已有研究卡，也不使 G0~G3 的研究完成状态失败。

### G1 财务门
输出财务优势、财务弱点以及五维状态：盈利、现金、资产负债、成长、资本配置。
状态只允许：`强 / 正常 / 弱 / 不适用 / 数据不足`。
总分不是主结论。

### G2 商业论点门
至少需要：回报来源、竞争位置、错价假说、最强反证、Thesis Breakers。
缺失输出：`研究未完成`。

### G3 估值门
模型未完成或关键参数无依据时输出：`估值未就绪`。
不得自动回退到固定 PE/PB 主估值。

### G4 研究状态门
所有门禁结果独立保存。已证实的论点受损须单独突出展示，不被数据或估值缺口掩盖；
缺失与负面事实不能混同。G0~G3 通过时只输出
`研究与估值已就绪`，不输出价格相关结论。价格吸引力由独立的
`PriceAttractivenessAssessment` 在 `READY` PriceBridge 之后判断；无合法桥接时返回
`NOT_ASSESSABLE`。G4 不生成订单、股数或真实仓位。

## 7. 统一研究状态
当前状态由 `ResearchGate` 与 `PriceAttractivenessAssessment` 分别输出，聚合后只允许
以下中文状态：
- `数据不足`
- `研究未完成`
- `估值未就绪`
- `研究不通过`
- `研究与估值已就绪`
- `价格缺乏吸引力`
- `等待更有吸引力的价格`
- `重点观察`
- `估值具备研究吸引力`
- `持有研究跟踪`
- `暂停新增研究`
- `论点受损，需复评`
- `退出研究池`

禁止使用：`强烈买入`、`立即买入`、`满仓`、`清仓`、`目标仓位 X%`；研究状态不得直接产生订单。

## 8. Excel MVP 统一展示结构
优先复用现有：`00_首页Dashboard`、`00_公司总览`、公司研究页、估值页、`21_决策验证`、指标证据页。
不要新增大量 Sheet。

### 8.1 首页
首页至少显示：
| 股票 | 路径 | 数据日期 | 研究状态 | 估值状态 | 主要论点 | 最大反证 | 阻断项 | 下一事件 |
|---|---|---|---|---|---|---|---|---|
必须包含 600519、000333、601088。

### 8.2 公司研究卡
每家公司必须有：
1. 股票代码、公司名、行业、研究路径、`as_of`、行情日期、最新财报期。
2. 一句话 Thesis：靠什么赚钱、主要回报来源、错价假说或“尚未证明错价”。
3. 财务五维：盈利、现金、资产负债、成长、资本配置。
4. 至少 3 条支持依据。
5. 至少 3 条最强反证或明确“证据不足”。
6. 至少 3 条 Thesis Breakers。
支持依据与反证不得为凑数量生成；事实、解释、待验证风险线索分开标记。证据不足须明确具体缺口，不能计作已完成的支持/反证。Thesis Breakers 是有经济理由的复评条件，须标明依据、观察指标和可用数据；未经论证不得编造阈值。阶段 A 可以保留缺口，但三家公司均须展示有证据的财务事实与具体业务判断，空壳卡片不能通过。
7. 当前 blockers。
8. 下一事件 1~3 条。
9. 估值状态。

### 8.3 估值显示
估值未完成时只显示：`估值未就绪` + blockers。
估值完成后显示：主模型、保守价值、基准价值、乐观价值、当前价格、相对基准安全边际、相对保守情景安全边际、估值置信度、关键敏感参数。
不得只显示一个“目标价”。

## 9. 阶段 B：600519
先复用现有茅台研究成果，不得从零重做全部历史专项。
主模型从当前已研究的归母权益 / 剩余收益 / 可持续分配能力路径中选择一个冻结版本。
必须补齐：bear/base/bull、关键假设、敏感性、估值置信度、反向估值。
固定 PE/PB 只能做交叉检查。

## 10. 阶段 B：000333
主模型：FCFF。
复用 `scenario_valuation.py` 数学核心，不重写。
重点输入：EBIT/NOPAT、CapEx、折旧、营运资本、WACC、净债务/非经营资产、股数。
重点研究：ROIC、自由现金流、海外业务、资本配置。
输出 bear/base/bull、confidence、reverse valuation。

## 11. 阶段 B：601088
主模型：周期正常化估值。
禁止“最新一年低 PE = 低估”。
重点输入：中周期煤价、销量、单位成本、维持性 CapEx、电力/铁路/港口、净现金、可持续分红。
必须输出：正常化利润、bear/base/bull、周期位置解释、confidence、reverse valuation。

## 12. 反向估值
新增：`src/value_investment_agent/reverse_valuation.py`
目标只回答：当前市场价格要求公司未来做到什么。
可输出：隐含利润 CAGR、隐含长期 ROE/ROIC、隐含终值增长、隐含正常化煤价/利润。
反向估值仅用于解释，不是第二套主估值。每次固定其他假设，标明求解变量、搜索范围和估值日期；允许无解或多解，不同时把多个未知量宣称为唯一市场预期，不为匹配价格调整独立主模型。

## 13. 估值置信度
只允许：`高 / 中 / 低`。
使用透明规则，不使用 LLM 黑盒评分。
至少考虑：数据完整度、商业稳定性、行业周期性、关键参数敏感度、预测跨度、终值占比、模型交叉检查分歧。
置信度为低时，ResearchGate 不得输出研究与估值已就绪，也不得进入
`PriceAttractivenessAssessment` 的正向价格吸引力结论。

2026-09-22 已增加 `valuation_confidence.py`：置信度由上述显式证据按固定政策阈值计算；
未知、未测量或未通过必要检查时失败关闭为低，不采用 LLM 黑盒评分。

## 14. 安全边际
同时保留：
```text
margin_to_base
margin_to_bear
```
当前研究展示废止“安全边际 >= 30% => 自动建仓候选 => 10%仓位”的直接映射。历史冻结实验及回执保留原义，不追溯改写旧规则或已有模拟账本；后续策略变更另立版本验收。
安全边际只是研究输入之一。
研究状态至少同时考虑：证据、商业论点、公司质量、估值、估值置信度。

## 15. 旧 PE/PB 模型
`valuation.py` 不删除，但明确降级为 `reference_multiple_valuation`。
用途仅限：sanity check、相对估值参考、市场预期比较。
不得作为正式主内在价值来源，也不得继续为全市场新增股票硬编码目标 PE/PB。

## 16. Codex 实施顺序

### 2026-09-22 P0.5 合入状态

P0.5 文档已合入为 `docs/value-investment-architecture-correction-p05-20260922.md`，并从本日起优先于 B2/B3 证据补充。当前按用户要求暂停新开发，只完成目标合入；不新增 Shenhua / Midea 证据脚本，不继续 Moutai execution、historical、R1 refinement 或 paper strategy 扩展。

恢复开发后的唯一顺序为：

1. PriceAttractiveness semantic correction：修改 ResearchGate、新增 `price_attractiveness.py`、重组 `CurrentResearchStatus`，并补 READY / PENDING / STALE 状态测试；不修改 Moutai 估值参数、交易执行或仓位逻辑。
2. `ValuationAssumptionSet`：建立 Facts / Assumptions 分离，Moutai 只映射现有参数，Shenhua 开始形成正常化假设；不继续扩历史证据，不按股价反向调参。
3. Materiality：以 Midea 财务公司为首例建立通用合同，只判断 LOW / MEDIUM / HIGH / UNKNOWN，不直接解除 `MODEL_NOT_APPLICABLE`。

P0.5 全部通过后才恢复 Midea 研究级估值收敛和 Shenhua 正常化估值收敛。

### 2026-09-21 当前实施状态

阶段 A 的实际基线、证据与工作簿发布回执见
`excel-mvp-baseline-20260921.md` 和 `excel-mvp-stage-a-acceptance-20260921.md`。
三家公司均以统一 ResearchCase/ResearchGate 写入原 Excel，均明确标示
`估值未就绪`，且不生成订单、数量或真实仓位。研究展示层已跑通，但阶段 A 的严格
内容验收尚未通过：三家公司均需补足至少三条可追溯的支持依据、反证与 Thesis
Breakers，并完成五维财务状态及 G0-G4 门禁对齐。

下一顺序固定为：先完成 P0.5 的研究/价格语义、AssumptionSet 与 Materiality 三层，再恢复
Midea 研究级估值与 Shenhua 正常化估值。B1 现有条件性模型可保留为研究材料，但不得提前
写成正式估值结论或交易判断；价格吸引力必须等待合法 `READY` PriceBridge。

### A0 基线
创建 `docs/excel-mvp-baseline-20260921.md`。
只记录：当前 commit、当前 Excel Hash、三家公司已有数据覆盖、当前相关测试结果。
不要重新审计整个项目。

### A1 ResearchCase
创建 `research_case.py`。
先让 600519 能生成统一 ResearchCase JSON。

### A2 ResearchGate
创建 `research_gate.py`。
统一输出 research_status 和 blockers。

### A3 ValuationResult
创建 `valuation_models/base.py`。
此时不要求 000333 / 601088 有正式估值。

### A4 三家公司进入 Excel
600519 使用现有研究结果。
000333 允许 `估值未就绪`。
601088 允许 `估值未就绪`。
但三家公司都必须有：身份、数据日期、财务摘要、Thesis、反证、blockers、Thesis Breakers、下一事件。
完成 A4 后结束该轮并汇报阶段 A 验收，下一轮按 B1 继续；这不代表整个项目完成，也不自动暂停持续目标。不提前并行重写三套模型。

### B1 600519 主估值
完成 bear/base/bull、confidence、reverse valuation，并同步 Excel。

#### 2026-09-21 当前 B1 状态

已导出 2026-09-21 冻结模型的 bear/base/bull 条件研究结果和同日有界反向估值诊断，
结果文件为 `runtime/valuation-results/600519-current-equity-stage-b/evidence.json`。
同日双源行情 1,252.57 元/股已通过 matched close，价格桥接状态为 `READY`；相对熊/基准
情景分别为 -210.5% / -161.8%。该结果已写回原 Excel。

该结果状态仍是 `conditional_research_only`、置信度为低，`formal_fair_value` 为空、
`valuation_approved=false`、`trade_approved=false`、`live_eligible=false`。负安全边际只
说明当前价格高于这些条件情景值，不是卖出指令、低估/高估结论或研究吸引力。优势持续期
已审计为有界中央政策，但未来实际持续时长仍未得到经验证明；全年2026母公司可分配现金
尚未披露，折现率仍是研究区间而非实际未来资本成本。B1-P1 的模型准入已通过，但逐日
模拟执行政策尚未实现，因此不能形成模拟拟单或实盘准入。

2026-09-21 收盘后正式链已完成：双源收盘证据、同日 P1 证据链、反向估值诊断、独立
`PriceBridgeResult`、候选工作簿 WPS 只读校验和带备份的原子发布。发布的原表 SHA-256 为
`76b3d55e0009a88a1366b281acaca9b3238ab8e3c53e2bb340440ca28cdca946`；同日后一次神华候选卡
发布后，当前原表 SHA-256 为
`a1d755f7705135d3ada9c84a8021cb57b0c3b4459b08dc802f133aade4ddf26f`。
同日稍后，神华子公司归属边界审计证据并入研究卡并原子写回原 Excel 后，当前原表
SHA-256 为 `17036d1f8ebc094df9287ab25b4bf256f70b6aa9f1df23dedd16d3e7a98afa9b`。
2026-09-22 恢复 B1 同日价格桥接后再次候选构建、WPS 只读验证并原子发布，当前原表
SHA-256 为 `030e702789c37d66580f99ca5769b28289cd820457ad77c0c9196e019c499ef5`。
研究级阶段验收见 `docs/moutai-stage-b1-acceptance-20260922.md`；工程验收见
`docs/moutai-stage-b1-engineering-acceptance-20260921.md`。

### B2 000333 FCFF
完成 FCFF、confidence、reverse valuation，并同步 Excel。

#### 当前架构收敛约束（2026-09-21 用户指定）

本阶段的唯一工程目标是让 `000333` 通过统一接口生成
`ValuationResult`。输入仅限已验证的 `FinancialFacts` 与
`ResearchCase`；输出固定为 `bear/base/bull`、`confidence`、`blockers`。
必须复用统一 `ValuationModel` 和共享 `scenario_valuation.py` 算术，禁止
新增美的专属估值框架、以固定 PE 作为主模型、或修改交易/订单模块。

当 `FinancialFacts` 尚未通过验证时，仍须生成同一 JSON 合同并同步 Excel，
但三项情景值必须为 `null`、状态必须为 `估值未就绪`，并完整列出 blockers；
不得为了满足字段完整性伪造 FCFF 区间。只有验证后的事实、假设和每股桥接齐备，
才允许共享模型计算 bear/base/bull 与后续反向估值。

#### 2026-09-21 当前 B2 状态

共享 FCFF 契约已通过 fail-closed 工程验收，见
`docs/midea-stage-b2-engineering-acceptance-20260921.md`。工业口径 FCFF 剥离为
`MODEL_NOT_APPLICABLE`，合并企业价值桥接为 `VALUATION_NOT_READY`；不生成
bear/base/bull、价格桥接或安全边际。原因是年报未单独披露金融业务利润表、资产负债表、税费、
债务、现金与营运资本，不能把合并净债务和合并现金直接称为工业 FCFF 输入。

2026-09-22 已补齐共享情景算术路径：`FinancialFacts.scenario_inputs` 可承载显式
bear/base/bull 预测、终值、权益桥接、暴露分区、股份与证据，并复用
`scenario_valuation.value_scenario`。该路径仅用于工程验证；美的现有年报载荷仍保持
`not_ready`，不因此生成正式估值。

同日进一步把 FY2025 会计每股收益范围与期末 A/H 股本独立 Hash 锁定：
`midea-2025-share-basis-20260922`。该包记录期末总股本 `7,597,145,346` 股、会计加权
普通股 `7,559,265` 千股、稀释后 `7,608,132` 千股及年末库存股只有账面金额而无股数，
明确会计加权分母不注册为当前估值分母；`share_basis_approved=false`，未写入任何
`ordinary_shares` 模型输入，FCFF 生产路径继续 `not_ready`。

2026-09-22 同日完成估值适用性登记：`mature_manufacturing -> fcff` 经济路线为
`SUPPORTED`，但工业口径 FCFF 剥离为 `MODEL_NOT_APPLICABLE`、合并企业价值桥接为
`VALUATION_NOT_READY`，因此不注册算术模型和输入。生产结果同时嵌入 `valuation_route`
与 `valuation_applicability`，保持 `not_ready / PENDING_EXTERNAL_DATA`；FCFF facts
升至 v2 路径 `midea-fcff-facts-20260922`。

同日再增加 `midea-consolidated-equity-scope-20260922`，从同一份 Hash 锁定年报封存合并
归母普通股权益 `223,221,305` 千元、少数股东权益 `13,202,918` 千元、归母普通股净利
`43,945,411` 千元及可见金融业务口径。`residual_income_or_equity_value` 仅作为
`CANDIDATE_NOT_REGISTERED` 候选进入适用性证据和研究卡，预测 ROE、权益成本、派息政策和
当前普通股分母未注册；不生成任何情景值，FCFF 生产路径继续 `not_ready`。

同日再增加 `midea-2014-2024-equity-return-candidate-20260922`，把 2014--2024 各年原始
年报的归母权益、归母利润、现金分红和回购式现金回报锁成逐页候选序列。序列只证明历史
现金回报披露，不代表未来 ROE、权益成本、派息政策、当前普通股分母或干净盈余权益滚动
对账；适用性包的下一证据清单只列前瞻假设与当前范围，不把“历史证据仍缺失”继续写成阻断
原因。所有行 `model_input=null`，研究卡和 Excel 只展示候选证据，FCFF 与权益价值路线继续
`not_ready`，不生成任何情景值、价格、安全边际、仓位或订单。

### B3 601088 周期模型
完成周期正常化估值、confidence、reverse valuation，并同步 Excel。

#### 2026-09-21 当前 B3 状态

共享周期正常化模型和 2014--2025 原始序列已通过 fail-closed 工程验收，见
`docs/shenhua-stage-b3-engineering-acceptance-20260921.md`。已增加
`runtime/company-research/shenhua-cyclical-candidate-inputs-20260921/evidence.json`，
将官方披露整理为未审核候选。三项优先阻塞已进一步生成
`shenhua-2026-share-bridge-20260921`、`shenhua-2025-parent-operating-profit-bridge-20260921`
和 `shenhua-2025-attributable-net-cash-bridge-20260921` 三个未审核证据包；它们记录候选值
但均保持 `model_input=null`。维护/发展资本开支、绝对单位成本、折现率和长期增长率仍未批准，
因此估值状态保持 `VALUATION_NOT_READY`。

同日后增加 `shenhua-2025-subsidiary-allocation-evidence-20260921` 边界审计包：固化母公司
法人利润表、七家重要非全资子公司的持股、少数股东损益、分红、权益及财务摘要，并证明七家
少数股东损益合计 88.32 亿元对合并 93.34 亿元、少数股东权益合计 457.23 亿元对合并 723.44 亿元
仍存在未列示部分。该审计明确母公司投资收益 446.07 亿元不能当作集团归母税前营业利润，
所有估值输入继续为 null；对应研究卡已写回原 Excel。

2026-09-22 进一步复核 HKEX 英文/IFRS 年报 Note 44、Note 10 及主要子公司附注，增加
`shenhua-2025-ifrs-subsidiary-tax-review-20260922`。英文报表只列示内部抵销前的 Revenue、
Expenses 和 Profit and total comprehensive income，仍未披露子公司逐户税前利润和所得税；
税务调节中“不同分/子公司适用税率”影响 -42.28 亿元也阻断比例分配。因此神华估值仍为
`VALUATION_NOT_READY`，所有相关模型输入保持 null；该复核已写入研究卡并原子发布回原 Excel。

2026-09-22 另增加 2014--2025 运营周期序列
`shenhua-2014-2025-operational-cycle-series-20260922` 及其独立审查
`shenhua-2014-2025-operational-cycle-audit-20260922`。审查把煤炭价量、自产煤均价与单位成本、
售电量与电价全部定为逐页可追溯的时期事实，不批准任何字段进入 `CyclicalFacts.operating_inputs`；
同时记录混煤均价与自产煤单位成本不得配对、2019/2020 电价不可比、部分自产煤销量来自后续年报
对比表以及 2025 年产量 332.1 百万吨与销量 332.3 百万吨不得混用。对应研究卡已更新并原子发布回
原 Excel；估值状态保持 `VALUATION_NOT_READY`。

2026-09-22 进一步增加 2014--2025 归母利润与现金税候选序列
`shenhua-2014-2025-attributable-profit-series-20260922`。该包按年记录合并营业利润、税前利润、
所得税费用、归母/少数股东净利润和“支付的各项税费”，并给出统一所有权比例 pro forma 与不分摊
所得税的宽边界。它明确不把“支付的各项税费”当作所得税率，因为该现金流口径包含资源税及其他
税费；所有行仍为候选研究边界，未写入 `CyclicalFacts.operating_inputs`。对应研究卡已更新并
原子发布回原 Excel；估值状态保持 `VALUATION_NOT_READY`。

2026-09-22 继续增加 2014--2025 外部煤价与 2025 成本运输桥接
`shenhua-2014-2025-price-cost-transport-bridge-20260922`。该包把各年报披露的环渤海/NCEI 指数、
秦皇岛现货价、公司自产/长协/内部转移价及铁路、港口、航运单位成本逐页锁定，并明确 2018 缺失、
2019 只有区间、2023 指标定义切换和 73.2/77.7 百万吨内部煤电销售/耗用口径差异。对应研究卡已更新并
原子发布回原 Excel；未写入任何 `CyclicalFacts.operating_inputs`，估值状态保持
`VALUATION_NOT_READY`。

2026-09-22 再增加 NCEI/BSPI/CCTD 外部指数一手溯源包
`shenhua-external-index-provenance-20260922`。该包哈希归档 NCEI 首发公告、当前 NCEI 页面、
历史查询公开壳页、NDRC 的 BSPI 试运行通知和 CCTD 编制方案，并明确当前 NCEI 两个即时读数只作
观察、四类历史指数表均受缴费会员权限限制，不能冒充已取得的历史原始档案。对应研究卡已更新
并原子发布回原 Excel；未写入任何 `CyclicalFacts.operating_inputs`，估值状态保持
`VALUATION_NOT_READY`。

2026-09-22 再增加 CCTD 五个公开历史指数端点
`shenhua-public-index-history-20260922`：BSPI、太原、陕西、鄂尔多斯与长江口 JSON 均逐字节
归档并保留 URL、SHA-256 和抓取时间。BSPI 覆盖 2010-06-29 至 2026-09-16 共 802 个唯一日期；
所有观察值均为 `model_input=null`。该包同时记录 CTPI/TCPI 命名不一致、单位标注和发布缺口。

同轮进一步建立 BSPI 与年报年度均价对账包
`shenhua-bspi-annual-report-reconciliation-20260922`。2014、2015、2016、2017、2020、2021、
2022 七个可比年份的端点未加权年度均值与神华年报披露值的最大偏差为 0.49 元/吨，其中五个年末值
完全一致；2018/2019 无可比年报均值，2023 年起年报改用 NCEI。该结果只佐证序列口径吻合，不证明
历史值未经修订或原日期已公开。对应研究卡已更新并原子发布回原 Excel；未写入任何
`CyclicalFacts.operating_inputs`，估值状态保持 `VALUATION_NOT_READY`。

同轮再增加 BSPI 点-in-time 发布页与转载页证据包
`shenhua-bspi-point-in-time-publications-20260922`。秦皇岛煤炭网 2017/2021/2022 的
577/737/734 一手文章 API 响应与网页外壳、CCTD 2014/2015/2016 转载页，以及中国能源网明确标注
来源为“秦皇岛煤炭网”的 2017/2020/2021/2022 转载页均按 URL、字节数和 SHA-256 归档。证据包明确
2014 页面中的 525 不是年末最后发布，2017 最终发布 577 与年报 578 保持分离，2020 期末 585 的
运营方原文在当前搜索索引和完整栏目列表中缺失；易航网作为第二处独立转载页已一并哈希归档，
与中国能源网共同佐证 2020 期末 585 文本，但均不得升级为原文或用于插值。所有发布值均为
`model_input=null`。对应研究卡已更新并原子发布回原 Excel；未写入任何
`CyclicalFacts.operating_inputs`，估值状态保持 `VALUATION_NOT_READY`；发布后原表 SHA-256 为
`60845fda99b73aa9c7a94622c8bdade83e038b4ea020fc32e35d12aa3c4f8b5a`，随后易航网证据
补充后再次发布，新原表 SHA-256 为
`26883e034d23a4a0de7752674ac6b2be5edf61a319484645953cb6931b60465e`。

同日继续补齐该点时包的发布方归属与原始页可得性：中国能源网 2018 与河北长城网运营方集团报道
固定 569，CCTD 瑞达期货 2019 评论固定 551，CEI 2020 列表页只保留标题“环渤海动力煤价格指数585
元/吨”、2020-12-31 日期与登录受限的文章路径。新增 `PUBLISHER_PROVENANCE` 与
`ORIGINAL_AVAILABILITY`，`operator_primary_article_missing_years=[2018,2019,2020]`，
`not_collected_years=[2023,2024,2025]`；全部佐证仍为 `model_input=null`。证据包更新后 SHA-256
为 `2b5112abd8814c456874a0ff68704344b3c04b484ed534e809dca513d4bc1af2`，对应研究卡经 WPS
只读导航后原子发布回原 Excel，发布后原表 SHA-256 为
`2203b670ea21b9767e9d831b9289e9d16c80a8685f52fa2930b4569da118359f`。

同轮再增加 2025 内部煤电销售/耗用口径复核
`shenhua-2025-internal-coal-power-reconciliation-20260922`。中英文年报交叉核验确认 73.2 百万吨
是煤炭分部内部销售、77.7 百万吨是发电分部内部煤耗用，二者不是同一口径，且年报没有披露
4.5 百万吨差异的吨数桥接；47,702 百万元燃料动力成本不能除以 77.7 百万吨当作内部转移价。
对应研究卡已更新并原子发布回原 Excel；未写入任何 `CyclicalFacts.operating_inputs`，估值状态
保持 `VALUATION_NOT_READY`。

## 17. 阶段 A 验收标准
- [x] 三家公司出现在首页。
- [x] 三家公司使用统一 ResearchCase。
- [x] 三家公司都有数据日期。
- [x] 三家公司都有一句话 Thesis。
- [x] 三家公司都有支持证据。
- [x] 三家公司都有最强反证。
- [x] 三家公司都有 Thesis Breakers。
- [x] 三家公司都有 blockers。
- [x] 三家公司都有下一事件。
- [x] 未完成估值的公司明确显示 `估值未就绪`。
- [x] Excel 不生成订单、数量或真实仓位。
- [x] WPS 可复开。
- [x] Excel 关键字段与 JSON / 数据库一致。

阶段 A 完成语句：`Excel 多公司研究结构 MVP 已通过。`

## 18. 阶段 B 验收标准
- [ ] 600519 有冻结的研究主模型。
- [ ] 000333 有 FCFF。
- [ ] 601088 有周期正常化模型。
- [ ] 三家公司都有 bear/base/bull。
- [ ] 三家公司都有 valuation confidence。
- [ ] 三家公司都有 reverse valuation。
- [ ] PE/PB 仅作为交叉检查。
- [ ] 模型关键参数有依据。
- [ ] 关键数字可追溯到 evidence refs。
- [ ] quarantine 数据不进入模型。
- [ ] 估值未通过时 Excel 能正确降级。

阶段 B 完成语句：`多公司价值投资研究 MVP 已通过，可在 Excel 中对三类 A 股形成可追溯的研究级价值判断；该状态不等于 R1 历史有效性或 R2 实盘准入。`

## 19. 明确延后的内容
当前 MVP 不做：全市场深度 DCF、银行正式估值、保险正式估值、券商正式估值、LLM 自动交易、券商 API 下单、分钟/Tick 回测、宏观择时、自动真实仓位、历史安全边际参数优化、为了产生交易而调阈值、大量新增 Excel Sheet、大量新增公司专用一次性脚本。
P0.5 完成前另外冻结：新增第四家公司、继续新增 Midea/Shenhua 证据考古脚本、Moutai execution / historical / R1 扩展、全市场筛选、Web 前端、复杂 CycleAnalyzer 和市场情绪系统。

## 20. 每轮 Codex 汇报格式
按 P0.5 文档第 52 节固定汇报，并把 blocker 分类到 FACT / ASSUMPTION / MATERIALITY / MODEL / PRICE：

```text
Engineering Status:
Current Data Status:
本轮解决的问题类型:
本轮通用架构变化:
本轮公司适配变化:
测试:
新增 company-specific scripts:
当前 blockers:
下一唯一任务:
等待的 Production Validation:
```

不得用测试数量、脚本数量、文档数量代替业务进度；新增公司专用脚本必须写明理由。

## 21. 第一条执行指令
以下 A0-A4 是 2026-09-21 阶段 A 的历史执行记录，不再重复执行。当前第一执行指令以 P0.5 文档第 53 节为准：暂停新增 Shenhua / Midea 证据脚本，恢复后先做 PriceAttractiveness semantic correction。

Codex 立即执行：
1. 创建 `docs/excel-mvp-baseline-20260921.md`。
2. 创建 `src/value_investment_agent/research_case.py`。
3. 创建 `src/value_investment_agent/research_gate.py`。
4. 创建 `src/value_investment_agent/valuation_models/base.py`。
5. 将现有 600519 研究成果转换为第一个 `ResearchCase`。
6. 为 000333 和 601088 生成同结构 ResearchCase，允许估值状态为 `估值未就绪`。
7. 将三家公司同步到当前 Excel 首页 / 公司总览。
8. 验证 WPS 可复开和关键字段一致。
9. 结束本轮阶段 A 工作并汇报，后续按 B1 继续。
10. 汇报阶段 A 当前完成度。
在第 7 步完成之前，不开始重写三套估值模型。

## 22. 最终判断标准
项目是否在前进，不看代码量，只看 Excel 是否越来越能帮助投资者理解并比较真实公司。
阶段 P0.5 解决：研究、估值、假设、重大性、价格桥接和价格吸引力是否彻底分离？
阶段 A 解决：能不能用统一结构论证多家公司？
阶段 B 解决：能不能对不同类型公司用适合的模型形成可复算估值？
R1 以后解决：这些规则在历史和前瞻模拟中是否具有足够经济证据？
R2 以后才解决：是否允许进入受限的人工实盘辅助。
各层不得混为一谈。

## 23. 后续顺序与环境约束
阶段 A（已验收）→ P0.5 → Midea 研究级估值收敛 → Shenhua 正常化估值收敛 → 三公司统一验收与冻结 → 20-50 家固定跨行业样本 → 之后才恢复首例 P1/P2/P3、真实历史与前瞻模拟及 R1 → 多公司模拟组合 → R2 评审。已有必要行情、备份、风险显示和维护继续；MVP 不撤销已获授权的独立日常任务。
沿用原目标第5、6、8节的数据缺口处理、原表发布与环境保护。保护服务器 PTA、Hermes、PostgreSQL 和既有资源限额；原Excel的人工笔记、持仓、交易和月度历史必须保留。阶段 A 优先使用版本化 JSON 与现有持久化能力，不以新增数据库表为前置条件；一致性核验针对实际使用的事实来源。
每个阶段完成后，基于实际产物客观评估可用能力、限制及下一步合理性；缺乏依据的模型允许明确记录不适用及下一条有依据的研究路径，不能无限补证或为满足三公司数量强行通过。P0.5、阶段 A、阶段 B、R1、R2 分别验收。

## 24. P0.5 验收与恢复顺序

- [x] ResearchGate 不再输出价格相关结论，只有研究状态：数据不足、研究未完成、估值未就绪、研究未通过、研究与估值已就绪。
- [x] 新增 `PriceAttractivenessAssessment`；只有合法 `READY` PriceBridge 才可输出价格吸引力，PENDING / STALE / INVALID 一律 `NOT_ASSESSABLE`。
- [x] 禁止统一 30% 安全边际或固定价格阈值，必须 Profile-aware；置信度低或熊市下行风险过高时不得输出 `RESEARCH_ATTRACTIVE`。
- [x] 新增 `ValuationAssumption` / `ValuationAssumptionSet`，Facts 与 Assumptions 永久分离；每个假设有 basis、rationale、evidence、confidence、sensitivity，模型内部不得隐藏关键经济假设。
- [x] 新增 Materiality 合同；UNKNOWN 继续 fail-closed，LOW / IMMATERIAL 必须有量化暴露或上下界，不得自动解除 MODEL_NOT_APPLICABLE。
- [x] Moutai 假设映射到统一结构但参数不改；Midea blocker 明确分类为事实、假设、重大性或模型适用性；Shenhua 从历史证据收集转向形成正常化假设。
- [x] 三家公司共享同一 PriceAttractiveness 接口；Excel 展示 Research、Valuation、Assumption status、PriceBridge 和 PriceAttractiveness，但不生成买卖指令。
- [x] Core tests 进入 GitHub Actions；提交至少按 PriceAttractiveness、Assumptions、Materiality+Midea、三公司适配+Excel、Tests/CI/docs 的意图拆分。

只有以上全部通过，才允许写 P0.5 完成语句并恢复三公司生产估值收敛。
