# D2 架构差量与适配器交接（2026-10-08）

## 1. 范围与证据等级

本文件是单公司接线交接及未来接口 draft，不是实现、阶段验收或完成回执。本轮只写本文件，不修改源码、核心合同、目标或 Excel，不运行测试、真实研究包、发布入口或外部项目。Root 负责 replay 修复集成及真实 600519 包执行；其他代理的公司研究不在本文件工作范围。

证据来自实际工作树的有界静态读取，不依赖提交记录或文档自称完成。代码定位统一使用绝对路径与观察时行号；并行工作可能改变行号，关键字及第 8 节字节指纹用于复核。最后有界核对时点为 2026-10-08 18:13 +08:00。

继承五库审查 [第 8 节设计](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:109) 和 [43 文件静态核查边界](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:184)，不重新扫描、下载或执行外部源码。继承 [D2 输入边界审查](D:/GPTProject/value-investment/docs/current/d2-adapter-boundary-review-20261008.md:13)，但以下以本轮新增源码接线更新 F1-F4 的解释，不改写旧报告。

Root 提供的 fresh 事实：C 盘 Excel 截至 10/2、7 可见/55 隐藏；D2 research.json 的调度原因 BLOCKED_NO_REGISTERED_SCOPE；128 pass/2 fail（missing approval replay）；9 原件字节匹配；600519 10/8 verified_close=1255.79；事件覆盖 INCOMPLETE；本机离线 ledger 有效会话 0。这些属于 Root 输入，本代理没有重新验证对应运行产物，也没有得知新的真实运行结果。不得用该报价、原件字节或测试数量替代完整 D2 验收。

## 2. 实际调用链与可复用模块

```text
M2 DiscoveryReceipt / CandidateReason
  -> [尚缺显式单候选交接及经过审阅的 case 内容]
  -> build_research_case.py -> product.research_case -> typed ResearchCase

显式 source-bound package + quote/event/reviews + scope request
  -> run_company_research.py 或 build_current_workbench.py
  -> product.company_research（调度、来源绑定、输入覆盖）
  -> m1_valuation_package_builder.build_descriptor
  -> research_input.build_research_run_spec
  -> attach_research_reviews
  -> ResearchApplicationService（共享 model/gates/决策/精确制品）
  -> research result + artifact bundle
  -> workbench 的 repository replay
  -> decision_surface.project_verified_decision_workbench
  -> product candidate（正式发布/Excel 验收另属 Root）
```

| 模块/入口 | 已有接线与复用判断 | 证据定位 |
| --- | --- | --- |
| 入口注册 | 当前 case/research/valuation/workbench/event 与 M2 均有登记；登记不证明纵向通过。 | [current-cli-entrypoints-v2.json](D:/GPTProject/value-investment/config/current-cli-entrypoints-v2.json:19) |
| 单公司 runner | 显式 package，quote/event/reviews 的 path/hash 成对；先处理 Evidence Stop，再构造 descriptor/spec，最后调用共享服务；继续复用此编排。 | [company_research.py](D:/GPTProject/value-investment/src/value_investment_agent/application/product/company_research.py:146)、[descriptor/spec/reviews](D:/GPTProject/value-investment/src/value_investment_agent/application/product/company_research.py:246)、[共享调用](D:/GPTProject/value-investment/src/value_investment_agent/application/product/company_research.py:291) |
| package builder | typed Case/Facts/AssumptionSet/bindings、profile/model 与 PIT/dependencies 是已有共同入口；不另写按股票代码选公式的流水线。 | [m1_valuation_package_builder.py](D:/GPTProject/value-investment/src/value_investment_agent/m1_valuation_package_builder.py:461) |
| source-bound v2 差量 | v2 跳过隐式 distribution；builder 在 finalize 前调用本地原件及 source-bound descriptor 核验。不是已通过的真实验收。 | [distribution 分支](D:/GPTProject/value-investment/src/value_investment_agent/m1_valuation_package_builder.py:488)、[核验调用](D:/GPTProject/value-investment/src/value_investment_agent/m1_valuation_package_builder.py:554) |
| 研究引擎 | 共享 model.value，再保存制品并 build_decision_recommendation；财务算法及 gate 不应复制到产品投影或 adapter。 | [model.value](D:/GPTProject/value-investment/src/value_investment_agent/research_application.py:556)、[决策生成](D:/GPTProject/value-investment/src/value_investment_agent/research_application.py:728) |
| review 输入 | 将 exact Case/Facts/Assumptions payload 带入决策；人工审批可缺失。事件材料性必须绑定 exact scan/hash，且 COMPLETE、窗口一致、逐公告全覆盖。 | [research_reviews.py](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:30)、[事件门](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:40) |
| 精确重放 | bundle repository + dependency refs 恢复输入，再完整重建 policy；当前 Root 修复按封存 input hash 恢复可选 payload presence，独立于是否提供审批。 | [可选输入恢复](D:/GPTProject/value-investment/src/value_investment_agent/application/decision/restore_decision_recommendation.py:174)、[完整重建比较](D:/GPTProject/value-investment/src/value_investment_agent/application/decision/restore_decision_recommendation.py:255) |
| 当前产品投影 | 只接已重放 workbench，校验主体/日期/建议类型/私人输入边界；candidate 服务已有 path/hash 入口。必须复用它，不从表格或旧卡片重算建议。 | [decision_surface.py](D:/GPTProject/value-investment/src/value_investment_agent/application/product/decision_surface.py:64)、[candidate 接线](D:/GPTProject/value-investment/src/value_investment_agent/application/product/product_workbench_candidate.py:1472) |

