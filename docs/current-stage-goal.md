# 当前总目标：M2-M7 初步真实投资辅助系统

更新：2026-09-24 / 人工审查纠偏版。用户已将下一Goal扩到M7，不再在M2完成后退出。
总Goal ID：`VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`。
当前产品聚焦仍为 M2 与人工 Checkpoint A；工程已推进到 M7 Daily Workbench 候选，但不得把工程推进速度当阶段验收。
总目标现已进入实现阶段；先从 M2 的 W1/W2 共同合同时点、官方身份、逐证券覆盖与通道合并开始，
分阶段验收。不因总范围授权生产迁移、计划任务、通知、私人组合导入或公开推送。
权威分工遵循AGENTS；唯一长期路线为 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md)，本文件选择执行范围与交接门。
旧m2-current-progress-review等文件是历史输入，不覆盖最新范围；W0-W7是M2内部工作流，不是Milestone M0-M7。

## 2026-09-24 人工审查后的多维状态

工程、研究/产品、人工/运营分别记录，禁止用一个 `READY` 掩盖其他维度：

```text
M1  Engineering DONE | Research Workbench DONE | 已完成人工 G3 初审
M2  ENGINEERING_DONE | PARTIAL                | PENDING_HUMAN_REVIEW
M3  ENGINEERING_PARTIAL_PLUS | PARTIAL        | PENDING_HUMAN_REVIEW
M4  ENGINEERING_DONE_SIMULATED | PARTIAL      | PENDING_PRIVATE_INPUT
M5  ENGINEERING_DONE_OFFLINE | PARTIAL        | PENDING_RECONCILIATION / OPERATIONS
M6  PREFLIGHT_DONE | operationally NOT_STARTED | PENDING_AUTHORIZATION / SHADOW
M7  DISPLAY_ENGINEERING_DONE | PARTIAL        | PENDING_USER_ACCEPTANCE
```

本轮纠偏后的机器门已覆盖：M3 正向价格门、M4 决策制品绑定、M2 二阶段
Channel Verification、M5 旧人工 review Hash reconciliation、M3
Historical Research Replay（事实/报价 PIT，规则为追溯并显式标记），以及 M7
10 个日常主入口工作台。Checkpoint A-D、真实 IPS/Portfolio 与 M6 运营验收仍
保持人工待办。

M7 Daily v2 用户查看、完整性核验、故障与回退入口见
[m7-assisted-use-runbook-20260924.md](m7-assisted-use-runbook-20260924.md)。
M2-M7 当前全部人工待办与签收边界见
[m2-m7-human-review-handoff-20260924.md](m2-m7-human-review-handoff-20260924.md)。

## 总体成果与阶段交接

从主动发现公司，推进到能解释买/加/持/减/退理由、回看原始买入逻辑、结合真实组合评估仓位/股息、每日监控重要变化，最终用户在原Excel中独立使用。
全部Review始终人工决策，action=no_order；不连接券商或自动下单。

| 阶段 | 同一Goal中的工作 | 交接门及用户可见成果 |
| --- | --- | --- |
| M2 | 完成下方W0-W7和AC1-AC12 | 可信四通道/全市场/3份新发现研究或否决/原Excel；Checkpoint A |
| M3 | Decision Review、理由卡、Evidence Bundle、Entry/Journal/Consistency；复用人工G3和事件门 | 真实历史决策链、状态正反例、至少3卡用户理解；BUY/ADD需有效价格/模型/审批与最小确认容量；Checkpoint B |
| M4 | 用户确认IPS/组合、保守分层仓位、集中度与当前/正常化股息收入 | 真实组合对账、预算守恒/压力/隐私验证；缺用户资料仅做非个人化工程 |
| M5 | 事件采集/重大性/依赖失效/有界重算/通知与恢复 | 与M4可在M3合同稳定后部分并行；真实事件/静默/故障恢复，生产调度/通知单独授权；共同Checkpoint C |
| M6 | 授权后的shadow、资源/安全/备份恢复、真实运营验证 | 不少于20连续真实交易会话及真实事件，隔离恢复与真实RPO/RTO；OPERATIONAL_ACCEPTANCE_PASSED |
| M7 | 既有个人工作台整合、可追溯发布、用户独立任务验收与交付 | 复用M6不再加一轮20会话；用户签收后INITIAL_ASSISTED_USE/Checkpoint D，总Goal完成并停止 |

