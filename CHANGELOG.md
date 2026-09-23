# Changelog

## v2026.09.24-m3-decision-acceptance-audit

### Release Scope

为 M3 非个人化 Decision Card 增加可重复机器验收入口，同时复核 M2 AC1-AC12。
本版本不生成 Entry、Journal、Consistency、个人组合或订单，不改原 55 页生产工作簿。

### New Capability

- 新增 `src/value_investment_agent/m3_decision_acceptance_audit.py`，固定冻结 M1
  输入、预登记、候选工作簿、manifest、WPS 副本、WPS 只读收据和原生产表 Hash。
- 重放三张真实负向卡并检查确定性、来源 Hash 绑定、`no_order`、无正向状态、
  无禁止的交易/仓位文本，以及原 55 页生产表未改变。
- 新增 `scripts/audit_m3_decision_acceptance.py --run-tests` 和 3 项回归测试，
  并纳入 GitHub Core Research Gate。
- 机器门 `m3c1-m3c6` 为 `DONE`，`m3c7` 明确保持
  `PENDING_HUMAN_REVIEW`；Checkpoint B 仍需用户实际阅读并复述三张卡。

### Verification

- M3 定向回归：29 passed。
- M2 AC1-AC12 全量离线复核：AC1-AC7、AC11 `DONE`；
  AC8、AC9、AC10、AC12 `PENDING_HUMAN_REVIEW`。
- 仓库全量离线回归：2180 passed、6 skipped、18 warnings、0 failed。
- M3 审计收据：`runtime/m3-decision-acceptance-audit-20260923T190024Z/receipt.json`，
  SHA-256 `2bb49e94df6740330d2713dee03eec1c44bb2be753f3afbbd40b1560797c8259`。
- 独立 M3 候选继续为 15,102 bytes，SHA-256
  `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`；
  原生产工作簿继续为
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

### Acceptance Boundary

- M2 与 M3 均继续保持 `PARTIAL`；本次没有新增正向投资结论。
- 未写入原工作簿 `00_决策复核`，也未发布任何个人化决策卡。

## v2026.09.24-m3-decision-card-read-model

### Release Scope

建立 M3.2 的公开非个人化 Decision Card 只读模型、冻结 M1 证据应用编排和独立 Excel
候选。本版本不生成个人化 BUY/ADD/HOLD/REDUCE/EXIT，不合成 Entry、Journal 或
Consistency，不修改原 55 页 WPS 生产工作簿。

### New Capability

- 新增 `src/value_investment_agent/decision_read_model.py`：
  - `DecisionCard` 保持 `requires_human_review=true`、`action=no_order`；
  - 系统状态与个人组合缺失、原始 Entry 缺失、人工决策记录缺失分开表达；
  - 保留决策时点、规则版本、Evidence Bundle、artifact refs、来源 SHA-256 与 blockers；
  - 未提交决策意图时不伪造意图，也不生成任何正向复核状态。
- 新增 `src/value_investment_agent/m3_decision_application.py`，消费已封存 M1
  `integrated-runs.json`，逐证券解析 PreDecisionEligibility、计算七个证据段落的
  canonical SHA-256，并以缺失组合前置和 `decision_intent=None` 失败关闭编排。
- 新增 `src/value_investment_agent/m3_decision_card_workbook.py`，生成独立 4 页
  候选：决策卡、缺失与阻断、来源哈希、证据引用；无公式重算，只做展示。
- 新增 `scripts/build_m3_decision_card_candidate.py` 与
  `scripts/verify_m3_decision_card_wps.ps1`，支持无覆盖、哈希固定的候选生成和
  WPS 只读打开/计算/页序/链接校验。
- 新增 13 项回归测试并纳入 GitHub Core Research Gate。

### Real Artifacts

- 输入收据：
  `runtime/m1-post-review-20260923T114228Z/integrated-runs.json`，
  SHA-256 `b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459`。
- 独立候选：
  `A股价值投资_M3决策卡候选_20260924.xlsx`，15,102 bytes，
  SHA-256 `589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d`。
- WPS 云盘同名副本与仓库候选逐字节一致；WPS 只读验证 `status=passed`，
  4 个工作表、31 个证据链接、0 个公式错误。
- 三张真实卡片均为 `INSUFFICIENT_RESEARCH`、`reason_kind=RESEARCH_INCOMPLETE`、
  `portfolio_status=MISSING`、`entry_status=NOT_REQUIRED`、
  `decision_intent=null`、`action=no_order`。