## 3. 重复消费者、状态冲突与未接通

| 差量 | 当前事实 | 最小交接要求 |
| --- | --- | --- |
| research CLI 与 current workbench | workbench 直接再调用 runner，output_path=None；不消费上一次 research.json。非 stopped 路径必须有 bundle/recommendation 并重放。 | [workbench.py:100](D:/GPTProject/value-investment/src/value_investment_agent/application/product/workbench.py:100)。两入口用于不同输出，不是两个财务引擎。一次性 scope 不得先跑研究再盲跑 workbench；缺少“已有 fresh result -> current workbench”显式入口是产品复用缺口。existing 模式不能冒充该入口。 |
| 批量研究消费者 | research_batch 也从 descriptor 建 spec，调用同一共享服务，再映射 batch status；与单票 runner 的覆盖输入、review、receipt、调度处理不完全相同。 | [research_batch.py:413](D:/GPTProject/value-investment/src/value_investment_agent/research_batch.py:413)、[共享调用](D:/GPTProject/value-investment/src/value_investment_agent/research_batch.py:664)。保留批量依赖指纹/缓存门，不扩大单票授权为批量 scope。 |
| 独立估值消费者 | valuation 产品服务调用另一路显式 FCFF-only application builder，直接 FCFFValuationModel.value；共享模型，但不含完整 ResearchApplicationService 决策链。 | [valuation.py:37](D:/GPTProject/value-investment/src/value_investment_agent/application/product/valuation.py:37)、[FCFF-only](D:/GPTProject/value-investment/src/value_investment_agent/application/valuation/company_valuation_result.py:102)、[实际算术](D:/GPTProject/value-investment/src/value_investment_agent/application/valuation/company_valuation_result.py:160)。能算估值不代表 D2 或 router 多模型产品闭环完成。 |
| 旧结果/recipe/历史预览消费者 | existing workbench 明确 EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE、NOT_READY；recipe 是解释；独立 candidate CLI 是 historical preview。 | [existing workbench](D:/GPTProject/value-investment/src/value_investment_agent/application/product/workbench.py:82)、[recipe](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_recipe.py:8)、[preview CLI](D:/GPTProject/value-investment/scripts/current/build_product_workbench_candidate.py:2)。这些路径不能替代 fresh 当前决策。legacy latest-server 诊断继续隔离：[report_recommendations.py:12](D:/GPTProject/value-investment/scripts/diagnostics/report_recommendations.py:12)。 |
| status 语义冲突 | 调度 wrapper status=BLOCKED_BY_RESEARCH_SCHEDULER，具体原因在 schedule_gate；服务 COMPLETED/COMPLETED_WITH_BLOCKERS 是运行状态；suggested_state 是 recommendation_type。 | [调度结果](D:/GPTProject/value-investment/src/value_investment_agent/application/product/company_research.py:122)、[服务状态](D:/GPTProject/value-investment/src/value_investment_agent/research_application.py:769)、[产品字段](D:/GPTProject/value-investment/src/value_investment_agent/application/product/workbench.py:142)。不得将 BLOCKED_NO_REGISTERED_SCOPE 当模型结论，或 COMPLETED/NO_ACTION 当 READY。 |
| D3 未接通 | 当前 workbench 固定 BLOCKED_PRIVATE_INPUT、position_guidance=null；投影仅支持当前 NO_ACTION/BUY_CANDIDATE。加减退出解释文字不等于真实持仓/Entry Thesis/IPS 已接入。 | [workbench.py:151](D:/GPTProject/value-investment/src/value_investment_agent/application/product/workbench.py:151)、[decision labels](D:/GPTProject/value-investment/src/value_investment_agent/application/product/decision_surface.py:33)、[未评估持仓条件](D:/GPTProject/value-investment/src/value_investment_agent/application/product/decision_surface.py:216)。依赖 D2 后再做个性化，不补造私人输入。 |
| D4 未闭环 | 事件 review CLI 和材料性输入已有，但需要完整真实 scan、逐公告处置及 signed receipt；目前 Root 报告 INCOMPLETE。 | [review_event.py:22](D:/GPTProject/value-investment/scripts/current/review_event.py:22)、[签名要求](D:/GPTProject/value-investment/scripts/current/review_event.py:32)、[完整扫描门](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_reviews.py:46)。公共事件证据采集可独立推进，但不能据此宣布持续失效/重算链已通过。 |
| D5/D6 未接通 | D5 现有合同拒绝非 synthetic scope，预算类型不证明真实授权；真实观察不能灌入 synthetic signal。Root 的 ledger0 不提供真实会话验收。 | [sentiment_contracts.py:48](D:/GPTProject/value-investment/src/value_investment_agent/domain/portfolio/sentiment_contracts.py:48)、[synthetic policy](D:/GPTProject/value-investment/src/value_investment_agent/domain/portfolio/sentiment_contracts.py:87)、[预算约束](D:/GPTProject/value-investment/src/value_investment_agent/domain/portfolio/sleeves.py:41)、[D6 目标依赖](D:/GPTProject/value-investment/docs/current/advisory-sentiment-satellite-goal-v1.md:208)。本轮只隔离未来 sidecar。 |

