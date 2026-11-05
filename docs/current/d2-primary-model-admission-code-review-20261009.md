# D2 主估值准入代码审查（2026-10-09）

## 范围和结论

本轮为 bounded code review。只新增本文；读取当前工作树实际源码、package-v8/workbench-v10/event-followup-v9 和已有测试；没有改源码、JSON、Excel、旧文档或批准，没有执行 research CLI、生产操作、发布或完整 suite。没有代替 Root 正在进行的经济假设敏感性审查。

主估值研究可以继续经公开独立研究推进；它不是私人 IPS/组合任务。现有共享模型计算、G3 精确批准、当前模型有效性、价格桥接、非个性化候选是不同门禁。不能把财务 G1 通过、模型有数值或价格桥接 READY 单独当作主估值/投资准入。

当前模型成功时固定输出 `conditional_research_only`，不存在仅修改某个 `primary` 状态便自动升级的模型入口。既有精确研究批准可以准入条件结果，不要求重写模型结果 status。具体“主情景”经济含义仍由研究和批准的范围负责，代码不自动判断假设是否中性。

## 本轮实际证据

| 对象 | 当前事实 |
| --- | --- |
| `runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json` | SHA-256 `c48e3dbfbe8b643cc71a609a2277f726246a1f32b1ac5dcb4b2da47055ec3d04`；v2 源合同，28 个 catalog sources、42 个三情景参数 bindings |
| `runtime/d2-model-bound-followup-20261008/workbench-v10.json` | SHA-256 `b88fa501a3bcd76fb538ab633a9ea1f086cc0aa35877e41c2bacf3c996935d2c`；G0/G1/G2=true，G3=false；低置信条件结果；ModelValidity UNKNOWN；NO_ACTION；entry/reduce/position=null |
| `runtime/d2-canonical-integration-20261008-v9/canonical-integration-historical-preview.xlsx` | 本轮只读哈希仍为 `58e828835842416ae83c239637ad722ebf7c2f16603b02a8ac2f4161184a7179`；旧成果冻结；不把旧验收收据当作本轮 fresh 验收 |
| 本轮 fresh 只读代码验证 | `python -c` 调用 `build_descriptor(actual_package, root=root)` 和 `ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)`，退出码 0；没有执行 application persistence 或生成输出文件；输入/工作台前后哈希相同 |

fresh 验证读到 `normalized_parent_profit_cny=null`，实际 operating inputs 只有 `start_book_equity`、`ordinary_shares`；模型 blockers=[]，仍得到 404.823132132816367… / 479.879911433847652… / 572.738699601067929…，status=`conditional_research_only`、confidence=低。同一 descriptor 的 quote 为 verified_close、2026-10-08、1255.79；扫描仍携带两项未复核 blockers。这里只证明代码消费边界及冻结结果复算，不证明主情景经济合理性或批准。

## 重要发现和接入限制

1. **正常化利润空值是研究范围解释，不是剩余收益模型独立强制门禁。** 实际字段在 `research_case.financial_summary.financial_scope_review.normalized_parent_profit_cny`，不是 model operating input；原包第 1664 行为 null，第 1702/1705 行明确不认可正常化盈利/中性主估值。模型只强制权益起点和股数（[residual_income.py:76](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:76)），消费权益及 ROE 路径（[residual_income.py:343](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:343)）。builder 还会过滤 operating_inputs 中的 None（[m1_valuation_package_builder.py:210](D:/GPTProject/value-investment/src/value_investment_agent/m1_valuation_package_builder.py:210)）。金融尾部、正常化盈利和 `not_accepted` 元数据没有成为独立模型 predicate；当前安全性依赖真实 case/assumptions blockers 和范围复核，不能只删文字、改 approved 或填一个未经核实的利润数。Root 可审阅有界前瞻 ROE/净利润推导，不必为了通过代码伪造精确 normalized profit；能否作为主情景须由该范围的独立研究结论决定。

2. **仅把正式 review 附到旧 pending scan，不能关闭现有阻断。** [research_reviews.py:65](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:65) 把原 validity.blockers 和 scan.blockers 都带入 spec。[event-scan-current-model.json:15](D:/GPTProject/value-investment/runtime/d2-source-bound-current-20261008/event-scan-current-model.json:15) 的两项正是“七公告尚需材料性复核”和“模型前披露尚未纳入当前基准”。即使事件 review 的 decisions 无未解项，ModelValidity review 分支仍保留 base blockers（[model_validity.py:192](D:/GPTProject/value-investment/src/value_investment_agent/model_validity.py:192)）；PriceBridge 可显示 READY 但保留 blockers，最终 recommendation 仍 NO_ACTION。阻断的是有效性/价格/候选节点，不是独立研究。最短可复用路径是据真实已完成复核生成 append-only successor scan 及其正式 review，同步新包的 catalog/path/hash/scan_watermark；不得覆盖旧 scan 或为了放行清空真实风险。

