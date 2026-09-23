# LONG-TERM VALUE INVESTMENT SYSTEM ROADMAP

版本：2026-09-23 / roadmap-v3。按用户最新要求，下一总Goal贯穿M2-M7；M1与Post-M1 Stabilization已完成，M2为PARTIAL，M3-M7尚未产品验收。审查代码基线：`f4bb55cd686838b874b6a8b0c601492c8bd7aab5`。路线与当前执行范围已经冻结，实际实现由 [current-stage-goal.md](docs/current-stage-goal.md) 控制。

本文件仍是唯一跨阶段路线，不新建平行Roadmap。用户已将下一总Goal扩展为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`：从M2逐阶段推进至M7，不必每过一关重新建立Goal。M1保持冻结；当前聚焦M2，执行范围和交接门见 [current-stage-goal.md](docs/current-stage-goal.md)，事实见 [execution-status.md](docs/execution-status.md)。内部阶段完成后必须审查、记录证据再继续，不能因总目标扩大跳过验收；生产操作、私人资料和人工研究批准仍有独立授权边界。

## 1. Current Reality Audit

### 1.1 已提交基线与本轮边界

| 项目 | 实际证据 |
| --- | --- |
| Git | main；HEAD `f4bb55cd686838b874b6a8b0c601492c8bd7aab5`；开始审查时工作树干净，跟踪 origin/main；本轮文档改动另属未提交工作状态 |
| 最新提交 | 2026-09-23 21:55:48 +08:00，Release M2 candidate workbook snapshot and changelog |
| 继承提交 | `60c9de0` 人工复核回执；`f26f726` Post-M1 稳定化；`6658b14` M2 首次运行；不回到旧 60c9de0 起点 |
| CI | [35870537557](https://github.com/MingMingLiu0112/value-investment/actions/runs/35870537557)，本 HEAD 的 push；offline-core 与 postgres-integration 均 success；workflow 为 `.github/workflows/core-research-gates.yml` |
| 本地测试 | 本轮全量 2118 passed / 6 skipped / 18 warnings，290.45s；跳过为4项无隔离PG DSN、1项无PG二进制、1项已有冻结输出。CI仅指定核心清单，不代表投资方法有效 |
| M2 封存 | `runtime/m2-live-20260923/manifest.json` 的8个文件 Hash 本轮全部复核一致；只证明保存字节完整，不证明时点和经济判断正确 |
| 原 Excel | 12,210,200 bytes；SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`；历史发布记录为42页；本轮不编辑、不宣称重新通过 WPS 视觉/公式验收 |
| M2 展示 | 独立 `A股价值投资_M2机会发现_20260923.xlsx`；不是原工作台已完成统一接入的证明 |
| 未操作 | 生产数据库、SSH、PTA、计划任务、行情采集、工作簿和研究批准；本轮仅测试、内存反例、只读核对与文档修订 |

### 1.2 已完成与不能声称完成的部分

- Stage A、P0/P0.5、三公司工程、C0-C3 保持冻结；不重复建设。
- M1 的20家分层样本、6份研究档案、三公司 Application/原Excel、输入包/PIT及隔离 PostgreSQL replay 已有验收收据。M1 DONE 指机器可验证研究工作台，全部投资结论仍受 conditional_research_only 限制；不是估值/股息全部获批。
- Post-M1 已落地 HumanResearchApprovalReceipt、EventMaterialityDecision/Review、BridgeContributionAssessment、InterimReportPolicy、PreDecisionEligibility，并接入 Application/G3/ModelValidity/PriceAttractiveness/CurrentResearchStatus。现有 PreDecisionEligibility 是研究准入前置合同，不是完整投资决策/Portfolio 门；可选的价格评估输入也不能让未来 BUY 路径绕过必需检查。
- 稳定化 `f26f726` 已修旧茅台断言、标识 one-off generator、隔离 stress haircut 和 legacy。下一 Goal 的 W0 只重核/维护回归，不再次开发这些已完成项目。
- M2 真运行收据：官方 Universe/行情匹配均5568，财务证据覆盖873个证券、股息覆盖3622、金融不支持121；Quality=0、Dividend=50、Value=50、Cyclical=50，去重113。Legacy=747，只作shadow。Quality=0不等于全市场没有好公司，也可能说明数据不足。
- M2已形成 run-once 和独立展示，但不是可依赖的 L2 毕业；完整决策、个人仓位、每日可靠运营仍未完成。

### 1.3 人工复核后的正确拒绝状态

来源：`runtime/m1-post-review-20260923T114228Z/`，对应用户研究输入与版本化回执；不是本轮重新批准。

| 公司 | Human G3 | ModelValidity | DecisionEligibility |
| --- | --- | --- | --- |
| 000651 格力 | REJECTED_NEEDS_REWORK | STALE | NOT_ELIGIBLE |
| 600741 华域 | REJECTED_NEEDS_REWORK，HIGH priority | VALID | NOT_ELIGIBLE |
| 600887 伊利 | APPROVED_CONDITIONAL_LOW_CONFIDENCE | STALE | NOT_ELIGIBLE |

旧茅台/美的/神华冻结反例继续保留，不被这三家公司替换。格力/华域桥接 stress 不代表新获批估值；伊利条件批准不等于条件已经解除。未来重估必须 Facts + 版本化 Assumptions + Bridge -> Model -> 新 ValuationResult -> 新 HumanApproval，不能倒推 operating value 后 haircut 冒充正式估值。