### Verification

- M3.2 定向回归：13 passed。
- Decision/PreDecision 联合回归：32 passed。
- Core Research Gates 等价离线清单：330 passed。
- 仓库全量离线回归：2177 passed、6 skipped、18 warnings、0 failed。
- WPS 收据：`runtime/m3-decision-card-wps-20260924/receipt.json`。
- `py_compile` 与 `git diff --check` 通过。

### Acceptance Boundary

- M2 继续保持 `PARTIAL`，M3 继续保持 `PARTIAL`。
- 本版本是 M3.2 的独立展示候选，尚未写入原工作簿 `00_决策复核`，不能代表
  Checkpoint B 或 M3 产品验收。
- 原 canonical、M2 候选和 WPS 生产原表保持 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。

## v2026.09.24-m3-shared-decision-domain

### Release Scope

建立 M3 的解释性投资决策共享域基础，把研究证据、人工决策、原始入场论点和一致性复核
定义为不可变版本化契约。本版本只完成离线领域工程，不生成任何个人化买入建议，不连接
券商，不改变 Excel 字节。

### New Capability

- 新增 `src/value_investment_agent/investment_decision.py`：
  - `DecisionArtifactReference` 与 `DecisionEvidenceBundle` 保存证据依赖及 SHA-256；
  - `MinimalPortfolioPreconditions` 把最小容量输入与决策复核分开；
  - `InvestmentDecisionReview` 以 `action=no_order`、强制人工复核为固定边界；
  - `EntryThesisSnapshot` 保存确认后的原始论点、情景估值、风险、反证和 breaker；
  - `DecisionJournalEntry` 采用追加式人工确认/拒绝记录；
  - `InvestmentConsistencyReview` 比较当前事实与原始入场论点；
  - `evaluate_investment_decision()` 聚合前置资格、证据、置信度和容量约束。
- 在 `research_artifacts.py` 和 `research_artifact_codecs.py` 注册六种追加式 artifact：
  `decision_evidence_bundle`、`minimal_portfolio_preconditions`、
  `investment_decision_review`、`entry_thesis_snapshot`、
  `decision_journal_entry`、`investment_consistency_review`。
- 新增 13 项定向测试，覆盖拒绝路径、人工边界、Entry/Journal/Consistency 及仓库
  保存-恢复往返，并把新测试纳入 GitHub Core Research Gate。

### Decision Boundary

- 缺 Portfolio 输入时只返回 `WATCH`，不能产生正向 BUY/ADD；
- 正向复核必须同时满足 `ELIGIBLE`、中/高置信度、完整证据和人工确认容量；
- BUY 不能静默转成 ADD；HOLD 必须有原 Entry 和当前理由；
- REDUCE/EXIT 保留显式人工复核；实际/模拟 Entry 必须价格，历史重建必须注明；
- Consistency 优先级为 `BROKEN > NEGATIVE > all-FULFILLED > CONSISTENT`。

### Verification

- 新决策测试：13 passed。
- 决策与 codec 联合回归：17 passed。
- GitHub Core Research Gate 等价离线清单：317 passed。
- 仓库全量离线回归：2164 passed、6 skipped、18 warnings、0 failed。
- `py_compile` 与 `git diff --check` 通过。

### Workbook Version

- 本轮不修改任何 `.xlsx` 字节。仓库 canonical、独立候选和 WPS 生产原表仍为 SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- `A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx` 继续作为同内容独立快照。
- M2 保持 `PARTIAL`，M3 本轮仅标记为共享域工程基础，不等同于 M3 产品验收。

## v2026.09.24-m2-acceptance-auditor-ci-fix

### Fix

- 修复 M2 审计器回归测试对 untime/ 本地证据的隐式依赖。该目录被 Git 忽略，
  因此首次版本在 GitHub 干净 checkout 中执行完整 udit() 时会读取不到固定收据。
- 将依赖真实运行产物的完整审计回归替换为三个封闭单元回归：AC1 本地与 CI 同时绿、
  AC12 人工复核边界保留、任一机器项 PARTIAL 时产生 blocker。
- 	ests/test_m2_acceptance_audit.py 当前为 7 passed。本提交不改变任何 Excel
  文件字节或 SHA-256，不连接生产数据库，不生成交易指令。

## v2026.09.24-m2-ac12-acceptance-auditor

### Release Scope