继承 F1-F4 后的实际差量：v2 原件不能缺 local binding（[source_bound_inputs.py:51](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:51)）；source cutoff 必须同 research_as_of、逐 source availability 不晚于 cutoff（[同文件:84](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:84)）；NOT_ADMITTED distribution 不消费隐式包（[同文件:99](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:99)）；消费的 scenario leaves 与 named reviewed assumptions/bindings 必须完整、唯一、数值相等且引用已绑定来源（[同文件:104](D:/GPTProject/value-investment/src/value_investment_agent/application/product/source_bound_inputs.py:104)）。这些是新增的静态接线证据，不把旧报告的四个问题继续一概标成“完全未修”，也不标成已验收关闭。

剩余边界：上述 v2 限制不自动升级 legacy 包；原件 SHA 和引用 ID 不证明 PDF 页表提取、币种/单位/归母/合并口径正确；source 级可用时间不能替代每项实际消费事实的时点与口径映射；NOT_ADMITTED 是显式不准入分红，不是分红研究完成。真实 adapter 必须保留这些差异，不按输入 schema 默默补 VERIFIED。

## 4. M2 候选到 ResearchCase 的最小接线

已有 M2 `CandidateReason` 保存 symbol/name/channel/reasons/metrics/evidence_refs/evidence_date/data_status/profile_status/priority_tier/candidate_class（[m2_opportunity_discovery.py:420](D:/GPTProject/value-investment/src/value_investment_agent/m2_opportunity_discovery.py:420)）；candidate_pool 保留同股全部通道原因（[同文件:773](D:/GPTProject/value-investment/src/value_investment_agent/m2_opportunity_discovery.py:773)）。verified pool 只过滤已经 VERIFIED 的记录，不承担研究晋级（[同文件:780](D:/GPTProject/value-investment/src/value_investment_agent/m2_opportunity_discovery.py:780)）。receipt 有规则、时点、Universe、证据和 coverage/candidate signature（[同文件:789](D:/GPTProject/value-investment/src/value_investment_agent/m2_opportunity_discovery.py:789)）；signature 不是完整原件哈希替代物（[同文件:810](D:/GPTProject/value-investment/src/value_investment_agent/m2_opportunity_discovery.py:810)）。

