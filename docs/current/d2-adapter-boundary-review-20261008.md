# D2 适配与真实输入复用边界：只读对抗审查（2026-10-08）

## 1. 裁决

**第 8 节作为未来 D1/D5 的观察接口草案，已覆盖默认可关闭、version/date/hash/来源及阶段隔离，方向满足当前目标；它不是已实现、已运行或已获数据/投资准入的适配器。现有 M1 package builder 可以复用为转换基础，但不能直接视为通用 source-bound 单公司真实输入准入器。真实 D2 接入前有三个 P1 核验缺口及一个 P2 显式依赖缺口需要修补。** 本报告只提出修补要求，不实施修补，也不扩大 D1/D5。

审查对象是 HEAD `5ba570920f588f4660e91439dedb5ab6f32ff1fe` 下的实际工作树，包含既有未提交修改和未跟踪合同；不能只用 HEAD 推断被审代码。审查日期为 2026-10-08，关键文件哈希于 `2026-10-08T17:44:06+08:00` 读取；写后核验发现并行工作新增 residual-income valuation_timing，于 `2026-10-08T17:49:05+08:00` 重读 builder/research_input。随后于 `2026-10-08T17:51:05+08:00` 发现 runner 新接入 local-source verifier，已重读并将 F3 更新为“显式 local_path 核验已补、真实入口强制性与事实语义仍缺”。行号和第 7 节哈希同步更新。以下行号指该工作树观察版本，路径均相对 `D:/GPTProject/value-investment/`。

范围：读取 `open-source-adapter-review-20261008.md` 第 8 节、sentiment/sleeve、研究与决策合同、M1 估值/分红包 builder 及相关 Application、存储和测试源码。唯一写入为本文件。未执行外部项目、业务 CLI、测试、联网采集、package 构建、Excel 读写或发布；未修改代码、目标、阶段状态或已有结果。反例均为静态控制流推导，不冒称已运行复现。

当前约束依据：`docs/current-stage-goal.md:30` 明确 D2 优先、D1 接口限定、D3 私人输入门及 D5 验证门；`docs/current/advisory-sentiment-satellite-goal-v1.md:204` 要求完整真实单公司链路，禁止用 synthetic 替换真实证据或当前价格；该目标 `:326` 分别要求报告代码、测试、真实数据和用户验收。

## 2. 需要优先修补的接口缺口

### F1 [P1] 假设绑定没有证明“被审假设就是实际计算输入”

证据：`src/value_investment_agent/m1_valuation_package_builder.py:533` 分别构造 AssumptionSet 和 bindings；`:540` 缺 bindings 时传空元组。`src/value_investment_agent/domain/research/research_run_contract.py:294` 的验证函数只有 facts/bindings 两个参数，`:300` 对空 bindings 直接返回无 blocker，`:315` 定位 scenario 字段，`:336` 只比较该字段与 binding.expected_value。它不读取 AssumptionSet，不验证 assumption_name 是否存在、不比较该假设对应 Bear/Base/Bull 值，也不检查模型所用字段是否全部被覆盖。`src/value_investment_agent/research_input.py:714` 和 `src/value_investment_agent/research_application.py:549` 都调用同一校验；Application `:556` 的实际估值消费 facts，`:1064` 则另行保存 assumptions。

静态反例：把 AssumptionSet 的 base 折现率写成 8%，实际 scenario 及 binding.expected_value 同写 12%；或删除 bindings。当前上述校验不能发现两套数值不一致。两个对象都进入 descriptor hash 并不能证明它们语义一致。已有 mismatch 测试 `tests/test_research_input.py:262` 检验 expected_value 与 scenario 不等，不足以覆盖这两种反例。后续 human/PriceBridge 门仍可能拒绝正向结论，因此本发现不宣称已产生真实买入建议。

最小修补要求：真实输入入口须在调用模型前，依据登记的模型输入映射，核验 AssumptionSet、binding 和实际 scenario 三者的值、单位、场景、版本与证据；覆盖所有实际消耗的估值假设，允许显式登记的转换关系，禁止空/部分/重复/无名绑定静默通过。缺失则 `ASSUMPTION_MISSING` 或隔离，不能补模型默认值。尤其 builder `:223` 的默认 retention 和 `:300` 的默认 currency，真实适配器须显式保留并核验其来源，不能把默认值冒充披露或审阅假设。依据 `docs/data-and-evidence-policy.md:76`，保存一套假设而计算另一套不算追溯完成。