为 M2 的 AC1-AC12 建立可重复、可回放的统一验收入口。审计器只重算已固定 Hash 的
真实 M2 运行、覆盖抽样、研究报告和工作簿发布证据，不重新采集市场，不写 WPS
原工作簿，不连接生产数据库，不生成估值、BUY、ADD、仓位或订单。

### New Capability

- 新增 `config/m2-acceptance-audit-v1.json`，固定 M2 运行收据、manifest、政策、
  AC9 覆盖抽样、AC8 研究报告、工作簿发布收据、两个 PIT 快照、55 个工作表门和最多
  30 个允许跳过测试的边界。
- 新增 `src/value_investment_agent/m2_acceptance_audit.py`，逐项重算 AC1-AC12：
  - AC1 继承稳定性、Git HEAD、本地全量和 GitHub Actions 结果；
  - AC2 官方 5,568 证券与四通道逐证券覆盖；
  - AC3 四通道真实线索、LEAD/PARTIAL 与空 Quality 成因；
  - AC4 版本化 policy、legacy shadow 和缺失指标不填零；
  - AC5 跨通道原因、画像适用和预算外账；
  - AC6 两个真实 PIT 信息边界、冷重放与未来证据拒绝；
  - AC7 当前真实市场 run、报价日期和完整分母；
  - AC8 实质研究/否决报告；
  - AC9 分层误放与漏筛审计；
  - AC10 原 Excel 发布 Hash、回退、WPS 收据和 55 页检查；
  - AC11 no_order、生产/调度边界、资源上限和无 symbol 专属流水线；
  - AC12 保留用户复核与 Checkpoint A 交接边界。
- 新增 `scripts/audit_m2_acceptance.py`，支持 `--run-tests`、`--ci-status`、
  `--wps-workbook` 和 `--json-only`，输出版本化 receipt 与 latest pointer。
- 新增 5 项审计回归测试并纳入 GitHub Core Research Gate。

### Real Artifacts

- M2 运行收据固定为 `runtime/m2-live-20260923-v3/receipt.json`，SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`。
- AC9 覆盖审计固定为
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- AC8 研究报告固定为
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- WPS canonical、仓库 canonical 和新 M2 候选工作簿继续逐字节一致，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 两个 PIT 快照保留在 `runtime/m2-live-20260923-v2/` 与
  `runtime/m2-live-20260923-v2b/`，用于证明两个真实信息边界及 v3 replay。

### Verification

- M2 定向回归：33 passed、0 failed。
- 仓库全量离线回归：2149 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Acceptance Boundary

- AC8、AC9、AC10 和 AC12 的机器证据通过后仍保持 `PENDING_HUMAN_REVIEW`，不能由
  审计器自动批准。
- M2 继续保持 `PARTIAL`，直到用户在实际 WPS 工作簿完成研究报告、分层样本、导航和
  证据链接复核，并完成 Checkpoint A 交接。
- 本版本不连接生产 PostgreSQL、不改服务器 PTA/Web App、不改计划任务，也不生成
  任何交易指令。

## v2026.09.24-m2-ac10-integrated-workbook

### Release Scope

把 M2 AC8 已形成的实质研究/否决报告并入现有 WPS 原工作簿的统一入口，同时保留 M1
Application 与原有 42 个工作表，受保护发布后把仓库 canonical、独立候选与 WPS 云盘生产
原表对齐为同一 SHA-256。本版继续 `action=no_order`，不生成估值、BUY、ADD、仓位、订单
或回测收益。

### New Capability

- `m2_discovery_workbook.py` 新增 `11_研究报告`、`12_研究证据` 两页，并在
  `00_M2总览` 增加内部导航；报告页保留通道结论、正反证、缺口和下一触发点，证据页保留
  来源 URL、原件 SHA-256、报告期、发布时间和抓取时间。
- `build_m2_original_workbook_candidate.py` 支持把固定 AC8 报告批或报告配置并入候选，
  并把报告 Hash 与统计写入 candidate manifest。
- `publish_stage_frontend.ps1` 新增 `-NewFrontendSheetCount`，允许 M1 的 6 页和 M2 的
  13 页使用同一受保护发布路径。
- 新增 `scripts/verify_m2_integrated_workbook_wps.ps1`，只读打开真实 WPS、计算工作表、
  扫描公式错误、核对工作表顺序、检查研究/证据行数与来源链接数。

### Real Artifacts

- 发布前原工作簿：12,210,200 bytes，SHA-256
  `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。