### 1.4 M2 代码审查与反例：并非只差三份报告

本轮未顺手修复业务代码；以下纳入同一 M2 Goal，不重开 M1：

| 发现 | 代码定位与复现 | 影响 / 必须验收 |
| --- | --- | --- |
| 时点门不足 | `m2_discovery_engine.py::build_discovery_receipt/build_channel_results` 未按 cutoff 排除未来分红；合成 fixture 把宣告日改为2026-10-01，9月23日仍入选 | 加 available_at、报价会话、方案状态和缺失时点处理；这不是已有当日数据确定错误的断言 |
| 旧缓存可被标为当前 | `run_m2_opportunity_discovery.py::run_once` 在 reuse-inputs 分支用 now 作多个 fetched_at，统一 quote_date 来自运行日期 | 原始采集/会话时间不可刷新；replay 与 current-run 分开；不能用同日签名重建证明 PIT |
| 官方分母未约束候选 | 行情合并使用来源证券并集；合成反例从 official 删除600004后仍入选，data_health=COMPLETE但含 extra-symbol blocker | 官方身份集合与交易状态实际约束准入，逐证券/逐通道覆盖账，不只总数 |
| 候选去重丢理由 | `m2_opportunity_discovery.py::DiscoveryRunReceipt.candidate_pool` 字典覆盖；合成600001入两个通道，返回只剩value理由 | 合并所有通道/证据/缺口；稳定优先级、转移和队列预算，不能最后一个通道获胜 |
| 完整性语义过强 | Dividend/Value/Cyclical 常以无价格冲突标 COMPLETE；Value 的 FCF/EV 指标、Cyclical正常化盈利仍为 None；Dividend tier A主要看高收益率 | 区分线索、已核候选、研究质量与报价健康；不把高息/低倍数排序当可持续性筛查 |
| 画像与覆盖不足 | `_profile_status` 以非金融且有行业判 SUPPORTED；每通道截前50；主要有聚合缺口统计 | screening适用不等于估值Registry支持；保留预算截断前分母与待研究对象；不支持不默转模型 |
| replay证明范围有限 | 改 evidence Hash/未来 fetched_at 后candidate_signature不变且入口接受；原测试仅6个 | 内容签名可以独立存在，但完整验收必须验证原件Hash、输入/规则/时点/覆盖和输出依赖，不只候选名单相同 |
| 用户路径尚分散 | M2是独立工作簿，原表已有阶段前台及M1页 | 下一Goal从原工作台给出统一市场->候选->Why Now->研究入口；保留手工与冻结页，不用继续堆表冒充产品 |

合成反例用于证明入口缺少拒绝检查，不能被写成真实股票或真实违规数据。金融 Quality 绕过的猜想本轮反例未复现，不列为已确认缺陷。现有 manifest 八项 Hash 一致是有效成果，应继承而非废弃。

### 1.5 真实成熟度

| 层级 | 当前结论 | 尚缺什么 |
| --- | --- | --- |
| L0 Engineering Foundation | HEALTHY，有边界 | CI不覆盖所有经济语义；新M2时点/范围问题仍须修 |
| L1 Research Workbench | BASICALLY READY / M1 DONE | 条件研究不等于Human G3通过，正常化分红和估值质量仍逐公司审查 |
| L2 Opportunity Discovery | PARTIAL / NOT USER READY | 第1.4节、安全的四通道真实验证、3份主动发现报告及统一前台 |
| L3 Explainable Decision Support | NOT READY | 完整决策、理由卡、Entry/Journal/Consistency与用户理解验收 |
| L4 Portfolio Decision Support | NOT READY | 用户确认IPS/持仓、组合容量与可持续收入 |
| L5 Continuous Monitoring | NOT READY | 事件运营、水位、异常恢复、通知与真实观察 |
| Initial Assisted Use | NOT READY | M6综合准入 |

方向仍正确：Research/Valuation/Evidence/Funnel，不是自动交易。真正偏差是用行情完备或名单重建成功代替研究/时点完备；应修相关通用路径。runtime JSON、有限 production adapter 和较大 publisher 是合理技术债，当前不要求生产迁移或全仓重构。

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
3. BUY/ADD 同时需要：Gates、绑定当前依赖且有效的 Human G3、覆盖目标日的 Event Review、商业/财务质量、Thesis、适用且可用的估值、最低置信度政策、ModelValidity、PriceBridge、可评估的 PriceAttractiveness、反证复核、重大性、适用时的股息可持续性、Portfolio Capacity。现有 PreDecisionEligibility 不是完整决策批准，缺任一必需输入不能放行。
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

`InvestorPolicyStatement` 由用户确认目标、收入需要、可投资资产范围、期限、应急现金/负债、风险承受及税费口径，明确最低现金、单股/行业/周期资产上限、流动性需求及是否允许集中投资。未知不猜测；研究工作可继续，但暂停个人化容量/仓位结论。

`PortfolioSnapshot` 保存 as_of、实际/模拟、账户范围、资产/现金/持仓数量、成本与市值口径、行业/共同风险、快照和人工核对记录。数据经明确导入或用户确认，不连接自动下单；私有账户数据不得进公开 GitHub。

`PortfolioRiskAssessment` 覆盖单股、行业、周期、同因子/商品/客户暴露、高股息、高估值、低置信度、流动性、现金、Thesis Risk。下行损失和永久资本损害优先，波动率/VaR 只能补充，估计相关性不被当成稳定真值。

