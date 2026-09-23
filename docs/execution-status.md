# 当前执行状态

更新：2026-09-23。本文只记录事实，不制定新任务。唯一活动任务见 [current-stage-goal.md](current-stage-goal.md)。

## POST-M1 Stabilization + M2 启动：2026-09-23

执行输入是用户复核后的 [m2-current-progress-review-20260923.md](m2-current-progress-review-20260923.md)。
当前活动阶段为 `POST-M1-STABILIZATION`，完成 A1-A5 后进入
`M2-MULTI-CHANNEL-OPPORTUNITY-DISCOVERY`。M1 保持 `DONE`，不重写历史。

- A1：修正茅台旧审计断言，从 P1 v4 契约自带的 hash-bound daily-simulation policy 推导执行政策事实，不删除红测试。
- A2：`build_m1_post_review_receipts.py` 标记为 `ONE_OFF_REVIEW_RECEIPT_GENERATOR`，并增加生产路径防误用测试。
- A3：临时桥接 haircut 增加 `stress_test_only / not_valuation_input / not_price_assessment_input`，域对象可序列化和 round-trip。
- A4：旧十样本估值画像、固定 Universe seed 与 PE/PB screen 明确标记为 legacy；M2 不得复用为候选排序。
- A5：`current-stage-goal.md` 已切换到 M2；本执行手册复制入 `docs/`。
- 稳定化验收：定向回归 14 passed；使用仓库内隔离 basetemp 的全量回归 2112 passed / 6 skipped；`compileall` 与 `git diff --check` 通过；Core 生产路径未新增 `000651 / 600741 / 600887` symbol 特例。

尚未声明 M2 完成。M2 需要真实全市场 run-once、真实数据覆盖、四个通道、候选原因、
缺失隔离、不支持行业隔离、可重放 PIT 和 Excel 候选输出。

## M1 收口：2026-09-23

- `M1-FIXED-SAMPLE-RESEARCH-WORKBENCH` 已达到 `DONE`；AC1-AC10 均由本地产物、隔离 PostgreSQL、WPS 发布收据和定向回归支持，最新审计状态为 `PASSED`、`action=no_order`。收据 `runtime/m1-acceptance-audit-20260923T091447Z/receipt.json`，SHA-256 `f7c71e507585d7660cc9f66320617738525a32abf141f2296ce46ee9ae90d16a`。
- AC4/AC6/AC10 不再被 G3 或事件材料性人工状态阻断。三家公司 G3 研究批准保留到 M3，模型前公告材料性复核保留到 M5，Excel 视觉确认保留到 M6；审计器只登记 `deferred_human_review`，不自动批准。
- 三家正常化股息情景仍 `NOT_READY`、全部估值仍 `conditional_research_only`、价格吸引力仍 `NOT_ASSESSABLE`。M1 完成只表示研究工作台闭环，不表示真实投资或交易准入。
- 未启动 M2，未连接生产 PostgreSQL、未 SSH、未改 PTA 或计划任务。

## M1 后人工复核纠偏与 M3/M5 决策门：2026-09-23

执行输入是用户复核后的 [m1-post-review-decision-gate-20260923.md](m1-post-review-decision-gate-20260923.md)，基线为 `cbec189 Close M1 workbench and defer decision-stage reviews`。M1 仍保持 `DONE`，冻结估值包、历史收据和原 WPS Excel 未修改。

- 新增五个 append-only 领域契约：`human_research_approval.py`、`event_materiality.py`、`valuation_bridge_review.py`、`interim_report_policy.py`、`pre_decision_eligibility.py`；Application、G3、ModelValidity、PriceBridge 和 CurrentStatus 已接入新门禁。
- 三家公司正式人工 G3 回执：`000651=REJECTED_NEEDS_REWORK`、`600741=REJECTED_NEEDS_REWORK + HIGH`、`600887=APPROVED_CONDITIONAL_LOW_CONFIDENCE`。回执绑定估值、ResearchCase、Facts、Assumptions 的 SHA-256，依赖变化会变为 `SUPERSEDED`。
- 24 条公告全部形成 EventMaterialityReview。分类为 2 `MATERIAL_REQUIRES_RECALCULATION`、4 `MATERIAL_RISK_MONITOR`、4 `MATERIAL_ALREADY_INCORPORATED`、5 `DUPLICATE_OR_DERIVED`、7 `NOT_MATERIAL`、1 `MATERIAL_SUPPORTING_EVIDENCE`、1 `REQUIRES_DECOMPOSITION`。格力和华域未解决资金桥接拆分保持 `UNRESOLVED`；伊利成本权益、留存/分红和减值归一化 ROE 仍为 `CONDITIONAL_REVIEW_PENDING`。
- 未经审计半年报默认改为 `CONFIDENCE_MODIFIER`，保留 `previous_classification=HARD_BLOCKER` 和版本链；已核实来源存在冲突、更正、范围不匹配或审计问题时才继续升级 blocker。
- 无有效人工 G3 时 Application 的价格吸引力强制为 `NOT_ASSESSABLE`。PreDecision Eligibility 要求 G0-G3、有效 Approval、当前 Event Review、`VALID`、`READY` 和可评估价格政策同时成立。
- 正式 runtime 收据目录 `runtime/m1-post-review-20260923T114228Z/`，manifest 覆盖 9 个文件 Hash；三家 integrated runs 均为 `action=no_order`，分别保持 `REJECTED/STALE`、`REJECTED/VALID`、`CONDITIONAL_APPROVED/STALE`，均 `NOT_ELIGIBLE`。
- 定向回归 `71 passed`；全量本地回归 `2107 passed, 6 skipped, 1 failed`，唯一失败仍是本文已记录的茅台旧 `daily_simulation_policy_implemented` runtime 指针断言，不在本轮改动路径内。GitHub Core Gate 已加入五个新契约测试文件。
- 未修改 M1 冻结 Hash、生产 PostgreSQL、计划任务、服务器 PTA/Web App 或原 WPS Excel。

## 用户指定的前端调整：2026-09-23 已更新原 Excel

独立于并行 M1 研究任务，本次只调整使用界面，不提升研究或交易准入状态。
原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 已备份并原子更新，新增工作台、研究看板、研究逻辑卡、决策复核、组合与股息、跟踪与数据六页。原30页的worksheet XML逐字节未变，持仓/交易/历史记录保留。