M3-M7完整Goal/依赖/Domain/Application/Persistence/Data/Tests/PIT/Acceptance/Forbidden/Exit合同在LONG-TERM-GOAL第9节，必须全部执行，不以此表代替详细门槛。

### 连续推进与等待

阶段验收通过后更新execution-status中的阶段/证据/下一工作包并自动继续，无需重新请求“是否进入下一阶段”。
每个阶段完成仍须客观评估投资逻辑、范围和后续计划，不因代码量或测试数增加就过门。
Engineering、Research、Current Data、Decision、Portfolio、Operations、User Acceptance分开记录；总范围批准不是所有阶段已准入。
人工签收/自然时间未满足时，允许继续已满足技术依赖的离线工程和M7展示准备；不把前阶段改成DONE，不发布未经确认的正向复核。
实际G3、IPS/持仓、最小容量、用户理解/交付签收不得代理编造。提前一次性说明所需输入，等候期间继续独立工作。
生产数据库迁移、服务/计划任务、通知目标、真实账户导入须提交具体范围、资源预算、回退和数据保护方案并获单独确认；现有服务器PTA优先保护。
不得以总Goal范围为由开公网数据库、读取历史口令自动部署、反复空等20天或擅自创建长期自动化；需要持续观察安排时另请求授权。
M6的20个交易会话按真实交易所会话计数，非20次运行；未满即未完成。重大缺陷修复后的观察规则沿用长期路线，不事后降低门槛。
所有阶段验收及用户签收达成后停止；不得自动增加M8、新行业/策略、Web或交易执行层。

## M2 阶段范围（当前聚焦，非总Goal终点）

以下保留M2具体工作流和验收；其中禁止BUY/ADD/仓位、生产改动的规定针对M2。M3/M4仅在对应门通过后提供人工决策支持，生产操作仍须单独授权。

## Goal / 用户可见成果

回答“整个A股现在有哪些公司值得重点研究，为什么？”：
官方Universe -> 低成本四通道 -> 线索/候选 -> 可解释优先级 -> 深研队列 -> 原Excel统一入口。
不产生BUY/ADD/仓位/订单；Decision-ready Candidate只表示可供M3消费的研究输入，不表示决策获准。
High Attention可为0，候选可以全部实质否决；不为了热闹填满板卡。

## 实际起点

审查HEAD `f4bb55cd686838b874b6a8b0c601492c8bd7aab5`，main，初始干净；最新提交2026-09-23 21:55:48 +08:00。
CI run35870537557两job成功；本轮本地2118 passed/6 skipped/18 warnings，跳过原因在execution-status顶部。
M2已有5568证券真实run、四通道0/50/50/50、去重113、独立WPS候选及8项Hash一致。
但时点约束、官方分母限制、多通道合并、完整性语义和统一前台仍不达毕业；绝非只剩三份报告。
完整代码定位与合成反例见长期路线第1.4节，不把反例当实际股票数据错误。

## 连续工作流与汇合点

### W0 基线、稳定化核对与预登记

重新取HEAD/dirty/CI/测试/manifest/原Excel源Hash；后续提交若已解决缺口，验证后跳过，不重复开发。
继承旧茅台断言修复、one-off维护标记、stress隔离与legacy边界，仅修可复现回归。
`build_m1_post_review_receipts.py` 不进入生产研究路径；临时haircut不能成为正式ValuationAssumption。
冻结M1及旧三公司历史证据；格力/华域/伊利NOT_ELIGIBLE不能为了产生BUY修改。
预登记通道规则理由、数据门、样本抽取、原件检查、队列预算、失败和stop rule。先于新候选/结果观察登记，不按结果挑公司或阈值。