### F2 [P1] aggregate available_at 不能代替逐输入 PIT 截止门

证据：`src/value_investment_agent/domain/research/research_run_contract.py:84` 的 SourceDescriptor 没有独立 source_available_at 及其依据，published_at/retrieved_at 均可省略。`:160` 的 PitFrame 只有 report_period/research_as_of/valuation_date/available_at/computed_at，`:170` 检查 available_at <= computed_at，`:176` 要求 available_at 的日期不早于 research_as_of。`src/value_investment_agent/research_input.py:720` 仅将 publication/retrieval 与整包 available_at 比较；没有要求每项必要事实/假设在研究 cutoff 前可用。`src/value_investment_agent/research_application.py:274` 重复相同上界比较。相反，sidecar 草案 `docs/current/open-source-adapter-review-20261008.md:143` 明确要求必要输入 available_at <= cutoff。

静态反例：research_as_of 与 valuation_date 为 9 月 22 日，新增原件 published_at 为 9 月 23 日，整包 available_at/computed_at 为 9 月 24 日。在其他校验满足时，以上时间判断不会因该原件晚于研究截止而拒绝；缺 published_at 也不会由该层拒绝。若把这个包当作 9 月 22 日重放，便可能引入未来披露。这里的 available_at 可合理表示研究产物实际可用时间，但必须另有信息截止门，不能把两个语义合并。

最小修补要求：真实适配器保留显式带时区 cutoff_at，以及逐 fact、assumption、event、quote 的 source_available_at/依据；必要输入均不得越 cutoff。原件日期级披露使用登记的保守可用上界，不臆造分秒。今天取得历史原件的 fetched/computed_at 保留真实时间，不强行改成历史日；历史公开可用与本系统同期保有分开表达，strict contemporaneous PIT 未证实就维持 NOT_PROVEN。依据 `docs/data-and-evidence-policy.md:24`、`:26`、`:77`。

### F3 [P1] 来源声明与身份匹配没有覆盖所有实际原件字节和事实语义

证据：估值 builder `src/value_investment_agent/m1_valuation_package_builder.py:145` 只是构造 source descriptor；`:230`、`:319` 接收调用方 verified 声明及 operating_inputs。`src/value_investment_agent/domain/research/research_run_contract.py:96` 校验哈希格式，不读取原件。Domain 身份核验 `src/value_investment_agent/domain/research/issuer_identity.py:179` 对 ref/source 的 id/hash 匹配，`:201` 核验官方来源地址及身份元数据；这些是必要的身份声明一致性检查，不是 PDF 内容或磁盘字节证明。

写后并行新增的实际入口已部分修补：`src/value_investment_agent/application/product/company_research.py:213` 调用 verify_package_local_sources，`:264` 重新核验其返回的全部原件。`src/value_investment_agent/application/product/source_bound_inputs.py:16` 至 `:25` 对存在 local_path 的包要求每个 source 都有本地路径并重算字节哈希；该路径不能再按原结论称为“完全未核验”。但该 verifier `:12` 在所有 source 均未声明 local_path 时直接返回空元组；当前 package schema/入口没有强制真实包必须走该路径。另一来源检查 `company_research.py:108` 只请求 request.new_evidence_ids，`:214` 无 request 时不调用该核验；`src/value_investment_agent/infrastructure/evidence/evidence_stop_schedule.py:34`、`:37` 仅选择 requested IDs。故完整字节验证仍由可选字段触发，不能对所有真实输入作保证；包自身 hash 不会随着其引用原件变化。

静态反例：包内全部 source 不写 local_path，保持包和 ref 的 SHA 声明一致，移走或修改一个不属于 new_evidence_ids 的既有财务原件；上述入口仍无法据此发现变化。有 local_path 的完整包已不适用此字节反例。另一个反例是原件未变而 operating_inputs 被错抄，重新计算 descriptor hash 后声明仍可自洽。此处不把调用方编造的声明当作已验证事实，也不宣称已突破下游全部投资门。