- 本次前台连接3家封存研究样本，含1家条件三情景及2家估值未就绪；不是正式重点关注池，不是今日行情，不是买卖建议。
- 下文 M1 W3 的6份新档案仍在独立候选中，未接入本前台；不能因本次原表发布而宣称M1的研究产品闭环通过。
- 新看板含原生筛选表、冻结导航、内部链接；未来决策、组合和监控区明确“未接入”，未知不填0。
- Excel相关回归：`19 passed`；64个内部链接目标、4个公式缓存和30张原表完整性校验通过；WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 只读打开/计算校验通过。桌面鼠标逐链接点击不在该收据范围内。
- 发布收据：`runtime/workbook-backups/stage-frontend-b65249ffe1874ca1859827665a4a001f/publication.json`；同目录 `before.xlsx` 为回退原件。新文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 保留六页的发布入口修改已在本地测试，未提交/推送；未部署服务器、未改定时任务。现有刷新只保留新页，不自动刷新这些封存快照。
- 构建运行时的退出异常与后续接入约束记录于 [excel-stage-frontend.md](excel-stage-frontend.md)，不把导出文件成功冒充无人值守发布已经可靠。

## M1 当前增量：2026-09-23 格力历史双源收盘价、PIT replay 与新 Application 候选

本节记录当时实际生成的新收据；该时间点的“未完成”只描述当时状态，最终 M1 收口见本文件顶部。

- 格力 `000651` 注入真实历史双源收盘价：腾讯与搜狐均 `38.18`，SZSE 交易日历为 `2026-09-22`；Application 桥接从 `PENDING_EXTERNAL_DATA` 变为 `READY`，当前数据为 `READY`。格力 FY2024 末期与 FY2025 中期派息实施原件也已补齐，见下方“格力股息生命周期”节。
- 三公司最新 Application：`000651 / 600741 / 600887` 全部 `COMPLETED_WITH_BLOCKERS`、`action=no_order`；三家报价桥接均为 `READY`，价格吸引力保持 `NOT_ASSESSABLE`。G3 与事件材料性后来按里程碑边界延后，不作为 M1 阻断。
- 隔离 PostgreSQL 冷启动已用更新后的格力数据包重跑：PostgreSQL 18.6，首轮写入 30 个制品，冷重启后 30/30 验证通过，`semantic_equality=true`。最新收据 `runtime/m1-postgres-cold-replay-20260923T060159Z/receipt.json`，SHA-256 `bd643fc080c82d2c174948067918488ae8c38aee2f6a615d763d7bc9ed9286e8`。
- 新披露 PIT replay：`m1_pit_replay.py` 对格力、华域、伊利三家真实官方 PDF 重放报告期披露可用边界；每家 2 份官方财报、4 个决策边界、3 个未来披露排除点，只按 `published_at` 选择，不用 `retrieved_at` 推断历史可用。收据 `runtime/m1-pit-source-replay-20260923T042556Z/evidence.json`，SHA-256 `f9a19f4da5d06ace7cb5b681e910925f45137f3c17df9e600be0f782ae34bf7f`。
- 原五粮液真实财报更正 replay 继续作为 AC7 的更正反例：`runtime/company-research/000858-revision-replay-20260909T131721971494Z/evidence.json`。
- 新 Application Excel 候选：6 个工作表顺序、WPS 只读打开、公式重算与哈希不变检查通过；候选 SHA-256 `2b913f65f3d0f7bb7696431902c890943147a18139b4ecccc41f75da9c8cb1b8`。
- 已复制到 WPS 云盘 `M1_三公司研究Application候选_20260923_122010.xlsx`；复制前后哈希一致。原 `A股价值投资_Agent前端智能跟踪模板.xlsx` 未覆盖，AC9 的受保护原表发布仍未完成。

## M1 原 Excel 整合发布：2026-09-23

上一段最后一项已推进为受保护的原表整合发布。这里只是把三公司 Application 六页追加到原 WPS 工作簿，不是 M1 完成，也不是交易建议。

- 修复 `scripts/stage_frontend_package.py` 的关系 ID 冲突：原表与新增 M1 页面都使用过 `stageFrontend1..6`，会导致 WPS 把前六页错误绑定到旧 parts；现在新增页使用独立 `m1Application1..6`，并对每个 `.rels` 做重复 ID、悬空目标和前六页 part 映射 fail-closed 校验。
- 早先 `runtime/m1-integrated-workbook-20260923T043200Z/` 中带重复关系 ID 的候选已判定为结构无效，从未发布；不要把它当作可用 Excel 产物。
- 新候选为 42 个工作表：前 6 个是 M1 Application 页面，原 36 个 worksheet XML 逐字节未变、顺序保留；首屏标题为 `M1 三公司研究 Application 候选`，状态为 `完成，有阻断`，全程 `action=no_order`。
- 集成候选 SHA-256：`36fd26812f84dd0b9931725ebeec93cf5311c17f408974714c434ab5a22970ac`；发布前源文件 SHA-256：`2912da27ef545256393c8ea46a404278a26630587ae313a7df626e57709564ae`。
- 发布前 WPS 收据：`runtime/m1-integrated-workbook-20260923T044629Z/wps-integrated-receipt.json`；发布后再次只读打开验证：`runtime/m1-integrated-workbook-20260923T044629Z/wps-published-receipt.json`，42 页、标题/状态、哈希不变检查均通过。
- 发布收据：`runtime/workbook-backups/stage-frontend-3c253a9761bb44489872ce7268e9a933/publication.json`；同目录 `before.xlsx` 为可回退原件。
- 防回归测试：`tests/test_stage_frontend_package.py` `3 passed`，覆盖关系 ID 唯一性、原关系目标保留和重复 ID fail-closed。
- M1 仍未完成：G3 人工估值审批、股息实质评估、更完整的跨模型情景与剩余真实缺口均未结束；发布页明确显示 `完成，有阻断`，没有生成价格吸引力或买入结论。

## M1 事件扫描合同与真实 CNINFO 封存：2026-09-23

上一版把中报原文当作事件扫描证据是不成立的。本轮新增显式 `EventScanResult` 合同，并把三家估值包改绑到真实 CNINFO 公告窗口证据，避免“任意非空引用 = 已完成且无重大事件”。