### W1 数据时点、官方身份、Coverage共同合同

复用现有Universe、市场Adapter和Evidence合同；核对沪深北身份与证券/交易状态，不让源外证券进入正式池。
区分run generated_at、source fetched_at/available_at、report_period、quote_session；缓存不刷新成今日，未知时点不进入相应历史结论。
current-run使用真实有效会话；盘中/休市明确最近已完成会话或未最终收盘，不给日历日贴收盘标签。
逐证券逐通道记录EVALUATED/PASS/REJECTED/DATA_GAP/CONFLICT/UNSUPPORTED/NOT_EVALUATED或等价合同；分母及原因可对账。
报价健康、财务覆盖、研究证据完备分开。异常可隔离单只，不能因报价足够多就把整批事实标COMPLETE。
Policy/schema、输入和输出身份冻结后才允许并行改消费者，避免各工作流另造状态机。

### W2 四通道、候选合并与适用性

在W1共同合同上并行Quality/Dividend和Value/Cyclical；通道研究要求以长期路线第9节M2表及research-methodology为准。
先cheap screen得到线索，再对有界集合补关键多期事实；不要求全市场DCF或每只全量原件深研。
高股息/低PE可以触发研究线索，不能直接成为完整候选/高优先级的充分条件。
股息的普通/特别、预案/已宣告/已支付、收益率分母时点、现金覆盖/债务/CapEx/周期分开；未知正常化保留UNKNOWN。
Value补盈利/资产/现金及负债质量；Cyclical比较当前与有依据正常化范围/周期代理，不机械取历史峰值/均值。
筛选画像适用与估值Registry支持分开，不以“有行业字符串”证明模型支持；未知/金融/NAV等不默认FCFF。
合并保留所有channel/reasons/metrics/evidence/missing/veto，输出Why Now；保存进入/退出/降级原因和政策版本。
队列预算只截工作量，不悄悄丢掉全体通过者、数据缺口和截断分母；优先级不能等同便宜排行榜。
允许空池；legacy PE<=25/PB<=3/市值>=50亿只作shadow，不参与新排序。

### W3 PIT / Replay / 反例与抽样工具

与W2/W4并行，但使用同一合同。复用现有20家M1分层材料及明确新增对象，必要时有界扩到20-50家验证，不重做M1全部研究。
增加未来披露、时间未知、旧缓存、非官方证券、冲突、缺页、退市/停牌、Profile未知、跨通道覆盖、预算截断、特别分红与周期高点等反例。
从不可变输入包冷重放，验证原件Hash、已知时间、政策/解析器版本、状态及证据依赖；候选signature相同不足以毕业。
至少两个真实信息边界的PIT重放，验证未来信息被排除、更正/晚到与规则变化可解释。历史Universe未知则限缩证明范围，不捏造无幸存者偏差。
抽样规则与样本ID提前登记，覆盖入选、拒绝、缺数据、不支持、预算外、legacy差异；评估误放和疑似漏筛，不将小样本写成全市场精确错误率。

### W4 Excel read model / 候选设计

与W2/W3并行开发展示投影，先fixture明确标识；不在Excel重复财务/筛选计算。
复用现有前台导航，主入口可看市场覆盖、四通道、候选/深研队列、Why Now、证据/缺口、研究或否决报告。
仅一套当前工作台；独立M2文件可保留为历史快照/候选，不再造成用户每天寻找多个“最新版”。
买卖/组合/每日监控仍显式未接入，不能显示虚假的0信号或已有实时服务。
保留原人工区、交易/持仓/历史、M1冻结输出；新增动态区域与冻结区域明确分开。

### W5 真实全市场运行与新发现研究

