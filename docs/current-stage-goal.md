# 当前总目标：M2-M7 初步真实投资辅助系统

## CURRENT AUTHORIZATION：STAGE-EXECUTION-CORRECTION-CONTINUATION（2026-09-30）

本阶段承接唯一长期总 Goal `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`，优先把已有研究推进到可复核估值和决策审查，不以继续增加未知项或研究档案为进度。完成口径是：分类现存问题、关闭真实 A 类 blocker、将可容忍不确定性纳入情景、对证据不足路径执行 `EVIDENCE_STOP`，并只在模型有效性与报价日事件覆盖成立时形成有效 `PriceBridge` / `Decision Review`。本阶段不代表总 Goal、产品或用户验收完成。

用户最新阶段指令覆盖此前“持续公共研究工作台”的工作优先级：暂停 TSA/PKI 扩张、历史 PIT 补证和重复扫描；不新增公司、框架、版本族或工作簿，不重开 600519；baseline v13 和原始收据保持 immutable。R2、R3、R5、R6 仅阻断各自 DAG 节点。M4 不读取私人组合，M6 维持未启动，永久 `action=no_order`，由用户作最终投资决定。

本阶段现有基线与执行状态：三家公司 A/B/C/D 分类为 3/3。对现存官方材料完成有界复核后，研究估值层的 A blocker 为 `0 / 0 / 0`；按 `000333 / 600887 / 601088` 顺序，分类数分别为美的 `A0/B6/C0/D4`、伊利 `A0/B5/C2/D1`、神华 `A0/B3/C3/D1`。另将伊利 2026-09-29 报价日短融结果单独列为 `EVIDENCE_STOP`，不混入其研究估值分类。美的 `mature_manufacturing` profile 显式授权共享 residual-income 替代模型，FCFF 默认和交易模块不变；但 2026-06-30 普通股分母不能由库存股账面金额、单一回购批次或期间加权 EPS 得到可信区间，当前 case disposition 为 `INSUFFICIENT_PUBLIC_EVIDENCE`，停止重复审查同一披露。后日 9 月 29 日 A/H 分母不回填 6 月 30 日。美的另外三项 `EVIDENCE_STOP` 仅限定于 FCFF 的金融业务拆分、内部抵销和项目级 CapEx。伊利的后续共享研究运行绑定了 case、注册回执、冻结 v13 snapshot、来源复核和共享模型结果，issuer identity 为 `VERIFIED`；低置信度 `CONDITIONAL_VALUATION_READY`（Bear/Base/Bull CNY 8.05/11.02/13.13；敏感区间 CNY 7.10-15.03）。18 格敏感性以共享函数复算 18/18 匹配。该结果不改写 v13：baseline 仍 `BASELINE_PARTIAL / VALUATION_NOT_READY`，且 `STRICT_PIT=NOT_PROVEN`。伊利 SCP010/011 到期结果在已保留的 CNINFO 与上交所索引中仍不可核实，标记为报价日范围内的 `EVIDENCE_STOP`；不得推定兑付、续作或违约，故 `ModelValidity` 未建立、没有 `PriceBridge`，`Decision Review=NOT_ASSESSABLE`。神华并购报告证明近期标的盈利贡献非零，但无法桥接到收购后当前范围的跨周期、可归属归母盈利；当前研究 case disposition 为 `INSUFFICIENT_PUBLIC_EVIDENCE`，停止重复检查同一组报告和周期序列。上述 stop 均只描述当前已审、已哈希绑定的证据集；只有出现新的、能填补明示缺口的正式证据才重开，不声称全互联网不存在其他披露。详见本文件下方状态和当前纠偏研究记录。

```text
CURRENT_STAGE = STAGE-EXECUTION-CORRECTION-CONTINUATION
STAGE_STATUS = ACTIVE
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
ACTIVE_PROSPECTIVE_CASES = 000333, 600887, 601088
BASELINE_COMPLETE = 0/3 / snapshot-v13 is frozen, all cards remain BASELINE_PARTIAL
DESCRIPTIVE_RESEARCH_CARD_FIELDS = 3/3 / R1_REVIEWED / NOT_A_FORMAL_BASELINE_PASS
STRICT_PIT = NOT_PROVEN / registration and build times unattested
LATEST_VERIFIED_SESSION = 2026-09-29 / all three matched-close quotes
BLOCKER_CLASSIFICATION = 3/3 / 000333=A0/B6/C0/D4; 600887=A0/B5/C2/D1; 601088=A0/B3/C3/D1 / retained public evidence set
RESEARCH_A_BLOCKERS = 0/3 / remaining case stops are bounded INSUFFICIENT_PUBLIC_EVIDENCE
YILI_2026_09_29_CNINFO_CANDIDATES = 10/10 dispositioned / A0/B2/C7/D1; bounded CNINFO only, no watermark advance; quote-day financing outcome is evidence-stopped
YILI_2026_09_30_OFFICIAL_SSE_INDEX = first 3/151 pages (30 rows) / 2026-06-17..2026-09-29 / SCP010-011 outcome absent from retained pages only / no default inference
YILI_2026_09_30_CNINFO_SNAPSHOT = 0 rows / exact issuer+date query at 01:00 +08 / local clock only / not full-day or cross-channel coverage
YILI_POSTCLOSE_EVENT_SUPPLEMENT = 4 CNINFO originals hash-verified / 3 event groups / B2/C1; not a complete event scan
YILI_QUOTE_DAY_REVIEW = 2026-09-29 close CNY 27.24 verified / SCP010-011 CNY 20bn outcome EVIDENCE_STOP in bounded official-source set / ModelValidity not established
MIDEA_SHARE_DENOMINATOR = VERIFIED_2026-09-29 / 7,445,382,896 outstanding A/H shares excluding treasury / post-date disclosure; no baseline backdating
MIDEA_MODEL_DISPOSITION = FCFF_NOT_APPLICABLE / explicit shared residual-income alternative authorized / no valuation run
MIDEA_DENOMINATOR_DISPOSITION = D1 / INSUFFICIENT_PUBLIC_EVIDENCE / no dated all-treasury-share count; no 2026-06-30 per-share valuation
MIDEA_APPLICABILITY_V4 = runtime/company-research/midea-valuation-applicability-20260930-v3/evidence.json / SHA256 aebcaf46591cc6814e2e40e117665edb8d58fe3fd9ff6423db949a3a5d750973
SHENHUA_ACQUISITION_REPORT = CNINFO 1224979750 / SHA-256 bound / 12 target-company audited simulated statements for 2023, 2024 and 2025-01..07 present / no current-perimeter attributable-earnings bridge
SHENHUA_SCENARIO_ENVELOPE = HISTORICAL_DRIVER_ANCHORS_PREPARED / NOT_JOINT_SCENARIOS / NOT_PROFIT_FORECAST
SHENHUA_SHARED_MODEL_DIAGNOSTIC = NOT_READY / 6_MISSING_INPUT_FIELDS / BEAR_BASE_BULL_VALUES_NULL / current disposition INSUFFICIENT_PUBLIC_EVIDENCE / D1
ISSUER_IDENTITY_DECLARATION_GATE = FAIL_CLOSED_ON_DECLARED_MISMATCH / run-case-typed+payload facts-and-cited-events / source identity authenticity remains upstream and is not independently established here
VALUATION_READY = 0/3
CONDITIONAL_VALUATION_READY = 1/3 / 600887 / low-confidence research-only
YILI_PROSPECTIVE_FOLLOWUP = prospective-600887-20260927-v2 / run prospective-600887-20260927-v2-followup-20260930T031923+0800 / descriptor 545c52ae909e842dc2d4aca55d091dfaa3c087c4a96937525cf0f767b0933b76 / issuer VERIFIED
YILI_FROZEN_BASELINE = snapshot-v13 unchanged / BASELINE_PARTIAL / VALUATION_NOT_READY / STRICT_PIT_NOT_PROVEN
FCFF_NOT_APPLICABLE = 1/3 / 000333 / current consolidated public scope
MIDEA_ALTERNATE_MODEL = PROFILE_AUTHORIZED / D1_INSUFFICIENT_PUBLIC_EVIDENCE / no admitted result
CURRENT_RESEARCH_DISPOSITION = 600887=CONDITIONAL_VALUATION_READY; 000333=INSUFFICIENT_PUBLIC_EVIDENCE; 601088=INSUFFICIENT_PUBLIC_EVIDENCE
FROZEN_BASELINE = all three v13 cards remain BASELINE_PARTIAL / VALUATION_NOT_READY / immutable
600887_PRICE_REVIEW = NOT_ASSESSABLE / quote-day event outcome EVIDENCE_STOP / ModelValidity not established / price_bridge=null
FORMAL_EVENT_WATERMARK_ADVANCE = 0 / 10 Yili candidate dispositions do not establish cross-channel completeness
CANONICAL_UPDATED = NO / approved artifact-tool unavailable; quote pointer remains 2026-09-28
CANONICAL_PUBLISHER_CONCURRENT_WRITE_GUARD = WINDOWS_CREATEFILE_WRITE_DENY + REPLACEFILE_BACKUP_COMPARE_AND_ROLLBACK / 36 focused tests passed / no workbook write
LATEST_CORE_RESEARCH_GATES = 1167_PASSED / 23_SKIPPED / 3_WARNINGS / CI offline-core list (139 files, UTF-8)
LATEST_STAGE_FOCUSED_TESTS = 66_PASSED / explicit alternate-model routing, Midea applicability, issuer identity, architecture line-budget regression
YILI_SENSITIVITY_GRID = 18/18 recomputed by shared model function / zero mismatches
SAME_PACKET_A_BLOCKER_REDUCTION_REMAINING = NO / current case research A blockers are closed or converted to scoped EVIDENCE_STOP; reopen only on new primary evidence meeting each stated trigger
M4_R2 = PARKED_NONBLOCKING
M6_R3 = PARKED / NOT_STARTED
M7_R5 = NOT_PASSED
action = no_order
```