- 新增 `src/value_investment_agent/event_scan.py`：分别保存扫描窗口、模型有效性窗口、覆盖完整性、公告级规则分类、模型前候选复核状态、阻断和证据引用；扫描窗口必须覆盖报价日，`PENDING_HUMAN_REVIEW` 与不完整覆盖不能生成 `VALID`。
- `scripts/collect_m1_event_scan.py` 从 CNINFO 归档三家 `2026-08-27 ~ 2026-09-22` 共 40 份公告：格力 8、华域 13、伊利 19；每家保留索引 JSON 和全部 PDF，逐份 SHA-256 已校验。收据目录 `runtime/company-research/m1-event-scans/20260923T051018Z/`。
- 三家桥接窗口 `2026-09-22` 均无公告，`ModelValidity` 仍为 `VALID`、`PriceBridge` 仍为 `READY`；但模型构建前分别有 7、4、13 份规则候选标为 `PENDING_HUMAN_REVIEW`，阻断已进入 Application 与 `价格桥` 展示，不冒充全周期事件复核完成。
- 三个估值包的 `model_validity_input.event_scan_ref` 已绑定证据文件 SHA-256，`scan_watermark` 改为 `m1-cninfo-event-scan-v1:<hash16>`；旧 `events=[] + 中报引用` 不再作为新路径的事实来源。
- 新 Application 收据：`runtime/m1-research-application-20260923T051116Z/evidence.json`。新集成候选与原表发布 Hash 均为 `4678b4aa3074f7d4e7c31134a2560326fdcd45f0fb1e367b2bb1c9c971ed0ed7`；原 36 页 XML 逐字节未变。
- 发布前 WPS 收据：`runtime/m1-integrated-event-scan-20260923T051301Z/wps-receipt.json`；发布后再次只读验证：同目录 `wps-published-receipt.json`。发布备份：`runtime/workbook-backups/stage-frontend-1688b2b905714859bc90ca57d9ed7a8c/`。
- M1 仍未完成：事件扫描现在是可审计证据，但模型前披露尚未人工完成材料性复核，G3、股息实质评估和更完整跨模型情景仍未结束。

## M1 AC5 股息生命周期证据与 Excel 发布：2026-09-23

上一版的三家股息包只有不完整除息台账和空收益率快照。本轮为伊利、华域建立真实法定生命周期证据，并把 AC5 的层次直接放进原 Excel 的 `02_股利评估`，而不是只停留在配置 JSON。

- 新增 `scripts/collect_m1_dividend_lifecycle.py`。证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T052056Z/` 共封存 11 份官方 CNINFO PDF：伊利 8 份、华域 3 份；每份保留原 PDF、PDFium 文本提取、来源 URL、发布时间、解析器版本和 SHA-256。清单文件 SHA-256：`974cbf76a327014131e702269aec7279ce9b2398319ee4909f23540c3cdfc89c`。
- 伊利 `600887`：FY2024 末期普通股利 `1.22`，提议 `2025-04-30`、批准 `2025-05-20`、除息/支付 `2025-06-06`；FY2025 中期普通股利 `0.48`，除息/支付 `2025-12-17`；FY2025 末期 `0.90` 仍为 proposal；2025-2027 股东回报计划明确登记为 policy，不是预测；未识别特别股利，未宣称前瞻 payout forecast。
- 华域 `600741`：FY2024 末期普通股利 `0.80`，提议 `2025-04-29`、批准 `2025-06-27`、除息/支付 `2025-07-25`；FY2025 末期 `1.00` 仍为 proposal；长期政策背景为 2009 上市以来每年现金分红，2009-2023 累计 `30.830 billion`；未识别特别股利，未宣称前瞻 payout forecast。
- 两个 package 版本升级为 `20260923.2`：`600887-quality-compounder.json` 有 3 条历史记录、2 个 `READY` 快照和 1 个显式 `NOT_READY` 正常化情景；`600741-mature-manufacturing.json` 有 2 条历史记录、1 个 `READY` 已宣告快照和 2 个 `NOT_READY` 快照。可持续性均为 `LOW`，保留可分配现金、现金流、资本强度和周期敏感等真实阻断。
- `src/value_investment_agent/m1_application_workbook.py` 的股利页扩展为三张连续证据表：可持续性摘要、法定生命周期台账、当前/正常化收益率快照。普通/特别、事实/政策/预测、paid/proposed、current/normalized 均可直接在 Excel 复核；`NOT_READY` 不改成已知。
- 防回归测试 `tests/test_m1_application_workbook.py` 锁定 `02_股利评估` 必须展示生命周期、当前/正常化、特别股利与事实/政策/预测分层。本轮相关聚焦回归：`80 passed, 1 skipped`。
- 新 Application 证据：`runtime/m1-research-application-20260923T053028Z/evidence.json`，SHA-256 `4933cf172f8ba784921ad6146948bd3570a8bf26e56c0cba9026829f92e4b113`。
- 受保护整合发布：42 页，前 6 页为 M1 Application，原 36 页 worksheet XML 逐字节未变；候选及发布 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea`。发布前收据 `runtime/m1-integrated-dividend-20260923T053128Z/wps-integrated-receipt.json`，发布后 WPS 只读收据同目录 `wps-published-receipt.json`，回退原件 `runtime/workbook-backups/stage-frontend-ffa20fa0a1d34a8ab3b41c5cc95759d3/before.xlsx`。
- AC5 已从“PARTIAL 占位”推进为两家有证据的 `LOW` 可持续性结论；但正常化情景仍 `NOT_READY`，格力 `000651` 的 paid 除息/支付台账仍未补全。因此 M1 不因本段完成。

## 当前摘要：M1 W3 已形成 6 份 READABLE 研究档案，估值与产品闭环尚未完成

2026-09-23 已完成 M1 W1 样本与方法预登记、W2 的工程边界，并推进 W3 真实研究档案。当前结果是 `M1 IN_PROGRESS`：已形成 6 份绑定官方原件、反证和下一事件的可阅读研究档案。`READABLE` 仅表示研究已完整呈现且未知项显式可见，不等于估值完成、股息通过、价格合理或可交易。