W1-W4工程合同汇合后，至少完成一次真实有效交易会话的全市场run，按来源/时期/行业列coverage。
采集有限并发/限流/失败预算，不SSH、不连接生产库；授权来源不可得时明确PENDING_EXTERNAL_DATA，其他工程继续。
依W0规则从系统新发现对象中抽取至少3家，形成实质研究或实质否决报告，至少覆盖两通道或记录为何当前来源限制未满足。
报告包括为什么入选/现在关注、商业与现金机制、关键事实/范围/可用日、模型适用性、股息与周期风险、最强反证、拒绝或进一步研究理由和下一触发点。
可复用M1引擎/证据但不能拿原固定公司重命名为新发现成果；不可支持的模型直接拒绝，不为出数值扩新金融模型。
若没有可追溯的新发现对象，保留空池与PARTIAL，不手选熟悉公司充数。三份报告不是三份“推荐”。

### W6 统一发布与联合验收

先候选生成与结构/read model核验，再备份/源Hash防覆盖/原子发布到既有WORKBOOK_PATH的自动展示区域。
文件占用或源Hash变化保留候选并请求处理，禁止强制关WPS或覆盖用户改动。
实际WPS只读打开、导航/筛选/长文本/证据链接/公式缓存验证；无法执行则记录未验收，不以openpyxl成功替代。
完成逐证券覆盖勾稽、误放/漏筛分层抽样、三报告原件复算、PIT/冷重放、全部回归与资源证据。
用户从原表能看清“值得研究”而不是“建议买入”；跨设备不能依赖只存在本机的D盘证据链接。

### W7 阶段收口 / 进入M3

记录Engineering、Current Data、Research Review、Excel/User Review分别状态；更新execution-status并给产品/投资方法/技术债客观评估。
达到M2全部AC后交付Checkpoint A、完成客观审查，记录阶段交接并在同一总Goal继续M3。任何单包或单阶段完成都不等于整个Goal完成。
外部或人工缺失只登记相应等待，不无限轮询、不伪造验收；可继续总Goal内技术依赖已满足的独立工程，不能跳过相应人工/生产门；依Goal工具实际停止/阻塞规则报告状态。

## M2 Acceptance：全部通过才能毕业

| ID | 必须证明 | 证据 |
| --- | --- | --- |
| AC1 | 继承稳定化且无未解释离线失败 | HEAD/dirty/CI/本地全量、skip理由、one-off/stress/冻结回归 |
| AC2 | 官方全市场身份与逐证券逐通道Coverage可对账 | official/raw Hash、交易状态、missing/extra/unsupported/预算外明细；不是固定5000门槛 |
| AC3 | 四通道真实有效、线索与已核候选分开 | 真实跨公司案例及各通道正反例；空Quality保留成因，不能将数据不足当无机会 |
| AC4 | 参数与数据门可解释且不后验调参 | versioned Policy、阈值依据/适用范围/反证；legacy只shadow；缺失不填0 |
| AC5 | 通道合并不丢原因、画像不误用、队列可解释 | 全原因/证据/缺口、Why Now、转移/预算与Profile适用收据 |
| AC6 | 时点/版本/Hash完整重放 | 未来/缓存等反例拒绝；两个真实信息边界；冷重放；历史覆盖限制明示 |
| AC7 | 至少一次真实当前市场run | 有效交易会话、采集时间/源、完整分母及失败清单；历史replay不冒充current |
| AC8 | 至少3家系统主动发现的实质研究/否决 | 预登记抽样、版本输入、原件、可读结论与反证；至少两通道交叉验证，不凑BUY |
| AC9 | 误放/疑似漏筛及缺口有分层审查 | 入选/未入选/数据缺口/不支持/预算外样本；没有收益后验筛选 |
| AC10 | 原Excel统一可用入口 | 受保护发布Hash/回退、WPS/导航/文本/链接/缓存，手工记录完整；未来板卡未接入 |
| AC11 | 无越权和性能失控 | no_order，无BUY/ADD/仓位；无生产DB/调度/PTA改动；有界资源、无symbol复制流水线 |
| AC12 | 真实用户成果与结束边界 | 工程/数据/研究/展示分别有据；用户能找到候选原因/缺口/报告；客观评估并记录交接后继续M3 |