详情见 [伊利 prospective case 后续估值运行](docs/current/600887-prospective-case-followup-20260930.json)、[伊利共享估值结果](docs/current/600887-shared-valuation-result-20260929.json)、[伊利估值就绪复核](docs/current/600887-valuation-readiness-review-20260929.json) 与 [执行纠偏研究记录](docs/current/track-b-execution-correction-20260929.md)。任何研究状态变化须给出旧状态、新状态、触发、证据和规则；价格只影响价格位置/吸引力，不改企业质量、Bear/Base/Bull 或股息可持续性。所有结论都保持 `action=no_order`，人工作最终投资决定。

## 2026-09-29 收盘后公共证据更新

9 月 29 日的深交所/上交所交易日历与腾讯、新浪原始报价已通过现有报价会话校验，三家公司均为 `matched_close`：000333 CNY 81.66、600887 CNY 27.24、601088 CNY 47.30。共享原始包为 `runtime/quote-sessions/20260929T080056442563Z/bundle.json`，SHA-256 `c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395`；对绑定包与 v13 prospective snapshot 的只读产品校验返回 `VERIFIED_IN_MEMORY_ONLY`，三个登记股票均进入同一产品模型，`workbook_modified=false`。采集/扫描的本机进程时钟未经独立认证，因此这不改变 `STRICT_PIT=NOT_PROVEN`。

收盘后 CNINFO 有界查询在约 16:02–16:03 +08 返回：000333 已知公告 `1225582141` 一条、600887 已知公告 `1225584526` 一条、601088 零条；没有发现新的公告 ID。它们只是查询时点快照，不能证明全日完整、多渠道完整或正式连续水位；美的正式水位仍 `INCOMPLETE`，伊利和神华正式覆盖仍至 9 月 27 日，正式水位未推进。伊利 `1225584526` 仅有公告日期，保守 `available_at=2026-09-30`，不用于 9 月 29 日结论。

伊利仍为低置信度 `CONDITIONAL_VALUATION_READY`，研究情景为 Bear/Base/Bull CNY 8.05/11.02/13.13，完整敏感区间 CNY 7.10–15.03。9 月 29 日收盘虽已验证，但没有覆盖至该报价日且完成候选处置的来源完整事件审阅，因此没有生成有效 `ModelValidity`、`PriceBridge` 或价格吸引力结论；`Decision Review=NOT_ASSESSABLE`。情景与现价的算术差异不能被表述成当前 `WAIT`、买入/卖出建议。

唯一工作簿的实体哈希与现有指针仍为 `849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb`，指针报价日仍为 9 月 28 日。本轮没有修改正式 watermark、trial pointer 或 Excel；获准的 `@oai/artifact-tool` 不在当前工作区依赖中，不用其他表格库替代，也不创建新 Excel。9 月 29 日行情尚未展示在 Excel。

## 2026-09-29 18:00 +08 执行纠偏更新

伊利 CNINFO 单发行人补查覆盖 2026-06-30 至 2026-08-26：10 条、单页完整，`index.json` SHA-256 `4f2d018f82e0b9c23b1963b099264f847278dd407dc9622f388bf818b88ed81e`，查询回执 SHA-256 `ca54e80b473a2fcb7dca88c5888c5485957e3c46fe08af8c98982bd9d2422332`。这是有限日期窗的 CNINFO 检索快照，不是跨渠道覆盖、正式水位推进或完整事件处置；融资券发行/兑付、担保及境外投资等候选不能以“没有新编号”替代审阅。9 月 28-29 日快照另含公告 `1225584526`，日期级发布时间按规则保守视为 2026-09-30 可用，不能用于 9 月 29 日结论。该公告确认 9 月 24 日偿付 CNY 25bn 短融；7 月发行公告显示另有 CNY 20bn 短融于 9 月 29 日到期，但当日偿付/续作及偿付后现金余额没有留存证据。因此伊利估值情景不变，报价日 `ModelValidity` 仍未成立。

神华正式重组报告 CNINFO `1224979750` 原件 SHA-256 为 `533bc24a80aeb1fbf2357218c5c19825cb0ab23176eb7d25d8ecd2d1f1256703`。报告第 20 页披露标的 2024 年扣非归母净利润 CNY 9.428bn（剔除长期资产减值影响后 CNY 10.570bn）；第 555 页备考扣非归母净利润显示 2024 年交易增量 CNY 7.889bn、2025 年 1-7 月增量 CNY 3.382bn。该材料推翻旧的“没有具名交易报告”证据停止理由，但单个完整年度加七个月不能证明并购后当前范围跨煤价周期的中周期盈利；神华 A blocker 仍为 1，不将短期备考数或简单年化冒充周期情景。

```text
YILI_2026_09_29_CLOSE = CNY 27.24 / DUAL_SOURCE_VERIFIED
YILI_CNINFO_GAPFILL_2026_06_30_TO_08_26 = 10 ROWS / COMPLETE_SINGLE_CHANNEL_WINDOW_ONLY
YILI_MODEL_VALIDITY_THROUGH_QUOTE = NOT_ESTABLISHED
SHENHUA_ACQUISITION_REPORT = FOUND / RECENT_PRO_FORMA_INCREMENT_VERIFIED
SHENHUA_MID_CYCLE_A_BLOCKER = OPEN
MIDEA_SHARE_DENOMINATOR_A_BLOCKER = OPEN
PRICE_BRIDGE_REVIEW_BLOCKERS = PROPAGATED / risk-monitor and follow-up flags are retained
OFFLINE_CORE_RESEARCH_GATES = PASS / 1148 passed, 23 skipped, 2 warnings
CANONICAL_EXCEL_UPDATED = NO
NEW_EXCEL = 0
STRICT_PIT = NOT_PROVEN
action = no_order
```

## 2026-09-29 22:09 +08 PriceBridge blocker 传递修复

代码审查发现：`ModelValidity.status=VALID` 可以同时保留 `MATERIAL_RISK_MONITOR` 或 `REQUIRES_DECOMPOSITION` 复核项；原 `bridge_with_quote` 在 READY、PENDING 和部分 INVALID 分支未统一传递这些 blocker，可能使价格桥隐藏仍待跟进的风险。现已统一合并调用方与 ModelValidity blockers，并在 READY 路径增加实际事件材料性回归。此修复只保留审查提示，不把 risk-monitor 自动改成模型失效；不会使未覆盖事件的伊利报价日门通过。

验证：定向 `test_price_bridge.py` 与 `test_event_materiality.py` 为 `28 passed`；GitHub `offline-core` 同清单本地复跑为 `1148 passed, 23 skipped, 2 warnings`，采用隔离 pytest 临时目录和 UTF-8 环境。全仓库测试未完成：初次运行在约 89% 连续无进度后中断；fail-fast 重跑遇到用户级 `pytest-of-Ming` 临时目录 `PermissionError`。因此不将全仓库结果宣称为通过。此次没有改变三家公司分类、估值或当前 Decision Review，没有改 Excel、watermark、PIT、交易状态或总 Goal 状态。

## 历史阶段快照：STAGE-EXECUTION-CORRECTION（2026-09-29，模型绑定前）

此处记录执行纠偏阶段当时的范围和审计快照，不再授权当前工作。审计入口基线为 `main@24ec94bff754b4139169cf79f9bbc1f356c0c71b`，当时与 GitHub `origin/main` 匹配；本地随后集成 issuer identity fail-closed gate（`24f4de3`），并修复通用架构边界及冻结 replay 断言。三家公司 A/B/C/D 分类和伊利条件估值已完成；对抗复核对报价日有效性追加的纠正，以本文件上方当前授权和对应复核文件为准。

本次估值输入账面基准日为 2026-06-30、报价日为 2026-09-28，日期差已披露；伊利股息可持续性仍 `DATA_INCOMPLETE / UNKNOWN`，严格 PIT 仍 `NOT_PROVEN`。Canonical Excel 因批准的 `@oai/artifact-tool` 依赖缺失未能原位更新，工作簿仍显示旧状态；没有创建替代 Excel。Issuer Identity Gate 已集成到 `main`，CNINFO/HKEX issuer registry 随包作为数据资源发布；身份门、架构边界与 replay 聚焦测试 `34 passed`。CI 同款 139 个离线测试文件本地结果为 `1142 passed, 23 skipped`，2 条 openpyxl 弃用警告；ACTUAL 私有回放素材未随仓库发布，按默认条件跳过。GitHub Core Research Gates run `36524898780` 对代码提交 `8bf11cd` 的 `offline-core` 与 `postgres-integration` 均成功。完整仓库测试未运行。

截至 2026-09-29 08:54 +08，交易所尚未开市，最近已验证收盘仍为 2026-09-28。前向 `prospective-timestamp-chain-v2` 吊销证据校验已完成本地工程验证：绑定 CMS signer 与唯一配置 CA 路径、核验路径证书的完整 CRL 及 genTime 覆盖、拒绝未知 critical CRL entry extension；TSA 与 CRL 网络请求固定到已解析公网 IP、忽略代理环境并拒绝重定向。72 项相关测试与 CI `offline-core` 集合 1112 项通过、23 项跳过。完整仓库测试曾运行至 87% 后停滞并中断，不计为通过。CRL 哈希目前写入收到时间戳后生成的 JSON 回执，回执与 CRL 清单本身未再由 RFC 3161 签名；因此可发现单独文件漂移，但不能证明回执与 CRL 未被同时改写。验证范围为单 signer 测试令牌及直接、完整 CRL，不等于通用 PKI 兼容或严格 PIT 证据。该改动没有请求真实 TSA 时间戳、生成运行时收据或更改历史收据；`STRICT_PIT=NOT_PROVEN`、M3 partial、三家公司估值未就绪、M6 未启动、M7 未验收及 `action=no_order` 均保持不变。

