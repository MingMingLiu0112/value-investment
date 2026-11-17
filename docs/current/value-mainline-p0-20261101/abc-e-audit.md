# VALUE-MAINLINE-P0：A/B/C/E1/E2 限定事实审计

- 审计基线：vf1 HEAD `283c7212d832f52118705bb095e046e0c36dcbfc`；2026-11-01。
- 根目录：`D:/GPTProject/value-investment/.tmp/vf1`。下列所有路径均精确相对此根；`path:symbol` 中冒号后为函数/类型/JSON选择器，不是股票代码时已明确说明。
- 唯一交付：`.tmp/value-mainline-p0/abc-e-audit.md`。仅静态源码、测试源码、留存JSON与本地SHA核对；没有运行模型、网络、API、DB、采集、部署或回归。留存测试/运行结论不冒称本轮执行。
- 既有脏文件 `config/current-research-drafts.json` 仅计算字节摘要、不读取账户语义、不改写；审计前 SHA256 `2aba22a9e043d20076c7c40916808aee1bae9ba48f13951b8d0735e6fa077686`。审计后再次核对。
- 用户列举维度按12栏展开：domain / application / schema / independent / CLI / run / tests / errors / provenance / Web / hardcoded / dependencies。independent指可独立调用及隔离边界，不代表经济独立批准。

## 结论

A、B、C、E1、E2均有实际实现，不能统一标“仅设计”；也不能统一标“通用自动闭环”。A是请求范围内原件与有限字段，B是便宜筛选及限额补证，C是固定五家画像/条件路由，E1有两家公司旧包再编译消费，E2有000568无旧包首编及共享v4消费。它们不是单一标准化输入/输出协议，也没有证据证明所有新公司可从A自动走到E2。

本轮没有证明需阻断合并的新P1/P2；这是限定合同盘点，不是全实现正确性或经济批准。统一复用合同由Root另行处理，不在此增设框架。

## 十二维矩阵

| 维度 | A 公开证据 | B 筛选/队列 | C 画像/适用性 | E1 旧研究重放 | E2 首编 |
|---|---|---|---|---|---|
| domain | 复用财务字段/原件校验；主要编排在application，无专属完整金融领域引擎 | 既有M2 dataclass/筛选策略在根包legacy模块，不等于尚未实现 | ResearchProfile及profile_applicability_v1，条件/拒绝/输入清单 | 复用v4现金与估值内核；不是独立新估值公式 | 同一v4内核；首编转换不是第二套估值 |
| application | run_public_evidence/load_bundle/validate_queue_public_evidence | scoped_screening→M2；priority_v2→enrichment_batch | package校验、既有分析重放；另有显式source-only lane | build_neutral_valuation_proposal→prepare/verify_pending_research_candidate | _prepare→build_v4_descriptor→RunSpec→ResearchApplicationService |
| schema | public-evidence-bundle-v1/status-v1；export另有合同 | M2 receipt v2、value-research-priority-v2，非A包直接替代 | company-research-profile-v1/source-company-profile-v1；适用性版本独立 | joint-capital-cash-path-proposal-v4；candidate/package/descriptor分别绑定 | first-research-input spec/receipt，D2 assumptions，native事实与v4包分离 |
| independent | 可传root/request执行；GET与采集分离 | 可传绑定report/receipt/export执行；不需要LLM | validator明确不读registry/router/model；load层可重放模型 | 需要既有package+policy+choice；并非无旧包入口 | build与replay函数独立；不调用E1 pending producer，但依赖共享neutral compiler |
| CLI | collect_public_evidence.py；queue CLI成对接包/hash | build_value_research_queue.py，v2显式导出/hash、可选执行补证 | 本次未找到专属C CLI；已有函数/API | build_joint_cash_v4_candidates.py固定两家；replay_pending_candidate.py | scripts调用检索未发现build_first_research_input首编CLI；函数与公开读取API已实现 |
| run | 600519/600887实际原件各1 debt_ratio；不等于完整事实 | 三目标股票均有四通道评估；真实补证成功样本是000151/000498，不能移花接木 | 600519/600887原分析指纹不变；另三家路由/拒绝；000568不属C验收 | 两家candidate留存ACTUALLY_CONSUMED，conditional_research_only | 000568 FIRST_INPUT_COMPILED；留存API conditional_research_only、84 native事实 |
| tests | direct consumer含partial/损坏/错绑定/CLI先拒绝；组件/API类型测试 | queue/priority/scoped及批量补证测试；real opt-in | validator/source/API反例及两组real env | 两公司real测试强制开关；调用prepare+verify，跨公司隔离 | native/首编/API/Web测试；真实源env；禁止E1依赖、篡改、缺资本、旧输出覆盖等 |
| errors | PARTIAL健康者可用；坏已登记原件failclosed；无核验source拒绝 | 缺字段/冲突/不适用/预算排除分开；不可把来源不可用当0候选 | UNKNOWN/mixed/金融拒绝；坏当前包不可回退source-only掩盖 | hash/implementation/choice/版本错拒绝；不自动授materiality或价格准入 | 严格时间/身份/单位/期间/列位置/历史操作；缺输入保留缺口，source变化要求新版本 |
| provenance | raw PDF/receipt/facts/export闭包；原fetched保留，非严格历史PIT | scope/日期/manifest/receipt绑定；SSE/SZSE非全A | 原文段落/原件/资本依据及验证指纹，不由行业标签单独决定 | policy/package/source/implementation/descriptor绑定 | 原件native重读；财务字段scope/期间/geometry；source+implementation+descriptor复核 |
| Web | GET public-evidence；SystemStatus独立面板 | 既有候选研究选择/发现读模型；不证明实时全市场或部署 | 公共profile endpoint→CompanyProfilePanel | 既有公司analysis/JointCapitalReview，非通用新研究启动 | first-research-inputs/{symbol}→FirstResearchInputPanel；GET会冷编译计算，不采集/写出 |
| hardcoded | 限1–6请求、支持期间/解析版式；非股票白名单式通用财报理解 | 阈值/预算/通道为显式策略；本轮不改公式 | FIXED_SECTION_POLICIES硬编码3个审核段落hash+family/scopes；明示冻结边界 | CLI CASES为600519/600887及固定路径/choice；底层编译函数可参数化 | 事实helper使用symbol参数，具体页/标签/列/假设在manifest/spec；单家公司成功不证明任意版式 |
| dependencies | 官方取得/留存loader→财务抽取/导出；A→B需精确export匹配 | A补证/既有金融观察→M2→队列→补证；不自动保证C/E2成功 | A/source或E1已有包；router/identity/profile合同 | 旧package、D2式假设、v4内核、source-bound adapter | native事实+D2假设+issuer registry+v4；不要求E1旧估值；C是否经济采纳仍独立 |