本次文档审查不宣称以上新增验收已经通过。已有5568运行、文件Hash与测试结果应复用，但不再采用“1-6、8-10全过，只剩三报告”的旧结论。

## 提交、隐私与停止纪律

按可独立验证的合同/通道/展示/真实验收批次提交，不按每家公司复制流水线；同一合同变更与测试一起提交。
提交前检查diff和敏感信息，暂存明确路径，禁止git add .。源码、schema、脱敏fixture和文档可入库；个人持仓、生产dump、密钥、未授权原件和原WPS人工数据不可公开。
大原件仅保留私有manifest/Hash及合法来源指针；CI使用合成/脱敏fixture。推送只在当前Goal有明确授权时执行，本轮不commit/push。
需要不可逆生产动作、方法冲突或不可替代用户输入时请求确认；整个总Goal不得自行批准G3或编造IPS；生产调度仅在M5/M6相应门满足且具体方案获单独确认后实施。

## M1 历史目标收口

目标 ID：`M1-FIXED-SAMPLE-RESEARCH-WORKBENCH`，状态：`DONE`。固定样本研究工作台的
AC1-AC10 机器验收已通过；研究结论全部保持 `conditional_research_only`。正式 G3
研究批准和模型前公告材料性复核是后续 M3/M5 的决策阶段复核，M1 只保存为显式
`deferred_human_review`，不作为研究工作台验收阻断项。正常化股息情景仍显式
`NOT_READY`，这是后续研究缺口，不代表研究状态可以升级。
可重复的 AC1-AC10 机器验收入口为 `scripts/audit_m1_acceptance.py --run-tests`；
审计器只核本地证据，不批准 G3 或事件材料性。逐条公告/G3 后续复核台账由
`scripts/render_m1_human_review_packet.py` 只读生成，见
`docs/m1-human-review-packet-20260923.md`。以下 M1 章节保留为历史授权和完成定义，不再作为新增任务。

## 继承与替代

Stage A、P0/P0.5、三公司工程/Excel MVP、C0-C3 保留冻结，不重做。C3 完成说明工程平台成立，不代表研究内容或生产系统就绪。
原独立 C4 adapter 建议被本目标的第一个技术工作包吸收，不能只完成 adapter 就宣布本目标完成；旧 C3 W1-W12 原定义保留在 Git 提交 `494d085`，验收在 [execution-status.md](execution-status.md)。历史扩样本审查仍是当时事实，不是当前任务授权。

## Goal / 用户可见成果

把已有平台推进为真实研究工具：20家固定样本分层入组，其中至少6家形成可阅读研究档案；复用现有模型、股息合同与原WPS Excel，回答为什么研究、怎样赚钱、价值/股息的条件、当前价格位置、最强反证及下一事件。

这不是买卖信号、仓位或实盘准入阶段。保持 `action=no_order`。第一个用户可见增量在6家深研时交付，不等20家结束才展示。

## 实际起点与优先风险

审查HEAD：`494d0857c7edb4b76b0527d773065013b7abf2d1`；当前HEAD的GitHub两项CI均success。
本轮实测CI清单173 passed / 4 PostgreSQL skipped，冻结验收9 passed，真实runtime内存replay语义相等。
主要缺口：
- Manifest只能配置policy；replay仍绑定三公司/茅台输入，Excel未消费新Application结果。
- `research_application.py` 可接受case/spec与facts日期混配，available_at可早于输入；登记assumptions没有明确绑定实际scenario_inputs。
- `research_batch.py` 在rule_version改变但输入hash相同时仍可UNCHANGED。
- G3来源为旧case状态，需与本次计算绑定；正式人工研究批准归属 M3，M1 不自动批准，也不把未批准状态作为研究工作台阻断项。
- 三公司仍无通过生产验收的估值；Distribution为PARTIAL。
- 原Excel当前Hash与历史冻结不同，必须重新取当前源Hash保护人工区，不回退用户工作。