最小修补要求：在真实 source-bound 包的显式版本入口强制每个实际消耗的原件/派生包提供固定本地引用及实际字节核验，不允许删除全部 local_path 退回声明模式；旧包可以保留兼容/只读状态，但不能自动获得真实数据准入。建立逐字段事实到原件物理页/表头/摘录、原始与标准化值、期间、单位、主体及登记验证方法的关系。身份从受核验原件/元数据核验，不能因填入 security_code 即成立；hash 正确、身份通过、数值含义核验分别报告。模型执行前缺失/篡改应拒绝或隔离，不仅影响最终推荐。可参考已有更严格的只读加载边界 `src/value_investment_agent/application/product/existing_valuation.py:307`，但该加载器 `:275` 已明确字节认证不等于研究审批或严格 PIT。依据 `docs/data-and-evidence-policy.md:31`、`:34`、`:38`。

### F4 [P2] 单公司 package 仍有隐式分红包依赖，且会读其他公司

证据：`src/value_investment_agent/m1_valuation_package_builder.py:488` 无条件按 root/symbol 调用 optional_dividend_result_for_symbol；`:490` 仅按 result.as_of 排除晚于 facts 的结果。`src/value_investment_agent/m1_distribution_package_builder.py:204` 最终调用 dividend_results_by_symbol；`:191` 加载所有分红包，`:192` 任意包失败均报错；`:152` 扫目录，`:153` 的 JSON 解码甚至在单包 try 之外。`:121` 确有分红来源字节核验，不能误报为完全没有验证。

静态反例：显式单公司估值 package 不变，目录内同公司分红包发生替换会改变结果输入；另一个公司坏包则可能阻断本公司转换。descriptor `src/value_investment_agent/research_input.py:749` 的确把选中 dividend_result 纳入 hash，所以不是“变化完全不入哈希”；问题是输入集合并非调用方显式固定，来源包版本和选择规则不能由顶层 package 单独重放。

最小修补要求：通用 source-bound 单公司适配器应接受显式 distribution package/result 的 path/id、version、SHA 和时间引用，或明确 null/缺失原因；不得静默扫描整个公司目录，也不得以日期早于 facts 代替逐分红阶段/可用时点校验。所有被消费的依赖进入同一 manifest/receipt，单公司缺失与其他公司错误隔离。该修补是 D2 输入边界，不是扩展分红模型或 D1/D5。

## 3. D1/D5 草案与现有合同的满足程度

| 要求 | 已有证据与判断 | 仍需冻结的最小边界 |
| --- | --- | --- |
| 可关闭 | 第 8 节 `:133` 定义总/通道/binding 默认关闭、DISABLED 空观察且无 IO/import/worker；`:176` 列出测试要求。设计满足，运行验证未做。 | 关闭后下游不得继续把缓存或旧 latest 作为当前观察；旧载荷仅作历史审计。拒绝/关闭结果保留请求与原因，不靠读取原始输入补审计字段。 |
| version | `:118` 有 contract_version；`:142` 有 commit/adapter/formula/parser/config/schema 和规则变更失效。设计覆盖。 | profile/规则版本及成员有效期必须实际进入规范化依赖指纹，不只是“变更会失效”的文字；独立实现公开公式时如实记录本项目实现/方法出处。 |
| date | `:120` 有 as_of/cutoff；`:143`、`:148` 区分 publication/availability/fetch/compute，禁止伪造历史观察。设计满足。 | 保留逐字段及成员水位；不要投影为仅有整包 available_at 的旧 M1 包并丢失截止证据。 |
| hash | `:144` 覆盖代码/原始/成员/规范输入/输出，排除 output_hash 自身。设计覆盖。 | 明确 canonical 编码、Decimal/null/日期表达与排序，输入/输出哈希独立重算；反例 F3 的原件字节核验不能省略。 |
| 来源 | `:141` 分离代码与数据；`:150` 分离代码许可与数据权利；`:146` 保留 coverage/缺失原因。设计满足。 | 许可或数据权利 UNKNOWN 必须保持明确拒绝/审计状态，不因 MIT、HTTP 成功、非空字段或 OBSERVATION_ONLY 变成正式数据准入。 |
| 核心隔离 | `:156` 禁止 D1 总分/BUY；`:168` 禁止 D5 真实观察进入现有 synthetic 合同及更改核心结果。满足当前阶段范围。 | 任何 future source-bound package -> decision 的转换都必须单独过真实数据与投资门；不从 feature 值补造 valuation、审批、私人组合或 budget。 |