现有 builder 只从 direct case/nested research_case/records.case 中选出已写好的唯一 Case，再 typed conversion（[research_case.py:20](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_case.py:20)、[实际构造:57](D:/GPTProject/value-investment/src/value_investment_agent/application/product/research_case.py:57)）。没有候选理由自动变 thesis/事实/假设的转换。

最小 handoff draft：

1. 显式选一只证券，绑定 exact M2 receipt 路径/hash、run/rule/as_of、Universe/membership 和全部通道原因及原始 evidence refs；保留 LEAD/VERIFIED 原意。
2. 补正式 issuer/security/exchange 身份证据及 profile/router 适用性；筛选 metrics/priority 只解释为何研究，不写入 Facts.verified 或研究批准。
3. 另提供经过审阅的 case 内容：thesis/counter-evidence、问题/缺口、证据时点、风险、下一触发；缺失就保持缺失，不由 score 自动补齐。
4. 将该 case-source 显式交给已有 `build_research_case.py --symbol --source --output`（[参数](D:/GPTProject/value-investment/scripts/current/build_research_case.py:18)），再与来源绑定 Facts、实际估值 AssumptionSet/scenarios、quote/event/reviews 构成单公司 package，复用现有 runner。手工来源录入也必须留版本/hash receipt。

此接线仅减少上游到研究入口的重复录入；不新建筛选排名、不改变核心 ResearchCase 合同，不创建独立公司研究引擎。

## 5. D2 输入交接与 D3/D4 执行次序

通用 source-bound 单公司 package 不可丢失的约束：

| 边界 | 交接必须保留 |
| --- | --- |
| 输入时点 | report period、逐 Facts/Assumptions/source published/available/basis；research_as_of/cutoff、valuation date、实际 fetched/reviewed/computed；quote session/final 状态；event effective/available/detected、扫描起止/coverage。今天 observed_now 不回填历史运行或同期 PIT。 |
| 身份与版本 | security_id/symbol/exchange/issuer 及依据；case/package/run/descriptor/schema；profile/model/parser/formula/rule/config 版本及精确引用；事实、报价、分红、事件、审批同主体、相容版本。 |
| 实际估值假设 | 保留 Bear/Base/Bull、名称/单位/basis/rationale/evidence/confidence/sensitivity、折现/增长/ROE/留存/现金流时点/股数/terminal；审阅假设与模型真实消费 scenario 的一一映射。quote 只进 PriceBridge，不反拟合内在价值假设。 |
| 来源与口径 | URL/id/local_path/SHA、物理页/表/摘录、提取与核验方法、input_fact_ids；原始值/标准化值、币种/单位/FY-YTD-TTM/合并-母公司/归母-少数股东/普通股分母；代码许可与数据使用权分别记录。null 与有证据的 0 分开。 |
| 旧结果不可变 | 保存 exact ID/version/hash、实际依赖 manifest、旧 conditional/rejected/stale 的原意；更正只能追加新结果与 supersedes/invalidation。latest 是可变指针，解析后仍须精确重核。关 sidecar 禁止旧缓存作为当前信号，但不改写/删除历史制品。 |