`PositionGuidance` 输出允许/不允许升级、阶段、条件范围与剩余容量，而非单股各算20%。推荐增量受单股、行业、共同风险、流动性、现金和总组合约束的最紧上限限制；多个候选共用预算，不能重复分配同一现金。具体上限须由 IPS/政策审查登记，本路线不捏造通用百分比。

初版层级为 ZERO / WATCH_ONLY / STARTER / NORMAL / ADD_ALLOWED / MAX_CAPACITY / STOP_ADDING / REDUCE_REVIEW / EXIT_REVIEW，不输出未经规则验证的伪精确百分比。Starter -> Normal -> Add -> Max 每次升级需新证据/置信度/价格改善和容量；LOW Confidence 即使看似便宜也不发大仓位建议，未知可为零。正常持有 -> 停止加仓 -> Reduce -> Major Reduce -> Exit 保留降级原因。允许完全不持仓，不为资金利用率强制满仓。

`DividendIncomeProjection` 区分已到账、已宣告未到账、Forward、Normalized sustainable income；按实际持股/权益登记/币种/税费情景计算，不能把承诺当现金。显示 Annual/Forward/Normalized Income、Yield on Cost（仅成本体验）、Dividend Concentration、Sustainability Distribution。回购不是个人到账股息，特别股息不机械年化。目标收入不足不能通过增加周期高息暴露掩盖风险。

## 7. Target Event Architecture

每天更新行情、公告/财报、分红、回购、资本结构及重大经营信息，不每天重做所有深度研究。使用变化依赖：Data -> Change Detector -> Materiality -> Affected Dependencies -> Invalidate/Recalculate -> Review -> Notify。

`ChangeEvent`：event_id、security_id/symbol、event_type、detected_at、effective_at、available_at、previous_state、current_state、severity、reason、evidence_refs、confidence、requires_human_review、supersedes/correction 引用。严格区分事件生效、披露和系统知晓时间。

事件类型至少为 NEW_FINANCIAL_REPORT、MATERIAL_ANNOUNCEMENT、DIVIDEND_CHANGE、BUYBACK、CAPITAL_ALLOCATION_CHANGE、VALUATION_ZONE_CHANGED、PRICE_ATTRACTIVENESS_CHANGED、THESIS_WEAKENED、THESIS_BREAKER_TRIGGERED、MODEL_STALE、POSITION_RISK_CHANGED。

价格变动只重算桥接/价格位置，不能直接改内在价值。财报或资本动作按依赖重算 Facts/Valuation/Distribution；Thesis 变化回看 Entry。MarketContext 只影响研究优先级、风险解释和执行谨慎程度，不改 Bear/Base/Bull。

通知必须幂等、合并、可确认、可重试；无重要变化静默，正常日 0 合法。关键源失联或扫描中断作为系统健康告警，不伪装为“没有重大事件”。晚到、更正、重复、乱序事件与重启需要 replay。Critical breaker 不被普通通知去重吞掉。

每周关注池复核，每月组合/股息复核，财报季完整 Thesis 复核，重大事件即时复核。建立 outbox/投递状态和审计，先有可验证 run-once，再独立授权调度。该路线图本身不创建自动任务。

## 8. Board / Dashboard Architecture

继续使用唯一原 WPS Excel；M1 已有 Application read model 发布，M2独立候选需整合为原表统一入口，未来 Web 复用，不在表格重写 Domain。板卡是同一事实的投影，不是第二套状态机。

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

**当前状态：DONE / FROZEN。** 以下保存当时工作台范围与毕业合同；决策级 G3/事件复核不重新加入 M1 验收。其后人工复核合同与稳定化也已落地，拒绝状态见第1节。

**Goal**：把 C3 平台变成可阅读、可复算的真实固定样本研究工作台：20 家分层入组、其中至少 6 家深研，原 Excel 展示共同输出。这是已冻结的历史阶段，不再作为启动目标。

**Why it exists**：消除输入/研究/显示断层，用真实不同经济结构暴露缺口，不再只完成 adapter。

**Prerequisites**：复核本轮 HEAD/CI；保留三公司冻结反例；先完成 manifest input 与时点/版本安全门，再新增样本。

**Domain changes**：最小完整 InputDescriptor/事实假设绑定；校正 roadmap-v1 在旧 C3 基线发现的输入/时点/规则复用风险；BusinessQuality/CapitalAllocation 的证据化最小评估合同，复用现有估值和 Distribution，不建完整行业评分平台。

**Application changes**：descriptor -> RunSpec -> Runner -> Repository -> read model -> Excel；manifest 在运行前逐公司校验并隔离坏 descriptor、未知 Profile、身份冲突；不从 symbol 猜模型。统一 evidence/facts 导入和人工研究模板，有 provenance 的半自动输入可用，不假称深研全自动。

**Persistence changes**：复用 C3 artifact；新增/版本化最小不可变输入包（Facts/Assumptions/源与版本关系）和报告投影；证明冷启动只凭包+代码版本可重放，不依赖散落的 rolling latest。仅 isolated/test PostgreSQL，CI 无生产 DSN。

**Data requirements**：预登记 20 家及选择理由，按 3 -> 6 -> 12 -> 20 推进；覆盖现有三画像、同画像第二家公司、不支持模型/资料缺失/经济风险反例。至少 6 家真实深研，不要求20家全部深研；每家入组都有真实身份、来源、口径、适用性及缺口。真实公司不能用 fixture 替代。