- 新候选：`A股价值投资_Agent前端智能跟踪模板_M2候选_20260924.xlsx`，
  13,199,222 bytes，SHA-256
  `64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911`。
- 仓库 canonical 原工作簿、新候选、WPS 云盘发布后原工作簿三者 SHA-256 相同。
- 55 个工作表：13 个 M2、6 个 M1 Application、36 个原工作簿页；42 个原有工作表被
  保留，96 个原始部分未变化。
- 研究报告 22 行，研究证据 245 行，识别 228 个来源链接。研究报告 JSON 的 SHA-256 仍为
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 发布前收据：`runtime/m2-original-candidate-20260924-v4/wps-prepublication.json`；
  发布后收据：`runtime/m2-original-candidate-20260924-v4/wps-published.json`；
  回退原件：`runtime/workbook-backups/stage-frontend-5e6ab310df554a49a100ccbcc6d68c33/before.xlsx`。

### Verification

- 定向回归：32 passed。
- 仓库全量离线回归：2144 passed、6 skipped、18 warnings、0 failed。
- 发布前和发布后的 WPS 只读校验均为 `status=passed`；实际引擎路径
  `D:\WPS Office\12.1.0.28505\office6` 已核对为 WPS。
- `git diff --check` 通过。

### Acceptance Boundary

- AC8 仍为 `AC8_REVIEW_PENDING`。
- AC10 机器检查为 `MACHINE_CHECKS_PASS`，但 WPS 脚本只验证只读打开、计算、公式错误、
  工作表顺序和链接数量，未做桌面人工逐链接/视觉点击验收，因此 Excel 用户审核仍标
  `AC10_REVIEW_PENDING`。
- M2 保持 `PARTIAL`；本版不单独宣告 AC8、AC10 或 M2 完成。

## v2026.09.24-m2-ac8-research-reports

### Release Scope

为 M2 AC8 建立预注册、证据绑定的实质研究与通道否决报告。工具只消费 AC9
`selected_leads` 已封存样本和固定 SHA-256 的真实 M2 输入，不按报告结果后验选择公司；
本版本继续 `action=no_order`，不生成估值、BUY、ADD、仓位、订单或回测收益。

### New Capability

- 新增 `config/m2-ac8-research-report-v1.json`，固定 AC9 审计、M2 收据、财务点与
  分红输入的路径及 SHA-256，并声明 3 份实质报告、2 个实质通道的最低门。
- 新增 `src/value_investment_agent/m2_research_report.py`：
  - 只读取 AC9 `selected_leads` 中的 `LEAD + DATA_PARTIAL` 样本；
  - 收据、财务点、分红文件 Hash 不匹配即拒绝，报告期晚于注册
    `latest_financial_period` 的点不进入证据；
  - 输出 `PENDING_DEEP_RESEARCH`、`REJECTED_FOR_CHANNEL` 或
    `INSUFFICIENT_EVIDENCE`，每份保留来源 URL、原件 Hash、报告期、正反证据与缺口；
  - `INSUFFICIENT_EVIDENCE` 不计入实质报告数量。
- 新增离线命令 `scripts/build_m2_research_reports.py`，只写新的 runtime 报告和 manifest。
- 新增 7 项确定性、最低门、防篡改、禁止执行键和未来报告期拒绝回归测试，并加入
  GitHub Core Gate。

### Real Evidence

- 报告：`runtime/m2-ac8-research-reports-20260924-v1/report.json`，SHA-256
  `dd55c02c75dec17ff766fa6b6ae529030d02a31376b305c02ddd0a8f5443c8a6`。
- 总计 18 份报告；16 份实质报告，覆盖 `dividend_cash_return`、`value`、`cyclical`
  三个通道；3 份 `PENDING_DEEP_RESEARCH`、13 份 `REJECTED_FOR_CHANNEL`、
  2 份 `INSUFFICIENT_EVIDENCE`。
- 代表案例：600011 华能国际保留为股息深研线索；600582 天地科技因经营现金流或
  自由现金流为负被通道否决；603799 华友钴业因扩张资本开支导致自由现金流为负且缺少
  正常化周期证据被否决；000151 中成股份因固定输入缺少核心财务点而诚实记录为证据不足。
- `machine_status=MACHINE_CHECKS_PASS`，`acceptance_status=AC8_REVIEW_PENDING`；
  全部产物不含 BUY/ADD/仓位/订单键。

### Verification