3. **正式事件准入缺少强制的具体模型/假设绑定。** [EventMaterialityReview:202](D:/GPTProject/value-investment/src/value_investment_agent/event_materiality.py:202) 的必填身份是 symbol、scan id/hash/window；[research_reviews.py:40](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:40) 检查扫描、完整公告集合、公布时间和 source hash，没有比对 valuation/package/assumption hash。`affected_artifacts` 是描述字段，不是强制校验的模型依赖。相同扫描下切换模型/参数后，旧正式事件 review 可通过 attachment 的扫描检查；这是实际接口覆盖缺口，不是本轮证明已发生的真实误准入。既有解释层 v2 有严格 package/workbench/consumed-assumption 绑定（[event_followup.py:68](D:/GPTProject/value-investment/src/value_investment_agent/application/product/event_followup.py:68)），但它不自动变成正式 materiality approval。Root 后续须复用这些绑定约束到现有正式复核入口，或在真实复核与验收中明确新模型适用范围；不能将旧扫描 hash 相同视为新主模型已复核。

4. **公开 delegated review 获治理授权，但正式 typed receipt 没有显式 delegated 身份。** [LONG-TERM-GOAL.md:62](D:/GPTProject/value-investment/LONG-TERM-GOAL.md:62) 允许独立 Reviewer/SubAgent、Root 裁决，且第 69 行区分研究批准和用户投资决定；不是所有带 human 的节点都要用户签字。可是 [HumanResearchApprovalReceipt:170](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/human_research_approval.py:170) 和 [EventMaterialityDecision:110](D:/GPTProject/value-investment/src/value_investment_agent/event_materiality.py:110)、review 第 241 行只接受 `human_research_lead`。这些检查验证标签/形状，不验证真实 reviewer 授权，不能拿字符串通过冒充 human。公开独立研究、有限范围接受/拒绝及可追溯 reviewer provenance 可继续完成；要让 delegated 正式准入可机器消费，Root 需要在既有审批合同/验证器内补明确身份与授权映射，或消费真实存在的相应正式 receipt。无需另建框架；当前未接入期间保持未准入，不能自动批准假设。

## 逐入口的真实字段和复核证据