**Tests**：合同/算术、错误日期与未来数据、登记假设与计算一致、rule/model/parser 变化重算、坏输入隔离、无 symbol 特化、原三公司回归、真实数据与 fixture 分层、DB round-trip/replay、Excel 投影和保护测试。

**Point-in-Time requirements**：每个深研案例至少一个封存研究时点；当前有效交易会话单列；至少两家公司做两个可证明信息可用边界的时点 replay，其中含更正/迟到或新披露。当前抓取的历史报表不能自动证明当时可用。

**Acceptance criteria**：20 家有入组/缺口账；6 家有完整可读研究档案；其中至少3家、覆盖至少2种现有适用模型，形成有真实事实和登记假设支持的有界三情景、敏感性/置信度及反向估值（无有界解可有理由）；至少2家完成有依据的股息可持续性评估，可为 LOW，不要求结论优秀。三情景只有占位/未核口径不计入。至少3家完成对应当前有效报价及事件扫描的 PriceBridge 正向验证；模型失败案例另保留。不用低置信度自动制造价格吸引结论。

**Forbidden scope**：全市场正式漏斗、买卖状态/仓位、Web、金融行业新模型、ShareholderYield 完整引擎、50家自动扩容、生产迁移/调度/部署。不得删冻结证据、调旧参数凑通过或增加公司专用流水线。

**Exit criteria**：共同结果已显示于原 Excel，源 Hash/人工区/WPS 检查有收据；至少一次隔离 PostgreSQL 冷启动重放；给出 coverage/gaps 与技术债报告。研究有合理拒绝是成果，但“20家全是占位/缺失”不毕业。M1 只保留 `conditional_research_only` 和显式缺口；正式 G3 研究批准归 M3、公告材料性与事件决策归 M5，不把这两类后续人工复核当作 M1 完成阻断。外部不可用可完成工程并登记未完成的真实验收，不虚报 M1 DONE。达到标准后停止，交用户复核 M2。

### M2. Multi-Channel Opportunity Discovery

**Goal**：继承已有5568证券run-once，完成可信的主动发现：全市场 -> 四通道 -> 可解释候选 -> 研究优先级 -> 深研队列 -> 原Excel重点关注。不是仅补三份报告，也不是重建M2。

**Why it exists**：回答“整个A股现在值得研究谁、为什么”，把粗筛线索与经过证据核验的研究候选分开。

**Prerequisites**：M1保持DONE；W0重核Post-M1稳定化/全量离线测试/CI/冻结Hash。既有one-off回执生成器只维护，不成为新的Milestone；已有修复不重做。

**Domain changes**：复用 UniverseSnapshot/ChannelScreenResult，补逐证券逐通道Coverage、版本化筛选Policy、Candidate多原因合并及Funnel转移；Profile分筛选适用与估值支持。可提前形成Decision-ready Candidate read model，仅表示未来输入可消费，绝不表示Decision eligible。

**Application changes**：有界采集/缓存 -> cutoff及适用性验证 -> 四通道 -> 线索补证 -> 候选合并/预算 -> 新发现报告 -> read model。current-run/replay入口分开，旧缓存不改成今日；单只失败不阻塞其他公司，整批不可信不能发布成当前完整市场。

**Persistence changes**：不可变原始输入/Universe/Policy/版本/known-at/Hash、逐证券状态、候选与转移、抽样名单及运行收据。沿用现有本地Artifact/JSON合同，完成冷重放与索引责任说明；不连接生产数据库、不为过关新增生产迁移。

**Data requirements**：官方当期身份/交易状态、真实有效行情会话、财务/分红/周期证据可用日。全市场只做cheap screen；候选层有界补多期事实，不要求5568家公司全部深研。通道门见下表，所有阈值说明经济理由、适用范围、敏感性、失败反例和版本，不优化历史收益。

| 通道 | 粗筛可以使用 | 晋级候选必须检查 / 缺失处理 |
| --- | --- | --- |
| Quality | 资本效率、持续盈利、现金转换、杠杆等低成本指标 | 多期可比性、债务口径、现金质量及行业适用；总分不能抵消硬缺口；低覆盖留DATA_GAP而非好公司不存在 |
| Dividend / Cash Return | 明确basis的DPS和收益率 | 分红历史/状态/普通与特别、派息与现金覆盖、CapEx/债务/周期风险；缺项保留线索，不标可持续或因高息升A；深层正常化可先为UNKNOWN |
| Value | PE/PB等可解释便宜度观察 | 盈利/资产/现金质量、负债或一次性收益风险、可能折价机制；相关倍数不是独立经济证据，不能把FCF缺失当完整价值筛查 |
| Cyclical | 行业/价格/当期倍数 | 多期利润/现金/商品或行业周期代理、正常化与当期差异及低谷债务承受；无可靠中周期证据只留线索/缺口，不编造正常化数值 |

**Tests**：正反例及空池；未来公告/未知available_at、旧缓存、休市/盘中/停牌、非官方证券、缺页/缺报、价格冲突、跨通道理由保留、截断预算、Profile未知/不支持、普通/特别分红、股息陷阱、周期峰值、Hash篡改/规则变更/重启。0 unexpected offline failures，现有测试不能替代新增语义反例。

