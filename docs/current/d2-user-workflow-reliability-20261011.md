# G/I：只读研究恢复、历史与错误隔离实证

任务附件 `9ce4f59b-b90a-414b-bf24-ec252c475a75`，基线 `6fd7ed9cb3b0a4034dbc5084095bebffab31b4f4`。本包只新增 `runtime/d2-user-workflow-reliability-20261011-v1/` 与本文；未改共享 src/tests、旧收据或正式研究。复用 v3 的 815 项恢复归档，没有重新加密/归档、生成密钥、重算估值或候选。

## 实际通过

- 815 项已有恢复条目重新 hash 核验通过；消费后冻结恢复资产 hash 仍一致。
- 两家公司选定 v5 候选、typed ResearchCase、decision DAG、空白人工 intake 均实际消费通过。候选生成日 2026-10-11，财报基准 2026-06-30；没有继承批准或把旧财报变成新事实。
- 从恢复代码调用既有 `_render_pending_candidate_review` / `_render_report`，生成真实中文可读报告四份。600519 条件值 437.66/587.88/812.27，600887 9.80/10.08/10.30，仅原候选显示，无新公式或估值运行。正式状态 NO_ACTION，价格未准入，仓位为空。
- 第一次报告生成后，结束子进程，再启动新子进程重新核验来源及报告字节；四份报告逐字一致。此“断点”是已有输出的来源复核，不是假称正式日报/签名消费自动续跑。
- publication 显式路径映射消费继续 PASS，quote floor 2026-10-09；当前 C-drive Excel 与指针仍匹配 `83908b2513e1d9cf7dbdc17f0ad6f56b7a213e94f52a3bb0398af60339ab5b29`。
- 恢复 Excel 只读解析通过，62 张总 sheet、7 张 managed pages 实际可读。55 张原有 sheet 与新增 managed pages 的口径不能混同。openpyxl 未保存/重算；本项不是本轮 GUI/WPS 或用户体验验收。

可直接阅读的新产物：

- `runtime/d2-user-workflow-reliability-20261011-v1/600519-candidate-review.md`
- `runtime/d2-user-workflow-reliability-20261011-v1/600519-readonly-daily-report.md`
- `runtime/d2-user-workflow-reliability-20261011-v1/600887-candidate-review.md`
- `runtime/d2-user-workflow-reliability-20261011-v1/600887-readonly-daily-report.md`

运行用恢复 src/PYTHONPATH，原 repo 文件、网络和 subprocess 负向探针均拒绝。仅为 Python 应用层 audit hooks，不是 OS 沙箱。复核脚本自己的输出目录被明确允许写入，没有原 repo 数据回退。

## 有意义的错误与断点验证

候选 hash 错误和 OSError 注入均被原 verifier 拒绝；600887 健康候选仍通过。调用既有 `run_daily_batch`，将真实恢复 candidate verifier/renderer 作为只读回调：600519 故障 RUN_FAILED，600887 报告/receipt 完整保留；新目录重试两者通过。没有调用 ResearchApplication，不把此回调试验冒称完整 daily CLI 或新研究运行。

同目录 daily/batch 再执行被 FileExistsError 拒绝，证明已有证据不会覆盖。现有 batch 支持公司间错误隔离和新目录重试，没有自动续写旧目录合同；这不是需要再造调度系统的理由。

**实际代码缺口：签名消费完成标志与历史追加不一致。** 当前 `research_reviews.py:304-306` 先写 consumption receipt，最后才写认证历史；`237-251` 又拒绝任何已存在输出目录。若最后一次 history 写入中断，会留下 receipt/可能的审批 packet，但 authenticated head 未追加，同目录重试拒绝。

已分别用冻结代码和当前代码实际注入最后一次 OSError，重现“receipt 存在、history 不存在、重试拒绝”。当前模块 SHA `cc212c355149dbf2b03a5504e01db0839fca95e0eae2fbb514ea33d52e5099cb`。为不生成新钥或伪装真实审核，此验证仅 stub 认证完成后的 I/O 边界，reviewer=null、approval=None；所有 `fault-test-root` / `current-code-write-fault-root` 内的 consumption-like receipt 都是显式合成故障工件，不是合法审核证据。没有主张批准绕过。

最小必要工程：在现有 consumer 内明确完成标志只在 packet/history 所需写入完整且复核后成立，并给相同 source/hash 的未完成输出一个 fail-closed 复核/重试合同；不可把半成品视为成功，也不可删历史或覆盖旧记录。复用既有 signed-response fixtures，必要测试只覆盖 history append 失败、receipt 写失败、重试与已有 authenticated head 一致性。没有提出新审批协议。共享代码修改需由 Root 集成，本包未实施。