- M2 AC8 与 AC9 定向回归：28 passed。
- 仓库全量离线回归：2143 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`M2 / PARTIAL`。本版提供 AC8 真实研究报告证据，但不单独宣告 M2 完成；原 Excel 统一
发布、W6/W7 联合验收与用户可见审核仍继续。

### Excel

本轮未生成新的工作簿，也未改动 WPS 生产工作簿。仓库内 6 个已公开工作簿仍与 WPS
云盘同名文件逐字节一致，版本清单继续由
[docs/excel-artifact-version-record-20260924.md](docs/excel-artifact-version-record-20260924.md) 记录。

## v2026.09.24-excel-artifact-version-record

### Release Scope

将仓库内 6 个工作簿快照与 WPS 云盘 `价投跟踪` 目录逐字节核对，并补交独立的
工作簿版本清单。该清单列明文件名、字节数、SHA-256、最近提交和 WPS 一致性，
不把 Excel 上传解释为交易就绪。

### Workbooks

- 原工作簿：12,210,200 bytes；SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- M2 原表候选：13,168,877 bytes；SHA-256 `95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`
- M2 机会发现：53,299 bytes；SHA-256 `a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`
- M2 机会发现 v2：1,020,221 bytes；SHA-256 `4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63`
- M1 三公司候选 03:30：17,357 bytes；SHA-256 `0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbdbbd51c3d34`
- M1 三公司候选 12:20：17,025 bytes；SHA-256 `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`

上述 6 个仓库快照与 WPS 同名文件均字节一致。详细提交锚点见
[docs/excel-artifact-version-record-20260924.md](docs/excel-artifact-version-record-20260924.md)。

### Verification

- `git status`：提交前工作树无未跟踪的公开源码或工作簿变更。
- WPS/仓库工作簿 SHA-256：6/6 一致。
- `action=no_order` 继续保持不变。

### Status

`M2 / PARTIAL`。本次为版本记录和上传确认，不推进 M2 完成验收。

## v2026.09.23-m2-ac9-stratified-coverage-audit

### Release Scope

为 M2 AC9 建立预注册分层覆盖审计：以固定 seed 和 SHA-256 排名规则抽取入选线索、
拒绝、数据缺口、不支持、预算外、未评估、显式排除和 legacy/new 差异样本，并对真实
2026-09-23 收据执行机器勾稽与抽样阅读。本版本继续 `action=no_order`。

### New Capability

- 新增 `config/m2-coverage-sampling-v1.json`，固定收据路径、SHA-256、run id、覆盖与候选签名。
- 新增 `src/value_investment_agent/m2_coverage_sampling.py`：
  - 8 个预注册层，每通道固定抽样 6 条，不按收益或结果后验挑样本；
  - 收据文件 Hash、run id、日期和两个领域签名不匹配即拒绝；
  - 检查每通道 5,568 分母、PASS/候选对账、预算外可追溯、无已核候选、
    PARTIAL 证据语义、证据日期、legacy 记账和 Quality 空池解释；
  - 报告明确 `MACHINE_CHECKS_PASS`，验收仍为 `AC9_REVIEW_PENDING`。
- 新增离线命令 `scripts/audit_m2_coverage_sampling.py`，只写新 runtime 审计报告。
- 新增 6 项防篡改、确定性、覆盖完整性、禁止执行键回归测试，并加入 GitHub Core Gate。

### Real Audit Evidence

- 收据：`runtime/m2-live-20260923-v3/receipt.json`，SHA-256
  `869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220`。
- 审计报告：`runtime/m2-ac9-coverage-audit-20260923-v2/report.json`，SHA-256
  `3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695`。
- 所有机器检查通过。Quality 空池被解释为 873/5,568 财务证据覆盖限制；
  2,255 个通过对象因 50 条展示预算保留为 `BUDGET_EXCLUDED`；150 个展示对象均为
  `LEAD` 和 `DATA_PARTIAL`，已核候选为 0。
- 抽检未发现候选被错误升级为估值、BUY 或仓位。Value 文案“多指标便宜度”在下一版
  rule text 中应更准确描述其 PE/PB 与推导 ROE 输入。

### Artifacts

- `docs/m2-ac9-stratified-coverage-audit-20260923.md`。

### Verification

- M2 分层覆盖审计定向回归：6 passed。
- 仓库全量离线回归：2137 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`PARTIAL`。AC9 已有真实分层审计和抽样阅读证据，但不单独宣告 M2 完成；原 Excel 发布、
至少三份新发现研究/否决和 W6/W7 联合验收仍继续。