约束及已有模块的更细定位沿用 [边界审查第 4 节](D:/GPTProject/value-investment/docs/current/d2-adapter-boundary-review-20261008.md:64)。输出不可覆盖门已存在于 [common.py:54](D:/GPTProject/value-investment/src/value_investment_agent/application/product/common.py:54)；精确依赖重放见 [artifact_bundle.py:36](D:/GPTProject/value-investment/src/value_investment_agent/application/decision/artifact_bundle.py:36)。

执行顺序遵循 [Goal gate order](D:/GPTProject/value-investment/docs/current/advisory-sentiment-satellite-goal-v1.md:223) 和 [当前 D2/私人输入边界](D:/GPTProject/value-investment/docs/current-stage-goal.md:30)：

1. Root 先验证 replay 修复，包括缺审批但可选 payload 存在/不存在的封存组合，哈希匹配后仍需完整重建；合法 NO_ACTION 不要求伪造审批。现有 [test_d2_optional_payload_replay.py:127](D:/GPTProject/value-investment/tests/test_d2_optional_payload_replay.py:127)、[篡改拒绝:157](D:/GPTProject/value-investment/tests/test_d2_optional_payload_replay.py:157) 只是 synthetic 测试源码证据，本文件不报告它们通过。
2. D2 使用真实 600519 显式 package/原件、cutoff 与完整实际假设绑定，先过数据/身份/PIT，再 Research/Financial gates、thesis/counter-evidence、估值。按具体门记录 admitted/conditional/refused，不把字节匹配叫事实批准。
3. D4 的公共事件采集/审核可与第 2 步并行。当前建议所需的完整事件扫描、逐项材料性、有效窗口及当前 quote 必须先满足，才形成有效 ModelValidity/PriceBridge 并进入建议。INCOMPLETE 不允许用“无重大事件”补齐；这属于 D2 价格有效性依赖，不要求先宣告完整 D4 完成。
4. D2 固定精确决策制品并经真实入口重放后，D3 才复用研究/估值结论；没有 IPS/portfolio/持仓 Entry Thesis 就继续 BLOCKED_PRIVATE_INPUT/null。非个性化研究输出与个性化仓位验收分别记录。
5. D4 持续监测再绑定 exact case/model/rule/event 版本，按来源可用时间失效受影响结论、生成有界重算请求及新结果，保留旧结果。当前源码有事件入口不证明连续监测与调度都已接通。D5 保持关闭；D6 的真实 Shadow/产品/用户验收独立，不以重复离线重放增加会话。

数据准入、投资准入及产品发布是分别验收的边界。真实负向输出可以验证拒绝能力；synthetic NO_ACTION 或缺完整事件/私人输入的负向跑通，不等于真实 D2 或 Goal 完成。

## 6. D1/D5 统一外层 envelope draft（不实现）

第 8 节已有 default-off、逐 observation provenance、有限预算；但空 DISABLED/拒绝结果没有固定外层 identity/version/date/hash（[现有 result:124](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:124)）。以下只补未来 owned-adapter 结果载荷设计，不修改当前核心合同或现有 status enum。

```text
ObservationEnvelopeDraft = {
  schema_version: "open-source-observation-envelope/v1-draft",
  status: "DISABLED" | "REJECTED" | "OBSERVATION_ONLY",
  reason_codes: [], action: "no_order",
  identity: {request_id, evaluation_id, channel, binding_id,
             subjects: [{security_id, symbol, exchange, membership_ref}]},
  versions: {request_contract_version, upstream_commit, adapter_version,
             formula_version, parser_version, profile_version, rule_version},
  dates: {as_of, cutoff_at, evaluated_at, reviewed_at,
          source_published_at, source_available_at, availability_basis,
          fetched_at, computed_at},
  sources: [{upstream_repo, immutable_code_url, data_provider, raw_data_ref,
             input_fact_ids, license_ref, code_license_status, data_rights_status}],
  hashes: {request_sha256, config_sha256, execution_budget_sha256,
           declared_inputs: [{ref, sha256, verification_status}],
           verified_code_sha256, verified_raw_sha256, verified_membership_sha256,
           verified_canonical_input_sha256, output_sha256},
  switches: {enabled: false, channel_enabled: false, binding_enabled: false,
             mode: "offline_snapshot_only"},
  execution_budget: {policy_version, max_subjects, max_features,
                     max_raw_bytes, timeout_ms, usage},
  capital_budget: {scope: "NOT_AUTHORIZED", policy_ref: null,
                   policy_sha256: null, core_value: null, tactical_hotspot: null},
  observations: []
}
```