| 入口 | 必须具备/更新的字段和证据 | 当前边界及代码 |
| --- | --- | --- |
| package/source descriptor | v2 schema、source_contract schema；带时区 cutoff 与研究日；每 source 的唯一 id、完整 local_path/hash、available_at/basis；facts/case/assumptions/bindings 引用不得漂移；quote/event path/hash 在 catalog；来源与报价观察不晚于 cutoff | [source_bound_inputs.py:51](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:51)、[source_bound_inputs.py:77](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:77)。字节/时点一致不替代源语义审查；strict contemporaneous PIT 未证明仍不能标已证明 |
| shared RI model | 真实发行人/quality_compounder route；facts.verified；有限正权益和股数；恰好 bear/base/bull；每情景 cost_of_equity、forecast_roes、retention、terminal_roe、terminal_growth；保留资金用途、存量/新增资本及优势期的推导、反证和边界 | [ResearchApplicationService:554](D:/GPTProject/value-investment/src/value_investment_agent/research_application.py:554)、[residual_income.py:105](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:105)。代码要求 cost>0、terminal_roe>0、forecast ROE>=0、0<=growth<cost 且 growth<=terminal_roe、retention∈[0,1]；不自动验证经济代表性；成功结果仍 conditional（第 537 行） |
| assumption set/bindings | 每个被消费三情景 leaf 均对应唯一 binding；name、scenario、field_path、expected_value、evidence_refs；AssumptionSet 的三情景值=绑定值=实际模型值；basis/rationale/confidence/sensitivity | [source_bound_inputs.py:134](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:134)、[m1_valuation_package_builder.py:328](D:/GPTProject/value-investment/src/value_investment_agent/m1_valuation_package_builder.py:328)。新主情景不能沿用旧 42 个绑定但偷偷换数，也不能删除真实 blockers 或人为提高置信度 |
| dated timing | valuation_timing.basis_at、valuation_at、命名 evidence；时区；basis<=valuation<首次年度支付；上海 valuation 日期=facts.as_of；依赖 model_version=dated-v2 | [residual_income.py:19](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:19)、[residual_income.py:320](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:320)、[residual_income.py:404](D:/GPTProject/value-investment/src/value_investment_agent/valuation_models/residual_income.py:404)。权益是历史基准；时间因子不是已观测当前净资产，也不证明中间分配/资本变动已全部吸收 |
| ResearchGate | G0 evidence_status=verified+refs；G1 research_status=financial_scope_approved；G2 支持/反证/逻辑破坏各>=3且有引用，thesis/return_driver/mispricing/next_events；G3 精确批准 | [research_gate.py:58](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/research_gate.py:58)、[research_gate.py:82](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/research_gate.py:82)。G1 当前只是限定范围；G2 是论点完整性。旧 ResearchValuationApproval 分支还要求 case approved/approved_low_confidence+result hash；新 human 分支可准入精确条件结果（第 142 行） |
| 正式研究批准 | approval_id、symbol/security/profile；valuation artifact id/hash、model id/version；case/facts/assumption ids 及各自 canonical payload hash；reviewed_at/review_as_of、真实 reviewer 类型、decision、price_assessment_eligible、conditions/followups/blockers/evidence | [human_research_approval.py:113](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/human_research_approval.py:113)、[resolve:331](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/human_research_approval.py:331)。哈希必须来自实际 descriptor 的 canonical case/facts/assumptions 和 valuation_result_sha256，不能用整份 package 的 file hash替代。任何依赖改变即 SUPERSEDED；仅有旧轻量 ResearchValuationApproval 不足以产生正向候选 |
| materiality/ModelValidity | acquired complete scan 精确 hash、窗口、retrieved_at；全公告逐个 decision/source hash/time；affected domains/facts/assumptions/artifacts、复核理由；coverage>=quote/decision 日；new model identity/as-of/valid_from；不存在未解重算、分解或风险监控 blockers | [research_reviews.py:38](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:38)、[event_materiality.py:299](D:/GPTProject/value-investment/src/value_investment_agent/event_materiality.py:299)、[model_validity.py:90](D:/GPTProject/value-investment/src/value_investment_agent/model_validity.py:90)。VALID 字样不能抹除 blockers；MATERIAL_RISK_MONITOR 也阻断候选。财务 ScopeMateriality 的 LOW/IMMATERIAL 要量化暴露/边界且有证据，UNKNOWN fail-closed（[materiality.py:101](D:/GPTProject/value-investment/src/value_investment_agent/materiality.py:101)），且不自动解锁 route（第 169 行） |
| PriceBridge/价格观察 | verified_close quote、symbol/date/price、source SHA；VALID 且覆盖报价日期的 validity；同 valuation symbol/model version/as-of、绑定 bear/base 和可重算 margins；无 blockers | [price_bridge.py:175](D:/GPTProject/value-investment/src/value_investment_agent/price_bridge.py:175)、[binding:383](D:/GPTProject/value-investment/src/value_investment_agent/price_bridge.py:383)。READY 是合法比较，不是价格便宜或 G3 批准 |
| nonpersonalized recommendation | 已解析正式审批+所有 raw dependencies；current event review、ELIGIBLE predecision、READY bridge、VALID model、RESEARCH_ATTRACTIVE、非低置信度、所有 blockers 为空；依赖日期不晚于 decision_as_of | [predecision:141](D:/GPTProject/value-investment/src/value_investment_agent/pre_decision_eligibility.py:141)、[build:311](D:/GPTProject/value-investment/src/value_investment_agent/application/decision/build_decision_recommendation.py:311)。quality_compounder 现规则要求价格<=bear；低置信度不输出正向（[price_attractiveness.py:145](D:/GPTProject/value-investment/src/value_investment_agent/price_attractiveness.py:145)）。主估值审阅通过不保证 BUY_CANDIDATE；旧参数/1255.79 报价即使其他门补齐仍不满足该价格条件 |

## 私人输入与用户/生产边界

没有发现非个性化候选误绑私人 IPS/portfolio 的代码门禁。builder 的 `positive` 条件不含 portfolio，结果同时固定 `portfolio_input_status=BLOCKED_PRIVATE_INPUT`、position=null、reduce_zone=null、action=no_order（[build_decision_recommendation.py:404](D:/GPTProject/value-investment/src/value_investment_agent/application/decision/build_decision_recommendation.py:404)）。产品组合步骤始终 BLOCKED，但不进入证券级 positive 条件（[decision_surface.py:380](D:/GPTProject/value-investment/src/value_investment_agent/application/product/decision_surface.py:380)）。已有正向测试明确同时断言 BUY_CANDIDATE 和 PRIVATE_INPUT/null；读取了测试源码，没有本轮重新执行测试。