**Point-in-Time requirements**：真实披露边界至少两个时点的加入/退出可解释重放；保存计算时刻和信息截止点。日期级已知信息采用保守上界。历史Universe未知就明确幸存者偏差限制，不声称完整历史全市场PIT。当前名单用后来事实补齐不能用于过去决策。

**Acceptance criteria**：以 current-stage-goal 的AC1-AC12为唯一可执行明细：逐证券覆盖可对账，四通道真实运行、线索与候选分开；至少一次当期全市场run和事先登记规则抽取的至少3家新发现实质研究/否决；对入选、漏筛、缺失、不支持及预算截断做分层抽检；原Excel统一入口显示Why Now/证据/缺口；完整重放且无错误时点放行。零High Attention合法，三份可以全部实质否决，不能为数量放宽准入。

**Forbidden scope**：BUY/ADD/仓位/订单、全市场DCF、完整M3决策对象、个人组合、Web、所有行业模型、收益调参、symbol专用流水线、修改冻结M1/人工区/生产数据库/计划任务/PTA。

**Exit criteria**：Engineering、Current Data、Research Review、Excel/User Review分别记结果；关键证据或用户可见验证未完成则PARTIAL，外部等待单列。全部毕业后交付Product Checkpoint A、完成客观审查，在同一总Goal中继续M3，不再因阶段完成退出。run-once不冒充每日自动运行。

### M3. Explainable Decisions and Thesis Continuity

**Goal**：建立 Research-to-Decision 的理由卡、入场论点、人工日记及买卖一致性，达到有边界的 L3。

**Why it exists**：解决“为什么买、为什么拿、哪里错了”，不是把 Attractive 改名 BUY。

**Prerequisites**：M1研究合同和M2候选来源通过；继承Post-M1 HumanApproval/EventReview/PreDecision门而非重建；注册决策政策/反例；最小 PortfolioPreconditions 与 Entry 确认输入明确，未提供则 WAIT。

**Domain changes**：InvestmentDecisionReview、DecisionEvidenceBundle、Buy/Hold/Add/Reduce/Exit Card、EntryThesisSnapshot、InvestmentConsistencyReview、DecisionJournalEntry；完整状态优先级及拒绝规则。

**Application changes**：研究 -> 前置检查 -> 理由卡 -> 用户确认/拒绝 -> Entry/Journal；Decision域、卡片read model、历史replay可在共享合同冻结后并行，真实BUY正向验收必须等待有效G3/Event/Price及最小人工确认容量；后续复核必须引用同一原始论点；无需买入才能继续研究。

**Persistence changes**：不可变决策/Entry/Journal 和更正链接、规则版本、Bundle 完整依赖；实际与模拟命名空间隔离；私有数据不得入公开 fixture。

**Data requirements**：M1/M2真实研究、价格和事件证据，明确的人工持有基线/模拟事件；没有原买入原因不捏造。

**Tests**：缺一项 BUY/ADD 前置即拒绝；跌价不自动加/卖、涨价不自动卖、breaker否决、理由与字段矛盾、重复确认幂等、事后重建标识、原始论点未被覆盖。

**Point-in-Time requirements**：重放当时的 Facts/规则/Portfolio/Entry；Current 不覆盖 Original；现实没有某类状态时用可证历史案例验证并标 historical。

**Acceptance criteria**：真实不同公司产生完整理由卡和版本链；至少一条从人工模拟 Entry 到新证据、Consistency 和减/退出复核的完整真实历史链；所有状态有反例测试，风险与估值减仓原因分开。至少3份卡片经用户阅读复核能复述理由和反证；用户验收未提供时不得自评通过。

**Forbidden scope**：自动创建成交、券商订单、数值仓位优化、自动把回测胜率当置信度。没有容量输入时不得发个人化正向复核。

**Exit criteria**：可追溯“哪条原始理由变化”，工程/研究/人类可理解性分别通过，形成Product Checkpoint B。真实 BUY 数量可为零，不能降低政策求信号；历史真实数据链可验证未在当前出现的状态，但仅合成正向测试不能声称真实BUY路径已验证。未有足够审批/容量的公司保持WAIT，当前可用范围逐项限定。

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

**Prerequisites**：M3版本/决策/Entry合同稳定后，可与M4并行建设事件收集、水位、outbox和恢复；Portfolio相关事件产品验收必须等M4真实合同。源健康/资源预算、通知目标及调度权限预先确定，生产动作仍单独确认。

**Domain changes**：ChangeEvent、MaterialityPolicy、DependencyInvalidation、Alert/ReviewDue；复用现有ModelValidity/Batch，补规则变化与事件扫描截止日失效。

**Application changes**：增量采集 -> 去重/更正 -> 重大性 -> 有界重算 -> Entry/Portfolio复核 -> outbox；财报季/周/月 Review Loop；只重算受影响对象。

**Persistence changes**：事件账、旧新版本关系、扫描水位、任务锁/checkpoint、outbox投递及确认；崩溃重启可补发且不重复建议。

**Data requirements**：真实财报/公告/资本动作/分红/价格和组合变化；公告日期级不确定性保守处理；源中断要形成健康事件。

**Tests**：重复/乱序/晚到/更正、失败恢复、静默日、Critical breaker、超时/限流/通知失败、价变不改内在价值、模型STALE不自动清空历史。

**Point-in-Time requirements**：保存 detected/effective/available 三时间、当时依赖和规则；事件历史replay不得提前通知。