截至 2026-09-29 07:03 +08，交易所尚未开市，最近已验证收盘仍为 2026-09-28；伊利 2026-09-29 到期的 200 亿元短融付款/续作结果未验证。Midea PIT 反审确认 GitHub PushEvent `22282999048`（报告时间 `2026-09-27T00:24:06Z`）最多支持提交中精确 v2 计划字节当时已公开，不能给 runtime receipt、事实采集或决策生成定时。回执自报 `receipt_created_at=2026-09-27T00:24:16.082830Z`，比计划 `declared_registered_at=00:45Z` 早约 20 分 44 秒，且 `declared_time_independently_proven=false`；校验器没有要求回执时钟晚于声明注册时钟。该先后关系语义未解决，不重解释、不改时间。v13 自报构建时间 `2026-09-27T09:22:55Z`（17:22 +08）晚于 cutoff；其后 RFC 3161 令牌分别绑定计划字节和工作台发布回执字节，均晚于原 cutoff，不能追认 v13。snapshot v13 仍 `strict_pit_admissible=false`，本轮不改变预登记起点/基线或严格 PIT 状态。原 GitHub API 响应留在本机忽略目录 `runtime/prospective-timing-audit-20260929/`，Hash `0690a327...13bcc867`；只作有范围限制的补充时间线索。

```text
CURRENT_STAGE = STAGE-EXECUTION-CORRECTION
M2 = DONE / CHECKPOINT_A_HUMAN_PASS
M3 = PARTIAL / STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN / R6
M4 = NONPERSONALIZED_ENGINEERING_DONE / PERSONALIZED_PARKED_WAITING_R2_NONBLOCKING
M5_600519 = NEED_MORE_EVIDENCE / STILL_NOT_READY / NO_NEW_VALUATION
M5_EVENT_ASOF_GUARD = IMPLEMENTED / 123_RELATED_TESTS_PASS
M5_EVENT_ASOF_SUCCESSOR = runtime/prospective-public-event-20260929/registered-public-event-projection-v6.json / 169ee7f1e59ecd0ef0df9d96c5560e6a7b05e80ff2e712c127ffb5d2b23772a9
M5_EVENT_ASOF_PUBLICATION = PUBLISHED / BOUNDED_SINGLE_DAY_SNAPSHOT / FORMAL_WATERMARK_NOT_ADVANCED / FINAL_USER_ACCEPTANCE_NOT_PASSED
M6 = PREFLIGHT_ONLY / OPERATIONAL_NOT_STARTED / VERIFIED_REAL_SESSIONS_0
M6_REAL_RESTORE_ACCEPTANCE = NOT_PASSED
M7 = DISPLAY_ENGINEERING_AVAILABLE / WPS_AND_ALL_PRODUCT_PAGE_READABILITY_PASS / FINAL_USER_ACCEPTANCE_NOT_PASSED
CURRENT_AUDIT_BASE = 24ec94bff754b4139169cf79f9bbc1f356c0c71b / ORIGIN_MAIN_MATCH_AT_ENTRY
LAST_VERIFIED_CORE_RESEARCH_GATES = 36491639226 / SUCCESS / OFFLINE_CORE_PASS / POSTGRES_INTEGRATION_PASS / FOR_5635477
LATEST_CORE_TESTS = LOCAL_CI_OFFLINE_CORE_1142_PASSED_23_SKIPPED / IDENTITY_REPLAY_FOCUS_34_PASSED / 2_OPENPYXL_DEPRECATION_WARNINGS
FULL_REPOSITORY_TESTS = NOT_RUN_THIS_TURN / PRIVATE_ACTUAL_FIXTURE_TESTS_SKIPPED_BY_DEFAULT
PROSPECTIVE_REGISTRATION = v2 / receipt 8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5 / process_clock_only_unattested
PROSPECTIVE_BASELINE = snapshot-v13 / ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5 / 3_BASELINE_PARTIAL
BASELINE_COMPLETE = 0/3 / EXISTING_V13_FROZEN_AND_UNCHANGED
BLOCKER_CLASSIFICATION = 3/3 / A_B_C_D
VALUATION_READY = 0/3
CONDITIONAL_VALUATION_READY = 1/3 / 600887 / LOW_CONFIDENCE_RESEARCH_ONLY
VALUATION = 000333_NOT_READY_A1; 600887_CONDITIONAL_READY_A0; 601088_NOT_READY_A1
ISSUER_IDENTITY_GATE = INTEGRATED_LOCAL_MAIN_24f4de3 / FAIL_CLOSED_AND_ARCHITECTURE_REPLAY_TESTS_PASS
FORWARD_TSA_PLAN = VERIFIED / 2006de88f0bc226d7191f5ee8fa5727a37b48cbb7373b252d9abf2c6fa981e18 / PLAN_BYTES_ONLY / STRICT_PIT_FALSE
PROSPECTIVE_TIMESTAMP_CHAIN_V2 = IMPLEMENTED_AND_LOCALLY_VERIFIED / NO_REAL_TSA_REQUEST_OR_RUNTIME_RECEIPT / STRICT_PIT_FALSE
CANONICAL_PUBLIC_WORKBENCH_TSA = VERIFIED / receipt 9fe94fd0b8219e7729264bbb7789ffd3290c634114024d900274e51ed7670da3 / genTime=2026-09-28T13:17:06Z / PUBLICATION_RECEIPT_BYTES_ONLY / STRICT_PIT_FALSE
CANONICAL_WORKBOOK_SHA256 = 849f3999129e57f8068f6cc9ed1bc301b0da158697492e9a3258aeb4865c43eb
CANONICAL_UPDATED_THIS_TURN = false / STATE_CHANGED_BUT_APPROVED_ARTIFACT_TOOL_MISSING
ARTIFACT_REGISTRY = V2_REGENERATED_FROM_CURRENT_POINTER / PERSONAL_PATH_REDACTED
M5_EVENT_PROJECTION = runtime/prospective-public-event-20260929/registered-public-event-projection-v6.json / 169ee7f1e59ecd0ef0df9d96c5560e6a7b05e80ff2e712c127ffb5d2b23772a9
M7_WPS_READONLY = PASS / runtime/publication-receipts/wps-m7-product-v6-20260928T192230Z.json / FINAL_USER_ACCEPTANCE_NOT_PASSED
M7_ALL_PRODUCT_PAGE_READABILITY = PASS / runtime/publication-receipts/readability-m7-product-v6-20260928T192230Z.json
WPS_VERIFICATION_RECEIPTS = LOCAL_RUNTIME_ONLY / EXCLUDED_FROM_PUBLIC_GIT / NOT_INDEPENDENTLY_REPRODUCIBLE_FROM_PUBLIC_CLONE
QUOTE_AS_OF = 2026-09-28 / COMPLETE / 000333_600887_601088
QUOTE_BUNDLE_SHA256 = 08d8dce83ba552ec77c4f6db0f95c7ec348b2b27b76dbc00dfbed86ec35088ea / 82.00; 27.03; 48.39
PUBLIC_EVENT_PROJECTION = 8_BOUNDED_EVENTS / 000333_600887_601088 / FUTURE_AVAILABLE_NOTICE_EXCLUDED_FROM_CANONICAL
CANONICAL_EVENT_VIEW = V6_BOUNDED_SNAPSHOT_PUBLISHED / FORMAL_WATERMARK_UNCHANGED / YILI_NOTICE_EXCLUDED_UNTIL_2026-09-30
PUBLIC_EVENT_OBSERVATION = 2026-09-28 21:36:51..21:38:40 +08 / CNINFO_EXACT_ISSUER_DATE_SNAPSHOTS / KNOWN_MIDEA_NOTICE_ONLY; YILI_AND_SHENHUA_ZERO / PROCESS_CLOCK_UNATTESTED / NO_NEW_EVENT
PUBLIC_EVENT_LATE_SNAPSHOTS = 000333 695082f4c4db4d981fd696dae71a6d97d5b1bf5a8786b5ae3f4bd48123273a45; 600887 d150108dbd2b7a71708c96a1a5555898746ded37337fc64e3728dd0ea97639a6; 601088 37b682cfd0e6a200fb404d0fcc46686fe54f90ad8888c829aae98ac20457d6cd
PUBLIC_EVENT_WATERMARKS = config/prospective-public-event-watermarks-v9.json / FORMAL_THROUGH_2026-09-27 / 3_BOUNDED_SNAPSHOTS_2026-09-28_TO_29 / NO_FORMAL_ADVANCE
YILI_EVENT_1225584526 = VERIFIED_REDEMPTION_2026-09-24 / 25BN_PRINCIPAL / AVAILABLE_AT_2026-09-30 / MATERIAL_RISK_MONITOR_CANDIDATE / NOT_APPLIED
MIDEA_CASH_FACTS = V3_CORRECTED_2025_CASH_EQUIVALENTS_68.509BN / MONETARY_FUNDS_85.247BN / 2026H1_CASH_EQUIVALENTS_74.614BN / NET_DEBT_NULL
MIDEA_H1_SEGMENTS = EXTERNAL_REVENUE_RECONCILED_TO_TOTAL_OPERATING_REVENUE / FINANCIAL_SERVICES_NOT_SEPARATELY_REPORTED / FCFF_NOT_READY
SHENHUA_INTERIM_DIVIDEND = CNY_0.98_GROSS_PER_SHARE / ESTIMATED_CNY_21.256BN / APPROVED / PAYMENT_UNVERIFIED / NOT_SUSTAINABILITY_PROOF
LATEST_GOAL_TESTS = TSA_AND_PROSPECTIVE_RESEARCH / 72_PASSED; CI_OFFLINE_CORE / 1112_PASSED_23_SKIPPED
REGISTRATION_RECEIPT_VALIDATION = FUTURE_TIME_AND_FALSE_ATTESTATION_CLAIMS_FAIL_CLOSED / PROCESS_CLOCK_ONLY_UNATTESTED
REGISTRATION_PLAN_EXTERNAL_TIME = GITHUB_PUSHEVENT_22282999048 / 2026-09-27T00:24:06Z / PLAN_PUBLICATION_ONLY / RECEIPT_UNATTESTED / STRICT_PIT_FALSE
CANONICAL_WORKBOOK_POINTER = PHYSICAL_WORKBOOK_HASH_MATCHES_849f3999 / V6_WPS_AND_READABILITY_VERIFIED / PUBLICATION_COMMIT_RECORDED_IN_GIT_HISTORY
SAFE_R1_REMAINING = MIDEA_FINANCIAL_BUSINESS_SCOPE_SHARE_DENOMINATOR_CAPEX_EQUITY_BRIDGE; YILI_DIVIDEND_CLASSIFICATION_NORMALIZED_DISTRIBUTABLE_CASH_AND_POST_REDEMPTION_LIQUIDITY; SHENHUA_TARGET_LEVEL_ACQUISITION_EARNINGS_CASH_RESIDUAL_AND_MAINTENANCE_GROWTH_CAPEX; FUTURE_STRICT_T0_T1_T2_EVIDENCE
YILI_DISTRIBUTION_PACKAGE = HISTORICAL_CLASSIFICATION_UNKNOWN / FORWARD_AND_NORMALIZED_USE_BLOCKED
YILI_PARENT_CASH_BRIDGE = CY2022_2025_SOURCE_VERIFIED / CY2025_PARTIAL_PROXY_COVERAGE_1.074X / NOT_NORMALIZED
CHECKPOINT_D = NOT_PASSED
R0_AUDIT_SNAPSHOT = HISTORICAL / R0-A_NOT_PROVEN / R0-B_PARTIAL
R0_OPEN_NODES = 2 / NONBLOCKING_TO_PUBLIC_RESEARCH / REQUIRED_ARTIFACTS_UNAVAILABLE
R0-C_RESOURCE_CAPACITY = CLOSED_AS_R3_INFRASTRUCTURE_DECISION
SAFE_R0_REMAINING = 0_AFTER_CURRENT_PRODUCT_FIXES_AND_POINTER_REBUILD
SAFE_R1_REMAINING = OPEN / MIDEA_FINANCIAL_BUSINESS_SCOPE_SHARE_DENOMINATOR_CAPEX_AND_EQUITY_BRIDGE; YILI_DIVIDEND_CLASSIFICATION_NORMALIZED_DISTRIBUTABLE_CASH_AND_POST_REDEMPTION_LIQUIDITY; SHENHUA_PRODUCT_SEGMENT_AND_ACQUISITION_BRIDGES; FUTURE_STRICT_T0_T1_T2_EVIDENCE
EXTERNAL_GATE_HANDOFF = DAG_SCOPED_NOT_TOTAL_GOAL_STOP
M6_OPERATIONAL = NOT_STARTED
M6_PRODUCTION_AUTHORIZATION = NOT_GRANTED
SHADOW_START_ALLOWED = false
M7_FINAL_USER_ACCEPTANCE = NOT_PASSED
INITIAL_ASSISTED_USE = NOT_REACHED
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
action = no_order
```