另一个 **P2 合同完整性问题，需在未来接口冻结时补齐，无需现在实现 D1/D5**：第 8 节 `:124` 的 ObservationResult 外层只列 status/observations/reasons/action，没有声明返回 contract_version、channel、subject/request identity、as_of/cutoff、config/dependency hash、computed_at、output_hash 的固定载荷位置。这些信息被放在每条 observation 的 provenance 中（`:146`），因此空 DISABLED/拒绝结果没有可靠的可序列化绑定。应为所有结果定义统一外层审计 envelope，并明确旧观察缓存失效/关闭语义；关闭路径仅绑定已给定请求和本地已加载配置，不读取被禁用原件。这里是草案的字段落位缺口，不是现存生产绕过证明。

当前 D5 合同刻意比真实接口窄：`src/value_investment_agent/domain/portfolio/sentiment_contracts.py:48` 拒绝非 synthetic scope；`:69` 只用五个布尔门保护 synthetic ENTRY_REVIEW；`:87` 限定 synthetic policy；`:109` 约束 tactical sleeve。`src/value_investment_agent/domain/portfolio/sleeves.py:41` 保护共享总预算，`:43` 的 USER_CONFIRMED 只是一个 scope 标签，不含真实政策 receipt。当前没有证据需要立即把这些 synthetic 类型扩成真实版本。将来不能只把 scope 改为 REAL、布尔值设为 True、policy_scope 填 USER_CONFIRMED 即宣称过门：需版本化带证据的 value/risk/PIT/OOS/cost/Shadow/授权预算核验，并保留 core/tactical 独立状态、绩效与共享风险约束。目标依据 `docs/current/advisory-sentiment-satellite-goal-v1.md:249`。

## 4. 通用 source-bound 单公司 package 的不可丢失约束

适配器复用现有 ResearchCase、Facts、AssumptionSet、ResearchInputDescriptor、ResearchRunSpec 及精确 artifact 引用。转换负责保持和核验语义，不按 symbol 选择估值公式，不复制每公司流水线，也不替上游填写 READY。以下是必须保留的输入契约，不是新增一套领域体系。

| 边界 | 必须保留及核验 | 已有证据/复用注意 |
| --- | --- | --- |
| 输入时点 | report_period 与每项 period_start/end/basis；research_as_of/cutoff_at；valuation_date；逐 source published/available/availability_basis；fetched/reviewed/computed；quote session/final 状态；event effective/available/detected 与扫描覆盖。模型产物实际可用时间不得早于必要输入；重放截止与今天计算时间分开。 | `research_run_contract.py:160` 保留五项包级日期，但不能填补 F2；政策 `:77`、`:81`。当前原件 observed_now 标签不得转为同期 PIT。 |
| 标识 | security_id/symbol/exchange、issuer identity 及核验依据；case/run/descriptor/schema/package version；profile/model identity/version；报价/估值快照精确 ID/hash；事实/假设/事件证据 ID。事实、研究、模型、报价、分红、审批必须同公司且版本相容。 | `research_input.py:667` 核验 profile/router，`:677` 核验 case/facts/assumptions；`research_application.py:245` 核验 quote、`:250` 核验 distribution。保留这些拒绝门，旧无身份包只能显式版本适配并重核，不能补默认身份。 |
| 财务输入口径 | 实际用于计算的每项 Facts，原始/标准化值、币种、单位、FY/YTD/TTM、合并/母公司、归母/少数股东、普通股/股本/复权范围；原件更正与 supersedes 链；null 和有证据的 0 分开。 | 政策 `:24`、`:27`、`:33`；builder `:206`、`:273` 的 typed conversion 不证明这些逐字段语义已经核验。 |
| 估值假设 | 实际 Bear/Base/Bull、假设名称/单位/basis/rationale/evidence/confidence/sensitivity/order、适用时点/版本；折现率/增长/ROE/留存/现金流日期/股数/币种/terminal 与 bridge 暴露边界；全部 scenario 输入与审阅假设映射一致。 | `valuation_assumptions.py:79` 已有显式假设字段；builder `:328` 和 `:375` 可复用，但需修 F1。market quote 只进入 PriceBridge，不进入 intrinsic assumptions，也不以行情反拟合假设。 |
| 来源与复用指纹 | 原件 URL/id/path/SHA、物理页/表头/摘录、parser/公式/核验方法与日期、input_fact_ids、代码和数据权利状态；把真实消费的 facts/assumptions/distribution/quote/event/reviews/config/rule/model/profile/parser/扫描水位固定到一个 manifest。 | `research_input.py:731`、`:769` 已把对象规范化入 hash；`research_run_contract.py:130` 的依赖字段含 profile_id，但不含独立 profile_version，须由 source-bound manifest 补足实际配置版本/hash。同 raw/input hash 不能豁免依赖变化（政策 `:78`）。 |
| 旧结果不可变 | 精确结果版本、payload hash、输入 manifest 和所用规则；固定 ID/hash 读取，latest 仅是可变指针且解析后重核。追加更正、新输入和新结果，用 supersedes/invalidation 关联；保留旧 conditional/rejected/stale/not_eligible 和审批原意。关闭 sidecar 不删除证据，也不能让旧载荷继续充当当前信号。 | `research_artifact_repository.py:103`、`:121` 追加版本，`:158` 加载时验证，`:198` latest 转为精确加载；`application/decision/artifact_bundle.py:36` 按 ID 无 mutable head 重放。`application/product/common.py:54` 拒绝覆盖现有输出，适配器不可改成覆盖同一路径以使验收通过。 |