| 核查项 | 当前事实 |
| --- | --- |
| 新合同 | `research_run_contract.py`、`research_input.py`；版本化 descriptor 为 `m1-fixed-sample-input-v1` |
| PIT 边界 | 分别保存 report/research/valuation/available/computed；拒绝日期掩盖、未来可用时间、未来报告期、来源在可用边界后发布/抓取；三家真实披露边界 replay 已生成 |
| 假设绑定 | 登记 assumption 必须命中实际 `facts.scenario_inputs`；不一致记为 blocker，不生成订单 |
| G3 边界 | `ResearchValuationApproval` 绑定模型、版本、估值日期和结果 SHA-256；旧 `case.valuation_status` 不再自动通过 G3 |
| 依赖失效 | batch 同时比较输入 SHA-256 与 dependency SHA-256；model/parser/scan/profile/requested-model/rule 变化会重跑或隔离失败 |
| 坏输入隔离 | 坏 descriptor、未知 Profile、未来 availability 只进入 `input_failures`，不终止同批其他公司 |
| W1 样本登记 | 20 家分层预登记账在 `config/m1-fixed-sample-preregistration-v1.json`，覆盖原3家、3画像、同画像第二家、不支持、资料不足和风险反例 |
| W1 方法与停止规则 | 来源、字段、深度、预算、20家上限、3次证据尝试后暂停、不伪造 READY、`action=no_order` |
| W3 共享建造器 | `m1_provider_dossier.py` 统一 schema、必需维度、证据 ID 引用、原文件 SHA-256 与 latest pointer 发布 |
| W3 六家证据档案 | 格力 `000651`、五粮液 `000858`、兖矿 `600188`、伊利 `600887`、海尔 `600690`、华域 `600741`；均绑定官方 PDF、来源 URL、发布时间、报告期与 SHA-256 |
| READABLE 语义 | complete 研究章节允许保留显式 `UNKNOWN` 维度；`MISSING/NOT_STARTED/BLOCKED/PARTIAL` 仍阻止可读性；READABLE 不等于估值完成或交易就绪 |
| W3 报告状态 | 20 家：`READABLE=6`、`PARTIAL=0`、`BLOCKED=3`、`NOT_STARTED=11`；全部保持 `action=no_order` |
| 聚焦测试 | 本轮 M1/Research Application/股息/报价相关回归 `80 passed, 1 skipped`；股息页新增 AC5 分层防回归测试 |
| 全量离线套件 | 历史结果为 `2054 passed`、`6 skipped`、`1 failed`；本轮在首个旧失败处停止，失败仍为 `test_moutai_current_valuation_admission.py` 的 `daily_simulation_policy_implemented=false`，与本次 M1 股息文件无依赖 |
| 本地产物 | `runtime/m1-research-dossier-candidate-latest.json`、`m1-research-application-latest.json`、`m1-pit-source-replay-latest.json`、PostgreSQL replay 收据与 Application Excel 候选；原 WPS 工作簿已受保护发布为 Hash `64989f1461a156d9f1a3955fb2da6b07b3d65c4a4c72129037fd1117586b1cea` |
| 安全边界 | 未连接生产 PostgreSQL/服务器/PTA，未改 WPS 原表，未生成订单或仓位 |

六家 `READABLE` 档案的维度会显式保留 `UNKNOWN`，研究缺口继续显示未审计、ROIC、正常化利润、法人层级现金和模型输入等问题。W3 仍要继续补齐跨模型情景估值、股息可持续性、报价/事件桥接、隔离 PostgreSQL 冷启动 replay 与原 Excel 安全发布；没有这些验收，不能宣称 M1 完成或初步投资就绪。

## M1 格力股息生命周期与 AC 事实矩阵：2026-09-23

本节补齐 AC5 第三家、用更新后输入包重跑 AC8，并把 AC1-AC10 固化为可核对的事实矩阵。所有状态仍是 `action=no_order`。