## v2026.09.23-m2-pit-and-partial-evidence

### Release Scope

加固 M2 W1/W2 共同合同：旧输入冷重放不得重标为当前时间，未来或未知时点的
证据不得进入历史快照，缺少深研证据的便宜筛选线索不得显示为 `COMPLETE`。
本版本继续执行 `action=no_order`，不生成估值、BUY、ADD、仓位或订单。

### New Capability

- `DiscoveryRunReceipt` 新增可选 `quote_date` 字段；旧 v2 收据仍可向后兼容读取。
- 收据构建时拒绝：
  - `quote_date > as_of`；
  - `universe.as_of > receipt.as_of`；
  - 任一 `EvidenceReference.fetched_at > generated_at`。
- 官方 Universe 缺少 `fetched_at` 时直接失败，不再用系统当前日期补时点。
- 财务点仅保留带时区、且 `available_at/fetched_at/created_at <= evaluation_at` 的记录；
  未来或时区未知的点不会进入财务证据。
- Dividend 证据的 `fetched_at` 使用原始分红输入的实际抓取时间，不再统一盖成运行时间。
- 非 Quality 通道候选在缺少 FCF/EV-EBIT、正常化利润、派息可持续性等深研证据时统一为
  `DATA_PARTIAL`；Dividend 最高优先级降为 B，Value/Cyclical 降为 C。
- `scripts/run_m2_opportunity_discovery.py --reuse-inputs`：
  - 必须有既有 `receipt.json` 和全部保留输入，否则失败；
  - 保留原收据的 `generated_at`、`quote_date` 和源 `run_id`；
  - 新运行使用 `m2-replay-*` ID，并在清单中记录 `replay_of_run_id`；
  - 不再把旧输入重标为当前日历日。

### Real Replay Evidence

- 输入：`runtime/m2-live-20260923-v2b/` 的真实 5,568 家保留输入。
- 输出：`runtime/m2-live-20260923-v3/`。
- 原始时钟保持：`generated_at=2026-09-23T15:12:00.735987+00:00`，
  `as_of=2026-09-23`，`quote_date=2026-09-23`。
- `replay_of_run_id=m2-20260923T231200Z`；新 `run_id=m2-replay-20260923T232854Z`。
- 字节收据重放与原始输入冷重放均一致。
- 覆盖签名不变：`4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- 候选签名更新：`f77fd5f0e139cf0ab283e9aee9fdd2f4f66695071c85816f303c9b31715cbe79`。
- 通道可见数仍为 Quality 0、Dividend 50、Value 50、Cyclical 50；已核候选 0。
- 候选数据状态：Quality 无候选；Dividend/Value/Cyclical 全部 `PARTIAL`。

### Artifacts

- 更新 `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`
  - SHA-256：`95993fa8721d4d333463b8ac48677b1700cbeec98d7eb4aad4bb457385baef6a`
  - 仍保留后 42 个原工作簿页，`original_parts_unchanged=96`
  - 已同步到 WPS 云盘独立预览，未替换生产原工作簿

### Verification

- M2、原工作簿候选、Frontend stage 与发布边界定向回归：24 passed。
- 仓库全量离线回归：2131 passed、6 skipped、18 warnings、0 failed。
- `git diff --check` 通过。

### Status

`PARTIAL`。本版修复时点重标、未来证据和证据完整度语义，不等于 M2 验收完成；
预注册抽样、至少三份新发现研究报告、真实 WPS 视觉验收和后续 M3-M7 仍继续。

## v2026.09.23-m2-lead-verified-original-candidate

### Release Scope

在保持 `m2-opportunity-discovery-v2` 冷重放语义的前提下，把“便宜筛选产出”与
“已经深研核实的候选”在领域模型中显式分开；同时增加从原工作簿生成受保护
M2 候选工作簿的离线发布入口。本版本继续执行 `action=no_order`，不生成
估值、BUY、ADD、仓位或订单，也不把候选发布为生产工作簿。

### New Capability

- `CandidateReason` 新增 `candidate_class`，只允许 `LEAD` 或
  `VERIFIED_CANDIDATE`；当前所有四通道筛选输出均明确标记为 `LEAD`。
- `DiscoveryRunReceipt.verified_candidate_pool()` 只返回后续深研验证门通过的候选；
  当前真实运行中该池为空，不再用“候选数”暗示研究已经完成。
- 候选签名包含 `candidate_class`，冷重放仍可验证新旧层级字段。
- M2 工作簿新增“研究层级”列，显示“研究线索”或“已核候选”；总览分别展示
  线索数与已核候选数。
- 新增 `scripts/build_m2_original_workbook_candidate.py`：
  - 校验原工作簿预期 SHA-256，源文件变化即拒绝；
  - 只接受 `action=no_order` 的有效 M2 收据；
  - 复用 `stage_frontend_package.graft`，原工作簿页和原始 ZIP 部件保持字节不变；
  - 拒绝覆盖已有输出，并产出 `candidate_verified_not_published` 清单；
  - 不执行对 WPS 云盘原工作簿的原子替换或发布。
- 新增回归测试覆盖源 Hash 变化拒绝、输出已存在拒绝、原页与原公式保留、
  OOXML 关系有效，以及所有屏幕结果是研究线索这一合同。

### Real Run And Candidate Evidence

- 复用 2026-09-23 真实全市场 5,568 家官方证券保留输入生成
  `runtime/m2-live-20260923-v2b/`。
- 展示候选仍为 Quality 0、Dividend 50、Value 50、Cyclical 50；已核候选 0。
- `candidate_signature=a4f555b789c3942c690c1e288e5ce3bfa210544cd9ffcc63803d4c1eeb46f4c7`。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- 原工作簿候选：
  - 源 SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
  - 候选 SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`
  - 53 个工作表，前 11 个为 M2，后 42 个为原工作簿页
  - `original_parts_unchanged=96`，`status=candidate_verified_not_published`