**Acceptance criteria**：真实事件触发受影响报告与理由变化；当前静默与健康失联可区分；每日输出含新进/退出关注、各Review、Thesis/Dividend警报和系统异常，全部0合法。关键事件真实历史replay与在线观察分开验收。

**Forbidden scope**：每天全量深研、LLM无预算读全市场原件、新闻热度改估值、重复worker、未经授权通知/改生产任务。

**Exit criteria**：run-once与恢复/投递证据通过后，经授权接既有调度做 shadow；自然时间观察交M6，不循环等待未来事件把工程卡死。

### M6. Operational and Real-Use Readiness Validation

**Goal**：完成真实运行、数据、恢复及安全方面的准入验证，输出 `OPERATIONAL_ACCEPTANCE_PASSED`；M7在此基础上完成个人工作台最终交付。保留原M6全部实质验收，不把增加M7当作推迟或取消安全门，也不认证策略盈利。

**Why it exists**：真实可用还需要稳定数据、可恢复运营、用户理解及错误处理，测试不能替代。

**Prerequisites**：M1-M5产品验收；单独确认生产migration、账户数据/发布/通知/调度范围；保护PTA的资源基线与回退方案。

**Domain changes**：不新增投资策略；只补验收发现的适用性、拒绝或解释缺口。

**Application changes**：完成批准的staging->shadow->limited-use切换、数据源失效降级、健康检查、应急停发布/停新增复核能力；保留研究和证据读取。

**Persistence changes**：生产角色最小权限、事务一致性、完整输入/结果/事件/私有Journal、数据迁移parity；独立加密备份和恢复到新库，不恢复覆盖生产。

**Data requirements**：真实全市场日期快照、实际个人组合（可全现金）、真实事件与已核研究；模型未覆盖行业明确拒绝，正式使用行情需授权与质量复核。

**Tests**：离线合同+真实数据复算+PIT+隔离DB+Excel+恢复/资源/异常演练+人工任务测试，全部绑定同一候选版本。旧历史实验不得成为当前准入隐式依赖。

**Point-in-Time requirements**：历史信息集/当前信息集/模拟/真实账户清晰隔离；按当时可知数据重建至少一条入场至变化复核的决策链。

**Acceptance criteria**：满足第12节全部条件。必须预登记不少于20个连续真实交易会话的shadow观察，含至少一次真实财务或资本分配事件；若自然时间未覆盖，保留为未完成线上验收，历史replay只补工程验证，不能代替真实运行。每日重复执行不增加交易会话计数；按交易所会话记录，缺失/关键故障不能算成功，重大缺陷修复后重启受影响版本的观察窗口。20个会话是候选运营最低观察门，不是工期或收益统计证明，可在观察前基于风险加严，不可事后放宽求通过。

**Forbidden scope**：自动交易、以盈利/出现BUY作为毕业条件、删不利样本、无授权部署、挤占PTA资源、用备份文件存在代替恢复成功。

**Exit criteria**：独立审查工程/研究/当前数据/决策解释/组合/运营及阶段用户验证，全部通过后标 `OPERATIONAL_ACCEPTANCE_PASSED` 并在同一Goal进入M7，列明支持画像、未覆盖范围、风险和复审日期。任何P0身份/未来数据/错误放行缺陷未解决不得准入。M7复用这些证据，不重复要求另一轮20会话。

### M7. Personal Investment Workbench Delivery

**Goal**：在M6已验证的系统上完成个人投资工作台的端到端交付与用户独立使用验收，最终达到有边界的 `INITIAL_ASSISTED_USE`。M7是本次新增定义，不是已存在或已完成的阶段。

**Why it exists**：把“组件和运营通过”落到用户能每天使用的一个入口，最后证明用户知道研究谁、为何买/持/卖、组合与股息有什么风险；不是再造新功能平台。

**Prerequisites**：M2-M5产品能力与M6真实运营门全部通过；真实用户IPS/组合、授权发布与通知范围已确认。M7只读展示整合和任务脚本可提前准备，最终签收不可提前。

**Domain changes**：原则上不新增投资领域；仅修端到端验收暴露的理由缺口、状态矛盾、依赖失效或边界错误。Entry、Decision、Portfolio、Event沿用原合同。

**Application changes**：同一原Excel主入口贯通全市场、候选、深研、重点关注、人工买入/加仓复核、持有理由、风险/减仓/退出、股息现金流、今日变化与数据健康。导航可定位对应Evidence/Entry/Journal；未来Web仍能复用同一read model，不在本Goal另建Web。

**Persistence changes**：形成受控的发布清单，绑定代码/配置/数据库schema、规则、研究与决策版本、组合时点、原Excel Hash、恢复收据和支持范围；维护手册及非敏感说明可入Git，私有资产不公开。保留可回退的上一发布版本。

**Data requirements**：当期已验证市场快照、受支持公司的真实研究、人工确认组合（全现金合法）、真实事件、决定及原始论点。尚无真实买入的用户可用显著标识的人工模拟Entry与真实历史信息链完成交互验收，不捏造实际成交/买入理由，不把模拟状态显示为今日信号。

**Tests**：复用M2-M6验收并补端到端用户路径、状态一致性、断链/过期/源失联、无持仓/空候选、工作簿占用与回退、权限/隐私和用户任务测试。仅修阻碍交付的缺陷，不因交付再做全仓重构。

