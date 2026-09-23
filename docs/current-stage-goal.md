# 当前执行目标：M2 多通道机会发现

更新：2026-09-23。`POST-M1-STABILIZATION` 已完成并冻结；当前唯一活动阶段为
`M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`。执行输入为
[m2-current-progress-review-20260923.md](m2-current-progress-review-20260923.md)。

## M2 Goal / 用户可见成果

系统首次主动回答“整个 A 股现在应该看谁”：以交易所 Universe 为分母，建立
Quality、Dividend/Cash Return、Value、Cyclical 四个证据通道，把候选、进入原因、
缺失数据、支持画像和证据日期写入 Excel。候选只进入深研队列，不生成 BUY、仓位或订单。

## M2 边界

- 不做全市场 DCF；禁止银行/保险被误套现有非金融模型，缺失不得默认为 0。
- 旧 `PE<=25 / PB<=3 / 市值>=50亿` 仅保留为 `LEGACY_VALUE_SCREEN` shadow，不作候选排序。
- 每家公司至少记录 `channel / reasons / evidence_date / data_status / profile_status`。
- 最终必须完成一次真实 run-once、可重复 PIT 重放，以及 Excel 候选板卡。
- 未完成真实数据验收时只标 `PARTIAL`，不宣布 M2 完成。

## M2 Acceptance

不能因为创建了 Channel class 或完成一次 JSON 运行就通过。M2 必须依次满足：

1. 全市场 Universe 分母完整。
2. Quality、Dividend/Cash Return、Value、Cyclical 四个通道真实运行。
3. 缺失数据不会默认为 0，必须在指标和原因中显式保留缺失。
4. 银行、保险、券商等不支持画像不进入通用通道，进入 `UNSUPPORTED` 隔离。
5. 每个候选都有进入通道、指标、证据日期、数据状态和画像状态。
6. 无候选是合法快照，不得为凑候选降低门禁。
7. 至少从“系统主动发现”的公司里形成 3 份实质研究或否决报告。
8. 同一 `run_id + rule_version + raw inputs` 可以重放，并核对候选签名。
9. Legacy PE/PB 仅作 shadow 对比，不参与新候选排序。
10. 用户能在 Excel 中直接看到候选、进入原因、缺失和不支持项。

第 1-6、8-10 项已由 2026-09-23 真实全市场 run-once 形成证据；第 7 项尚未完成，
因此当前 M2 状态为 `PARTIAL`。下一步不得复制 symbol 专用流水线，只做有界、
可归档的三份新候选研究/否决报告。

## 当前保护

- M1 冻结包、冻结验收 Hash、生产 PostgreSQL、生产调度器、服务器 PTA/Web App 和原 WPS 人工区均不修改。
- 所有输出保持 `action=no_order`；M2 是机会发现，不是决策或交易准入。

跨阶段规划和真实基线见 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md)。本文件是唯一当前执行范围，不与长期文件建立两套任务队列。

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