## 实际源码/调用定位

### A
- `src/value_investment_agent/application/research/public_evidence.py:run_public_evidence`、`:load_bundle`、`:validate_queue_public_evidence`、`:public_evidence_status`。
- `scripts/current/collect_public_evidence.py:main`；`scripts/current/build_value_research_queue.py:main` 在调用v2 builder/写queue之前验证成对public-evidence参数及financial_export path/hash完全一致；有receipt原件再经load_retained_official_report复核。
- `src/value_investment_agent/infrastructure/screening/financial_export_v2.py:adopt_annual_export`；已核字段不升级为全部财务事实。
- `src/value_investment_agent/presentation/web_api/app.py` 的 `GET /api/v1/public-evidence` → `public_evidence_status`；`web/src/pages/SystemStatus/index.tsx` → `web/src/components/PublicEvidencePanel.tsx:PublicEvidencePanel`。
- `tests/test_public_evidence_consumer.py:test_partial_preserves_gaps_and_replays_healthy_original`、`:test_partial_with_corrupt_declared_original_rejects_before_queue_write`、`:test_cli_rejects_before_builder_writer_or_explicit_enrichment`；`tests/test_public_evidence_status_fields.py`；`web/tests/public-evidence-panel.test.tsx`。

### B
- `src/value_investment_agent/m2_opportunity_discovery.py:DiscoveryRunReceipt`、`:ChannelEvaluation`；`src/value_investment_agent/m2_discovery_engine.py:M2ScreeningPolicy`（legacy根包，不是新domain目录）。
- `src/value_investment_agent/application/discovery/scoped_screening.py:scoped_inputs/build_discovery_receipt` → `src/value_investment_agent/infrastructure/screening/evidence_screen_v3.py:build_discovery_receipt`。
- `src/value_investment_agent/application/research/value_research_priority_v2.py:build_value_research_priority_v2/reuse_durable_income_export`；`value_research_queue.py:build_value_research_queue`；`value_enrichment_batch.py:execute_value_enrichment_batch`（同目录）。
- `scripts/current/build_value_research_queue.py:main`，v1默认，v2显式；下载需另显式开关。durable reuse可写新export，不能把所有B函数笼统称“只读”。
- `src/value_investment_agent/application/discovery/value_candidate_selection.py:load_current_public_candidate_research` 为现有Web调用链；`presentation/web_api/app.py` 实际导入调用。
- `tests/test_value_research_priority_v2.py:test_missing_or_unavailable_never_receives_score/test_hash_and_budgets/test_export_cannot_replace_retained_base_or_escape_runtime`；`tests/test_scoped_screening.py:test_new_public_collection_rebuilds_exactly_without_reacquisition`（SCOPED_SCREEN_REAL_ROOT）；`tests/test_value_enrichment_batch.py`。