全部结果固定保留上述 key；实际未知值为 null，空集合为 []，不省略身份/版本/日期/hash组。请求已有 channel/as_of/cutoff/subjects 即原样绑定；缺失 identity/as_of/cutoff 不生成观察，开启时 REJECTED/MISSING_REQUEST_METADATA，关闭时仍 DISABLED 并留缺项原因。evaluation_id 与 evaluated_at 由本地调用产生；computed_at 仅指实际特征计算时间，DISABLED 时为 null，不能用 evaluated_at 冒充 source_available_at。

DISABLED 优先检查总/通道/binding 开关，只绑定调用方已提供的请求与已加载配置，不读取禁用原件、许可证文件、代码、网络、不 import 上游、不启动 worker、不重算特征。request/config/execution-budget hash 可在内存中计算；调用方声明 hash 留 declared_inputs/UNVERIFIED，未读字节的 verified_* 必须 null。禁止为了补 envelope 来源或版本去读取被禁用输入。REJECTED 保留到拒绝前实际完成的核验及原因，未核验字段仍 null；两种状态 observations=[]。

REJECTED 的 granular reason_codes 可映射已有 LICENSE_UNKNOWN/SOURCE_UNAVAILABLE/INSUFFICIENT_EVIDENCE/STALE/QUARANTINED 等拒绝语义；这不是修改旧枚举。许可 UNKNOWN、来源/PIT/身份/单位/hash/coverage/预算失败都不得转 OBSERVATION_ONLY。该状态只表示观察载荷通过相应数据边界，仍无 signal、估值、仓位或投资准入。

规范哈希 draft：UTF-8、固定 schema 与 key 排序、无多余空白；Decimal 用规范十进制字符串（零规范为 "0"，禁止 NaN/Infinity）；日期为 ISO date，时刻含明确时区；subjects 按稳定身份排序，成员/逐输入 hash 按固定 ref 排序。request hash 不含运行时钟；output hash 对完整结果去掉自身字段后计算，包含状态、原因和 audit metadata。declared hash、verified raw hash、canonical input hash 与 output hash 分离；关闭也有可核验 output hash。规则/公式/parser/profile/config/membership/预算变化使当前缓存不合格，不覆写历史 payload。

运行预算与资金预算独立：D1_FACTOR/D5_HOTSPOT 各自有限 subject/feature/bytes/time 配额；沿用 [五库审查建议限额](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:172)，不自动扩大扫描。运行配额不授权任何 sleeve 资金；资金默认 NOT_AUTHORIZED/null，不合成 USER_CONFIRMED receipt、不挪用 CORE_VALUE 预算。未来真实 tactical 预算另须人类授权及共享总风险门。D1 仅既定 EP TTM/GPA，D5 仅既定三项观察（[原 scope](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:154)）；不扩特征、排行榜或策略。

关闭切换时禁止读取旧缓存作为当前观察；旧记录仍供精确历史审计。核心 D2 不依赖该可选 envelope，失败不会使核心研究状态升降；真实观察禁止进入现有 synthetic D5 合同（[原隔离要求](D:/GPTProject/value-investment/docs/current/open-source-adapter-review-20261008.md:168)）。未来实现才需验证全关闭零 IO、空拒绝审计字段完整、null/真实零区别、hash/PIT/预算反例及关闭后缓存失效，本轮不写这些测试。

## 7. Root 实际入口验证交接

以下是入口与待提交证据，不是本代理已执行命令。不得填猜测的文件名/hash；Root 用其真实 600519 manifest 中的路径、scope 和 exact hash，输出到新的仓库内路径。