## 2026-09-28 Verified Quote Display Correction

The canonical workbook previously showed the three registered companies as
having no usable price even though its bound daily quote receipt contained
matched 2026-09-28 closes. The prospective opportunity projection now displays
the symbol-specific matched close and date, labels the quote as verified while
stating that price attractiveness cannot yet be assessed, and retains the
unready valuation state and `action=no_order`.

The same `WORKBOOK_PATH` workbook was updated in place. Its SHA-256 is
`2f72dc76bcf6a74449dec5a336cc41540ae84bb1e7935badb7248a4b8a6c1bcf`; the prior
`0bfc9fae...` bytes are preserved in
`runtime/workbook-backups/canonical-before-m7-product-ux-20260928T085546Z.xlsx`.
WPS read-only verification and all-page readability passed. The three visible
prices are 000333 CNY 82.00, 600887 CNY 27.03 and 601088 CNY 48.39, all as of
2026-09-28 close; none is a valuation or trading signal.

Focused product regressions passed 51 tests. Strict contemporaneous PIT remains
unproven; all three company valuations remain not ready; M4, M6 and M7 user
acceptance gates remain unchanged; `action=no_order`.

本阶段按持续轨道推进公共市场数据、三家预登记研究案例、公共事件、唯一 Canonical Excel 和方法验证。报价与事件只接受公开、可追溯证据；新交易会话按交易所日历判断，不以运行日期代替。每次研究状态变化保留旧状态、新状态、触发、证据和规则。基线中的登记/构建时间仍为 `PROCESS_CLOCK_ONLY_UNATTESTED`，不得称为严格同期 PIT。只在新公共事实、研究状态或证据缺口真实变化时原位更新工作簿；不因重复运行发布相同内容。

2026-09-28 产品 as-of 复核发现，v3 曾在 09-28 观察截止下显示美的公告 `1225582141`，其保守 `available_at` 为 09-29。v4 将其移出活动事件、证据和决策集合；独立复核随后指出，即使标注隔离，把公告细节留在同一本截止日工作簿仍可能造成前视泄漏。追加 successor v5 将完整排除来源绑定在 runtime 审计投影中，而 canonical Excel 六个可见页均不显示公告 ID、事件 ID、标题、路径或来源哈希。123 项相关回归通过；最终工作簿已原位发布，WPS 只读验收与可读性审计通过。strict PIT、三家公司估值和交易状态不变，`action=no_order`。

用户于 2026-09-28 明确收敛本阶段执行重点：唯一用户产品继续是 WPS `WORKBOOK_PATH` 指向的 canonical Excel；围绕 000333、600887、601088 推进真实前瞻研究、strict contemporaneous PIT、事件连续性和财务质量门，不以增加抽象、候选 Excel 或历史 replay 为主要产出。不得新增公司扩大范围；需要的代码变更必须对应真实链路失败或证据/安全风险。无新事实时允许不发布工作簿。根目录历史工作簿仅在逐项迁移验证通过后才能归档，不能因视觉整洁要求破坏哈希、收据或引用。

当前研究主体为 `000333 / 600887 / 601088`，均未达到估值就绪。伊利快照中的 `yili-2026h1-financial-quality` 是无数值/单位/页码的报告级占位项；其六项具名 H1 原子事实已分别准入，不能将该占位项解释为缺少另一条财报指标，也不能据此宣称研究基线完整。详见本轮状态记录及独立审查。

当前阶段继续 Track A-E 的有界公共研究、前瞻 PIT、公共事件和日常工作台。M4 私人组合仅为 `PARKED_WAITING_R2_NONBLOCKING`；它不阻断上述 DAG。R0-A/R0-B 的下方快照保留为上一专项审计结论，不构成本阶段停止条件；若后续具体任务触及它们，按证据与当前 R0/R1 规则单独重开。不得进入 M6 生产/Shadow，不请求 M4 私人输入，不代签 M7，不产生订单。

本轮 R1 补充记录已形成：美的关联方主要母公司应收余额与合并财报的匹配及未调平事项见
`docs/current/track-b-midea-related-party-bridge-review-20260928.md`；神华 2014–2025
经营序列的年度来源、重述、范围断点和可用时间边界见
`docs/current/track-b-shenhua-operating-series-classification-20260928.md`。神华文档经 R1 复核后
更正收购标的为“杭锦能源”，并补上 2016/2018/2020 比较表的物理页码与 SHA；已核实的原始值/重述值版本事实也已追加。剩余神华逐字段重述/分部桥接仍开放。美的母公司层面匹配已完成，逐笔合并抵销和关联银行产品调节在留存公开披露中不可得，已分类为外部证据缺口；以上研究均不构成估值模型输入或 strict PIT 证明。

2026-09-28 连续性勘误复核了各公司 10:00..10:02 +08 的 CNINFO 精确发行人快照：美的只返回已知公告 `1225582141`，伊利和神华为零条；无新事件，故不重建投影、不发布 Excel。神华 2026-03-31..2026-09-27 的留存窗口现可由哈希匹配且分页结束的索引接成无日期缺口 CNINFO 链，旧 gap-fill 文档中的“仍有缺口”结论已由独立勘误更正；这不覆盖发行人 IR/交易所渠道，也不证明检索时钟。美的留存日期窗口 2026-03-31..2026-09-27 连续，但正式初始水位仍 `INCOMPLETE`，不从回溯索引静默晋级。三家公司 09-28 快照时间均为本机进程时间、无独立时间戳；严格 PIT 仍 `NOT_PROVEN`。详情见 `docs/current/track-c-prospective-watermark-continuity-corrigendum-20260928.md`。

神华 FY2023/FY2024 原始值与 FY2025 重述值已经按原件复核；页码勘误、利润算术勾稽及未解决的分部残差记录在 `docs/current/track-b-shenhua-operating-series-corrigendum-20260928.md`。这只收窄 ResearchCase 的证据缺口，不准入正常化利润，不改变估值门或 baseline。

伊利分红研究现已核实 FY2021-FY2025 分红金额和 CFO 覆盖，其中 FY2021-FY2023 实际支付生命周期均有实施公告，FY2021-FY2023 另有年报 CFO 与长寿命资产购建现金支出。FY2022 扣除该购建支出后的有限覆盖约 1.023x；它不是 normalized FCF，亦未证明现金可分配。普通/特别性质分类和正常化可分配现金仍未知；研究卡见 `docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md`，DividendSustainability 仍 `DATA_INCOMPLETE / UNKNOWN`。

截至 2026-09-28 13:30 +08，CNINFO 实施公告 `1225335436` 已核实伊利 FY2025 末期股息 CNY 5,692,824,600.30（每股 CNY 0.90）于 2026-06-05 支付；上一状态摘要中“FY2025 末期支付方案尚待生命周期核实”已过时。该时点的 FY2021/FY2022 现金流缺项随后由官方年报补齐，见下方 13:50 状态更正。来源可用时间按 2026-05-30 00:00 +08 保守处理，抓取时间仍是未独立认证的本机进程时间，不构成 strict PIT 证据。