表中未写完整前缀的 `research_input.py`、`research_run_contract.py`、`research_application.py`、`valuation_assumptions.py`、`research_artifact_repository.py` 分别位于 `src/value_investment_agent/`、`src/value_investment_agent/domain/research/`、`src/value_investment_agent/`、`src/value_investment_agent/`、`src/value_investment_agent/`；政策行号指 `docs/data-and-evidence-policy.md`。上述必须项来自既有政策，不授权本轮修改这些文件。

## 5. 数据准入、投资准入与 D2 完成必须分开

1. **数据准入**回答来源原件、身份、时间、口径、数值和哈希是否成立。代码获许可、来源非空、包能序列化、hash 一致、synthetic 测试通过，都不能单独把 E1 升成正式 FinancialFacts。保留 E0/E1/E2/E3、缺失/冲突/隔离和各字段验证状态。
2. **研究/估值准入**另核验 profile/model 适用性、financial/research gate、thesis/counter-evidence、假设与真实输入一致性及版本化审批。数据通过不意味着 ValuationResult READY。现有 conditional_research_only 不因一次新下载、算术重放或 PriceBridge 标签变成正式合理价值。
3. **价格/建议准入**另核验当前真实交易会话、模型有效窗口、重大事件扫描/材料性复核、PriceBridge、PreDecision 和适用风险条件。建议不是订单；无真实 IPS/portfolio 时 `BLOCKED_PRIVATE_INPUT`、position_guidance=null。私人输入缺失不阻断独立单公司数据/研究工程，但不得补造个人仓位。
4. **D5 准入**即使存在真实 feature observation，仍需 value gate、PIT 历史成员控制、预登记规则、walk-forward/OOS、费用/滑点/停牌/涨跌停/流动性模拟、独立重放、Shadow 与独立预算。真实行情与策略有效性是两个证据层。

这些分层符合 `docs/data-and-evidence-policy.md:44`、`:46`、`:79`，以及目标 gate 顺序 `docs/current/advisory-sentiment-satellite-goal-v1.md:223`。

**NO_ACTION 是合法结果，不是 D2 完成凭证。** `tests/test_decision_recommendation.py:68` 用重复字符哈希，`:73` 用 fixture-v1 facts；`:402` 至 `:420` 的 NO_ACTION 验证缺少已存依赖时失败关闭。`tests/test_d2_workbench_decision_projection.py:24`、`:54` mock 掉真实 runner，只证明未绑定正向输出拒绝与参数转发。`tests/test_d5_satellite_contracts.py:16`、`:24` 使用 synthetic budget/features，不能计入真实 D2 或 D5。