## 工作包顺序

### W1 基线、样本与方法预登记

核对HEAD/dirty diff、CI、运行环境、源与目标文档；记录支持画像与测试层次。
预登记20家公司及选择理由，不按后验收益/便宜与否/易出数值选择；包含原3家、现有3种经济画像、同画像第二家公司、模型不支持、资料不足和经济风险反例。
登记数据来源、字段/假设要求、样本研究深度、预算、stop rule和验收口径。负面/不支持公司允许保留，不为凑完成率剔除。

### W2 可信输入与共同安全边界

建立版本化input descriptor -> typed RunSpec adapter；包含security/profile、Facts、Assumptions、ResearchCase、distribution、quote、validity/event scan、源Hash与信息截止日。
校正日期/可用时间、实际计算假设映射、规则/模型/解析器/Profile/扫描水位的fingerprint失效；区分report_period、research_as_of、valuation_date、available_at、computed_at。
坏descriptor与未知Profile在单公司边界隔离，不能在构建整批前抛错终止所有公司，也不能套默认模型。
G0-G2 -> 合法计算 -> G3绑定本次结果与后续批准记录；M1 只允许 `conditional_research_only`，正式 G3 批准和事件材料性复核归属 M3/M5，不能以模型算出数值自动升级研究状态。
保留原三公司快照，先通过跨公司/跨版本/跨日期/未来数据/更正/规则变化回归再扩大真实样本。

### W3 真实研究与6家公司可见闭环

把独有解析留Provider，把公共事实/假设转换、校验、计算、桥接与发布放共同路径。
对至少6家完成可读研究档案：BusinessQuality、FinancialQuality、CapitalAllocation、Thesis/Return Drivers/Mispricing、最强反证、可观察breaker、下个事件。
BusinessQuality至少表达优势/弱点/证据/置信度，覆盖Moat、定价/客户、行业结构、ROIC/增量ROIC、再投资、资本强度、现金转换及优势期，未知/不适用明确。不以总分代替解释。
复用三现有模型与C2 Distribution；有证据的有界假设可研究，不要求内部细节永远精确披露，也不能用无依据范围解除模型适用性问题。
先交共同read model和Excel候选，展示已完成和未完成的研究，保留原表人工内容。反向估值给预登记边界、多解/无解原因。

### W4 12 -> 20 分批扩展与输入持久化

每批审查Profile/Data/Valuation/Dividend gaps、新增公司成本与真正重复能力，再继续下一批。
每个入组对象有真实身份、来源、画像适用性、已支持输出或明确缺口；不得只导入股票代码就计入20家。
复用C3 Repository保存完整可重放输入包及结果依赖。不是重建数据库平台；仅disposable/test PostgreSQL。没有本机Docker/DSN可使用既有GitHub隔离CI，不得回退生产DSN。
验证冷启动由封存输入和版本恢复同一语义；断网不依赖rolling latest重新查询。

### W5 原Excel发布与验收收据

Publisher只消费Application read model/artifacts，数值不在单元格重算成另一套研究结论。
先保存候选、源Hash、回退文件，检查人工区/历史不变，再原子发布原WPS工作簿；冲突/占用保留候选，不能关闭用户文件强行覆盖。
实看受影响板卡、导航、文本和公式缓存，明确日期/可信度/缺口/研究非交易状态；跨设备查看不依赖本机绝对runtime路径。
完成测试分类、真实原件复算、DB cold replay、样本gaps、技术债、产品成熟度和下一阶段合理性审查。

## Acceptance Criteria