截至 2026-09-28 13:50 +08，CNINFO 年报和实施公告补齐 FY2021-FY2023 支付生命周期、净利润、CFO 及购建固定/无形/其他长期资产现金支出；FY2021-FY2025 的现金分红/利润与 CFO 覆盖已量化。FY2022 扣除长寿命资产购建现金后的余额仅为分红的 1.023x。普通/特别分类及 normalized distributable cash 仍未建立；伊利分红可持续性仍 `DATA_INCOMPLETE / UNKNOWN`。相关原件 Hash 与计算口径见分红研究卡和执行状态最新增量；没有改变 prospective baseline、strict PIT、估值或交易状态。

神华分部桥接勘误将 FY2025 CNY 8,086m/CNY 4,923m 差额更正为“煤炭分部总收入/成本与产品表之间的残差”，而非外部收入差额；集团分部总收入与成本的汇总算术可调平，产品残差、4.5 Mt 内部煤量差和杭锦并表贡献仍未解释。601088 仍 `CYCLICAL_MODEL_NOT_READY / VALUATION_NOT_READY`。

当前 canonical workbook 指针绑定 WPS 发布回执
`runtime/publication-receipts/canonical-m7-product-publication-20260928T074028Z.json`、
只读验收回执 `runtime/publication-receipts/wps-m7-product-asof-v5-clean-20260928.json`、可读性回执
`runtime/publication-receipts/readability-m7-product-asof-v5-clean-20260928.json` 和文件哈希
`02a5f594c50a402858ddaed5b3520bafd396be1442114add7ae51df011698b47`。前一 v7 检查点在 v6 基础上
追加三家 2026-09-28 约 05:14–05:15 +08:00 的 CNINFO 单日快照；美的重复发现公告
`1225582141`，伊利、神华返回空结果。全天及多渠道覆盖未证明。后续 v8 检查点见下文。

此前 R0 收尾专项的范围和结论归档为历史快照；它不覆盖本段当前授权。Prospective receipt verifier 现会拒绝未来创建时间、声称独立认证的本机时间、非 `receipt_created_at` PIT 锚及任何已观察结果/估值/信号/私人组合标志；对应定向回归通过。它不能证明历史本机时钟真实，故既有收据仍为 `PROCESS_CLOCK_ONLY_UNATTESTED`，strict PIT 仍 `NOT_PROVEN`。研究收据和工作簿仍为证据，不因阶段切换而覆盖或重做。

## 本轮阶段增量（2026-09-27）

Track C 对已有 CNINFO `1225185584`（国家能源集团财务有限公司风险评估报告）完成原件哈希绑定和有界研究，归为 `MATERIAL_RISK_MONITOR`，同时保留“发行人自评称 2025 年末无不良贷款”的证据限制。它是预登记前的历史公开材料，不是新的前瞻观察，不证明损失或独立信用质量，也不改变估值；详细记录见 `docs/current/track-b-shenhua-operations-and-capital-allocation-20260927.md`。

同一 canonical Excel 已更新神华事件卡，并修复发现的审计链接偏移。最终工作簿 SHA-256 为 `01af2106d8e1a656750790b0d1f7ee79fd8264c9f24d5bd1d28899aa90eefee1`；发布回执、WPS 只读验收及证据链接复核记录在 `docs/execution-status.md` 本轮中断审计下。审计行包含本地原件路径、精确 SHA-256 和可点击 CNINFO URL。非产品用户管理页和冻结页通过发布器保全比较。

仍保持 `STRICT_PIT=NOT_PROVEN`、三家公司 `VALUATION_NOT_READY`、`M6_OPERATIONAL=NOT_STARTED`、`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`、`INITIAL_ASSISTED_USE=NOT_REACHED`、`action=no_order`。截至 2026-09-28，神华 CNINFO 精确发行人已留存查询窗口由 watermark v4 形成无日期缺口链；范围不含发行人 IR、交易所渠道、后续更正或检索时点之后公告，且历史公告在预登记前已公开，不能作为 strict PIT 证明。

## 本轮阶段增量（2026-09-28）

随后同一工作簿依据三家已注册公司的公开事件研究状态原位更新。组合投影为
runtime/prospective-public-event-20260927/registered-public-event-projection-v1.json
（SHA-256 ecdce96a4a63a72b191942896b751cbae0da3a4087b9f5ef871aea7b0333f3a0），
共 8 张事件卡：美的 3、伊利 1（证据不足/材料性未定）、神华 4。神华新增财务公司风险监控和限售股解禁事件；后者是已有股份流通状态变化，不是新增发行或卖出信号。Shenhua v1/v2 投影保持不变。发布后 canonical SHA-256 为
f4b7a2721f2947a1e7b65087289c8660b48d6a423e32f22afabadd4edc748970；
WPS 只读验收通过，六张产品页可读、公式无错误、保护页保持不变。
config/current-trial-workbook.json 分别记录 quote-as-of（2026-09-24）与事件水位（2026-09-27），
报价仍为部分覆盖并缺少 600887。2026-09-25..27 为休市/周末，无新完成交易会话，故本轮没有刷新行情。
三家公司估值仍 NOT_READY，严格 PIT 仍 NOT_PROVEN，M6_OPERATIONAL=NOT_STARTED，
M7_FINAL_USER_ACCEPTANCE=NOT_PASSED，INITIAL_ASSISTED_USE=NOT_REACHED，action=no_order。

### 2026-09-28 后续增量

美的 CNINFO 精确发行人单日扫描发现公告 `1225582141`。原件 SHA-256
`94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686`，原文确认
2026-10-13 临时股东会，议程涉及限制性股票回购注销及 2026 中期利润分配方案。
通知未新增注销数量、批准/实施结果或分红金额，故只登记治理/资本配置后续触发；
不改变已准入事实、股份数、股息可持续性或估值。精确扫描与原件审阅边界见
`docs/current/track-c-midea-egm-notice-20260928.md`。

对美的 FY2025 年报及 2026H1 半年报原件另作逐页固定资产、在建工程和折旧核对。
报告列有现金购建、固定资产新增/处置、在建工程转固和项目名称，但未区分维护与扩张
用途，也无项目回报证据；维护 CapEx、增长 CapEx、正常化投入均继续 `UNKNOWN`，
FCFF carve-out 和估值仍 `NOT_READY`。详情与原件 SHA-256 见
`docs/current/track-b-midea-capex-fixed-assets-review-20260928.md`。

`artifacts/current/artifact-registry-v2.json` 已替代 v1 成为当前逻辑导航索引：以本机
`WORKBOOK_PATH` 解析 canonical Excel，仅记录其 SHA-256 与指针核验状态，不写入个人绝对路径；
仓库根目录同名工作簿被标为历史参考快照。v1 字节未改，根目录及 WPS 工作簿均未改写。
生成脚本在 hash 不一致时 fail-closed，连续两次重建得到相同 registry SHA-256
`b833b84b9d646fa34b64ff9f5714eaa83d907e60dd649cb51c36cfa61a0107c4`（已按当前 canonical pointer 重建）。

只读产品审查发现机会页名单滞后、若干审计来源缺可点击 URL、双证据卡只链接首条，以及
公司页混入旧样本。已补测试并修复产品投影与链接组导航；美的三条既有公告 URL 传至审计页，
伊利公告缺少留存官方 URL 时继续 fail-closed 不猜造。新增的美的股东会通知经原件审阅后，
作为单条有界 M5 治理/资本配置监控事件形成 successor 并更新到同一 canonical Excel。
现有机会页和公司页均为三家已注册对象；新卡跳转至审计行 A44，原件 URL、ID、SHA-256
与可用日可见。组合投影为
`runtime/prospective-public-event-20260928/registered-public-event-projection-v2.json`
（SHA-256 `f5938dc5b381230efd686078c923b8b4d0aab3562148f33ccbfa6c4749a12609`），共 9 张卡。
后续同一 canonical Excel 发布了 M4 个性化暂停状态，发布回执为
`runtime/publication-receipts/canonical-m7-product-publication-20260927T204125Z.json`；
最终 canonical SHA-256 `ef0523b9596b3bed682d85898fab20dd68b1ee889181cb7a00744ca4bb1136e8`，
WPS 只读验收回执为 `runtime/publication-receipts/wps-m7-product-parked-20260928.json`。
61 张表得到保全，6 张产品页可见、55 张旧页隐藏；该工程验收不等于 M7 最终用户验收。
美的正式 watermark 仍为 `INCOMPLETE` 且 `public_event_as_of=2026-09-27`；新增的
`public_event_observation_as_of=2026-09-28` 只表示单日精确 CNINFO 观察，不宣称全天、连续、
多渠道覆盖或 strict PIT。行情仍为 2026-09-24 部分覆盖并缺少伊利。估值、M6、M7 最终用户验收
及 `action=no_order` 状态均未改变。

美的公告 `1225582141` 已追加到账本，`source_available_at=2026-09-29T00:00:00+08:00`；
该日单窗口只作为 bounded evidence，000333 连续水位仍 `INCOMPLETE` 且 `coverage_through`
不变。正式记录及 writer-generated time 边界见 `docs/execution-status.md` 当前增量。

本轮全量本地回归 `3160 passed, 30 skipped`；canonical workbook 与 WPS 只读回执 hash
一致，未在这轮水位更新中写入工作簿。v5/v6 水位与清单定向测试 `10 passed`。
实时 GitHub fetch 因连接重置未完成，未对远端 CI 作新声明。

神华 601088 的 CNINFO 窗口水位 append-only successor 为
`config/prospective-public-event-watermarks-v5.json`（继承 v4）。保留的七个索引窗口从
2026-03-31 连续覆盖至 2026-09-27 19:22:35 +08:00；覆盖仅指 CNINFO 精确发行人及已留存日期窗口，不等于全渠道公告完整性。v3 历史记录保留。窗口中 2026-09-04 会议材料 `1225546779` 披露中期分红税前每股 0.98 元、约 212.56 亿元，`1225579981` 记载股东会于 2026-09-23 通过；A 股实施、登记和支付日期尚待公告。`1225565223` 的 8 月运营统计是发行人自报且比较期已重述、含 4 月并入资产，仅作运营监控。办公地址变更 `1225567741` 与会议通知 `1225546775` 不构成需展示的经济事件。四份索引原件及 R1 边界见 `docs/current/track-c-public-event-gapfill-20260927.md`。