| 步骤 | 实际入口 | 必须保留的验收证据 |
| --- | --- | --- |
| Case 接线 | `scripts/current/build_research_case.py --symbol 600519 --source <reviewed-case-source> --output <new-case.json>` | 唯一公司、全部候选原因、正式身份/profile、case evidence/cutoff、输入输出 hash；不是运行 M2 扩扫。 |
| 新研究 | `scripts/current/run_company_research.py --symbol 600519 --package <package> --quote <quote> --quote-sha256 <hash> --event <scan> --event-sha256 <hash> --research-reviews <packet> --research-reviews-sha256 <hash> --output <new-research.json>`；仅在确有注册重开请求时追加 `--schedule-request <request>` | [参数来源](D:/GPTProject/value-investment/scripts/current/run_company_research.py:23)。冻结 package/quote/event/reviews/ledger/scope，保存 CLI receipt 的 output hash、source_verification、输入指纹、逐层 blocker 及 bundle。若 scope 拒绝则不绕过或伪注册；记录 exact reason。 |
| 当前工作台 | `scripts/current/build_current_workbench.py` 支持相同 package/quote/event/reviews/scope 参数，另需 `--output`，可 `--report` | [实际参数](D:/GPTProject/value-investment/scripts/current/build_current_workbench.py:20)。这是另一次 runner 调用。一次性重开场景选它作为首次纵向入口并保存其嵌入 bundle/决策，或由 Root 另行解决 pinned fresh-result 消费缺口；不要重复消费同一 scope。 |
| 重放与产品读模型 | workbench 内先 `verify_decision_recommendation_payload`；再 candidate application 的 `decision_workbench_path/sha256` 调用 projector | [workbench 重放](D:/GPTProject/value-investment/src/value_investment_agent/application/product/workbench.py:116)、[投影](D:/GPTProject/value-investment/src/value_investment_agent/application/product/decision_surface.py:108)。缺审批的 exact 封存输入仍应重放，错误依赖/主体/日期/hash/完整重建不一致必须拒绝。 |
| 发布边界 | current publisher 有 `--decision-workbench` 和 `--decision-workbench-sha256`；独立 historical preview CLI 未提供这对参数 | [真实 publisher 参数](D:/GPTProject/value-investment/scripts/current/publish_product_workbench_to_canonical.py:1043)、[转发](D:/GPTProject/value-investment/scripts/current/publish_product_workbench_to_canonical.py:1098)。不误把 preview 命令当 fresh current 验收入口；本轮不运行 publisher、不制作或复制 Excel。Root 另负责候选保留、正式展示/WPS及用户验收。 |

Root 应分别报告：replay 工程验证；真实 package 来源/事实/PIT/假设准入；quote 和事件有效性；真实决策及 exact bundle 重放；当前产品呈现；私人输入与运行验收。CLI exit 0、128 pass/2 fail 的旧摘要、synthetic NO_ACTION、单条 verified_close 以及既有 Excel 页面数量，都不能合成“D2/Goal 完成”。没有所需外部证据时保留负向结果与明确重开触发，不承诺 BUY 或收益。

## 8. 静态观察字节绑定

2026-10-08 18:12-18:13 +08:00 读取。以下只固定当时源码/设计字节，既不是测试回执，也不认证财务真伪；并行修复后 Root 应重新绑定其最终运行所用版本。

| 文件 | SHA-256 |
| --- | --- |
| `docs/current/open-source-adapter-review-20261008.md` | `97d0a1f0f2f73a1c46b4f2dd6988488f802cad0109f9069b63c754403cea2e94` |
| `src/value_investment_agent/application/product/source_bound_inputs.py` | `d959c55faee7d5292f7390a72990e7c7d884d9132dc4d84f58d11047a79e0533` |
| `src/value_investment_agent/m1_valuation_package_builder.py` | `61d8e23cd06b51170b88b3c3ba8e25aad2d4b627196914ddbf4fa24cab3fc36e` |
| `src/value_investment_agent/application/product/company_research.py` | `8252065f0f150d8ce35cdadba8c7f753c90348260c9deb8070239b56e13cd3a3` |
| `src/value_investment_agent/application/decision/restore_decision_recommendation.py` | `d9ae783ab3c2c7ecc95613d2789a7040a066587e9f1122c115d0c9051a02c7f0` |
