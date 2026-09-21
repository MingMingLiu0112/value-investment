# A股价值投资 Agent：Excel MVP 执行目标（Codex 短执行版）

> 版本：v2.2
> 日期：2026-09-21
> 仓库：`MingMingLiu0112/value-investment`
> 目标文件：`docs/value-investment-excel-mvp-goal.md`

## 1. 当前唯一目标
尽快交付一个用户打开 Excel 就能实际使用的多公司价值投资研究版本。
当前固定三家公司：`600519 贵州茅台`、`000333 美的集团`、`601088 中国神华`。
用户打开 Excel 后，必须能回答：公司靠什么赚钱、财务怎么样、核心论点是什么、最强反证是什么、估值是否就绪、当前价格是否有研究吸引力、哪些事实会推翻结论、下一次关键事件是什么。
本阶段定位：**可追溯的价值投资研究辅助系统**，不是自动交易、保证盈利或券商下单系统。

## 2. 与现有目标文档的关系
本文件负责当前阶段 A/B 的范围、执行顺序和验收；`value-investment-goal-prompt.md` 是唯一启动入口，`value-investment-goal-framework-v2.md` 提供金融口径和后续验收约束。附件中的指令自本次合入起成为项目目标。
本文件不直接删除现有 `value-investment-goal-prompt.md` 的有效约束。
继续继承以下底线：一手披露优先、来源/Hash/日期可追溯、数据冲突不静默覆盖、quarantine 不进入正式估值、缺失值不填 0、历史数据遵守 point-in-time、WPS 原表发布保护、模拟与实盘隔离、R1/R2 独立验收。
若旧文档的短期顺序要求“继续只深挖茅台后才允许扩展”，与本文件冲突时，以本文件的 Excel MVP 顺序为准。
R1 历史验证和 R2 实盘准入继续保留，但不作为 Excel MVP 的前置条件。

## 3. 不可突破的边界
证据、数据或模型关键门禁失败时，只能降级为：`数据不足`、`研究未完成`、`估值未就绪`、`需复评`。
不得为了产生结论而放宽门禁。
不得自动下单、生成真实订单、生成真实券商数量、将模板本金当真实本金、将研究状态直接映射成真实仓位。
估值区间是研究结果，不得写成“可直接照做”的强制交易价。
Excel MVP 通过不等于历史策略有效或实盘准入。

## 4. 当前实施只分两个阶段

### 阶段 A：Excel MVP
先建立统一 `ResearchCase + ResearchGate + ValuationResult`。
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
估值未完成时允许 `bear/base/bull = None`。

## 6. 阶段 A 的统一研究门禁

### G0 证据门
检查当前价格、最新财报、核心事实、来源、自动验证、quarantine、数据日期。
失败输出：`数据不足`。保留仍有依据的财务和商业研究；行情缺失只阻断依赖当前价格的判断，不清空已有研究卡。

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
所有门禁结果独立保存。已证实的论点受损须单独突出展示，不被数据或估值缺口掩盖；缺失与负面事实不能混同。只有 G0~G3 通过且预先登记的吸引力判据满足时，才能升级为 `估值具备研究吸引力`；其他情况显示对应缺口或复评状态。
G4 不生成订单、股数或真实仓位。

## 7. 统一研究状态
只允许以下状态：
- `数据不足`
- `研究未完成`
- `估值未就绪`
- `研究不通过`
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
置信度为低时不得升级为 `估值具备研究吸引力`。

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

### 2026-09-21 阶段 A 已验收状态

阶段 A 的实际基线、证据与工作簿发布回执见
`excel-mvp-baseline-20260921.md` 和 `excel-mvp-stage-a-acceptance-20260921.md`。
三家公司均以统一 ResearchCase/ResearchGate 写入原 Excel，均明确标示
`估值未就绪`，且不生成订单、数量或真实仓位。此状态只完成研究展示层，下一唯一
任务为 B1：贵州茅台的适用主估值、情景、置信度和反向估值。

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

已导出冻结模型的 bear/base/bull 条件研究结果与有界反向估值诊断，结果文件为
`runtime/valuation-results/600519-current-equity-stage-b/evidence.json`。其状态为
`conditional_research_only`、置信度为低、`current_price` 与两项安全边际均为空：最近的
双源尝试为盘中报价，不满足模型日期与收盘价同日桥接。故 B1 尚未验收，不得将条件值
标为正式合理价、买卖价或研究吸引力；B2 不得提前开始。

归档的 2026-09-14 同日收盘价和模型不能替代该缺口：模型依赖的政策哈希
`ce8c7...` 已不在当前工作树、Git 历史或证据归档中，故无法从精确输入重演。归档
算术仅可阅读，不得导出为可复算价格比较或安全边际。后续必须由当日收盘后、同日完整
政策与证据链重新生成可复演模型；找不到旧输入时不回填或猜测。

2026-09-21 12:52 上海时间，`ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh`
已由 Windows 计划任务实际运行并返回 `0`。收据
`runtime/company-research/600519-preclose-capital-receipt-20260921T045237Z/`
记录了巨潮索引与资本刷新文件的 SHA-256，并明确 `trade_approved: false`。该成功只证明
收盘前资本事件证据链可运行；收盘价、同日模型桥接和 B1 验收仍待收盘后任务验证。

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

### B3 601088 周期模型
完成周期正常化估值、confidence、reverse valuation，并同步 Excel。

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

## 20. 每轮 Codex 汇报格式
每轮只汇报四块：
1. `Excel 用户可见新增`：本轮用户打开 Excel 能多看到什么。
2. `完成的代码`：核心文件和 run_id。
3. `当前 blockers`：最多 5 条。
4. `下一步唯一任务`：只允许一个最高优先任务。
不得用测试数量、脚本数量、文档数量代替业务进度。

## 21. 第一条执行指令
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
阶段 A 解决：能不能用统一结构论证多家公司？
阶段 B 解决：能不能对不同类型公司用适合的模型形成可复算估值？
R1 以后解决：这些规则在历史和前瞻模拟中是否具有足够经济证据？
R2 以后才解决：是否允许进入受限的人工实盘辅助。
四层不得混为一谈。

## 23. 后续顺序与环境约束
阶段 A → 阶段 B（茅台、美的、神华依次完成）→ 首例 P1/P2/P3、真实历史与前瞻模拟及 R1 → 多公司模拟组合 → R2 评审。已有必要行情、备份、风险显示和维护继续；MVP 不撤销已获授权的独立日常任务。
沿用原目标第5、6、8节的数据缺口处理、原表发布与环境保护。保护服务器 PTA、Hermes、PostgreSQL 和既有资源限额；原Excel的人工笔记、持仓、交易和月度历史必须保留。阶段 A 优先使用版本化 JSON 与现有持久化能力，不以新增数据库表为前置条件；一致性核验针对实际使用的事实来源。
每个阶段完成后，基于实际产物客观评估可用能力、限制及下一步合理性；缺乏依据的模型允许明确记录不适用及下一条有依据的研究路径，不能无限补证或为满足三公司数量强行通过。阶段 A、阶段 B、R1、R2 分别验收。