### C
- `src/value_investment_agent/domain/research/research_profile.py:ResearchProfile/PROFILES`；`profile_applicability_v1.py:contract_for_profile`（同目录）；permits_valuation_without_inputs=false、permits_approval=false。
- `src/value_investment_agent/application/research/company_profile.py:validate_company_profile_for_package/project_company_profile/load_company_profile`；最后一个会调用project_value_research_analysis校验实际descriptor一致。
- `src/value_investment_agent/application/research/company_profile_sources_v1.py:FIXED_SECTION_POLICIES/_load_fixed/load_source_company_profile`。三段hash映射为manufacturing/commodity_operations/financial_institution，仅冻结原文审核，不是通用行业分类器。
- `src/value_investment_agent/presentation/web_api/app.py` 的profile handler仅在NO_CURRENT_SOURCE_BOUND_RESEARCH时转source-only；坏当前证据不回退。
- `web/src/pages/DecisionDetail/index.tsx` → `web/src/components/CompanyProfilePanel.tsx:CompanyProfilePanel`。
- `tests/test_company_profile.py:test_validator_cannot_recurse_to_analysis_or_route/test_actual_current_sources_to_new_c_consumption_without_writes`；`tests/test_company_profile_sources_v1.py:test_actual_fixed_source_receipts`；`tests/test_company_profile_api.py:test_damaged_current_research_never_uses_source_only_lane`。真实源开关分别VALUE_COMPANY_PROFILE_REAL_ROOT、VALUE_SOURCE_COMPANY_PROFILE_REAL_ROOT。

### E1
- `src/value_investment_agent/application/product/neutral_valuation_proposal.py:build_neutral_valuation_proposal/compile_joint_cash_choice_v4`；`pending_research_candidate.py:prepare_pending_research_candidate/verify_pending_research_candidate/_verify_joint_economic_inputs`（同目录）。
- `scripts/current/build_joint_cash_v4_candidates.py:CASES` 固定两公司；可选发布会碰当前pointer，本轮不执行。另有 `scripts/current/replay_pending_candidate.py`。
- `src/value_investment_agent/application/research/value_research_analysis.py:project_value_research_analysis`、`application/product/economic_review_materials.py:project_joint_capital_review`，两公司real test确实调用这些consumer。
- `tests/test_joint_cash_v4_two_company_real_replay.py:test_two_real_companies_use_one_v4_shared_consumption_path`：JOINT_CASH_V4_REAL_REQUIRED=1时缺真源fail而非skip；有源即经prepare/verify。不能把默认无源skip的CI当真实验收。
- 模型输出只为conditional_research_only；旧候选重放与事件重大性、经济批准、当前价格资格分离。

### E2
- `src/value_investment_agent/application/research/first_research_input_v1.py:_prepare/build_first_research_input/replay_first_research_input/_implementations`。
- `src/value_investment_agent/infrastructure/filings/first_research_fact_replay_v1.py:replay_first_research_facts/_native_column`；原页字段/金额/期间列几何核对，不是自由LLM抽取。
- _prepare显式拒绝predecessor/market/approval额外键；TTM为受限同字段FY+当期H1−同期H1；historical reported amount不能手填假设；owner cash/capacity/floor必须标假设。
- replay实际构建v4 descriptor→ResearchApplicationService.run_company_research；不是仅回显已存估值。build要求新输出目录；replay读原件/包并校验冷重算一致。
- `src/value_investment_agent/application/product/first_research_input_view_v1.py:read_first_research_input` → `presentation/web_api/first_research_input_routes.py:register_first_research_input_routes` → `GET /api/v1/first-research-inputs/{symbol}`；DecisionDetail→FirstResearchInputPanel。
- `tests/test_first_research_input_v1.py:test_default_entry_calls_root_cold_helper_twice_and_never_e1/test_existing_output_is_never_overwritten/test_missing_base_is_a_gap_not_an_invented_main_valuation/test_real_source_environment_acceptance`；`tests/test_first_research_fact_replay_v1.py`；`tests/web_api/test_first_research_input_api.py`；`web/tests/first-research-input-panel.test.tsx`。真实源env E2_REAL_SOURCE_ROOT。
- 旧E2 receipt实现pin仍为raw bytes；本轮静态重算其9个实现/identity文件pin均无差异。不得把后续main专用portable basis合同追溯覆盖旧E2。