公开独立研究可完成事实口径、正常化/前瞻收益的有界解释、资本用途/权益成本/终值/分配敏感性、事件影响与范围材料性、来源/时点验证、真实 reviewer provenance、独立接受或拒绝，以及 Root 离线集成与重放。研究不足可合法拒绝，不等待未来成为事实，也不需要索取私人 IPS 才继续。

R2 私人 IPS、真实持仓/现金/成本/账户约束及原始个人 Entry Thesis 只阻断个性化仓位/加减退复核；R3 生产数据库、调度/通知、账户导入、正式 Shadow/恢复等须具体授权；R4 真实资金投资决定、R5 最终产品签收属于用户。正式 canonical 发布不在本轮授权内。研究批准不等于上述任何批准。本审查不签 human receipt、HUMAN_PASS、BUY/ADD、PRODUCTION_AUTHORIZED 或 USER_ACCEPTED。

## 下一步最短可执行路径（交 Root；本轮未执行）

1. Root 用当前经济敏感性和公开独立复核结果形成一个 append-only successor package；明确“主情景”的用途/不确定性、更新所有真实受影响 facts/assumptions/bindings/来源时点和版本，不覆盖 package-v8/workbench-v10。normalized_profit 不能验证时可保持未知并说明模型适用范围，不能声称已核实或沿用有限财务范围作全批准。
2. 对 exact successor descriptor 先复算内置 RI 模型，审阅实际 consumed inputs、dated convention、三情景、置信度和反证；冻结 canonical case/facts/assumptions 与 valuation hashes。这是正式 receipt 的被批准对象；不能先制造批准再调整参数使它匹配。
3. 用既有 complete scan/review 合同生成真实 successor materiality review，逐公告说明已纳入/未纳入/需重算/风险监控；对模型前输入及扫描 blockers 用实际证据关闭或保留。新扫描/模型/假设须明确同一复核范围，先解决 findings 2/3；现有 event-followup-v9 只可复用研究证据，不能转名充当正式批准。
4. 对研究准入采用真实独立 reviewer + Root 裁决及可追溯权限；既有正式 receipt 的 delegated 身份缺口交 Root 在原合同中解决（finding 4）。有合法适用 receipt 时，复用 `shared-research-review-inputs-v1` 的 `bindings.human_approval`/`bindings.event_materiality`；不另建模型、建议或发布链。
5. 复用 [run_company_research.py:74](D:/GPTProject/value-investment/scripts/current/run_company_research.py:74)：`--symbol 600519 --package <新包> --research-reviews <新review packet> --research-reviews-sha256 <真实hash> --schedule-request <满足Evidence Stop的新请求> --output <新工作台>`。quote/event 若独立传入，须 path/hash 成对且匹配新包 catalog。此入口先校验再消费一次性 reopen request（[company_research.py:229](D:/GPTProject/value-investment/src/value_investment_agent/application/product/company_research.py:229)），不要重复跑来制造批准。
6. 验证 G3/ModelValidity/blockers/PriceBridge/predecision 和整包依赖重放；即使主研究已准入，按实际价格/置信度保留 NO_ACTION 或输出仅供人工复核的 nonpersonalized BUY_CANDIDATE；仓位/订单保持空。随后才让已有 product consumer 读取新工作台；本轮不生成产品或碰旧 Excel。

## 验证范围和交接

FILES_CHANGED：仅本文。FILES_READ：上述 actual package/workbench/scan/event-followup、ResidualIncome model、builder/source contract、ResearchApplicationService、ResearchGate、human approval/research review、materiality/ModelValidity、dated timing、PriceBridge/price assessment、predecision/recommendation、decision_surface 和相关 tests；不依赖提交记录判断行为。

TESTS：本轮无 pytest/suite 执行。只读 fresh descriptor+model 复算退出 0；旧 package/workbench/v9 candidate 哈希核对通过。读取 [test_d2_conditional_shared_service.py:254](D:/GPTProject/value-investment/tests/test_d2_conditional_shared_service.py:254) 的正向/批准漂移/完整 bundle replay 断言和 [test_decision_recommendation.py:386](D:/GPTProject/value-investment/tests/test_decision_recommendation.py:386) 的 nonpersonalized 正向断言；这些是 synthetic 工程合同，不能当真实公司审批或本轮 fresh test pass。

BLOCKERS：当前真实包的经济范围/G3、正式 reviewer 及事件准入、扫描 blockers、低置信度和价格条件各自阻断相应节点；私人输入只阻断个性化节点。CONFIDENCE：对静态入口、当前 JSON 和实际复算结论高；对主情景经济合理性不作结论。本轮没有发现私人 IPS 误阻断证券级候选；上述正式 delegated 身份和 model-bound materiality 是明确待接合同限制，不宣称全部准入已闭环。