1. 原三公司冻结语义回归通过；新增同画像公司不新增symbol if/else或复制整条pipeline。
2. 错日期、未来输入、事实/假设不一致、规则/模型变化、坏descriptor隔离有测试；实际模型输入和登记假设可一一追溯。
3. 20家真实分层入组账、至少6家可读深研档案；不支持/缺失/拒绝不是假READY。
4. 至少3家、覆盖至少2种现有适用模型，有真实核验事实和有依据假设支持的有界Bear/Base/Bull、Confidence、Sensitivity和Reverse Valuation（无有界解必须解释）。占位、未核口径和纯fixture不计。
5. 至少2家公司形成实质DividendSustainability评估及证据，可为LOW；当前/正常化、普通/特别、事实/政策/预测分开。不能为了数量把UNKNOWN改为已知。
6. 至少3家有对应当前有效交易会话的已验证Quote与事件扫描，PriceBridge正向验证；没有当前价时保留估值，未通过当前数据验收就不声称全目标完成。使用最新已结束有效会话，不等待不必要的未来收盘。
7. 至少2家公司有两个信息可用边界清楚的时点replay，含新披露/更正/迟到反例；不能从抓取日推断历史known-at。
8. 隔离PostgreSQL保存/加载/完整输入冷启动replay通过；清楚区分真实数据replay与CI synthetic fixture。
9. 原Excel消费同一Application输出，有候选/发布/源Hash/保护/WPS验证收据；只生成JSON不算产品完成。
10. 不发BUY/ADD/仓位、不连生产数据库、不改PTA或生产计划任务、不降低证据/模型标准。交付最终事实状态矩阵与用户复核事项，保留真实缺口。

以上是数量和质量双门；不要求任何公司当日价格便宜，不要求三原案例解除所有研究限制。
LOW Confidence的有界研究可以展示，但不得直接升为价格吸引或个人买入复核；它不替代第4项关于事实/假设完整性的要求。

## Files Likely Affected

- `research_e2e_replay.py`、`research_application.py`、`research_batch.py`、`fixed_sample_manifest.py`及配置/input descriptor。
- 最小Facts/Assumptions输入包与artifact codec/repository；相关Profile/model输入绑定、Gate顺序。
- BusinessQuality/CapitalAllocation最小证据化研究合同和Distribution映射，按真实复用需要新增，不先建空类目录。
- Application read model、`workbook_simple_overview.py` / 对应publisher adapter，相关tests/fixtures/CI。
- 样本/研究证据登记、验收收据、execution-status；真实证据与个人数据不进公开Git。
- 不确定实际模块名时先查仓库，不凭此列表强制新建文件。

## Forbidden Changes

禁止全市场正式screen、Web、BUY/ADD/REDUCE/EXIT决策引擎、仓位算法、新银行/保险/NAV模型、复杂ShareholderYield、扩到50家、券商接入/订单。
禁止生产PostgreSQL migration、SSH部署、改计划任务、启动新常驻服务、改PTA。
禁止改冻结果凑通过、删除旧研究证据、把原Excel整体替换为新模板、覆盖用户人工区、公开密钥/生产数据。
允许在当前工作包中修复已确认的共享输入完整性问题，禁止无关大重构。旧专用解析可保留，但不得用于复制下一家公司流程。

## 执行与停止条件

持续推进M1所有可独立完成的工作包，不在adapter或unit tests完成时结束。每批有研究/产品增量与审查。
明确分别报告Engineering、Research、Valuation、Dividend、Current Data、Price Assessment、Publication；外部等待标PENDING_EXTERNAL_DATA。M1 范围内机器可验证结论用 DONE/PARTIAL；G3 与事件材料性等后续决策复核记录为 deferred_human_review，不阻塞当前研究工作台，也不污染无关工程状态。
遇到外部源不可用、用户文件占用或自然时间不足时，完成其余独立工作，保存证据与重开条件；不忙等、不伪造、不自动扩范围。真实验收未满足只能PARTIAL，不能标Goal achieved。
遇到真实不可恢复数据风险/生产权限需求，停止相关高风险动作并说明所需授权，继续其他安全工作。
M1 机器验收完成后更新execution-status，客观评估成熟度/剩余限制，停止M1。不要自动开始M2，也不要宣称初步真实投资就绪；该称号须通过LONG-TERM-GOAL的M6。