- 格力 `000651` 新增两份官方派息实施原件：FY2024 末期 CNINFO `1224534765.PDF`、FY2025 中期 CNINFO `1224936369.PDF`。分布包升级为 `package_version=20260923.2`。
- 格力生命周期现在为：FY2024 末期普通股利 `2.00` 已支付，批准日 `2025-06-30`、除息/发放日 `2025-08-29`；FY2025 中期普通股利 `1.00` 已支付，批准日 `2025-11-24`、除息/发放日 `2026-01-23`；FY2025 末期 `2.00` 仍为提议，未批准。无特别股利，无前瞻支付预测。
- 股息快照：trailing paid `3.00 / 38.18 = 0.07857517...` 为 `READY`；声明提议 `2.00 / 38.18 = 0.05238345...` 为 `READY`；正常化情景仍 `NOT_READY`。
- 格力可持续性结论为 `LOW`，不是“可维持”或投资依据；财务公司、受限现金、金融资产与法人层级可分配现金仍未拆通。
- 证据目录 `runtime/company-research/m1-dividend-lifecycles/20260923T055500Z/`；清单 SHA-256 `41f2114f7261370984e0219a8ec13aba658ff6f7b32af2b97c2ae7430b97c965`。两份新 PDF SHA-256 分别为 `8d4b488560f9d3ec81c9349757cda9d9bdee4cdbbecb97911761e2f6a93b4b64` 与 `89ab10370d6601c698426eb6a37dba664687ca03ee59a46208e104068d62d3dd`。
- 更新后的三公司 Application 与 42 页集成工作簿再次发布：原 36 页 XML 逐字节保留；发布后 WPS 工作簿 SHA-256 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`。候选、备份与发布前/后 WPS 收据均在 `runtime/m1-integrated-dividend-20260923T055026Z/`。
- AC1-AC10 正式状态与证据见 [m1-acceptance-fact-matrix-20260923.md](m1-acceptance-fact-matrix-20260923.md)。最终：AC1-AC10 `DONE`；G3 研究批准延后到 M3，事件材料性复核延后到 M5，Excel 视觉确认延后到 M6。
- 后续里程碑才需要逐项完成的 G3 估值审批、CNINFO 事件重要性阅读和 Excel 可用性检查见 [m1-human-review-checklist-20260923.md](m1-human-review-checklist-20260923.md)。六份档案的机器可读深度已抽查，人工质量复核可保留，但不阻塞 M1。
- 收束后聚焦回归 `82 passed`；`compileall` 与 `git diff --check` 通过。当前 WPS 工作簿 SHA-256 仍为 `a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`，未再改动。
- 新增可重复执行的本地验收审计器 `scripts/audit_m1_acceptance.py`：只读核对 dossier、输入/估值/股息包、PIT replay、PostgreSQL 冷回放与 WPS 发布收据，并可选重跑 AC1/AC2 回归。审计器 schema v2 区分 M1 机器验收与 M3/M5/M6 后续人工复核；最新运行收据见“机器复算入口”节。
- 新增 `scripts/render_m1_human_review_packet.py`，从冻结 Application/事件扫描包生成 [m1-human-review-packet-20260923.md](m1-human-review-packet-20260923.md)：当前 24 条待人工阅读公告均给出本地原件、CNINFO 原件和 SHA-256 前段，另有三家公司 G3 决策表。生成器只读，`action=no_order`。
- 当前脏工作树按 GitHub offline-core 同款 30 个测试文件重放：`226 passed`。系统默认 `C:\Users\we\AppData\Local\Temp\pytest-of-Ming` 因 Windows 权限拒绝导致 4 个 setup error；使用项目内 `runtime/pytest-tmp-ci-full` basetemp 后全部通过，未修改系统目录权限，未把环境错误写成代码失败。

M1 已在上述口径下完成。`VALID` 或 `READY` 仍不能写成价格吸引力或交易准入；条件研究、正常化股息缺口和后续人工复核状态全部保留。

## M1 Application 与三公司候选展示：2026-09-23

本轮没有把 M1 标为完成。当前三家公司均保持 `action=no_order`，输出状态均为 `COMPLETED_WITH_BLOCKERS`。伊利事实层的三条重复门禁已拆开：前瞻 ROE 保持为登记的低置信度假设，ROIC 缺口保留在研究反证/人工批准项，beta 缺失移到 `cost_of_equity` 假设；伊利因此得到 `conditional_research_only` 的 Bear/Base/Bull 与 `READY` 价格桥，但仍没有人工 G3 批准，不能形成价格吸引力或交易结论。华域股利能力说明改为“提议分配，尚未批准/支付”，不再把未经审计的中报语境误写成分母。

- 新增三公司版本化股利包、共享加载器、有界反向估值与批量 Application runner；新候选展示层只读取已有 Application/股利/反向估值结果，不在 Excel 重算。
- 本地产物：`runtime/m1-research-application-latest.json`、`runtime/m1-research-application-workbook-20260923T033001Z/m1-research-application-candidate.xlsx` 及 manifest/WPS 只读收据。
- WPS 云盘只新增独立候选副本 `M1_三公司研究Application候选_20260923_033001.xlsx`，未修改原工作簿。
- WPS `ket.Application` 实际路径 `D:/WPS Office/12.1.0.28505/office6` 以只读方式打开、重算、扫描公式错误后哈希不变：`status=passed`。

## M1 隔离 PostgreSQL 冷启动 Replay：2026-09-23

本地没有启动 Docker Desktop、常驻服务、生产 PostgreSQL、SSH 或 PTA。本轮使用项目内忽略的 `.m1-postgres-venv` 中 `postgresql-binaries==18.6.0`，在 `127.0.0.1` 随机端口创建一次性 PostgreSQL 18.6 集群，从三份真实 M1 valuation/distribution 配置完整执行共享 Application，停库后从同一数据目录冷启动并逐条恢复验证。

- 新增 `src/value_investment_agent/m1_postgres_cold_replay.py` 与 `scripts/run_m1_postgres_cold_replay.py`；只允许 loopback 地址，不接收外部 DSN。
- 首次运行写入 28 个 typed research artifacts、28 个 head、87 条 reference；三家输出均为 `COMPLETED_WITH_BLOCKERS`、`action` 为 `null` 或 `no_order`，无订单或仓位字段。
- 冷启动后 28/28 artifact 通过 SHA-256 与 canonical payload 语义相等校验；首轮和冷启动 artifact fingerprint 均为 `5635429903544517fccb41826a62c1986a3ae855771d49c4cc3c79e248568a8f`。
- 真实验收收据：`runtime/m1-postgres-cold-replay-20260923T040611Z/receipt.json`；收据 SHA-256 `8ec0f2bfbd18e16f8dc7d0ac647c8cbb6df76443945ef59104b2510d0f16f4f8`，状态 `PASSED`。
- 隔离环境定向测试：`2 passed`；普通离线环境无本地二进制时按设计 skip，不把本机真实验收与 CI synthetic fixture 混为一谈。

## M1 启动前审查基线（2026-09-22）

本轮任务是系统审查与长期目标收敛，只修改文档，没有实施 M1、修改业务代码、Excel、数据库、生产任务或服务器。新增 [LONG-TERM-GOAL.md](../LONG-TERM-GOAL.md) 规划六个大 Milestones；唯一待启动长期目标为 M1-FIXED-SAMPLE-RESEARCH-WORKBENCH。原独立 C4 adapter 建议被吸收为 M1 输入完整性工作包，不再单独作为产品目标。

以下是本轮重新观察的状态；后面 C0-C3 的测试数、Hash、旧缺口和“下一任务”属于各阶段历史，不覆盖本摘要。

| 核查项 | 本轮事实 |
| --- | --- |
| 开始 Git HEAD | `494d0857c7edb4b76b0527d773065013b7abf2d1`，2026-09-22 20:33:40 +08:00，C3.14 close governance and record green CI receipt |
| 本地/远端 | GitHub main 同一 SHA；开始工作树干净；本轮文档为新增未提交工作，未推送 |
| 当前 HEAD CI | [35727941981](https://github.com/MingMingLiu0112/value-investment/actions/runs/35727941981) 两项 offline-core/postgres-integration 均 success；不是只引用前一提交绿色收据 |
| 本机 CI 同款文件清单 | Python 3.13，`pytest -q -p no:cacheprovider`；173 passed、4 skipped，2.48s；4项因未配置 `C3_TEST_POSTGRES_DSN` 跳过，未连接生产 |
| 冻结历史验收 | `test_moutai_valuation_export.py` + `test_three_company_unified_acceptance.py`：9 passed，0.77s |
| 真实 runtime replay | 调用 `run_three_company_replay` + InMemory Repository：all_semantics_matched=true、no_order；未生成新runtime收据/改latest |
| 三公司 | 茅台conditional/低置信度、VALID/READY桥接；美的/神华not_ready；三家production valuation均NOT_AVAILABLE，cash return均PARTIAL |
| 原Excel当前Hash | `4EA4AB6F291E0D3C8838A1729007C8B29D0825CCF7CA6459BBD16257BEC0188E`，12,138,778 bytes，mtime 2026-09-22 17:30:45；不同于历史冻结Hash，不能回退覆盖 |
| 未验证 | 最新生产数据原件、生产DB/服务/计划任务、全量历史测试、WPS界面与公式重算 |

当前 workflow 本机实测是173项，不沿用旧文档176项。CI PostgreSQL的4项使用自包含fixture；本轮真实runtime是在内存repository重放。两者都不证明生产PostgreSQL已迁移或真实市场研究有效。

### 新发现与复现

- `research_application.py:292`：显式spec.as_of可掩盖facts日期不一致。以既有测试fixture令case/spec为2025-12-31、facts为2024-12-31，仍返回outcome，valuation日期为2024-12-31。
- `research_application.py:266`：可将2025年输入的结果available_at设为2024-01-01；完整PIT约束尚未建立。
- `research_batch.py:310`：相同input hash而rule_version从v1变v2，仍得到UNCHANGED。
- 登记AssumptionSet并不自动证明它驱动了facts.scenario_inputs；G3仍读旧case状态。需在M1同一可信输入链修正/证明，而不是继续堆接口。
- Manifest-driven input adapter和Application结果到Excel仍缺；旧PE/PB screen仍可从CLI调用，必须标legacy后迁移，不能声称已经退役。

复现使用既有测试fixture和纯内存对象，无业务文件改动。明确异常原因和证据在LONG-TERM-GOAL第1节；本轮没有为了让状态变好而修代码。

### 成熟度与下一目标

当前是 L0工程基础已具备、L1研究工具早期/PARTIAL，不是L3决策支持或L4组合支持。架构方向总体对齐；主要风险是平台验收领先于真实研究/产品可用性。
M1计划交付20家分层入组、6家深研、真实跨模型/股息/当前桥接、冷启动replay及原Excel共同展示，具体质量与停止条件以current-stage-goal为准。M2全市场、M3决策/Entry/Journal/一致性、M4组合、M5事件、M6生产验收均NOT_STARTED；本轮没有启动它们。

## 历史阶段记录（保留原验收，不作为当前任务队列）

## C0 已冻结

C0-PRICE-BRIDGE-INTEGRITY：`PASSED_FOR_FREEZE`。

- 提交：`df4d343 C0-price-bridge-integrity`。
- 新增 `QuoteSnapshot` 与显式 `bridge_with_quote()`；收紧 ModelValidity、PriceBridgeResult、JSON 恢复和下游聚合。
- `current_research_status_from_payloads()` 不再用估值 symbol 覆盖冲突身份。
- 定向回归 47 项、Core Gate 102 项通过；旧 runtime 合同显式重验，茅台 READY 恢复不静默洗掉冲突。
- 三公司 runtime Hash 与原 Excel Hash 未变。

C0 只修复共享工程合同，不表示研究、估值、股息能力、生产数据或价格判断已经完成。

## C1 验收基线

- C1 开始 HEAD：`df4d343726f0d49fd5570e30b075cc46faf859d0`，工作树干净。
- 未连接服务器、生产数据库或定时任务；未重做原始财报、行情或重大事项审计。
- 目标：固定样本准入协议与公共编排审查。

## C1 验收结果

C1-FIXED-SAMPLE-ADMISSION-ORCHESTRATION：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/fixed_sample_admission.py`，显式区分研究样本准入证据与估值推进证据。
- 新增 `FixedSampleAdmissionPolicy`、`FixedSampleCompanyAdmission` 和 `FixedSampleAdmissionReview`。
- 公共入口 `review_fixed_sample()` 对每家公司复用 ResearchGate、ValuationResult、ModelValidity、PriceBridge 和 CurrentResearchStatus 合同；不按 symbol 猜测 profile。
- 三家公司输出：