另外恢复入口边界：815 中有 `scripts/current/run_daily_trade_assistant.py`，但没有 `config/daily-trade-assistant-v1.json`。所以本包证明真实来源核验后的只读候选/报告入口，不宣称正常注册 CLI 在恢复目录完整运行。`--report-only` 仍是“研究运行而不依赖 Excel runtime”，不是只读存量 case 模式；本包未调用它以避免新模型运行。若 Root 要验收完整原 CLI，应先精确绑定注册 config 及其依赖，不生成替代 config。这里没有因缺该 config 重做归档或扩大收集。

## 签名与历史：仍不能宣称通过的事项

实际 `runtime/research-review-responses/*/*.json` 数为 0，恢复 authenticated head 为 null，正式 trust registry 空。空白 A 回应和 intake 不是签名历史。真实 signed-history 完整恢复尚无实际资产可验证；unsigned/unpinned 输入实际拒绝，没有模拟真人登记或审核。

既有 signed-response 测试已覆盖 signature tamper、unpinned、predecessor、forged history、scope/hash、revocation、expiry 等合同；本包只读审查这些覆盖，没有运行会新建测试密钥的 fixtures，也没有把历史测试替代本次真实签名使用。

四份历史 snapshot 一律保留 NOT_AGENT_ELIGIBLE：旧 S5 v5、旧 S5 v7、000651、600741。两个伊利 pending-candidate workbench 合格，不能因此升级它们的旧注册 workbench。合法原件 hash 可读、旧 index 原件确实保存、旧生成代码身份不完整，是不同结论；不删除失败、不改 metadata。

## Hash 与验收界限

| 产物 | SHA-256 |
| --- | --- |
| verification-manifest.json（30 项新工件） | `1e117a2f680aa6f4f309446893f1531b595bb2eaf324de229bc6e00cd0afaa55` |
| receipt.json | `f63b9834575466ce2b5ebc2fcf4d9970332a025d95edbd604dbc26804d7a7c38` |
| batch-isolation-verification.json | `14699584246f14fe38d86f0f0c08b29b39e624a5227cf521320319d4863423f5` |
| current-history-write-verification.json | `ba4484cd61dca33deafbe1a36cc5dd232d955570d39cf9065289ef48f52bdf82` |
| 复用的 v3 receipt | `1e6a8c05a260ab25b3ceb1fe7b4cfdeafa31b9cf0b3d1d9fd6e9b0ac9859d819` |

详细报告/script/output hash 全在新 manifest。首次+新进程复核耗时 7.809819 秒；Excel 解析 0.212856 秒，不作为系统恢复时间。

当前可交付：来源精确绑定的两公司只读研究、报告、审核准备与安全错误隔离。未交付：真人签名历史恢复、正式 daily 自动断点续跑、完整正常 CLI 恢复、GUI 用户验收。HumanReview != AgentReview，ConditionalValue != ApprovedFairValue，PriceObservation != PriceAdmission，action=no_order。生产/DB/offsite=false，systemRTO/RPO=null；无审批、仓位、20 真实会话或 INITIAL_ASSISTED_USE 声明。

## Root 后续实际产品验证

Root 将默认 update 切到选定 v5 package 后，伊利实际 preflight 暴露旧 index HASH_MISMATCH（预期 f68b，当前位置实际 1b26）。Root 使用既有 daily-original-recovery-v1 scoped manifest，将新 package 绑定到明确保留且精确 hash 匹配的 index 原字节，未覆盖旧 index。本包未生成替代原件。

后续 `runtime/daily-trade-assistant/20261011-user-workflow-actual-update-v1/batch-receipt.json` 已实际生成：600519/600887 均 RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS、研究日期 2026-10-11、建议 NO_ACTION；10/9 行情为 HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY。此前产品 preflight 缺口已由 Root 修复并完成实际 update。此后续原 repo 运行不能反向宣称冻结 815 恢复目录已经补齐正常 CLI config，也不升级四份历史 snapshot。

签名消费 I/O 缺口交由 KierkegaardB 修复；本包原故障证据保留，尚不把新的工程测试或空 trust registry 宣称真人签名历史已验收。

## F 展示区分与安全发布验证

独占 successor：`runtime/daily-trade-assistant/20261011-user-workflow-preview-v1/`。继承原 v6 `publication_input_binding` parent chain，旧收据与旧经济包不改。formal company valuation/price/decision、研究日期和生成日期不改，不运行 ResearchApplication 或重算候选。首页新增无正式准入与人工审核流程摘要；公司主区明确“保留基线（未替换为v5候选）”；下方两公司 10/11 条件值区标题明确“选定v5待审候选”。v7仅后续版本比较，不继承审批。