- 候选以独立预览复制到 WPS 云盘，未替换生产原工作簿。

### Artifacts

- 新增 `A股价值投资_Agent前端智能跟踪模板_M2候选_20260923.xlsx`
  - SHA-256：`b57da4f4d3e8fd46ef24dc220820b8be9187f2c79503c5b1835f5761b9318335`

### Verification

- M2 与原工作簿候选定向回归：19 passed。
- `git diff --check` 通过。

### Status

`PARTIAL`。本版固定了线索/已核候选边界并演示未发布的原工作簿候选阶段，
不等于 M2 验收完成；深研报告、预注册抽样、完整时点重放、用户可见发布验收
与后续 M3-M7 仍按 `docs/current-stage-goal.md` 和 `LONG-TERM-GOAL.md` 继续。

## v2026.09.23-m2-v2-coverage

### Release Scope

将 M2 机会发现协议升级到 `m2-opportunity-discovery-v2`，把候选列表与完整覆盖账分开，
修复未来披露泄漏、源外证券混入、跨通道原因丢失和预算截断分母不可对账问题。
本版本继续执行 `action=no_order`，不生成估值、BUY、ADD、仓位或订单。

### Git Commits

- `0ba4660 Expand active goal from M2 through M7 with stage gates` 后继续本地开发。
- 本条目提交 M2 v2 协议、引擎、运行脚本、回归测试、Excel 快照与版本记录。

### New Capability

- 每个官方证券在每个通道保留 `PASS / REJECTED / DATA_GAP / CONFLICT / UNSUPPORTED / NOT_EVALUATED / BUDGET_EXCLUDED` 覆盖记录。
- `coverage_signature` 覆盖完整分母，`candidate_signature` 只覆盖展示候选；收据冷重放同时校验两者。
- 官方 Universe 外的行情只计入健康异常，不进入候选池、覆盖账或 Legacy shadow。
- 同一证券跨通道进入时保留全部通道原因，不再使用字典覆盖。
- 超出 `max_per_channel` 的通过者记为 `BUDGET_EXCLUDED`，保留原因和分母。
- 复用原始输入时保留各 payload 自己的 `fetched_at`，不再用当前时间重新盖章。
- 分红公告日期晚于运行 `known_at` 的未来披露会在进入证据层前被排除。
- 新增 `10_逐通道覆盖` 工作簿页，展示完整分母、状态、原因、画像和证据日期。

### Real Run Summary