## 三家公司真实样本（已读本地文件，不重新计算模型）

| 模块/公司 | 精确路径及JSON定位 | 本轮核得事实 |
|---|---|---|
| A 600519/600887 | `artifacts/current/public-evidence-a-20261030.json:actual_public_sources[symbol]`；`runtime/public-evidence/20261030T110724-accepted/bundle.json:items[request.symbol]` | 各1 debt_ratio；来源VERIFIED不代表完整事实。000568不在此A验收包，不能借E2原件宣称已走此A consumer |
| B 三家 | `runtime/daily-marketwide/g1-restored-20261028-v4/receipt.json:channel_results.<channel>.evaluations[symbol]` | 600519：质量DATA_GAP、现金REJECTED、价值REJECTED、周期NOT_EVALUATED；600887：质量DATA_GAP、现金BUDGET_EXCLUDED、价值REJECTED、周期NOT_EVALUATED；000568：质量DATA_GAP、现金PASS、价值BUDGET_EXCLUDED、周期NOT_EVALUATED |
| B 000568 | `runtime/daily-marketwide/g1-restored-20261028-v4/value-discovery-report.json:leads[37]` | 该报告有000568 lead，无600519/600887 lead；筛选观察不等于获研究批准 |
| C 600519/600887 | `runtime/c-closeout-20261031/api-acceptance/receipt.json:results`；`artifacts/current/company-profile-c-closeout-20261031.json:results[symbol]` | SOURCE_BOUND_PROFILE，既有分析指纹不变，formal=false；000568不属冻结五家，未把E2成功反填C |
| E1 600519 | `runtime/joint-cash-v4-current/20261028T044953763337Z/600519/candidate.json:model_context_scope/candidate_valuation.status` | ACTUALLY_CONSUMED / conditional_research_only / research_admitted=false / no_order；SHA 97a83c496feab701fe3f4718d8c09535ce18226729210bc2deac5f625f930086 |
| E1 600887 | `runtime/joint-cash-v4-current/20261028T044953763337Z/600887/candidate.json:model_context_scope/candidate_valuation.status` | 同上；SHA 96e5894b08dd1342139c6a8dd88867619334f77807f7bf6fc28af64067fd6f42 |
| E2 000568 | `config/current-first-research-inputs-v1.json:cases.000568.receipt` → `runtime/e2-first-input-000568-20261031/compiled-20261031T111006911210Z/receipt.json` | FIRST_INPUT_COMPILED；SHA b3c3b1eec045381779156dc150d57a67c21a9c0c92fedd94403c42f390e92b48；不是C新增分类 |
| E2 000568 API留存 | `runtime/e2-first-input-000568-20261031/api-acceptance-final/receipt.json:status/valuation_status` | SOURCE_BOUND_FIRST_INPUT_COMPILED / conditional_research_only，native_facts=84，main_range_adopted=false；这是留存API证据，不是本轮实时调用/浏览器验收 |

E1入口的旧包：600519 `runtime/product-cash-allocation-consumer/20261026T090212419386Z/candidate/package.json`（SHA 6af35ae4b060cf97dfe04d4735c02b54196aa86f98e55c7228ee8322b9bd4401）；600887 `runtime/cc1-companion-replay-20261023-v2-final/600887/package.json`（SHA 32ae408776c9efd2ab7a492926db035af85a3ce86d93229ea1a0e2c93479a91c）。两份symbol均实际核对，不能声称无旧包研究。

B后续成功证据 `artifacts/current/value-screening-b-20261030.json` 指向000151/000498各1 debt_ratio；它已明确替代“两个补证都失败”的中间状态，但没有为本任务三家公司创造新的补证成功结论。该artifact的queue_binding/bundle/financial_export三个hash本轮均一致。

## 校验记录与尚未证明事项

本轮仅本地字节/JSON验证：
- A验收摘要绑定的bundle及acceptance：2/2 hash一致；bundle SHA ab4d528f7f30144ac451a33d2326e9d143d7496f4d376a22a8a12800f877034a。
- B manifest直接绑定：9/9一致；manifest SHA c0b25d950bef78b880891b0fb3e74c4bf367b1fca38ef98f23d7246d0f79c633。
- C留存API receipt SHA 64646bfad728b3d0942458fb48aa37d4b9936683712291fec208a2a415e5b661，与公开摘要相同。
- E2 receipt直接path/hash绑定：9/9一致；实现/identity pin静态比较无差异。没有据此宣称重新解析了84项原页或本轮模型重跑。
- 测试只读检查测试体/真实env门禁，未执行；没有新增passed计数。历史E2摘要记载155 passed、C摘要114 passed，均只作为历史记录，不作当前重跑证据。
- Web挂载/服务调用已定位；当前端口、部署版本、浏览器行为、Root最新CI未由本轮验证。
- “设计目标”仍包括通用新公司自动分类、任意财报解析、A→B→C→E2统一复用合同、通用首编CLI/自动研究调度及主估值经济采纳。代码已有各自有界实现，不足以证明这些目标整体完成。
- 明确依赖而非新任务：来源身份/时间/币种、模型适用性、假设可辩护性、资本与现金约束、经济批准、执行资格是不同合同。首编/运行成功不自动填补它们。
\n
## 追加：阶段1=A+B（当前代码复核）