**Point-in-Time requirements**：从任一Review卡可还原当时的事实、假设、报价、规则、Entry和组合，清楚区分Original/Current、historical/current、simulated/actual；原买入理由不被新研究覆盖。

**Acceptance criteria**：
1. 用户从原工作台能完成：发现关注对象、解释Why Now、查看反证/估值/股息边界、读买入理由、判断为何加或不加、解释继续持有、查减仓/退出与原论点的变化、查组合集中度、查正常化股息脆弱性、查今日重要变化及源健康。
2. BUY/ADD/HOLD/REDUCE/EXIT Review全部有理由和版本链；当下无合格信号可全WAIT，未验证的正向路径必须说明限制。历史案例/合成测试不能冒充当前获批机会。
3. 用户在常用设备完成实际阅读和操作确认，并能复述至少3份卡片的理由/反证，复用M3已通过的理解验收，另确认最终整合入口。代理不能替用户签收；另一个设备未验证时明确列限制，不宣称多端已测。
4. 给出一份简明使用/故障处置/恢复/停止发布说明、私有数据位置和授权清单、已知限制、支持画像及复审日期；运行失败有降级，无需用户每天排查日志。
5. M6不少于20个真实交易会话与恢复验收仍有效，无未关闭P0/P1错误放行、证据或运营安全问题；不以盈利、真实下单或出现BUY作为交付门。

**Forbidden scope**：自动下单、收益保证、用户未确认的风险偏好/研究批准、额外行业/策略/Web扩张、无限优化、修改原验收使之更容易通过、追加无必要常驻服务或损害PTA。

**Exit criteria**：最终验收表分别列Engineering/Research/Current Data/Decision/Portfolio/Operations/User Acceptance，全部有据且用户确认后标 `INITIAL_ASSISTED_USE`，完成总Goal并停止。缺任一项仍为PARTIAL/具体等待，不用“框架完成”替代交付。不自动增加M8、继续功能扩展或创建维护自动化。

## 10. Milestone Dependencies

```text
CURRENT: M1 DONE + Post-M1 DONE + M2 PARTIAL
  -> M2: 可信四通道主动发现 / Checkpoint A
  -> M3: 解释性决策 + Entry/Journal/Consistency / Checkpoint B
  -> M4 Portfolio域  ||  M5 Event基础设施
  -> M4+M5集成验收 / Checkpoint C
  -> M6: 授权shadow + >=20真实交易会话 + 恢复 / 运营准入
  -> M7: 个人工作台整合 + 用户独立使用签收 / Checkpoint D
  -> INITIAL_ASSISTED_USE / 总Goal完成并停止 (human review, no_order)
```

### 总Goal第一阶段：M2 的 DAG

```text
W0 核对已完成稳定化 / 基线 / 预登记
  -> W1 时点/身份/Coverage合同冻结
  -> [W2 四通道与候选合并 || W3 PIT/反例/抽样工具 || W4 Excel read model候选]
  -> W5 全市场有效会话run + 依规则抽样 + >=3份新发现实质研究/否决
  -> W6 统一原Excel发布 + Coverage/误放漏筛/重放联合验收
  -> W7 客观收口 / Checkpoint A / 阶段验收后继续M3
```

W1期间允许离线盘点源、Excel消费者和历史fixture，禁止多个工作流各自定义同名状态。W2的Quality/Dividend与Value/Cyclical可在同一合同/Policy下并行；合并后才运行端到端验收。W4先用明确fixture验证布局，真实发布等W5。不能让三份报告全部串行等待全市场深研，也不能先挑想要的公司再补抽样规则。

M3的Decision域、卡片展示、历史决策replay可并行；真实正向BUY验收汇合于有效G3/Event/Price、置信度及最小人工确认容量。M3只接PortfolioPreconditions，不提前造完整M4；缺IPS/持仓不阻塞非个人化理由卡，但禁止个人化BUY/ADD。

M4/M5可部分并行，不是M3前抢跑两阶段。共享Entry/Portfolio/Event合同先冻结，各自修改独立文件；组合事件、每日仓位复核与通知集成必须两边都通过。用户已授权将M2-M7纳入同一总Goal，因此满足依赖后可自动推进这些工程工作；这不等于授权生产改动、个人数据使用、通知或替用户签署验收。

### 用户可见产品节点

| 节点 | 通过后实际可用 | 仍不能宣称 |
| --- | --- | --- |
| A / M2 | 原Excel查看全市场覆盖、通道候选、Why Now、数据缺口、重点研究队列及实质报告 | 买卖信号、可持续收益、每日自动服务；High Attention可为0 |
| B / M3 | 受支持且证据满足的公司形成买/加/持/减/退人工复核理由；对照原买入逻辑，用户能复述反证 | 账户未知时的个人仓位；全部公司均可交易；没有真实正向链时不宣称BUY已获市场验证 |
| C / M4+M5 | 用户确认组合下的分层仓位/集中度/正常化收入复核；授权后的重要变化跟踪与静默 | 尚未经M6观察的稳定生产服务 |
| D / M7，依赖M6 | 用户实际使用签收；限定画像、已核数据与已确认组合内 INITIAL_ASSISTED_USE | 自动下单、盈利保证、全行业估值支持 |

Engineering Ready、Research Reviewed、Current Data Valid、User Ready分别验收。新增几种dataclass、全绿测试、工作簿能打开均不足以达成上述产品节点。

### 工作规模、风险与高强度运行