- 输入来源：2026-09-23 真实全市场 5,568 家官方证券快照。
- 行情匹配 5,568 家；缺失 0；源外 0；双源冲突 0。
- 展示候选：Quality 0、Dividend 50、Value 50、Cyclical 50；合并去重 113。
- 覆盖账：Quality 5568（PASS 0 / DATA_GAP 4672 / REJECTED 775 / UNSUPPORTED 121）。
- 覆盖账：Dividend 5568（PASS 50 / BUDGET_EXCLUDED 369 / NOT_EVALUATED 1946）。
- 覆盖账：Value 5568（PASS 50 / BUDGET_EXCLUDED 351 / REJECTED 3581）。
- 覆盖账：Cyclical 5568（PASS 50 / BUDGET_EXCLUDED 1535 / NOT_EVALUATED 3059）。
- `coverage_signature=4e1655de3e55b79bad0b2737cebf893d82049f4c495cf373a3e51344745cf805`。
- `candidate_signature=f7442de45283c4d3a21b17a846bb7b0028c3219b15617af3ed17848245ba4d0a`。
- 收据字节和原始输入冷重放均一致。

### Artifacts

- 新增 `A股价值投资_M2机会发现_v2_20260923.xlsx`
  - SHA-256：`4e2dc634fb5c093d7476ad99e41cf76ec642b5b98f6761a31f8d06f348368c63`
- 更新 `A股价值投资_Agent前端智能跟踪模板.xlsx` 至 WPS 2026-09-23 版本
  - SHA-256：`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`
- 新增 `M1_三公司研究Application候选_20260923_033001.xlsx`
  - SHA-256：`0cebce194667879d1fbae345cd9548c4cb1407b8528fade4b62e5dbd51c3d34`
- 新增 `M1_三公司研究Application候选_20260923_122010.xlsx`
  - SHA-256：`2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`

### Verification

- M2 定向测试：10 passed。
- 仓库内隔离 basetemp 全量回归：2122 passed、6 skipped。
- `compileall`、`git diff --check` 通过。

### Status

`PARTIAL`。本次修复 M2 覆盖账与时点重放合同，不等于 M2 或 M2-M7 总目标完成；
M2 的实质研究报告、原 Excel 统一发布、用户可见验收和后续 M3-M7 阶段仍按
`docs/current-stage-goal.md` 与 `LONG-TERM-GOAL.md` 继续。

## v2026.09.23-m2-partial

### Release Scope

完成 POST-M1 稳定化后的首个真实全市场 M2 机会发现 run-once，并发布独立候选工作簿快照。
本版本只负责主动发现深研候选，不生成估值、BUY、ADD、仓位或订单，`action=no_order`。

### Git Commits

- `f26f726 M2.0 complete post-M1 stabilization`
- `6658b14 M2.1-M2.6 multi-channel opportunity discovery run-once`
- 本条目提交：新增仓库内 Excel 快照与版本记录。

### New Capability

- 官方证券 Universe 快照与腾讯、新浪行情合并，支持价格冲突检查。
- Quality、Dividend/Cash Return、Value、Cyclical 四个独立筛选通道。
- 每条候选记录通道、进入原因、证据日期、数据状态、画像状态和缺失指标。
- 银行、保险、券商等不支持画像进入 `UNSUPPORTED` 隔离，不进入通用通道。
- Legacy PE/PB screen 仅保留 shadow 对比，不参与 M2 候选排序。
- 原始快照、收据、候选签名和 SHA-256 可重放。
- 生成展示专用 `A股价值投资_M2机会发现_20260923.xlsx`。

### Real Run Summary

- 官方 Universe：5,568 家；行情匹配：5,568 家。
- 价格冲突：0；行业映射：5,568 家。
- 财务证据：873 条；股息证据：3,622 条；不支持金融画像：121 家。
- 通道候选：Quality 0、Dividend 50、Value 50、Cyclical 50。
- 合并去重候选：113 家；Legacy shadow：747 家；重叠：86 家。
- Quality 为空是证据门禁失败关闭结果，未降低门槛强制放行。

### Artifact

- `A股价值投资_M2机会发现_20260923.xlsx`
- SHA-256：`a612a622cf476322724826c84b00783c51d65886fd3c9bb335159a509fa0c821`
- 与 WPS 云盘“价投跟踪”目录中的用户可见文件字节一致。

### Verification

- M2 定向测试：6 passed。
- 仓库内隔离 basetemp 全量回归：2118 passed、6 skipped。
- `compileall` 与 `git diff --check` 通过。
- 原始输入和收据重放候选签名一致。

### Status

`PARTIAL`。M2 验收第 1-6、8-10 项已有真实证据；第 7 项“从新发现候选中形成至少 3 份实质研究或否决报告”尚未完成。