600887 的已有真实负向材料也不能被抹去：`docs/current/d2-real-case-selection-20261007.md:48` 至 `:57` 记录九原件固定 manifest 与只读负向结果；`:59` 明确它是 existing research 的 fail-closed 读取，不是新 Facts/Case 准入、完整事件扫描、当前 quote 或 canonical 发布。该材料可作为真实旧结果读模型的证据，不能自动结案为 D2 纵向闭环。审查没有独立重算该运行时 manifest 或原件哈希，因此其运行结果在本报告中属于已有文档记载，不冒称本轮重新运行验证。

将来一条充分证据支撑的真实链路最终输出 NO_ACTION/WAIT/NOT_ASSESSABLE 可以符合其负向能力验收，不能为了得到 BUY 调参数；但必须按 D2 既定验收分别列出哪些真实输入已准入、哪些 gate 真实拒绝、当前 quote/事件覆盖是否成立、精确 artifact bundle 是否可重放、canonical 产品链是否完成及用户验收。拒绝处理通过不等于全部依赖已准入，synthetic NO_ACTION 更不能代替真实 D2 完成。本轮不更改验收标准或阶段状态。

## 6. 修补优先级与静态审查局限

Root 在下一次真实 source-bound 单公司接入前，应先补 F1-F3 的校验和 F4 的显式依赖，再通过同一共享 Application 链验证既有真实案例。仅需最小反例覆盖：空/部分 bindings、AssumptionSet 与 scenario 不一致、晚于 cutoff/未知 available 的输入、一个非新证据原件漂移、错误字段/单位/主体、外部目录变化与其他公司坏分红包，以及旧 ID/hash 的结果重放与不可覆盖。观察结果 envelope/关闭缓存语义在未来 D1/D5 最小合同冻结时补齐，不需要现在实现采集器、全市场排行、评分或策略。

未发现必须立即扩大或替换当前 synthetic D5 合同的理由；没有生产运行证据，不把未来 schema/版本缺项夸成已上线事故。现有 gate/identity/存储检查是有效基础，但不能证明 F1-F4 已被其他层统一补足。本文不评估收益、外部库执行正确性、实时网络可用性、Excel 布局或生产 Shadow。本轮没有运行测试；上述测试文件引用只证明测试源码覆盖了什么。

## 7. 关键观察版本 SHA-256

以下哈希绑定本报告的静态观察字节，不认证财务真实性、同期 PIT 或阶段验收。并行工作后文件变化需重新定位行号并复核结论。

| 文件 | SHA-256 |
| --- | --- |
| `docs/current/open-source-adapter-review-20261008.md` | `97d0a1f0f2f73a1c46b4f2dd6988488f802cad0109f9069b63c754403cea2e94` |
| `src/value_investment_agent/domain/portfolio/sentiment_contracts.py` | `4bdf6163c259ff170d21d56b67c25a5117f62270038a32677f8b331c54fe9473` |
| `src/value_investment_agent/domain/portfolio/sleeves.py` | `5c81e36574ae0864d4d306b5978b96e4d44c1274d67f5062991be0528759e2dd` |
| `src/value_investment_agent/domain/research/research_run_contract.py` | `4da9abf438a68a71dc35ffe6de9c1b070b2545317e3a4d651f99cea323daf095` |
| `src/value_investment_agent/m1_valuation_package_builder.py` | `f5e8c5c15cdb98afa974aae2001bd767a9d5aa9742a70ad1048807014e089c31` |
| `src/value_investment_agent/research_input.py` | `2b14523c4a766dce12a1534aadcc8d3d8d46ceaff68c12335d1c07d5c4082df9` |
| `src/value_investment_agent/application/product/company_research.py` | `c6381a02aa59b68041227a058b1decde2e34deb3ca6439f6c775bf2e9c83ac41` |
| `src/value_investment_agent/application/product/source_bound_inputs.py` | `f465b48b6c33fe6aa919070f026cb7858688cdcb2c74592fedf44135bb8b92a7` |
| `src/value_investment_agent/m1_distribution_package_builder.py` | `138e9a3301fae8bcbe0e198481fbf9bc372c053900fae72b32845199f7a1bdd9` |