| 剩余工作 | 预计规模 | 主要瓶颈 | 验收强度 |
| --- | --- | --- | --- |
| M2收尾 | 中大，通用边界修复+真实通道研究，不从零开发 | 当前/PIT来源质量、候选证据与原表整合 | 全市场逐证券账+通道正反例+3份新发现报告+抽样+WPS |
| M3 | 大，投资政策和解释性研究并重 | 有效人工审批、Entry真实性、用户理解 | 全状态拒绝/正向路径+真实历史决策链+至少3卡用户复述 |
| M4/M5并行 | 大，两个相对独立域后联合验收 | 私有IPS/持仓、事件完整性、幂等/恢复/通知授权 | 真实组合守恒/压力+真实事件+异常恢复+每日可读输出 |
| M6 | 实现量依缺陷而定，运营验收强度最高 | 真实自然时间、运维/备份/授权 | 不少于20连续交易会话+真实事件+隔离恢复 |
| M7 | 中，复用既有能力的最终交付，不扩新功能 | 用户参与、前台一致性、独立可用性 | 真实工作台任务验收+证据/Entry贯通+用户签收 |

每天约20小时只增加可用执行预算，不等于20小时有效研究，也不能把等待、限流、重试和测试并行当线性提速。当前没有足够稳定吞吐数据，暂不承诺“几小时/几周必完成”。W1与首批通道验证后，基于实际完成的可验收工作包、外部输入及人工响应更新 optimistic/base/risk-adjusted 剩余窗口，记录估计假设，不能拿测试数量外推进度。M6的20个交易会话是确定的最低观察长度，不折算成运行次数。

一个总Goal跨M2-M7多个workstream，不因一个包或阶段完成就退出。阶段验收有据后记录交接并继续；未通过不虚标DONE。若仅人工签收/自然时间等待，可继续总范围内依赖已满足的离线工程和M7展示准备，不能发布依赖未验收输入的个人化结论、跳过生产授权或提前签收M6/M7。范围/方法冲突、需单独授权的生产风险或关键人工输入须请求决策；有限重试，不无限轮询、空转或擅自设长期任务。证据Stop Rule按研究方法执行。

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
2. **PIT与版本假完整**：有日期/Hash但链不一致。M1已建立输入约束；M2新入口仍须修第1.4节缺口，不以签名一致替代信息可用边界。
3. **经济画像泛化错误**：三画像不是全行业；业务相似也可能有金融子公司、少数股东、监管/资源约束。适用性显式审阅，禁止默认模型。
4. **旧新入口混义**：旧screen、模拟账户/策略和Excel仍在。迁移有标签、回归和消费者清单，不无差别删除，也不让历史规则进入新决策。
5. **持续采集无产品增量**：证据stop rule、每批可读交付、假设/材料性边界复核；不会影响结论的新原件不无限收集。
6. **股息与价值双算/高息陷阱**：权益现金、分配状态、普通/特别、正常化、再投资和债务分开。
7. **规模/运营拖垮共享服务器**：分层计算、限并发/内存/重试、源预算；生产前核实PTA余量，不增加无必要常驻服务，不假设需要本机Docker Desktop。
8. **生产资产与公开仓库风险**：源码/schema/脱敏fixture可公开；持仓、密钥、生产dump、未经许可原件不公开。以私有证据存储及加密备份保障恢复。
9. **代理/接口/授权不稳定**：来源可替换但口径需再核验；不得通过不合规访问补数据；错误源不能被第二个同源镜像洗白。
10. **总Goal过大或虚假收口**：明确终点M7，以版本化阶段收据续接，每次聚焦依赖已满足的工作；M4/M5有界并行，不能同时无序铺开所有模块。所有验收完成后停止，不新增M8或无限打磨。

## 14. Explicit Non-goals

- 自动炒股、订单执行、券商接入、收益承诺、保证股息或强制满仓。
- 本轮编码、改Excel、连生产DB、改调度/服务器/做生产迁移；本轮仅审查和文档。
- 当前M2开发BUY/ADD/个人仓位、Web、所有行业估值；不为消除所有技术债大重构，不重新开发冻结M1。
- 将短期市场走势预测、技术指标拟合或最高回测收益变成价值投资主线。
- 每天荐股、以评分排名替代解释、用LLM作为唯一财务数字计算来源。
- 用真实资金交易来证明产品能力；模拟盈利或fixture全绿替代生产验收。
- 重新建设已冻结Stage A/C0-C3，或把新的有限研究允许解释成随意修改冻结历史。

## 15. Authorized Long Goal

**总Goal：VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE。**

按用户最新要求，终点由单独M2扩大到M7。继承f4bb55c及后续成果：M2主动发现 -> M3解释性决策/Entry一致性 -> M4/M5组合与事件有界并行 -> M6真实运营准入 -> M7用户交付。M1不重做，安全门不放宽。

每个阶段通过后记录证据并自动继续，不要求用户重新建Goal；真实研究批准、私人IPS/持仓、生产迁移/调度/通知和用户签收仍需对应人工输入/授权。当前聚焦M2，具体阶段门在 [current-stage-goal.md](docs/current-stage-goal.md)，可复制总Goal文本在 [value-investment-goal-prompt.md](docs/value-investment-goal-prompt.md)。

M7全部条件成立后才完成总Goal并停止。外部/人工/自然时间未满足时分别记录具体等待及已完成工程，不能以阶段代码齐全宣称INITIAL_ASSISTED_USE。