| 公司 | 编排合同 | 研究样本 | 有界价值 | 生产估值 | 显式决策 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | REUSABLE | ADMITTED_FOR_RESEARCH | CONDITIONAL | NOT_AVAILABLE | CONTINUE_CONDITIONAL_MODEL |
| 000333 美的集团 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | RESOLVE_MODEL_INPUTS |
| 601088 中国神华 | REUSABLE | ADMITTED_FOR_RESEARCH | NOT_AVAILABLE | NOT_AVAILABLE | PAUSE_PRODUCTION_VALUATION |

- 汇总状态：`engineering_orchestration_status=REUSABLE`，`production_valuation_available=false`。
- 所有记录均为 `human_confirmation_required=true`、`action=no_order`；不含仓位、订单、目标权重或实盘指令。
- 新增本地审查命令：`python scripts/review_fixed_sample_admission.py`。命令读取四个冻结指针，验证 Hash 后生成带 script/evidence Hash 的审查产物和 latest 指针。

验证证据：

- 新增防回归：`10 passed`，覆盖显式政策、条件估值不升级、空情景、缺研究证据拒绝、身份冲突、profile/model 类型失配、公共编排、序列化和三公司冻结回归。
- 更新后的 Core Gate：`112 passed`。
- 全量测试：`1901 passed, 1 skipped, 5 failed, 18 warnings`。5 个失败均是旧验收测试硬编码茅台报价日 `2026-09-21`；后台日更在 C1 验证期间将 current 指针推进到 `2026-09-22`。本轮未改历史验收测试或回退 runtime 日更产物。
- `compileall` 通过；`git diff --check` 通过。
- 美的、神华及研究卡 Hash 与冻结记录一致；茅台 current 已被后台日更推进，Hash 为 `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`。原 WPS 工作簿 Hash 仍为 `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1`。
- 未改动估值参数、原 Excel、生产数据库、计划任务或服务器服务。

## 阶段语义

三公司统一工程/Excel MVP、C0 和 C1 均通过冻结。C1 的 `REUSABLE` 表示共享审查入口可用，不表示任何公司生产估值或现金回报结论可用。