配置的本地字节 Hash 已记录：v3 `f7f00ac96efab81c631c543d8ecb9ba98ff03a1d89c4371a8cd546d1cb9e7119`，v4 `a7dbb1f35a157a80daf202ed91537e7c8ae8b9c135c828ed4108c3cb39063cb8`，v5 `950078fa30652b8acb8a0d7d2161408580dd21bf45194f77d3fbfc142b243c05`。v3-v5 当前为未跟踪文件；v5 将 9/28 单日窗口作为非连续证据保留，Midea coverage status 仍为 `INCOMPLETE`。

当前 watermark successor 为 `config/prospective-public-event-watermarks-v8.json`。
v8 原样保留 v7 的四条既有记录，追加美的 2026-03-31..2026-09-27 的相邻完整 CNINFO 日期窗口，
合计 106 条不重复公告。该日期区间的查询链已验证，但美的原始登记水位仍为 `INCOMPLETE`：
回溯窗口不能补证最初前瞻登记边界。v8 另存三家公司 2026-09-28 10:00..10:02 +08 的单日快照，
分别返回 1、0、0 条；美的仅重复已知公告 `1225582141`。所有抓取时间仍是未独立认证的本机进程时间，
快照不证明全天或多渠道覆盖，strict PIT 仍为 `NOT_PROVEN`。无新增产品事件，Excel 不变且不重新发布。

神华事件投影 v2 为
`runtime/prospective-public-event-20260927/shenhua-event-projection-v2.json`
（SHA-256 `1c88dd83902b766ac0c208f2b837fa157b91d40189a91a4ddb79bd33cf82a971`）。发布器 in-memory verification、三份原件 Hash 校验及保护页逐单元比较通过；同一 canonical Excel 已更新，最终 SHA-256
`522f6b11a01c2d87024c45496a4a6a3f3d101dba315274d34cb88167e7d3f6d6`。WPS 只读检查、事件到审计行及 CNINFO 原文链接检查通过。行情沿用已验证的 2026-09-24 部分覆盖包，没有声称刷新 2026-09-28 收盘数据。以上不改变任何估值、交易、strict PIT 或生产门禁状态。

### 2026-09-28 PIT 时间顺序与档案治理复核

独立审查确认当前三家均无可证明的 strict contemporaneous PIT 链。v2 注册回执的时间来自本机进程时钟；本机记录/文件元数据显示前瞻 baseline snapshot v13 在声明的 2026-09-27 08:45 cutoff 之后生成（该时钟本身同样未获认证），因此不得把事后采集、按来源可用日筛选的资料描述为当时已观察到的完整研究链。

美的 CNINFO `1225582141` 的保守 `source_available_at` 为 `2026-09-29T00:00:00+08:00`，既有观察记录却写 `observed_at=2026-09-28T01:36:33+08:00`。现将写入端和读取端均改为拒绝该时间倒置：原运行时文件及哈希保留作审计证据，但不得在任何更晚 cutoff 进入研究输入。此修复不更改 registration、baseline、事件水位、ResearchCase、估值或 Excel。

CNINFO 水位复核：000333 在已留存的 2026-03-31..09-27 窗口内无日期缺口，但正式状态仍 `INCOMPLETE`；600887 的 `COMPLETE` 仅覆盖 09-23..09-27；601088 的连续链仅覆盖 03-31..09-27。三家 09-28 查询仍只是局部单日快照，均不代表多渠道或全天完整性。不重复重扫历史窗口。

根目录只读盘点发现 29 个 `.xlsx`（1 个仓库参考快照、28 个历史候选）；全部仍有路径/哈希引用，当前没有候选能通过内容寻址迁移校验。没有移动或删除文件。实际 WPS canonical 仍由外部 `WORKBOOK_PATH` 指向，哈希保持 `b47141f63e57eec4857f83b42162738e6ce33ca040252f8ba9a15d6ff0133640`。

相关读取器、事件投影及观察账本定向测试 `46 passed`。行情截至 2026-09-24 仍为部分覆盖并缺少伊利；2026-09-28 交易日尚未收盘。无新增可评估事件、无 Excel 发布。三家 baseline 仍为 `PARTIAL`、估值仍 `NOT_READY`，strict PIT 仍 `NOT_PROVEN`；`M4_R2` 非阻塞，`M6_R3` 未授权/未启动，`M7_R5` 未通过，`action=no_order`。

## Historical R0 Audit Snapshot（2026-09-27；非当前授权）

以下仅记录 R0 收尾阶段的历史范围与审计事实。R0-A 保持 `NOT_PROVEN`：真实 M5 receipt → Product → Excel 未形成可验证绑定，实际重放依赖的原始 graph/plan/verified-facts/bounded-recalculation 原件缺失。R0-B 保持 `PARTIAL`：162 个 raw-only 指纹中，154 个仅为规则标注的潜在公开数值，5 个存在私密上下文命中，3 个未知；独立审阅认为 8 个都不能放行，CI artifact 下载返回 403，WPS/M4 私密边界未闭合。R0-C 仍是 R3 基础设施决定。不得据此生成 External Gate Handoff、宣称总 Goal 完成或生产就绪。

## Prospective Research Stage Evidence（当前阶段基线；逐项状态以新收据和下文当前执行回执更新）

以下轨道状态、研究事实和公开事件结果是本阶段既有基线；只在有新证据时增量更新，不重做已覆盖工作。

### 并行轨道与门禁（当前阶段基线）

| 轨道 | 当前状态 | 允许动作 | 不允许动作 |
| --- | --- | --- | --- |
| A：当前公共行情/报价 | `CURRENT_BUNDLE_RAW_REVALIDATED_PARTIAL` | 对当前保留 bundle 的原件重新解析并核验，显示已验证的部分覆盖；新交易会话后仅更新登记标的 | 将部分集合说成全覆盖；把公共行情源表述为交易所认证；用旧缓存伪造新收盘；将价格混入内在价值 |
| B：前瞻同期研究/M3 | `ACTIVE` | 维护预先登记的 2-5 个公共 ResearchCase，后续事实按可用时间进入 PIT 记录 | 用历史回放、后验结果或当前价格替代前瞻登记 |
| C：M5 公共事件/研究循环 | `ACTIVE_BOUNDED` | 从既有水位起做公开、有限、只读事件摄取；新材料只重开受影响研究 | 未授权 ACTUAL 应用、生产通知或重复扫描同一水位 |
| D：M7 日常产品/Canonical Excel | `INTEGRATED` | 仅在有新的、可核验的公共事实状态时发布到 `WORKBOOK_PATH` | 创建新的 current candidate、覆盖人工区或因模拟数据发布 |
| E：M6 生产前安全准备 | `PARKED_SAFE_ONLY` | 本地合同、CI、日历和安全验证 | 服务器部署、Shadow、调度、通知或生产数据库动作 |
| M4：私人组合 | `PARKED_WAITING_R2` | 保留已完成的非个人化工程和合成演练证据 | 请求/扫描/猜测 IPS、现金、持仓或私有密钥；把 M4 当成其他轨道的阻塞 |

当前行情 bundle 的原始腾讯/新浪响应由既有 `quote_sessions` 解析器重新计算，报告中的代码、双源价格、时点及基于归档交易所日历得出的交易会话必须一致；发布仅展示登记样本的报价，并显式标注缺失/排除代码。该重验证明展示值与所保留的响应字节一致，不证明数据供应商是交易所授权来源或其市场微观结构完整性。最新 canonical 产品发布与 WPS 只读复核见 `docs/execution-status.md` 顶部回执；该发布不是新行情采集，也不是最终用户验收。

前瞻 baseline 只允许 item-level fact admission：事实类型必须在显式白名单内，数值、单位、报告期间、合并范围、来源标签、物理/印刷页码必须与 Hash 固定的 PDF 对应页及邻接页文本一致。只有文件 Hash 或公告编号不再足以将 report-level placeholder 提升为财务事实。Registration receipt 每次 admission/observation 都必须复核 canonical registration fingerprint、确切计划字节、Git ancestry、receipt 时间及计划语义；重复 baseline case ID、observation supersession 分叉均 fail-closed。无法验证的报告级条目进入 `unadmitted_fact_ids`，不进入 known facts、observation ledger 或研究结论。

当前前瞻 baseline successor 为 `runtime/prospective-baseline-20260927/snapshot-v13-midea-h1-verified.json`（SHA-256 `ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5`）：美的 2025FY 三项摘要事实及 2026H1 三项摘要事实；伊利 2026H1 六项逐行核验事实；神华 2025FY 三项摘要事实及 2026H1 三项摘要事实。美的三项 H1 指标来自 CNINFO `1225531404` 原件物理第 7 页，PDF SHA-256 `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`，单位为人民币千元、报表未经审计，按日期级公告时间保守取 `2026-08-30` 可用。伊利和神华各有一项报告级条目未准入。神华 H1 数值绑定 CNINFO `1225531759` 原件及第 6 页；准入要求明确的“2026年上半年→2025年上半年”有序表头、行值、单位和范围匹配，比较列对应 2025H1 **重述后**口径。神华中期报表未经审计，附注册会计师有限审阅而非审计意见；伊利、神华 H1 可用时间为 `2026-08-28` 与 `2026-08-30`。Registration receipt 仍只有进程时钟证据、没有独立 TSA/签名，因此 snapshot 必须保持 `strict_pit_admissible=false`，不可计入 M3 strict contemporaneous PIT PASS。三家估值仍全部 `VALUATION_NOT_READY`，`action=no_order`。美的来源准入边界见 `docs/current/track-b-midea-2026h1-admission-20260927.md`。神华 2026-09-23..26 CNINFO gapfill 已补齐五份原件并完成局部审阅；随后 v4 通过留存查询窗口覆盖连续性校验，具体来源范围仍仅限 CNINFO 精确发行人及 2026-09-27 19:22:35 +08:00 之前的留存窗口。中期利润分配目前已知方案金额并已获股东会通过，但 A 股实施、登记和支付时间未见；限售股解禁是流通供给监测，不改变总股本。该历史公开材料不构成 strict PIT。校验收据与边界见 `docs/current/track-c-public-event-gapfill-20260927.md` 及 `docs/current/track-b-shenhua-2026h1-admission-20260927.md`。