使用 bundled artifact-tool、已成功运行一次 edit marker。复用 shared renderer 原内容，仅在新 .tmp 生成副本中修改 root 定位与三个展示标题；共享 renderer/domain 未改。第一次副本使用未规范化 Windows root，路径 containment 检查拒绝，未输出工作簿；失败 patch 记录保留。v2副本以 path.resolve 规范化 root 后输出并写完整 artifact receipt，公式错误扫描为0。Node 返回 exit1但导出/receipt完整，后续独立 hash、数值、原页、source 与真实 WPS 检查全部通过；不以该退出码本身冒称成功。

数值完整比较：七管理页所有24个 numeric cell 值按原序列保持一致（3基线条件值+21备选/候选条件值）；21来源条件值另行精确核验。既有保护集成证明55原页保持，62 sheet全部保留。publication source union实核358来源；handoff实列353来源。图像使用实际 WPS 7份PDF共34页，5张联系页逐张检查，并检查首页、公司首屏、公司末页大图。首页一页可读，无artifact HYPERLINK错误文本；真实23次内部导航通过，外网点击0；native只读与前后文件hash一致，可读性检查无clipped rows。长公司研究内容保留，不伪装为精简新经济研究。

| F 工件 | SHA-256 |
| --- | --- |
| 保护稿 | `b630e0198e10d6a8e6bac7a1b4ea91480fd96d51506c22019216aba1b3af7621` |
| 原 Canonical / parent | `83908b2513e1d9cf7dbdc17f0ad6f56b7a213e94f52a3bb0398af60339ab5b29` |
| 新 publication input | `cd25804800f0a319b4a584edf09af50760a966c4b8017c6d6f79333e98a8e320` |
| canonical-preservation.json | `2ac1fca8cc8e60461c795758126cb24e889e230643f02f3fb5d9f0cabd5e7513` |
| source-bindings.json | `022fab45c9f0b8ade1be4545f40aa6804965dac2c1e7b778b72ba2dba65ba734` |
| visual-review.json | `d5177121ec0548fb532acddcbaaf6df1e0c601c37fc56527f7b9b3d792abbeb0` |
| Root 实际 update batch receipt | `fc79c8bf4ab4fa0e9a607a1cd3eba862efa56557554a3515500a6359ea54ae3f` |

已运行既有 publisher `--verify-only`：VERIFIED_RESEARCH_PREVIEW_ONLY，current_price_bridge=NOT_ADMITTED、strict_pit=NOT_PROVEN、M7_FINAL_USER_ACCEPTANCE=NOT_PASSED、INITIAL_ASSISTED_USE=NOT_REACHED。Root 已检查 native 中文链接首页并明确授权继续发布；共享 config 即将更新通知已发送。实际发布与 pointer最终校验结果后附。

## F 实际发布与最终 pointer

已完成一次安全发布，未重复发布。Canonical 路径保持 `C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪/A股价值投资_Agent前端智能跟踪模板.xlsx`，实际 SHA 为上述 `b630e019...b3af7621`。旧 83908 完整备份到 `runtime/workbook-backups/canonical-before-reviewed-research-20261011T151242Z-e967767b.xlsx`，未覆盖旧收据。

publication receipt：`runtime/publication-receipts/canonical-reviewed-research-20261011T151242Z-e967767b.json`，SHA `072b6144f9601d9c7d2a96b6be7008c11f5768ddde1e404c6af4fb7b13370f98`。已发布 Canonical 后台 WPS 复核完成，7份PDF及只读 receipt 均存在，SHA前后相同；23次内部跳转再次通过。实际已发布 native receipt：`published-native-review/receipt.json`，SHA `29d252a5d71f2cb0da84e4c10746a5285c0f8f02e609a67712d348607218d8ef`。

已通知 Root 后使用既有 registration 流程更新 `config/current-trial-workbook.json`。新 pointer SHA `ca726d4e6f2d6c16bcf383ea38396c7872d00764234cca12475d93070bd25bc5`，状态 PUBLISHED_WPS_READONLY_VERIFIED；原 pointer 保存在新目录 `previous-current-publication-registration.json`。保留基线研究日期仍分别为600519 10/8、600887 9/22；选定v5生成日10/11独立记录，10/9行情仍 price_admitted=false，未把展示升级为研究/价格批准。

最终独立调用 `verify_workbook_publication` 通过，quote_floor=2026-10-09，Canonical/pointer/publication/native全部精确绑定。最终 receipt：`published-verification-v2.json`，SHA `5b9f0fdcb8474934e3c9326513cd3b71da6aeaa460cc89d0483268d71c3d11ae`，列全新runtime与执行脚本的实际hash/bytes。第一次 receipt 写入因 date JSON序列化失败留下空 `published-verification.json`，保留失败现场；v2仅把 verifier 返回 date序列化为ISO，不改收据语义、不重复发布或注册。

未修改共享src/tests或冻结研究/旧绑定材料。唯一授权共享配置变动是当前publication pointer。未提交。正式经济、G3、材料性/有效性、价格、仓位、真人签名历史、用户验收及INITIAL_ASSISTED_USE均未因此获准入。