| 维度 | 600519 贵州茅台 | 000333 美的集团 | 601088 中国神华 |
| --- | --- | --- | --- |
| Engineering Complete | READY：研究、估值和 C0/C1 共享合同可用 | READY：FCFF 算术与拒绝边界 | READY：周期算术与拒绝边界 |
| Research Complete | PARTIAL：商业/财务材料与论点存在，G3 未通过 | PARTIAL：事实范围 MODEL_NOT_APPLICABLE | PARTIAL：正常化假设和财务门未通过 |
| Valuation Complete | PARTIAL：低置信度 conditional_research_only | NOT_READY：无三情景值 | NOT_READY：无三情景值 |
| Dividend Research Complete | PARTIAL：有历史分红及分配交叉检查 | PARTIAL：有历史派息与部分财务材料 | PARTIAL：有派息与周期候选材料 |
| Production Data Ready | 2026-09-21 快照 READY；未验证 09-22 当前生产 | PENDING_EXTERNAL_DATA，并存模型适用性问题 | PENDING_EXTERNAL_DATA，并存未注册假设/输入问题 |
| Price Assessment Ready | NOT_ASSESSABLE：低置信度及研究门限制 | NOT_ASSESSABLE | NOT_ASSESSABLE |

三家公司完整 DividendSustainability 评估均未完成。

## 当前可追溯产物

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司研究卡 | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 茅台条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `4331175d74b692f6a449dd1c17afb775abd6596d178761bc004f7368d97636e7`（后台日更推进） |
| 美的未就绪结果 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 神华未就绪结果 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |
| 固定样本审查 | `runtime/fixed-sample-admission-review-latest.json` | `1dfe78e330ee45242d71a59a6888774408166fc215ca866816e4aefd6e535b4f` |

茅台估值日期为 2026-09-21，报价日已由后台日更推进到 2026-09-22；条件情景 403.44 / 478.43 / 571.25 元每股。此处仅描述研究模型，不是当前合理价或投资建议。美的、神华载荷日期为 2025-12-31，不能称作今日估值。

## 剩余风险与边界

- C1 是工程与准入协议验证，不替代生产行情、公告、重大事项或人工研究复核；当前价格评估仍为 NOT_ASSESSABLE。
- 后台日更会推进 current 指针；硬编码具体报价日的旧测试在日更后可能暂时失败，需在后续任务中把 current 回归改为对冻结快照的显式版本测试。
- 三家公司政策目前由 `scripts/review_fixed_sample_admission.py` 显式登记，属于受控 adapter；新增公司必须新增政策与证据，不能自动推断。
- 研究准入证据目前验证的是结构与 Hash 可追溯性，不是重新证明财务事实或论点内容正确。
- 固定样本协议尚未迁移到 PostgreSQL；runtime JSON 仍为当前可追溯中间产物。
- 通用多模型运行器与持久化注册表仍需在扩样本前补齐；最小现金回报研究合同由 C2 完成。
- 全市场漏斗、Web 前端和券商接入均未实现，不属于 C1 回归范围。

## C2 验收基线

- C2 开始 HEAD：`357e080b69edfe135eaabcd5d31dc7331e05b9d3`，即 C1 提交 `C1-fixed-sample-admission-orchestration`。
- 未连接服务器、生产数据库或定时任务；未改动估值参数、原 Excel、计划任务或服务器 PTA 服务。

## C2 验收结果

C2-MINIMAL-DISTRIBUTION-RESEARCH-CONTRACT：`PASSED_FOR_FREEZE`。

核心改动：

- 新增 `src/value_investment_agent/distribution.py`：`DividendRecord`、`DividendHistory`、`DistributionCapacity`、`DividendSustainabilityAssessment`、`DividendYieldSnapshot`、`DividendResearchResult` 与两个合法 yield 构建函数。
- `DividendRecord` 强制区分 proposed / approved / paid，并校验公告、批准、除息、支付和 known_at 的时序；`DividendHistory` 只接受 known_at 不晚于 as_of 的事实。
- `DistributionCapacity` 与 `DividendSustainabilityAssessment` 不依赖价格，按 ResearchProfile 识别；READY 能力及已知可持续性均不允许 UNKNOWN 置信度。
- `DividendYieldSnapshot` 只接受同证券 verified close quote，并强制 DPS / price / yield 可复算；当前收益率与周期正常化收益率是不同对象。
- `FixedSampleCompanyAdmission` 和公共入口 `review_fixed_sample()` 接受可选 typed `cash_return_result`，同时保留旧手工 status/explanation 兼容路径。
- `scripts/review_fixed_sample_admission.py` 使用同一合同读取已审查现金分配注册表和冻结研究/估值载荷，为三家公司生成 typed 结果。
- 旧茅台估值与三公司验收测试改为读取冻结的 2026-09-21 快照并校验固定 Hash，不再依赖 rolling current/latest 指针；干净 checkout 中这些冻结 runtime 快照缺失时显式 skip，不误报为当前生产失败。

三公司 typed 现金回报状态：

| 公司 | 历史分红 | 分配能力 | 可持续性 | Yield 快照 | 现金回报研究 |
| --- | --- | --- | --- | --- | --- |
| 600519 贵州茅台 | PARTIAL | PARTIAL | UNKNOWN | 1 | PARTIAL |
| 000333 美的集团 | PARTIAL | UNKNOWN | UNKNOWN | 0 | PARTIAL |
| 601088 中国神华 | PARTIAL | UNKNOWN | UNKNOWN | 2 | PARTIAL |

三家公司均仍是研究状态；有历史派息不等于分红可持续性或现金回报能力完成。公共审查保持 `REUSABLE`、`production_valuation_available=false`、`human_confirmation_required=true`、`action=no_order`。

验证证据：

- Core Gate 同款离线清单：`124 passed`。
- 冻结历史验收：`tests/test_moutai_valuation_export.py` + `tests/test_three_company_unified_acceptance.py`：`9 passed`。
- Distribution + 固定样本 + 价格桥接 + quote 定向回归：`74 passed`。
- 新离线三画像 typed 合同测试覆盖 600519 / 000333 / 601088 的 quality_compounder / mature_manufacturing / cyclical_cash_return，确认三公司复用同一合同且均为 PARTIAL。
- 审查命令成功生成：`runtime/fixed-sample-admission-review-20260922T101442190293Z`，evidence SHA-256 `022cfd2f501a358ff843799ec227a832d5a23a370cbd3238f238f93f2f4ed0d0`。
- `compileall` 与 `git diff --check` 通过。
- 全量历史测试尝试运行至约 83% 后停在旧网络/外部 fixture 路径，未作为 C2 验收依据；C2 只冻结上述离线 Core Gate 和定向回归证据。

## 剩余风险与边界