The Shenhua H1 source contract uses pypdfium2 character coordinates to bind the reported current-period value to the 2026H1 column group and the comparison values to the 2025H1 group. Missing or misaligned coordinates fail closed; this is a source-admission safeguard, not an audit or strict-PIT attestation.

伊利 CNINFO 事件水位的 append-only successor 是 `config/prospective-public-event-watermarks-v3.json`：对齐此前 2026-09-22 水位后，使用精确发行人、未过滤、完整分页查询补扫 `2026-09-23..27`，原始响应、请求索引、分页状态和公告 PDF 均通过 Hash 绑定。连续 CNINFO 查询现覆盖至 `2026-09-27T10:00:05Z`；只确认既有公告 `1225578520`，它在预登记前已公开且材料性仍 `UNDETERMINED / INSUFFICIENT_EVIDENCE`，不算 post-registration event。该局部推进不改变伊利模型/估值状态，也不补齐 issuer-IR、交易所公告或更正覆盖。美的与神华仍为 `INCOMPLETE`，其局部窗口不能证明更早日期连续。

已在有界 CNINFO 窗口补齐中国神华 2025FY A 股利润分配的股东会批准与实施公告证据链（每股含税 1.03 元，公告列示发放日 2026-07-13）；这属于历史资本配置/普通股息支持证据，不证明账户到账、未来可持续性或估值影响，也不推进 `601088` 的正式不完整事件水位。详情及原件 Hash 见 `docs/current/track-c-shenhua-dividend-followup-20260927.md`。

`600519` 维持 `EVIDENCE_STOP`：除非出现新的重大外部证据，不重开同一研究循环。
`M4_ENGINEERING=COMPLETE_FOR_CURRENT_SCOPE`、`M4_SYNTHETIC_REHEARSAL=COMPLETE`、
`M4_PERSONALIZED=PARKED_WAITING_R2`。`M6_OPERATIONAL=NOT_STARTED`，
`M7_FINAL_USER_ACCEPTANCE=NOT_PASSED`，`INITIAL_ASSISTED_USE=NOT_REACHED`。

### 当前最小前瞻研究合同

前瞻研究的当前预登记入口是
`config/prospective-research-observation-plan-v2.json`。v1 回执保留为历史记录，
其 caller-controlled `registered_at` 不构成独立时间证明。v2 将声明时间与系统生成的
`receipt_created_at` 分离，只有后者是 PIT 时间锚点，且必须不晚于观察起点。它登记 000333、600887、
601088 三个有界公共案例的画像、适用模型、来源定位器、待验证假设、PIT 截止时间与
观察起点；登记本身不抓取数据、不执行估值、不生成 Decision Support、不写 Excel。
`scripts/current/register_prospective_research.py` 只能向 `runtime/` 写入含计划 Hash 和
Git revision 的不可覆盖回执。后续评估必须分别记录 research/facts/quote/event 的时间，
不得将登记或历史样本称为生产验证。

### 中断审计

每次继续执行前，按 A-E 轨道选择最高优先级、无需 R2/R3/R6 自然时间且不会重复已有
收据的节点。不得因 M4 缺少私人输入停下公共研究；也不得以反复模拟、重复回放或新增
Excel 候选替代新的公共研究证据。

## 历史快照（非当前授权）

### Real-use readiness factual checkpoint

The 2026-09-26 bounded quote collection retained matched-close data for the
three fixed symbols and is now bound to the canonical Excel publisher. The
published product pages show the 2026-09-24 market-data observation with raw
evidence references, while frozen research facts remain explicitly separate:
this is not a valuation refresh, decision signal, or order. The WPS visual
review passed on the published canonical file. M6 `m6c2` and `m6c3` were
re-verified on the cited preflight commit; `m6c7` is still `PARTIAL` because future authorized venue coverage
is undefined. M4 was exercised only with synthetic data and remains
`WAITING_R2`; M3 strict PIT remains `NOT_PROVEN`; M5 remains
`PARTIAL_WITH_VALIDATED_NOT_READY`. The source-of-truth readiness matrix is in
the latest `execution-status.md` checkpoint.
Canonical daily quote publication did occur. No production, Shadow, or decision action occurred;
`action=no_order`.

当前唯一阶段为 `PRODUCTIZATION-SECURITY-AND-REAL-USE-CLOSURE`。唯一用户 Excel
入口为 `.env` 的 `WORKBOOK_PATH`，即 WPS 云盘中的
`A股价值投资_Agent前端智能跟踪模板.xlsx`；M7 的五页产品入口只允许原位发布到该
工作簿，`runtime` 中的候选文件不是用户入口。当前已完成原位发布的逐页保全、WPS 只读
打开与可读性复核，故 `M7_PRODUCT_UX=INTEGRATED`；最终用户签收仍未完成。
`SINGLE_CANONICAL_EXCEL=PASS`、`M7_PRODUCT_UX_IN_CANONICAL=PASS`、
`COMPETING_CURRENT_WORKBOOKS=0` 已由 GitHub Core Research Gates 复验；这不构成投资
辅助系统或最终用户验收通过。
`M4_PERSONALIZED=WAITING_R2`，`M6_OPERATIONAL=NOT_STARTED`，
`INITIAL_ASSISTED_USE=NOT_REACHED`，并永久保持 `action=no_order`。优先级是
M7 五页产品体验、关闭 ADV-P1-003/004、通用产品入口、M4 合成接入演练、M6
启动条件矩阵和历史验证维护。该阶段不建立 M8、不扩大市场范围，也不授权生产、
Shadow、调度、通知或账户导入。M2-M6 继续作为后台阶段，不得出现在用户导航中。
M7 Product Read Model 与五页 Excel 产品页已形成并集成至唯一 canonical workbook；ADV-P1-003/004 已通过签名审批
收据和运行控制重验关闭。第二轮对抗审查后：legacy M5 授权只能对已存在的同指纹批次
做只读重放，新建 ACTUAL 运行一律拒绝；M5/M6 的 trust root 必须命中已提交的 pin
注册表，该注册表当前为空，因此真实 ACTUAL/M6 授权默认 fail-closed；M7 组合数值仅在
M4 provenance 齐备时显示；M6 start matrix 支持 `SHADOW_START_READY`，但当前仍为
`shadow_start_allowed=false`。M5 签名审批收据现已强制 `valid_until`，并在签发、
恢复、验证和 durable application 路径按系统评估时间 fail-closed；调用方提供的
`generated_at` 不再作为授权时钟。真实 operator keystore 仍是首次真实授权前的开放
前置条件，不构成本轮工程阻塞。通用 CLI v2 将产品入口与工程入口分层
（product 15 / engineering 36）；M4 合成全链路演练已完成，但
`M4_PERSONALIZED_ACCEPTANCE=WAITING_R2` 不升级。M6 start matrix 完成，
`M6_OPERATIONAL=NOT_STARTED`。600519 historical validation 保持
`NOT_PIT_SAFE / NOT_ADMITTED / EVIDENCE_STOP`。

M4 Private Input Package 已形成单一安全入口，合成链覆盖草稿、加密、双密文对账和
显式人工确认；真实 R2 输入仍未提供，M4 个性化状态不升级。M7 只读试用入口已改为
`WORKBOOK_PATH` 的 canonical workbook；候选工作簿仅作为历史审计产物，M6 仍为
`NOT_STARTED operationally`，M7 R5 签收未开始。两项均保持 `action=no_order`。
M6 离线授权的裸 ID 领域入口已关闭：模式转换只接受签名验证器签发的证明对象，并保存授权
Hash、目标模式、操作者和有效期绑定；`LIMITED_USE` 继续无入口。历史验证第一案例保持
`NOT_PIT_SAFE / NOT_ADMITTED`，不运行策略绩效或 walk-forward。

```text
TOTAL_GOAL_STATUS = IN_PROGRESS_WITH_EXTERNAL_AND_NATURAL_GATES
INITIAL_ASSISTED_USE = NOT_REACHED
SPECIALIZED_GOAL_STATUS = ENGINEERING_DONE_WITH_VALIDATED_NOT_READY
SPECIALIZED_GOAL_SCOPE = M5_ACTUAL_EVENT_BOUNDED_NOT_READY_ENGINEERING_ONLY
M5_PRODUCT_ACCEPTED = false
M6_OPERATIONAL_COMPLETE = false
M7_USER_ACCEPTED = false
CHECKPOINT_D = NOT_PASSED
action = no_order
```

`WORK_PACKAGE_DONE`、`SPECIALIZED_GOAL_DONE`、`MILESTONE_ENGINEERING_DONE`、
`MILESTONE_PRODUCT_ACCEPTED`、`TOTAL_GOAL_COMPLETE` 为不同层级，不可互相简写。
总 Goal 退出仍须 LONG-TERM-GOAL 的 Engineering、Research、Current Data、
Decision、Portfolio、Operations、User Acceptance 全部证据及 M6/M7 门禁。