阶段来源采用用户本轮明确说明，不以旧聊天判断代替代码。

### B预算冲突：旧缺陷已关，不提出重复修复
- 当前 `src/value_investment_agent/m2_discovery_engine.py:870-873` 仅对 `EVALUATION_PASS` 应用展示预算，非PASS直接continue；报价冲突为CONFLICT而非字面QUOTE_CONFLICT。
- `tests/test_m2_opportunity_discovery.py:test_budget_preserves_quote_conflict_across_all_four_channels` 检验budget=1、排名2在四通道保留CONFLICT；无冲突对照才是BUDGET_EXCLUDED。
- `tests/test_value_candidate_selection.py:test_budget_quote_conflict_through_source_replay_and_research_queue` 从绑定原始报价得到期望值，验证price_conflict、shortlist及research_priority_eligible。
- 本轮仅执行以上两个定向test节点：**4 passed in 1.08s**；不调用模型/网络。隔离临时目录，无源码变更。这条追加取代正文“本轮未执行任何测试”的先前时间点记录。

### A manifest/恢复：已实现与真实缺口分开
- **已实现独立来源合同**：`infrastructure/filings/official_report_acquisition.py:acquire_official_report/load_retained_official_report`（src/value_investment_agent下），取得receipt独立于fact_snapshot/export，绑定source PDF、index_bindings、身份/期间/原fetched；不可称“无source manifest”。
- **已实现bundle留存重放**：`scripts/current/collect_public_evidence.py:main` 的previous-bundle/previous-sha256进入run_public_evidence，复核旧包并生成新结果。前提是依赖文件已在root；这不是恢复缺失文件。
- **确认的交付缺口：A专用闭包归档/恢复没有接入受支持CLI。** 真实验收 `.tmp/accept_public_evidence.py` 使用两个写死目录的shutil.copytree，再load_bundle及consumer核验；证明这一份数据搬迁后可重放，不是参数化独立恢复入口。现有 `src/value_investment_agent/infrastructure/public_evidence_archive.py:restore_public_archive` 支持旧tl11-p4-public-evidence-archive-v1、artifacts→runtime、全包预检/拒覆盖；src/scripts引用检索未找到A生产caller，只有直接tests。因此恢复底层并非空白，缺的是A闭包manifest生成/接线与入口。
- 此项是“可复用恢复交付缺口”，不是原件完整性绕过或已证明的金融错误；旧恢复成功不能记为通用恢复完成。

### 最小现有文件改动建议（仅建议，未实施）
1. 在现有 `application/research/public_evidence.py` 增加A包显式依赖枚举/归档辅助：先load_bundle及retained loader校验，枚举bundle/export/fact snapshot/receipt/PDF/raw index等实际绑定，禁止目录扫描/按股票猜路径。与Root ModuleRun复用同一来源清单，不另造竞争schema；previous_bundle是否纳入完整历史闭包应显式约定。
2. 复用现有 `infrastructure/public_evidence_archive.py:restore_public_archive`，由既有 `scripts/current/collect_public_evidence.py` 加明确归档/恢复模式接线。缺少A闭包映射时只补所需adapter；不修改load_bundle、筛选公式或旧回执。恢复显式指定manifest/hash、隔离目标；不网络、不重标fetched、不自动发布current。
3. 对应现有 `tests/test_public_evidence_archive.py` / `tests/test_public_evidence.py` 加：A真实形状闭包空目录恢复后loader/consumer相等；原始receipt/PDF/index字节与时间保持；缺依赖/坏hash/路径越界/目标异内容均在首次复制前拒绝；重复同字节幂等；CLI参数与禁止网络/发布；partial包保留缺口而不补造事实。
4. 若Root本轮ModuleRun已承担清单和恢复，不并行实现第二入口；只将这些验收项接入Root合同。

本次未改任何source/config/旧研究，仅追加该审计记录。B不再记未解决QUOTE_CONFLICT预算bug。