- 本任务是共享领域合同和 fail-closed 类型验证，不是三家公司的股息可持续性研究、生产数据核验或未来派息承诺。
- 现金分配注册表目前是受控 JSON adapter；茅台 fiscal attribution、提案/批准日期、税费和结算时点仍列为显式 blocker。
- Distribution 对象尚未迁移到 PostgreSQL；runtime JSON 仍是当前可追溯中间产物。
- ShareholderYield、完整 distribution_profile、行业阈值和回购/稀释口径未实现，不属于 C2。

## M1 Gree dividend lifecycle completion: 2026-09-23

See `docs/m1-gree-dividend-lifecycle-20260923.md` for the complete receipt.
The Gree `000651` distribution package now has official CNINFO implementation
evidence for FY2024-final and FY2025-interim dividends, both paid records now
carry verified ex/payment dates, and the workbook includes READY trailing and
declared yield snapshots. The normalized scenario remains NOT_READY.

Published workbook SHA-256:
`a62a6ae634ea949db36c3c209278515e2ee66ef3a61aaa25d59d2051d5954d58`.

## C3 验收基线

- C3 开始 HEAD：`d658b92 C2-minimal-distribution-research-contract`；工作树开始时的改动仅包含 C3 的 W1 治理校准。
- C2 的唯一建议后续任务“最小 Distribution 合同迁移到 PostgreSQL”已被 C3 吸收，但 C3 范围扩大到通用 Research Artifact 合同、Repository、Runner、Registry、Manifest、Batch、CI 与三公司 E2E。
- 数据库安全边界：`.env` 中的生产 `DATABASE_URL` 在本阶段不得连接；只使用 disposable/local/test PostgreSQL 或 GitHub CI 一次性实例。

## C3 验收结果

C3-RESEARCH-PLATFORM-FOUNDATION：`PASSED_FOR_FREEZE`。

提交序列：

```text
7903933 C3.1 governance and research artifact contract
6eee08e C3.2 repository and typed artifact round-trip
a89e269 C3.3 frozen runtime parity importer
b787b3e C3.4 profile-driven application research runner
365d845 C3.5 explicit valuation model registry contract
2bfe065 C3.6 versioned fixed sample policy manifest
33590bb C3.7 failure-isolated research batch contract
9d9231b C3.8 offline core and disposable postgres CI
13c5b03 C3.10 three-company frozen replay receipt
412564a C3.11 presentation boundary and expansion verdict
957243f C3.12 isolate postgres CI from ignored runtime data
fc49ab7 C3.13 align postgres import assertion with review scope
```

W1-W12 结果：

- W2-W3：新增 `sql/20260922_research_artifacts.sql`、`research_artifacts.py`、`research_artifact_codecs.py` 和 `research_artifact_repository.py`。新表 append-only，与旧混合语义 `valuation_results` 分离；round-trip、版本 head、Hash 与 fail-closed 均有测试。
- W4：`research_runtime_import.py` 把三公司 frozen runtime 核心 artifact 迁入 repository，输出 source path、source/database SHA-256 和 restored semantic status；缺失 `model_validity` 显式记为缺失，不伪造。
- W5：`research_application.py` 使用显式 `ResearchRunSpec`，按 Profile -> Router -> Model -> Validity -> PriceBridge -> Distribution -> CurrentStatus -> Repository 编排，不按 symbol 猜模型。
- W6：`valuation_router.py` 已表达三种 Profile 与三种模型/Facts 合同；未知 profile 为 `UNSUPPORTED`。
- W7：三公司 admission policy 迁入 `config/fixed-sample-manifest.json`，禁止交易键，loader 做 schema 与 profile/model 校验。
- W8：`research_batch.py` 隔离单公司 GAP/FAILED/UNSUPPORTED，支持 run_id、rule_version、时点和幂等输入 fingerprint。
- W9：GitHub Core Gate 保持离线，另增加 disposable PostgreSQL job；本地未使用生产 DSN。
- W10：`research_e2e_replay.py` 完成三公司 Manifest -> ResearchRunSpec -> Application -> Repository -> Batch replay。真实 frozen runtime 结果为 `all_semantics_matched=True`、`action=no_order`。新增命令行 `python scripts/run_three_company_research_replay.py`，输出独立 JSON 审计收据。
- W11：Application/Presentation 边界审查通过并记录技术债，见 [application-presentation-boundary.md](application-presentation-boundary.md)。Domain/Application 不依赖 Excel 或 PostgreSQL schema；旧 Excel publisher 尚未切换到新 Application result。
- W12：Expansion Readiness Verdict 为 `NOT_READY`，原因见 [fixed-sample-expansion-readiness-review.md](fixed-sample-expansion-readiness-review.md)。核心 pipeline 可复用，但缺少 manifest-driven facts/assumptions/quote input adapter，且 replay adapter 仍含茅台 symbol 专用分支。

验证证据：

- Offline Core Gate 全清单：`176 passed`。
- 新增三公司 replay 自包含 fixture：三种 Profile、三种模型、`no_order`、美的/神华 `not_ready`、神华 current/normalized yield 区分和 Hash 篡改 fail-closed。
- PostgreSQL integration 在本机无 disposable DSN，`4 skipped`；GitHub CI 中由一次性 PostgreSQL service 验证 migration、repository round-trip、frozen runtime import 和三公司 replay。最终验收运行 `35727542158` 的离线 Core 与 disposable PostgreSQL job 均为 success。
- 本机真实 frozen runtime 命令验证：`all_semantics_matched=True`、`action=no_order`、收据约 193KB。
- `compileall` 与 `git diff --check` 通过。
- 未连接生产数据库、未修改旧 `valuation_results`、未改动原 Excel、未调整估值参数、未触碰服务器 PTA 项目或计划任务。

## C3冻结时的后续建议（历史，已被M1吸收）

下面保留C3当时的建议，不是当前执行指令。当前唯一待启动目标见本文开头与current-stage-goal.md；adapter只是M1的前置工作包。

```text
NEXT TASK: C4-MANIFEST-DRIVEN-FIXED-SAMPLE-INPUT-ADAPTER
```

先移除三公司 replay 中的茅台 symbol 专用分支，建立 versioned per-company input descriptor，再以离线 fixture 和 disposable PostgreSQL replay 验收。验收前不新增第四家真实公司，也不自动扩样本。
