# LONG-TERM VALUE INVESTMENT SYSTEM ROADMAP

版本：2026-09-22 / roadmap-v1。规划状态：已设计，尚未实施。审查基线：`494d0857c7edb4b76b0527d773065013b7abf2d1`。

本文件规划未来多个 Codex Goal Runs，不是一次性开发全部系统的指令。职责：跨阶段产品路线、依赖和毕业门槛；不得放宽 `AGENTS.md`、架构、研究方法或证据政策。唯一待启动目标为 M1，其执行范围在 [current-stage-goal.md](docs/current-stage-goal.md)；运行事实在 [execution-status.md](docs/execution-status.md)。完成一个 Milestone 后停止、审查，再由用户启动下一个，内部工作包不再膨胀为 C4/C5/C6 平行目标。

## 1. Current Reality Audit

### 1.1 基线与审查边界

| 项目 | 实际核查结果 |
| --- | --- |
| 本地 HEAD / GitHub main | 均为 `494d0857c7edb4b76b0527d773065013b7abf2d1` |
| 最近提交 | 2026-09-22 20:33:40 +08:00，`C3.14 close governance and record green CI receipt` |
| 审查开始工作树 | 干净；本轮后续文档改动不属于这个已提交基线 |
| GitHub CI | [当前 HEAD 的 run 35727941981](https://github.com/MingMingLiu0112/value-investment/actions/runs/35727941981)：offline-core、postgres-integration 均 success；push main / PR 自动触发；main 当前未开启 branch protection |
| 本机重跑 | 当前 workflow 清单合并 PostgreSQL 测试：173 passed、4 skipped；冻结茅台及三公司验收：9 passed。历史文档的 176 passed 不作本次实测数 |
| 真实 runtime 内存 replay | `all_semantics_matched=true`、`action=no_order`；没有写 runtime 或连接数据库 |
| 当前原 Excel | 12,138,778 bytes，修改时间 2026-09-22 17:30:45；SHA-256 `4EA4AB6F291E0D3C8838A1729007C8B29D0825CCF7CA6459BBD16257BEC0188E` |
| 未验证 | 当日生产 PostgreSQL、服务器资源/服务、计划任务、最新行情原件、全部历史测试、WPS 界面及公式重算；本轮没有操作这些资产 |

Excel 当前 Hash 与历史冻结记录不同，不据此判断损坏，也不宣称仍是冻结原件。后续发布必须从当前文件重新取源 Hash、保留人工修改。本次只核对文件元数据、既有验收及 publisher 代码，未对所有表格单元格做内容审计。

### 1.2 真实能力，不按代码数量计进度

| 能力 | 结论 | 代码或产物证据 |
| --- | --- | --- |
| Stage A / P0 / P0.5 / 三公司展示 | 继承冻结，不重建；不等于研究内容全部合格 | 冻结验收 9 项本轮通过；ResearchGate、ValuationResult、PriceBridge 已分层 |
| C0 价格桥接 | 共享身份、时点、算术合同已落地 | `price_bridge.py`、`quote_snapshot.py`、相关离线回归 |
| C1 准入、C2 分配 | 有正式合同；三公司现金回报仍 PARTIAL | `fixed_sample_admission.py`、`distribution.py`、真实 replay |
| C3 研究平台 | 有可复用工程核心，不是生产研究平台完成 | `research_application.py`、`research_artifact_repository.py`、`research_batch.py`、模型 Registry、manifest |
| PostgreSQL | 一次性测试实例验证持久化；尚无生产迁移证据 | `sql/20260922_research_artifacts.sql`；4 项 CI integration 使用自包含 fixture，不是实时市场或生产数据 |
| 三公司 E2E | 保留旧语义，包括拒绝与缺口，不证明估值正确 | `research_e2e_replay.py`；本轮真实 runtime replay 为内存 Repository，和 CI PostgreSQL fixture 是两类证据 |
| 扩样本输入 | 尚不能直接通用 onboarding | replay 固定 `SYMBOLS` / 茅台指针，`build_replay_inputs()` 第 496 行按 symbol 选载荷 |
| Excel 新链路 | 旧展示可保留，新 Application result 尚未接入 | `workbook_simple_overview.py` 第 88/113/226/255 行仍读旧 runtime 指针 |
| 全市场基础 | 有旧行情采集、官方 Universe 对账及 baseline，不是从零开始 | `official_universe.py`、`market.py`、`cli.py` 第 428/445 行 |
| 多通道研究漏斗 | 尚未形成正式新链路 | `market.py` 第 103/105 行仍为 PE<=25、PB<=3、市值>=50亿元的历史 baseline；CLI 仍可调用，不能宣称已退役 |
| Business Quality / 决策 / 组合 / 事件 | 有研究字段及旧实验资产，没有本路线要求的完整正式域 | 新核心未发现 InvestmentDecisionReview、EntryThesisSnapshot、InvestmentConsistencyReview、DecisionJournalEntry、ChangeEvent 等正式类型 |

### 1.3 三家公司当前结论

| 公司 | 估值 / 价格桥接 | 分配与研究 | 可以说明什么 |
| --- | --- | --- | --- |
| 600519 贵州茅台 | conditional_research_only、低置信度；ModelValidity VALID、PriceBridge READY | cash_return PARTIAL；production valuation NOT_AVAILABLE | 有条件情景和合法价格连接；不能称为买入依据或完成股息研究 |
| 000333 美的集团 | not_ready；无可用三情景，缺有效性；bridge PENDING_EXTERNAL_DATA | 模型输入/口径问题仍在；cash_return PARTIAL | FCFF 算术可用，不等于美的 FCFF 研究完成；不只是等待行情 |
| 601088 中国神华 | not_ready；正常化输入未解决；bridge PENDING_EXTERNAL_DATA | 有 current / normalized yield 类型，但 cash_return PARTIAL | 两种股息率能分开表达，不证明正常化股息可持续 |

真实 replay 源估值 Hash 分别为 `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`、`10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc`、`b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6`。茅台引用是 rolling 指针，今后必须在收据中锁定已解析版本；后两家的旧模型日期不代表今日估值。

### 1.4 本轮复现的工程风险

以下没有顺手修复，纳入 M1 的同一输入可信闭环：

1. **日期一致性缺口**：`research_application.py:292` 用 `spec.as_of` 覆盖 facts 日期后，只比较 case；内存 fixture 证明 case/spec=2025-12-31、facts=2024-12-31 仍返回 outcome，并产生 2024-12-31 valuation。需要先定义研究日、财报期、估值日各自含义，不是简单强制财报期等于研究日。
2. **PIT 可用时间缺口**：同一入口第 266 行接受调用方 available_at；2025 年 facts/case 可以随结果标记 2024-01-01。类型里“有时间字段”不等于完整防未来数据验证。
3. **增量复用缺口**：`research_batch.py:310` 仅凭相同 input hash 与非 FAILED 复用；fixture 将 rule_version 从 v1 改到 v2，仍得到 UNCHANGED。规则、模型、解析器、Profile、事件扫描截止日和报价变化必须进入依赖 fingerprint 或失效检查。
4. **假设有两条表达路径**：Runner 保存 `spec.assumptions`，但 `model.value(spec.facts, spec.research_case)` 实际使用 facts 内的 scenario_inputs。尚需证明登记假设和计算输入一一对应，不能仅保存一个与计算无关的假设对象。
5. **G3 仍是输入状态门**：`research_gate.py:82` 读取 case.valuation_status；Runner 先 evaluate 再算模型。G2 检查论点文本、三组证据引用及事件文本，是有用结构门，但并未自动验证经济逻辑真伪。M1 要明确 G0-G2、计算、G3/人工研究复核的顺序与身份，不能自动批准全部新估值。

Repository 目前以 API/Hash 保持 append-only 语义，DDL 没有禁止数据库角色直接 UPDATE/DELETE 的机制；运行时 Facts、假设版本与完整依赖图尚未全量持久化。M1 补最小可重放输入包，生产权限/事务/备份在 M6 验收，不把测试 Repository 当成生产抗篡改系统。

### 1.5 方向与成熟度判断

核心方向没有变成自动交易系统；新路径保持研究/价格/执行隔离。风险是**平台合同完成速度快于研究内容和用户闭环**，以及旧入口/显示与新平台并存。不是推倒重来，也不能继续只数接口。

脚本文件名包含 moutai/midea/shenhua 的数量分别为 195/26/23；这不是活跃任务数。独有披露解析和历史 replay 可保留；新公司不得复制估值、Gate、桥接、发布或日更流水线。只在相关迁移完成后逐步退役重复入口，不做全仓库清理。

| 成熟度 | 毕业含义 | 当前 |
| --- | --- | --- |
| L0 Engineering Prototype | 合同、算术、存储和拒绝路径可测 | 已具备 |
| L1 Research Tool | 多家真实公司的可追溯研究、情景、股息与可读展示 | 早期 / PARTIAL；尚未达到 M1 毕业 |
| L2 Opportunity Discovery | 多通道稳定发现/排除候选，解释 Why Now | 未达到；旧 screen 不算毕业 |
| L3 Decision Support | 可解释的复核卡、入场论点及买卖一致性 | 未达到 |
| L4 Portfolio Decision Support | 结合私人 IPS/持仓/现金提出保守仓位复核 | 未达到 |
| L5 Continuous Monitoring | 真实事件驱动、静默与报警、可恢复运营 | 未达到 |

工程基础成熟度较高；研究可用性低到中；真实决策、组合、持续监控成熟度低。测试通过不证明策略有效，replay 成功不证明历史收益，Excel 能打开不证明估值正确。

## 2. Final Product Definition

面向 A 股中长期价值投资的智能研究、机会发现、持仓跟踪和决策支持系统，同时服务 **Capital Appreciation + Sustainable Dividend / Cash Return**。不承诺盈利、稳定收益或分红必然增长。

```text
全 A 股 Universe -> 多通道 Screen -> Candidate Pool -> Deep Research
-> ResearchCase + Business/Financial Quality + Capital Allocation
-> Distribution Sustainability + Profile-aware Valuation + Reverse Valuation
-> ModelValidity + PriceBridge -> Price Attractiveness
-> Decision Review + Portfolio Context -> Human Decision
-> Entry Thesis / Journal -> Monitoring -> New Evidence -> Thesis Revalidation
```

后台以便宜的计算筛查覆盖，再对小集合进行昂贵研究。L1 数百、L2 约 50-100、L3 约 10-30、L4 约 0-10 是容量设计，不是强制配额。全市场数量从当期官方身份清单求得，不硬编码“4000+”作为完整覆盖证明。允许高关注为零、全部 WAIT、全部现金。

最终用户能解释：今天研究谁、为何值得研究、为何现在考虑买、下跌后为何加或不加、为何继续持有、何时减仓、哪条原始逻辑已失效、组合是否集中、股息是否可持续、今天哪些变化需要复核。

## 3. Investment Philosophy

- 好公司不等于好股票；低 PE/PB 不等于低估；高当期股息率不等于可持续现金回报。
- 企业价值来自未来可归属的经济现金来源；竞争优势、再投资收益、资本配置和价格必须分开研究。
- 企业内在价值增长与股东分配共同解释长期回报，但不能把已包含在估值中的股息、回购、现金或终值再加一次。
- Bear/Base/Bull、假设范围、敏感性、最强反证与 Confidence 是默认输出，不输出缺少边界的精确单点目标价。
- 当前利润/商品价/股息与中周期正常化水平分开。金融、保险、NAV 等未登记经济合同前为 UNSUPPORTED，不自动套 FCFF。
- Research Attractive 不是 Buy Signal；所有决策状态只提示人工复核。证据不足、低置信度、模型不适用、报价不可靠或重大冲突时输出 WAIT / RESEARCH / NOT_ASSESSABLE。
- 不为产生交易调阈值、不回测拟合最高收益；验证研究过程、一致性、数据可用时间和错误放行。

方法依据：股利、潜在可分配权益现金和企业现金流不同，现金创造还要考虑再投资及债务现金流；本路线据此分开 Distribution 与 Valuation，而不是把股息率当价值。[Damodaran: Cash Flows](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm)
估值必须匹配现金流范围和折现率，不能混用股权与企业口径。[Damodaran: Valuation](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html)
组合建议前先明确投资者目标、风险承受能力、流动性、期限、税务及其他约束；这支持本项目先建立人工确认 IPS，而非默认固定股票权重。[CFA Institute: Suitability](https://www.cfainstitute.org/standards/professionals/code-ethics-standards/standards-of-practice-iii-c)
上述来源支持原则，不替本项目设定买点、仓位或收益门槛；具体政策需预登记理由、适用范围、反例和版本。

## 4. Target Domain Architecture

沿用现有 Domain -> Application -> Provider/Repository/Publisher 分层，不为路线图创建一批空类。下表是目标合同，除第 1 节明确确认者外均不表示已经实现。

| 域 / 对象 | 必要职责与输出 |
| --- | --- |
| Universe / SecurityIdentity | 交易所+证券身份、上市/退市/改名、交易状态、PIT 成分、覆盖与不支持原因；不得只靠代码前缀 |
| ChannelScreen / Candidate | Quality、Dividend/Cash Return、Value、Cyclical 四条独立可解释通道；保留入/出原因、缺失与否决；合并去重不丢原因 |
| ResearchProfile / CycleProfile | 经济画像、生命周期、资本结构、必需事实、适用模型；多画像可重叠，未知不猜测 |
| FinancialFacts / AssumptionSet | 事实期间/范围/单位与未来假设分开；版本、available_at、校验、证据、依赖输入包 |
| ResearchCase | 生意/客户/优势、Thesis、Return Driver、Mispricing Hypothesis、支持、反证、breaker、下一事件与研究者复核 |
| BusinessQualityAssessment | Moat、Pricing Power、Customer Stickiness、行业结构、ROIC/Incremental ROIC、再投资空间、资本密度、现金转换、优势期；每项有 Strengths/Weaknesses/Evidence/Confidence/不适用原因 |
| CapitalAllocationAssessment | 再投资、并购、偿债、分红、回购、现金保留、稀释；评估每股价值影响，不只列金额 |
| DistributionCapacity / Sustainability | 现金来源、必要投入、债务、资本约束、正常化分配、压力情景；不依赖报价，UNKNOWN 必须保留 |
| DividendYieldSnapshot | ordinary/special、paid/declared/forward/normalized、DPS、价格、股份/币种、known_at；不得用后来披露回填旧日 |
| ValuationRouter / Model Registry | 三现有模型先复用；扩模型需登记 Facts schema、经济适用性、版本和交叉验证，不用默认模型兜底 |
| ValuationResult / ReverseValuation | 三情景、置信度、敏感性、假设、证据、blockers；反向求解冻结其他假设、限定区间、多解/无解显式表达 |
| ModelValidity / PriceBridge | 新事件是否使特定模型 STALE；报价身份、时点和范围合法才连接，缺行情不清空已有估值 |
| PriceAttractiveness | 价格相对条件价值的位置；不能绕过研究门、适用性或反证，更不能直接变仓位 |

Quality 通道重视持续盈利、现金转换、资本效率、健康资产负债和再投资，不能直接按总分入买入池。Dividend 通道必须区分收益率筛查与可持续性研究；派息高但借债、必要 CapEx 大、周期顶点或一次性分红要暴露。Cyclical 用正常化盈利/分配，不永久外推峰值。Value 通道识别可验证折价机制及资产/盈利质量，不以单一低倍数批准。

依赖顺序：G0-G2 可先评估 -> 适用模型计算 -> G3 绑定本次估值与研究复核 -> Price Assessment。重大研究 blocker 可阻断结论，但不得把“完整 G3 先通过”作为模型计算的前置条件。

## 5. Target Decision Architecture

### 正式合同

`InvestmentDecisionReview` 至少包含 security_id、as_of、状态、理由代码及自然语言、前置检查、反证、阻断项、置信度、适用账户上下文、规则版本、Evidence Bundle、requires_human_review=true、action=no_order。

状态：INSUFFICIENT_RESEARCH / RESEARCH_CANDIDATE / WATCH / WAIT_FOR_PRICE / MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW / HOLD / MANUAL_REDUCE_REVIEW / MANUAL_EXIT_REVIEW。内部简称仅用于展示映射，不成为 broker API。数据未知不能默认为 HOLD，未完成减仓评估也不能假称应该继续持有。

### 前置条件与优先级

1. 先校验证券、版本、证据与 PIT 完整性，区分未知、冲突、未支持和已确认重大破坏。
2. 经证据确认的 Thesis Breaker 优先 Critical；即使便宜也禁止自动升级为 ADD。疑似 breaker 输出紧急人工核查，不把传闻当事实。
3. BUY/ADD 同时需要：Gates、商业/财务质量、Thesis、适用且可用的估值、最低置信度政策、ModelValidity、PriceBridge、反证复核、重大性、适用时的股息可持续性、Portfolio Capacity。
4. 缺 Portfolio/IPS 时只能研究或等待，不能发针对个人的正向 BUY/ADD 或数值权重。M3 只接最小已确认 capacity 合同，完整容量计算属于 M4。
5. EXIT/REDUCE 风险提示与 BUY 前置条件分开：已证实的永久损害不能因报价缺失被静默屏蔽，但必须说明缺报价、不得给交易数量/执行价。
6. 显示主状态并保留所有风险原因；禁止用加权总分抵消 veto。规则冲突采用显式优先级，不依赖代码分支顺序的偶然性。

| 状态 | 必须解释 | 不能作为唯一依据 |
| --- | --- | --- |
| BUY_REVIEW | Why Now、生意与回报、预期差、三情景、价格位置、置信度、股息条件、反证、breaker、持有逻辑 | 低 PE、高股息或单一安全边际 |
| ADD_REVIEW | 对比 Entry Thesis：价值是否维持、证据/置信度是否改善、风险容量是否允许，为何与第一次买入一致 | 股价下跌、摊低成本 |
| HOLD | Thesis/价值创造/资本配置/股息能力仍合理，风险未越界，当前继续持有理由 | 未触发卖出或数据缺失 |
| REDUCE_REVIEW | 明确 valuation / fundamental / concentration / opportunity-cost 类型及依据 | 价格上涨一定比例 |
| EXIT_REVIEW | 逐条比较原始 Thesis，列出 BROKEN、永久损害、极端高估或组合/机会成本原因 | 跌20%/涨30%自动退出 |

### Cards、Entry 与一致性

每次 BUY_REVIEW 生成 Buy Logic Card：为何现在关注、怎样赚钱、为何是好/可接受生意、优势、回报来源、市场可能错在哪里、Bear/Base/Bull、当前价及日期/位置、置信度、当前/正常化股息率与可持续性、风险、最强反证、错误证据、持有期限逻辑和跟踪事件。每次 HOLD/ADD/REDUCE/EXIT 也生成对应理由卡，用户应能复述，而不是看分数。

用户明确确认实际买入或模拟买入后，冻结 `EntryThesisSnapshot`：entry date/price、research/facts/assumptions/valuation 版本、核心 Thesis、回报来源、误价假说、三情景/置信度、股息论点、持有逻辑、风险/反证/breakers、催化/事件、Reasons to Add / NOT Add / Reduce / Exit。仅进入 BUY_REVIEW 不创建虚构成交。既有持仓没有原始记录时只能建立标注“事后重建”的基线，禁止回填成当时已知。

`InvestmentConsistencyReview` 对比 Original vs Current Thesis/Valuation/Risks/Dividend/Breakers，输出 CONSISTENT / WEAKENED / BROKEN / FULFILLED，逐项给 evidence 和 change reason；若原始快照缺失则不可评估。FULFILLED 不自动等于卖出。

`DecisionEvidenceBundle` 冻结 ResearchCase、Facts、Assumptions、Valuation、ModelValidity、Quote、Distribution、Portfolio Snapshot、Decision Rule、Evidence references 的版本/Hash。`DecisionJournalEntry` 记录时间、人工确认价格、系统意见、用户最终决定、双方理由、Entry 引用、实际/模拟区分；更正追加不覆盖。逻辑正确但亏损与逻辑错误却盈利分开复盘。

## 6. Target Portfolio Architecture

`InvestorPolicyStatement` 由用户确认目标、收入需要、可投资资产范围、期限、应急现金/负债、风险承受及税费口径。未知不猜测；研究工作可继续，但暂停个人化容量/仓位结论。

`PortfolioSnapshot` 保存 as_of、实际/模拟、账户范围、资产/现金/持仓数量、成本与市值口径、行业/共同风险、快照和人工核对记录。数据经明确导入或用户确认，不连接自动下单；私有账户数据不得进公开 GitHub。

`PortfolioRiskAssessment` 覆盖单股、行业、周期、同因子/商品/客户暴露、高股息、高估值、低置信度、流动性、现金、Thesis Risk。下行损失和永久资本损害优先，波动率/VaR 只能补充，估计相关性不被当成稳定真值。

`PositionGuidance` 输出允许/不允许升级、阶段、条件范围与剩余容量，而非单股各算20%。推荐增量受单股、行业、共同风险、流动性、现金和总组合约束的最紧上限限制；多个候选共用预算，不能重复分配同一现金。具体上限须由 IPS/政策审查登记，本路线不捏造通用百分比。

Starter -> Normal -> Add -> Max 每次升级需新证据/置信度/价格改善和容量；LOW Confidence 即使看似便宜也不发大仓位建议，未知可为零。正常持有 -> 停止加仓 -> Reduce -> Major Reduce -> Exit 保留降级原因。允许完全不持仓，不为资金利用率强制满仓。

`DividendIncomeProjection` 区分已到账、已宣告未到账、Forward、Normalized sustainable income；按实际持股/权益登记/币种/税费情景计算，不能把承诺当现金。显示 Annual/Forward/Normalized Income、Yield on Cost（仅成本体验）、Dividend Concentration、Sustainability Distribution。回购不是个人到账股息，特别股息不机械年化。目标收入不足不能通过增加周期高息暴露掩盖风险。

## 7. Target Event Architecture

每天更新行情、公告/财报、分红、回购、资本结构及重大经营信息，不每天重做所有深度研究。使用变化依赖：Data -> Change Detector -> Materiality -> Affected Dependencies -> Invalidate/Recalculate -> Review -> Notify。

`ChangeEvent`：event_id、security_id/symbol、event_type、detected_at、effective_at、available_at、previous_state、current_state、severity、reason、evidence_refs、confidence、requires_human_review、supersedes/correction 引用。严格区分事件生效、披露和系统知晓时间。

事件类型至少为 NEW_FINANCIAL_REPORT、MATERIAL_ANNOUNCEMENT、DIVIDEND_CHANGE、BUYBACK、CAPITAL_ALLOCATION_CHANGE、VALUATION_ZONE_CHANGED、PRICE_ATTRACTIVENESS_CHANGED、THESIS_WEAKENED、THESIS_BREAKER_TRIGGERED、MODEL_STALE、POSITION_RISK_CHANGED。

价格变动只重算桥接/价格位置，不能直接改内在价值。财报或资本动作按依赖重算 Facts/Valuation/Distribution；Thesis 变化回看 Entry。MarketContext 只影响研究优先级、风险解释和执行谨慎程度，不改 Bear/Base/Bull。

通知必须幂等、合并、可确认、可重试；无重要变化静默，正常日 0 合法。关键源失联或扫描中断作为系统健康告警，不伪装为“没有重大事件”。晚到、更正、重复、乱序事件与重启需要 replay。Critical breaker 不被普通通知去重吞掉。

每周关注池复核，每月组合/股息复核，财报季完整 Thesis 复核，重大事件即时复核。建立 outbox/投递状态和审计，先有可验证 run-once，再独立授权调度。该路线图本身不创建自动任务。

## 8. Board / Dashboard Architecture

继续使用唯一原 WPS Excel；M1 首先接 Application read model，未来 Web 复用，不在表格重写 Domain。板卡是同一事实的投影，不是第二套状态机。

| 板卡 | 回答的问题 / 最小内容 |
| --- | --- |
| 全市场 | 官方 Universe 分母、实际覆盖、报价/财报日期、失败/不支持、数据健康 |
| 候选池 | 多通道进入/离开原因、Why Now、rule version、待补证据 |
| 深度研究 | ResearchCase、完成状态、商业/财务/资本配置、反证、事件 |
| 重点关注 | 0-10 可为空；研究注意力而非荐股排名 |
| 买入 / 加仓复核 | Logic Card、前置条件、置信度、Entry 对比及容量 |
| 当前持仓 | HOLD 理由、Thesis/估值/股息变化、持仓快照时点 |
| 风险 / 减仓 / 退出 | 原始买入逻辑变化、严重性、原因类别和人工复核 |
| 股息现金流 | Current/Forward/Normalized、到账与计划、覆盖和集中风险 |
| 今日 / 本周变化 | 新进/退出重点关注、各类 Review、Thesis/Dividend alerts、重大事件、0 状态与源健康 |

每个数字/状态展示 as_of、available_at、来源/版本、Confidence、blockers。当前快照与历史 replay 显著区分。不能从空白得出零值，不能从 display_text 反推业务逻辑。人工输入需显式导入、校验、审计，不默读 Excel 修改核心假设。

跨设备一台发布端写回，其余查看；本地 D 盘路径不能成为另一台电脑理解结论的必需条件。先发布候选、检查 Hash/人工区保护/公式缓存、再原子更新原表；占用或冲突时保留候选等待，不覆盖。

## 9. Long-term Milestones

所有数目是验证设计，不是推荐配额；任何阶段都不强求真实 BUY/ADD/EXIT 当天出现。可以用真实历史 PIT 验证未在当前出现的状态，但不得把历史/合成状态标为今日生产信号。

### M1. Fixed-Sample Research Workbench

**Goal**：把 C3 平台变成可阅读、可复算的真实固定样本研究工作台：20 家分层入组、其中至少 6 家深研，原 Excel 展示共同输出。这是第一个且唯一推荐启动的长期 Goal。

**Why it exists**：消除输入/研究/显示断层，用真实不同经济结构暴露缺口，不再只完成 adapter。

**Prerequisites**：复核本轮 HEAD/CI；保留三公司冻结反例；先完成 manifest input 与时点/版本安全门，再新增样本。

**Domain changes**：最小完整 InputDescriptor/事实假设绑定；校正第 1.4 节风险；BusinessQuality/CapitalAllocation 的证据化最小评估合同，复用现有估值和 Distribution，不建完整行业评分平台。

**Application changes**：descriptor -> RunSpec -> Runner -> Repository -> read model -> Excel；manifest 在运行前逐公司校验并隔离坏 descriptor、未知 Profile、身份冲突；不从 symbol 猜模型。统一 evidence/facts 导入和人工研究模板，有 provenance 的半自动输入可用，不假称深研全自动。

**Persistence changes**：复用 C3 artifact；新增/版本化最小不可变输入包（Facts/Assumptions/源与版本关系）和报告投影；证明冷启动只凭包+代码版本可重放，不依赖散落的 rolling latest。仅 isolated/test PostgreSQL，CI 无生产 DSN。

**Data requirements**：预登记 20 家及选择理由，按 3 -> 6 -> 12 -> 20 推进；覆盖现有三画像、同画像第二家公司、不支持模型/资料缺失/经济风险反例。至少 6 家真实深研，不要求20家全部深研；每家入组都有真实身份、来源、口径、适用性及缺口。真实公司不能用 fixture 替代。

**Tests**：合同/算术、错误日期与未来数据、登记假设与计算一致、rule/model/parser 变化重算、坏输入隔离、无 symbol 特化、原三公司回归、真实数据与 fixture 分层、DB round-trip/replay、Excel 投影和保护测试。

**Point-in-Time requirements**：每个深研案例至少一个封存研究时点；当前有效交易会话单列；至少两家公司做两个可证明信息可用边界的时点 replay，其中含更正/迟到或新披露。当前抓取的历史报表不能自动证明当时可用。

**Acceptance criteria**：20 家有入组/缺口账；6 家有完整可读研究档案；其中至少3家、覆盖至少2种现有适用模型，形成有真实事实和登记假设支持的有界三情景、敏感性/置信度及反向估值（无有界解可有理由）；至少2家完成有依据的股息可持续性评估，可为 LOW，不要求结论优秀。三情景只有占位/未核口径不计入。至少3家完成对应当前有效报价及事件扫描的 PriceBridge 正向验证；模型失败案例另保留。不用低置信度自动制造价格吸引结论。

**Forbidden scope**：全市场正式漏斗、买卖状态/仓位、Web、金融行业新模型、ShareholderYield 完整引擎、50家自动扩容、生产迁移/调度/部署。不得删冻结证据、调旧参数凑通过或增加公司专用流水线。

**Exit criteria**：共同结果已显示于原 Excel，源 Hash/人工区/WPS 检查有收据；至少一次隔离 PostgreSQL 冷启动重放；给出 coverage/gaps 与技术债报告。研究有合理拒绝是成果，但“20家全是占位/缺失”不毕业。M1 只保留 `conditional_research_only` 和显式缺口；正式 G3 研究批准归 M3、公告材料性与事件决策归 M5，不把这两类后续人工复核当作 M1 完成阻断。外部不可用可完成工程并登记未完成的真实验收，不虚报 M1 DONE。达到标准后停止，交用户复核 M2。

### M2. Multi-Channel Opportunity Discovery

**Goal**：从全市场低成本发现候选并解释 Why Now，达到 L2。

**Why it exists**：研究工具要能找公司，而不只研究手工挑选的熟悉公司。

**Prerequisites**：M1 产品验收；固定样本缺口分类稳定。先复用官方 Universe/旧行情组件的合格部分；按原样本约束扩至20-50家验证通道反例，不以增加数量替代质量。

**Domain changes**：UniverseSnapshot、ChannelScreenResult、Candidate/FunnelTransition；先 Quality+Dividend，再 Value+Cyclical，同一里程碑按门推进；Asset/Growth/Special 留接口不实施。

**Application changes**：规则注册、数据适用性校验、批量 cheap screen、候选去重与路由、研究队列预算；新通道 shadow 对比旧 PE/PB baseline 后显式切换，保留历史入口标签，不悄悄改义。

**Persistence changes**：版本化 Universe、输入快照、通道/规则版本、入出理由、覆盖统计及任务收据；索引按实际查询需求，小批次写入，避免重存大原件。

**Data requirements**：官方可核对身份与当日交易状态；多期质量/现金/分红/债务/资本投入与周期指标；行情授权、频率及缺失清单。财务不支持不能被当作低分淘汰或零值。

**Tests**：各通道正反例、股息陷阱、周期高点低PE、不支持行业、缺失/冲突、重复证券、上市退市/停牌、分页漏采、数据分母勾稽、冷启动与资源预算、规则版本变化。

**Point-in-Time requirements**：历史 Universe 含当时上市和后退市者；无历史成分/可用时间则不能声称无幸存者偏差；更正前后版本与当时政策分别 replay。

**Acceptance criteria**：真实固定样本交叉验证四通道后，完成全市场当期 run-once；每个身份都有覆盖状态，每个候选有原因/证据/通道，缺失与模型不支持显式可见；从新发现而非事后挑选的候选中形成至少3份受支持画像的可读深研或实质否决报告。队列0合法，不强迫产生高关注。

**Forbidden scope**：全市场逐股DCF、买卖数量、收益优化、一次开发所有行业模型或Web。

**Exit criteria**：覆盖与候选转移可复算，真实日期下的四通道抽样误放/漏筛复核完成；重放与数据缺口不被测试通过掩盖。持续每日服务在 M5/M6 验收，run-once 不冒充运营上线。

### M3. Explainable Decisions and Thesis Continuity

**Goal**：建立 Research-to-Decision 的理由卡、入场论点、人工日记及买卖一致性，达到有边界的 L3。

**Why it exists**：解决“为什么买、为什么拿、哪里错了”，不是把 Attractive 改名 BUY。

**Prerequisites**：M1研究合同和M2候选来源通过；注册决策政策/反例；最小 PortfolioPreconditions 与 Entry 确认输入明确，未提供则 WAIT。

**Domain changes**：InvestmentDecisionReview、DecisionEvidenceBundle、Buy/Hold/Add/Reduce/Exit Card、EntryThesisSnapshot、InvestmentConsistencyReview、DecisionJournalEntry；完整状态优先级及拒绝规则。

**Application changes**：研究 -> 前置检查 -> 理由卡 -> 用户确认/拒绝 -> Entry/Journal；后续复核必须引用同一原始论点；无需买入才能继续研究。

**Persistence changes**：不可变决策/Entry/Journal 和更正链接、规则版本、Bundle 完整依赖；实际与模拟命名空间隔离；私有数据不得入公开 fixture。

**Data requirements**：M1/M2真实研究、价格和事件证据，明确的人工持有基线/模拟事件；没有原买入原因不捏造。

**Tests**：缺一项 BUY/ADD 前置即拒绝；跌价不自动加/卖、涨价不自动卖、breaker否决、理由与字段矛盾、重复确认幂等、事后重建标识、原始论点未被覆盖。

**Point-in-Time requirements**：重放当时的 Facts/规则/Portfolio/Entry；Current 不覆盖 Original；现实没有某类状态时用可证历史案例验证并标 historical。

**Acceptance criteria**：真实不同公司产生完整理由卡和版本链；至少一条从人工模拟 Entry 到新证据、Consistency 和减/退出复核的完整真实历史链；所有状态有反例测试，风险与估值减仓原因分开。至少3份卡片经用户阅读复核能复述理由和反证；用户验收未提供时不得自评通过。

**Forbidden scope**：自动创建成交、券商订单、数值仓位优化、自动把回测胜率当置信度。没有容量输入时不得发个人化正向复核。

**Exit criteria**：可追溯“哪条原始理由变化”，工程/研究/人类可理解性分别通过；真实 BUY 数量可为零，不能降低政策求信号。

### M4. Portfolio and Sustainable Income Guidance

**Goal**：结合真实人工确认组合与 IPS，给保守仓位/集中度/股息现金流复核，达到 L4。

**Why it exists**：单股便宜不代表适合当前组合，现金收入目标不能只依赖当期收益率。

**Prerequisites**：M3完整理由和Entry链；用户提供/确认账户范围、现金、持仓和IPS；缺用户输入只继续非个人化工程，不替用户编造约束。

**Domain changes**：PortfolioSnapshot、InvestorPolicyStatement、PortfolioRiskAssessment、PositionGuidance、DividendIncomeProjection；阶段升级/降级政策和容量合同。

**Application changes**：显式私有导入/对账、多个候选共同预算、情景压力、股息事件与数量口径校验、Review/Journal 联动；人工可拒绝建议。

**Persistence changes**：私有账户/持仓/现金/IPS版本，append-only变更；加密备份和权限分离；系统意见与实际人工交易分开存储。

**Data requirements**：真实持仓及现金对账、行业/共同风险映射、可交易性/流动性、历史与宣告/正常化分红；成本和公司行为调整、税费情景。真实资金无须为验收而交易。

**Tests**：总权重/现金守恒、重复预算、集中度上限、缺价格的风险区间、低置信度限制、零持仓、复权/分红/拆股、特别股息不年化、模拟与实盘隔离、隐私泄漏。

**Point-in-Time requirements**：组合、成本、政策和股息权益日均绑定当时快照；禁止把当前持仓用于过去的加减仓理由。

**Acceptance criteria**：至少一份真实人工确认组合完成对账和风险/现金流报告；另用分散/集中/全现金反例测试。Starter/Normal/Max与停止加仓/减仓均有明确条件；当前/Forward/Normalized收入和不确定性分别显示，不同股票争用现金时不越预算。

**Forbidden scope**：杠杆、衍生品策略、最优收益调参、自动调仓、自动读券商口令/下单，或代替用户设风险偏好。

**Exit criteria**：用户能解释组合风险和股息脆弱来源，数值建议有可复算约束；未经人工确认的组合不能贴真实准入标签。

### M5. Event-Driven Monitoring and Review Loop

**Goal**：让系统持续发现有意义变化，静默正常状态，达到 L5 的运营候选状态。

**Why it exists**：研究必须在新证据到来时失效/更新，不能形成一次性报告后遗忘。

**Prerequisites**：M1-M4版本和依赖合同；源健康/资源预算、通知目标及调度权限预先确定；生产动作仍单独确认。

**Domain changes**：ChangeEvent、MaterialityPolicy、DependencyInvalidation、Alert/ReviewDue；复用现有ModelValidity/Batch，补规则变化与事件扫描截止日失效。

**Application changes**：增量采集 -> 去重/更正 -> 重大性 -> 有界重算 -> Entry/Portfolio复核 -> outbox；财报季/周/月 Review Loop；只重算受影响对象。

**Persistence changes**：事件账、旧新版本关系、扫描水位、任务锁/checkpoint、outbox投递及确认；崩溃重启可补发且不重复建议。

**Data requirements**：真实财报/公告/资本动作/分红/价格和组合变化；公告日期级不确定性保守处理；源中断要形成健康事件。

**Tests**：重复/乱序/晚到/更正、失败恢复、静默日、Critical breaker、超时/限流/通知失败、价变不改内在价值、模型STALE不自动清空历史。

**Point-in-Time requirements**：保存 detected/effective/available 三时间、当时依赖和规则；事件历史replay不得提前通知。

**Acceptance criteria**：真实事件触发受影响报告与理由变化；当前静默与健康失联可区分；每日输出含新进/退出关注、各Review、Thesis/Dividend警报和系统异常，全部0合法。关键事件真实历史replay与在线观察分开验收。

**Forbidden scope**：每天全量深研、LLM无预算读全市场原件、新闻热度改估值、重复worker、未经授权通知/改生产任务。

**Exit criteria**：run-once与恢复/投递证据通过后，经授权接既有调度做 shadow；自然时间观察交M6，不循环等待未来事件把工程卡死。

### M6. Initial Real-Use Acceptance

**Goal**：完成“初步可以真实辅助个人价值投资”的有限生产准入，而非策略盈利认证。

**Why it exists**：真实可用还需要稳定数据、可恢复运营、用户理解及错误处理，测试不能替代。

**Prerequisites**：M1-M5产品验收；单独确认生产migration、账户数据/发布/通知/调度范围；保护PTA的资源基线与回退方案。

**Domain changes**：不新增投资策略；只补验收发现的适用性、拒绝或解释缺口。

**Application changes**：完成批准的staging->shadow->limited-use切换、数据源失效降级、健康检查、应急停发布/停新增复核能力；保留研究和证据读取。

**Persistence changes**：生产角色最小权限、事务一致性、完整输入/结果/事件/私有Journal、数据迁移parity；独立加密备份和恢复到新库，不恢复覆盖生产。

**Data requirements**：真实全市场日期快照、实际个人组合（可全现金）、真实事件与已核研究；模型未覆盖行业明确拒绝，正式使用行情需授权与质量复核。

**Tests**：离线合同+真实数据复算+PIT+隔离DB+Excel+恢复/资源/异常演练+人工任务测试，全部绑定同一候选版本。旧历史实验不得成为当前准入隐式依赖。

**Point-in-Time requirements**：历史信息集/当前信息集/模拟/真实账户清晰隔离；按当时可知数据重建至少一条入场至变化复核的决策链。

**Acceptance criteria**：满足第12节全部条件。建议预登记不少于20个连续交易会话的shadow观察，含至少一次真实财务或资本分配事件；若自然时间未覆盖，保留为未完成线上验收，历史replay只补工程验证，不能代替真实运行。20个会话是候选运营最低观察门，不是工期或收益统计证明，可在观察前基于风险加严，不可事后放宽求通过。

**Forbidden scope**：自动交易、以盈利/出现BUY作为毕业条件、删不利样本、无授权部署、挤占PTA资源、用备份文件存在代替恢复成功。

**Exit criteria**：独立审查工程/研究/当前数据/决策解释/组合/运营/用户验收，通过后仅标 `INITIAL_ASSISTED_USE`，列明支持画像、未覆盖范围、风险和复审日期。任何 P0身份/未来数据/错误放行缺陷未解决不得准入。

## 10. Milestone Dependencies

```text
CURRENT: C3工程平台 / L1早期，非投资决策就绪
  -> M1: 20家固定样本 + 6家深研 + 股息/估值/Excel真实工作台
  -> M2: 全市场身份对账 + 四通道候选发现
  -> M3: 决策理由卡 + Entry Thesis + Journal + 买卖一致性
  -> M4: Portfolio-aware容量/仓位 + 可持续股息收入
  -> M5: 事件驱动重算 + 每日重要变化与静默
  -> M6: 经授权shadow、恢复与用户验收
  -> INITIAL REAL INVESTMENT USE (human-reviewed, no_order)
```

M3的BUY/ADD依赖PortfolioPreconditions，但M3只接显式人工确认/模拟容量；M4才计算完整真实容量，避免循环依赖或提前发个人化信号。Entry/Journal与Consistency放同一Milestone，不能先做卖出再补原买入逻辑。M1起保存可失效依赖，M5才建完整事件运营。安全与PIT贯穿，不能等M6才补。

| 阶段 | 工作规模 | 主要风险 | 验收强度 |
| --- | --- | --- | --- |
| M1 | 大；工程与研究并重 | 披露口径、假设可信度、旧新展示迁移 | 真实20家账+6深研+跨模型+DB/Excel |
| M2 | 大；覆盖/通道/源质量 | 不支持行业、幸存者偏差、数据授权/限流 | 固定反例+全市场分母+真实候选审阅 |
| M3 | 大；领域政策与可解释性 | 研究状态被误读为交易、原论点缺失 | 状态反例+真实历史链+人工复述 |
| M4 | 中大；私人数据与约束 | 错误容量、集中风险、股息陷阱 | 真实对账+压力场景+隐私验收 |
| M5 | 大；持续运营 | 漏事件、误静默、通知噪音/OOM | 事件replay+故障恢复+在线证据 |
| M6 | 高验证强度，规模取决于发现问题 | 数据/运行/人类使用的联合风险 | 独立综合验收+真实观察+恢复 |

不承诺天数。每个Goal可跨多次运行续接已验收工作包，但只能有一个当前Milestone。外部数据、人工输入、授权和自然时间分开列状态，不能以一项等待阻塞所有独立工程，也不能越权自动启动下一阶段。

## 11. Acceptance Criteria

每个阶段收据至少记录：HEAD与dirty diff、运行命令/环境、样本manifest/源Hash、数据截止时间、规则/模型/解析器版本、事实假设/结果版本、测试分类/跳过原因、人工核验、未完成项目、覆盖分母、输入输出路径和Hash。

测试分类：Contract（身份/日期/不变量）、Unit（公式/边界）、Snapshot/Replay（封存语义与时点）、Excel（映射/不覆盖/公式缓存）、Integration（真实隔离DB/恢复/发布）、Production Validation（实时源/运行/人工）。六类不能互相代替。

全阶段共通门：
1. 正常/缺失/冲突/过期/不支持/更正/空结果均有明确输出；未知不静默转READY。
2. 财务数值可复算到原件，假设可找到依据与反证；Hash只证明字节一致，不证明经济解释正确。
3. 每家公司有独立状态；无价保留估值，无模型保留研究，无个人组合保留非个人化研究。
4. 准入/参数在观察前登记；没有收益后验挑选、没有为了3份估值降低标准。未达到数量与质量双门只报PARTIAL。
5. 每次内部工作包完成都交付可读增量，不等最后才让用户看到；不以此把中间包自称Milestone毕业。

状态分别记录 Engineering / Research / Valuation / Dividend / Current Data / Price Assessment / Decision / Portfolio / Operations。阶段用 NOT_STARTED、IN_PROGRESS、PARTIAL、PENDING_EXTERNAL_DATA、PENDING_HUMAN_REVIEW、PASSED_FOR_FREEZE；禁止单一READY掩盖其他维度。

## 12. Production Readiness Criteria

| 必须证明的真实用户能力 | 证据与归属 |
| --- | --- |
| 1. 从市场发现研究对象 | 当日官方Universe/通道结果及覆盖缺口，M2 |
| 2. 解释候选进入原因 | Channel/Why Now/规则版本，M2 |
| 3. 完整ResearchCase | 生意、财务、资本配置、Thesis/反证/breaker，M1 |
| 4. 模型适用 | Profile/Router与事实合同，M1；不支持明确拒绝 |
| 5. 情景与置信度 | 三情景、敏感性、假设、反向预期，M1 |
| 6. 股息研究 | current vs normalized、现金覆盖/压力/限制，M1/M4 |
| 7. 当前价格连接 | 最新有效交易会话+ModelValidity+PriceBridge，M1/M5 |
| 8. 决策复核状态 | 前置条件与否决原因，不是订单，M3 |
| 9. 买入/加仓理由 | Logic Card、Entry一致性、容量，M3/M4 |
| 10. 持有理由 | 正向Thesis复核，不因缺数据默认HOLD，M3 |
| 11. 减仓/退出理由 | 估值/基本面/组合原因分开，M3/M4 |
| 12. 原始逻辑可回溯 | Entry -> Consistency -> Journal，M3 |
| 13. 组合约束有效 | 私有真实快照/IPS、现金与风险预算，M4 |
| 14. 每日重要变化 | M5+M6真实运行收据、静默/异常/事件投递 |
| 15. 用户理解 | 用户能复述为什么买/拿/卖及何种事实会证伪，M3/M6 |

还须有：无未关闭P0错误放行、独立原件抽样复算、真实数据过期降级、私密信息隔离、恢复到新库的行数/Hash/证据/配置/Excel校验、实际RPO/RTO、源与目标身份保护、PTA资源基线未受损、一台发布端/可回退、运维故障处置手册。现有RPO<=24h/RTO<=4h是待测目标，不是已通过结果。

支持范围须写清楚：全市场身份/筛查覆盖不等于全行业估值支持；初版允许银行/保险/NAV UNSUPPORTED，但不得漏报覆盖。所有当前正向复核仍需用户判断，无任何收益保证。股市没有出现合格机会也能通过系统流程验收；不能为验收真实下单。

## 13. Major Risks

1. **研究内容空心化**：接口齐全但无可信估值/股息。M1数量与质量双门、读得懂的反证和原件抽样，不以全GAP毕业。
2. **PIT与版本假完整**：有日期/Hash但链不一致。M1先修已复现缺口，所有后续Bundle和增量重算继承。
3. **经济画像泛化错误**：三画像不是全行业；业务相似也可能有金融子公司、少数股东、监管/资源约束。适用性显式审阅，禁止默认模型。
4. **旧新入口混义**：旧screen、模拟账户/策略和Excel仍在。迁移有标签、回归和消费者清单，不无差别删除，也不让历史规则进入新决策。
5. **持续采集无产品增量**：证据stop rule、每批可读交付、假设/材料性边界复核；不会影响结论的新原件不无限收集。
6. **股息与价值双算/高息陷阱**：权益现金、分配状态、普通/特别、正常化、再投资和债务分开。
7. **规模/运营拖垮共享服务器**：分层计算、限并发/内存/重试、源预算；生产前核实PTA余量，不增加无必要常驻服务，不假设需要本机Docker Desktop。
8. **生产资产与公开仓库风险**：源码/schema/脱敏fixture可公开；持仓、密钥、生产dump、未经许可原件不公开。以私有证据存储及加密备份保障恢复。
9. **代理/接口/授权不稳定**：来源可替换但口径需再核验；不得通过不合规访问补数据；错误源不能被第二个同源镜像洗白。
10. **计划过大又无限延伸**：六个大Milestone分别启动/停止；M1止于20家与研究展示，不自动吞并M2-M6。

## 14. Explicit Non-goals

- 自动炒股、订单执行、券商接入、收益承诺、保证股息或强制满仓。
- 本轮编码、改Excel、连生产DB、改调度/服务器/做生产迁移；本轮仅审查和文档。
- M1开发全市场、Web、所有行业估值或个人仓位；也不为消除所有技术债大重构。
- 将短期市场走势预测、技术指标拟合或最高回测收益变成价值投资主线。
- 每天荐股、以评分排名替代解释、用LLM作为唯一财务数字计算来源。
- 用真实资金交易来证明产品能力；模拟盈利或fixture全绿替代生产验收。
- 重新建设已冻结Stage A/C0-C3，或把新的有限研究允许解释成随意修改冻结历史。

## 15. Recommended First Long Goal

**唯一选择：M1-FIXED-SAMPLE-RESEARCH-WORKBENCH。**

首要工程问题是可信输入到可读研究的完整链路，不是再孤立完成一个adapter。按内部工作包顺序：基线/预登记 -> 输入及PIT/依赖完整性 -> 原三公司回归 -> 6家公司深研和新read model候选展示 -> 12/20家分层验证 -> 原Excel安全发布 -> 隔离DB冷启动replay -> 产品/方法/技术债审查。

首批用户可见成果是6家公司的研究工作台：能看到生意、回报来源、三情景或具体拒绝原因、股息可持续性、当前价格位置、最强反证和下一事件；它仍不发布BUY/ADD/仓位。

完成定义与停止条件以第9节M1及 [current-stage-goal.md](docs/current-stage-goal.md) 为准。允许失败/缺失案例，不允许占位结果充数；无法通过真实验收就保留PARTIAL与可执行缺口，不假称初步实盘就绪。推荐启动文本见 [value-investment-goal-prompt.md](docs/value-investment-goal-prompt.md)。