M6 新增离线 R0 合同：恢复命令写内容寻址收据，绑定已登记 manifest、dump、
原件 Hash、隔离库表内容指纹和实际耗时；预检必须重新连接隔离库验证收据，
手填摘要仍不能 `DONE`。官方 SSE/SZSE 日历可校验完整已收盘会话，账本缺日即
中断连续段；目前全范围官方抓取来源认证、授权后真实运行收据及真实备份隔离恢复
均未取得，因此 `M6_OPERATIONAL=NOT_STARTED`、已验真实 Shadow 会话为 0。
现已对 600519 所在 SSE 的 2026 官方休市公告完成归档与第二次独立 HTTPS
逐字节比对；这仅证明该单一交易所公告来源，未来实际 Shadow 范围尚待绑定，
M6 整体日历项仍为 `PARTIAL`。
后续已同样归档并重取核对 SZSE 月度日历；生产授权的观察范围与真实会话收据
仍未建立，自报 `actual/success` 只列为 `declared_*`，已验连续会话与事件均为 0。
本机 Docker 引擎未运行且无本地 PostgreSQL 恢复工具，不能声称本轮完成真实 drill。
一次性 CI 双 PostgreSQL 实例的合成恢复测试已通过；它只证明工程链在隔离环境
可运行，不是用户真实备份、真实 RPO/RTO 或 M6 运营恢复验收。
当前 `18bc0ce` 的 [Core Research Gates](https://github.com/MingMingLiu0112/value-investment/actions/runs/36121893819)
两项作业均通过：备份容器显式只读挂载原件目录，原件字节写入内容寻址备份对象，
恢复 v2 收据在隔离临时目录重建并核对原件。CI 只使用合成 PDF 和一次性双库；
真实集群身份、异地副本及生产恢复仍未验收。

按 [LONG-TERM-GOAL 的R0-R6治理规则](../LONG-TERM-GOAL.md) 默认继续；机器校验R0与独立/委托研究复核R1不因名称含“人工/Review/Checkpoint”而中断。R2私人IPS/组合只阻断个性化M4，R3生产授权只阻断对应生产动作，R4真实资金决定始终由用户做，R5最终产品验收由用户签收；R6自然时间只记录触发和重开条件。请求用户或拟停止前先做`INTERRUPTION_AUDIT`并继续所有独立DAG。

当前：M2及Checkpoint A已完成；M3 Checkpoint B为PARTIAL，strict contemporaneous-rule PIT未证明（R6）；M4非个人化工程完成，个人化输入待R2；M5 600519已审9条、待审0条、已核H1事实5项、重大事件2条，情景研究`HUMAN_REVIEWED_NEED_MORE_EVIDENCE`，两条仍`STILL_NOT_READY`且无新估值。事件后证据到达只`REOPEN_RESEARCH`进入R1，不重复请求用户批准同一组假设。M6离线预检属R0、生产启动属R3、真实会话属R6；M7展示集成属R0，最终签收属R5。上述局部门不构成总Goal阻塞，永久`action=no_order`。

## 2026-09-25 人工情景研究复核

600519 两条 ACTUAL 重大事件已收到人工研究结论 `NEED_MORE_EVIDENCE`，
见 [只追加复核回执](receipts/600519-event-bound-scenario-human-review-20260925.json)。
A-E 五组估值假设均为 `NOT_APPROVED`；新增的四项研究阻断分别涉及事件后经营证据、
事件日折现输入、分配与留存、终值假设。八类新证据到达时仅 `REOPEN_RESEARCH`，
不自动批准参数或重算。原始有界重算的 `missing_dependency_node:valuation_inputs`
仍独立存在，两条事件均为 `STILL_NOT_READY`、`model_executed=false`、
`new_valuation_result=null`、`action=no_order`。M7 只读候选供目查；正式 WPS 表格未替换。

## 当前状态快照（2026-09-25）

M5 ACTUAL 离线专项已 fast-forward 整合至 `main` 的 `8db5994`；该 SHA 的
[Core Research Gates](https://github.com/MingMingLiu0112/value-investment/actions/runs/36095275207)
通过。600519 九条公告已完成原件 Hash 绑定的人工材料性审查，**当前待审为 0**；
其中两条为 `MATERIAL_REQUIRES_RECALCULATION`。半年报五项财务事实经原 PDF
确定性复验。两条事件均产生有界 `STILL_NOT_READY` 结果：
`model_executed=false`、`new_valuation_result=null`，阻断节点为
`EVENT_BOUND_REVIEWED_SCENARIO_INPUTS_REQUIRED`。M7 v7 仅为只读候选，正式 WPS
表格未发布或替换。详见 [专项交接](handoff-m5-actual-event-closure-20260925.md)
与 [事件绑定研究复核包](600519-event-bound-scenario-review-20260925.md)。

以下为 2026-09-25 专项收口时的历史快照，仅供审计；其中 M4 旧状态不再是当前授权，
必须以本文顶部 `CURRENT AUTHORIZATION` 为准。

```text
M5_ENGINEERING = ACTUAL_EVENT_OFFLINE_CHAIN_VALIDATED
M5_PRODUCT = PARTIAL_WITH_VALIDATED_NOT_READY
M3_CHECKPOINT_B = PARTIAL; STRICT_CONTEMPORANEOUS_RULE_PIT = NOT_PROVEN
M4_NONPERSONALIZED_ENGINEERING = COMPLETE; M4_PERSONALIZED_ACCEPTANCE = PENDING_USER_PRIVATE_INPUT
M6_PRODUCTION_AUTHORIZATION = NOT_YET; M6_OPERATIONAL = NOT_STARTED
action = no_order
```

下文保留早期阶段计划和历史快照，不得将其旧的九条 `PENDING_HUMAN_REVIEW`
描述用作当前状态。总 Goal 仍为 `VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`；
M5 的研究输入缺口不阻止 M4 私人输入准备、M6 授权前检查或 M7 其他展示验收。

更新：2026-09-24 / M2 Checkpoint A 已签收；M3 Checkpoint B 已完成人工语义复核，
但 strict contemporaneous-rule PIT 未证明，整体保持 PARTIAL。
用户已将下一Goal扩到M7，不在M2完成后退出。
总Goal ID：`VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE`。
当前产品聚焦为 M3 Decision Review / Checkpoint B；工程已推进到 M7 Daily
Workbench 候选，但不得把工程推进速度当阶段验收。
总目标现已进入实现阶段；先从 M2 的 W1/W2 共同合同时点、官方身份、逐证券覆盖与通道合并开始，
分阶段验收。不因总范围授权生产迁移、计划任务、通知、私人组合导入或公开推送。
权威分工遵循AGENTS；唯一长期路线为 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md)，本文件选择执行范围与交接门。
旧m2-current-progress-review等文件是历史输入，不覆盖最新范围；W0-W7是M2内部工作流，不是Milestone M0-M7。

## 2026-09-24 人工审查后的多维状态

工程、研究/产品、人工/运营分别记录，禁止用一个 `READY` 掩盖其他维度：

```text
M1  Engineering DONE | Research Workbench DONE | 已完成人工 G3 初审
M2  ENGINEERING_DONE | DONE                   | HUMAN_PASS
M3  ENGINEERING_PARTIAL_PLUS | PARTIAL        | HUMAN_REVIEWED_PARTIAL / STRICT_PIT_BLOCKER
M4  ENGINEERING_COMPLETE_NONPERSONALIZED | PARTIAL | PENDING_PRIVATE_INPUT
M5  ACTUAL_EVENT_OFFLINE_CHAIN_VALIDATED | PARTIAL_WITH_VALIDATED_NOT_READY | EVENT_BOUND_REVIEWED_SCENARIO_INPUTS_REQUIRED
M6  PREFLIGHT_DONE | operationally NOT_STARTED | PENDING_AUTHORIZATION / SHADOW
M7  DISPLAY_ENGINEERING_DONE | PARTIAL        | PENDING_USER_ACCEPTANCE
```

本轮纠偏后的机器门已覆盖：M3 正向价格门、M4 决策制品绑定、M2 二阶段
Channel Verification、M5 旧人工 review Hash reconciliation 与归档 PDF 绑定的只读阅读简报、M3
Historical Research Replay（事实/报价 PIT，规则为追溯并显式标记；strict
contemporaneous-rule PIT 尚未证明），以及 M7
10 个日常主入口工作台。Checkpoint A 已人工签收；Checkpoint B 的三张负向卡、
可理解性和无错误 BUY/ADD 子项已人工通过，但整体因
`STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN` 保持 `PARTIAL`。真实
IPS/Portfolio、Checkpoint C-D 与 M6 运营验收仍保持人工待办。

M5 阅读简报只帮助人工定位已验证 PDF 中的候选段落；它可作为可选 `04_阅读简报` 页
进入当时的复核候选工作簿，但不含材料性结论、受影响领域或事件创建路径。
这是历史阶段描述；九条公告的当前结论见本文顶部状态快照。

M7 Daily v2 用户查看、完整性核验、故障与回退入口见
[m7-assisted-use-runbook-20260924.md](m7-assisted-use-runbook-20260924.md)。
Checkpoint A 后的当前 M7 只读展示候选 v4 已接入 600519 重建披露连续性和真实
CNINFO 待复核队列，细节与边界见
[m7-daily-workbench-v4-post-checkpoint-a-20260924.md](m7-daily-workbench-v4-post-checkpoint-a-20260924.md)。
M2-M7 当前全部人工待办与签收边界见
[m2-m7-human-review-handoff-20260924.md](m2-m7-human-review-handoff-20260924.md)。
M3 Checkpoint B 的版本化只读复核包见
[m3-checkpoint-b-review-packet-20260924.md](m3-checkpoint-b-review-packet-20260924.md)。
M3 Checkpoint B 的 sequence 3 人工 partial 收据见
[m3-checkpoint-b-human-acceptance-20260924.md](m3-checkpoint-b-human-acceptance-20260924.md)。
M2 签收时保留的两项非阻断方法债见
[m2-non-blocking-method-debt-20260924.md](m2-non-blocking-method-debt-20260924.md)。

## 总体成果与阶段交接

从主动发现公司，推进到能解释买/加/持/减/退理由、回看原始买入逻辑、结合真实组合评估仓位/股息、每日监控重要变化，最终用户在原Excel中独立使用。
研究Review可由有来源记录的独立Reviewer或SubAgent完成；真实投资决定始终由用户本人做，`requires_human_review=true`、`action=no_order`，不连接券商或自动下单。

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
实际G3不得凭空批准，可经R1独立研究复核并保留证据；IPS/持仓与真实最小容量不得猜测，用户理解/最终交付签收不得代理。R2所需输入先由机器备齐最小私有包，再一次性说明；等候期间继续独立工作。
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
