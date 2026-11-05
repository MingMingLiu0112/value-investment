# VALUE-MAINLINE-P0：D1/G2 生命周期与产物持久化只读审计

基线：vf1 HEAD `283c7212d832f52118705bb095e046e0c36dcbfc`；2026-11-01。仅静态读取源码、SQL、现有测试文件名；没有调用模型、provider、数据库、生产服务，没有读取私人 pointer 内容或真实账户。开始时 `git status --short` 仅显示用户 `config/current-research-drafts.json` 修改。本报告不代表运行验收或数据库实机持久化验收。

## 结论与 Root 可立即复用点

已有两层，不应再建第二套 task/store：

1. `application/research/agent_review/task_execution_v1.py:59` 的 `ResearchTaskService(root)` 是文件持久化执行生命周期；`operating_task_v2.py:85` 的 `LiveOperatingTaskService` 继承它，复用目录、hash binding、锁、append version、atomic head、read/list/cancel/run/resume。两者分别使用 saved/mock 与显式授权 live 语义，不能互相升级 scope。
2. `research_artifacts.py:189/245/298` 的 Identity/Envelope/StoredArtifact 与 `research_artifact_repository.py:32` 的 repository 是研究产物身份与持久化合同；`ResearchApplicationService.run_company_research` 已实际使用它们。它不是任务队列。

最小 ModuleRun 是现有任务与研究产物的**投影/关联合同**：保留原 task_id、record_binding、artifact_id、payload_sha256 与输入绑定；八个操作适配到现有入口。没有记录的字段必须 null/UNKNOWN，不凭 SUCCEEDED 推导投资批准。已有任务只投影，不重签历史版本。同步研究入口缺生命周期记录时明确 `LEGACY_UNTRACKED_EXECUTION`，不能凭现存 receipt 补造创建、运行或取消事件。

## 真实存储、合同与代码入口

下列路径均相对 `D:/GPTProject/value-investment/.tmp/vf1/src/value_investment_agent/`，行号按审计时工作树。

| 入口 | 实际行为与复用限制 |
| --- | --- |
| `application/research/agent_review/task_execution_v1.py:59-165` | `runtime/research-task-execution-v1/<rt-id>/input.json` 固定输入；`versions/0001-<hash>.json` 等不可覆盖写入；`current.json` 原子可变头。每版本含 input_sha256/previous/version/status/updated_at；读取验证完整链，缺/过时 head 要显式恢复。每链最多256版本。不是外部不可篡改日志：可检测不一致，但没有外部签名锚定防止整链替换。 |
| 同文件 `:229/272/282/307/449/452` | create/read/list_for_symbol/cancel/run/resume。request_key 哈希确定 rt-id；相同 key 不同输入拒绝；mode 仅 SAVED_RESPONSE/MOCK。list 最多检查100目录项、返回20任务，超限明确报错；不会冒充完整全量历史。 |
| 同文件 `:313-447` | 调用前持久化 token reservation，未结算保留计费；bounded attempts/requests/tokens；execution 与 state 双锁；whole-packet checkpoint 重验。run 同步，API BackgroundTasks 负责同进程调度，不是耐久外部 worker queue。崩溃不会后台自动续跑。 |
| `application/research/agent_review/operating_task_v2.py:85/138/193/230/269` | live store 为 `runtime/research-task-execution-v1/live-operating-v1`；同样 input/version/current 合同，保留 role response hash、请求hash、context fingerprint、config/implementation pin、返回但被拒绝的响应、成本预留/结算。scope 区分 LIVE 与 TEST_ONLY；公开 partial 不等于 SUCCEEDED/批准。resume 只重排队，之后 run 才调用。已发布角色可重验复用；不明中断预留不清零，不承诺 provider exactly-once。 |
| `application/research/agent_review/snapshot.py:18/40` | `ResearchSnapshot` / `load_research_snapshot(root,workbench,expected_sha256,symbol)`：单一 ResearchCase、源原件bytes、证据ID、期间/可得性、workbench fingerprint 验证。它是输入快照，不是 Run store，也不是每个模块通用输入模型。 |
| `application/research/agent_review/llm_pilot.py:175/235` | `verify_llm_packet` / `run_llm_research_pilot` 是 saved/mock D1 原执行/重验入口；不要另建 role engine。 |
| `research_application.py:207/467/547/561/1117` | `ResearchRunSpec` → `ResearchApplicationService(repository,router,...)` → `CompanyResearchRunOutcome`；`_persist_core_artifacts` 用 spec.run_id 保存 case/facts/gate/assumptions/valuation/validity/quote/pricebridge/currentstatus 等已有类型。不等于整个 use case 一次原子提交：逐产物保存，中途失败可已有部分artifact。 |
| `research_batch.py:475/511/713/727` | `ResearchBatchService(repository, explicit evidence_stops,...).run(spec)`；实际 started_at/finished_at、company结果与artifact_ids、previous_run_id；input+dependency+rule一致才 UNCHANGED；Evidence Stop + 单次 reopen claim。复用 batch receipt，而非另造 batch task。无通用实时取消、队列或 ModuleRun 事件流。 |
| `application/research/explicit_cash_research_runner_v1.py:45` | 真正进入 typed v4 descriptor、source contract 验证、共享 router/service。**此 helper 构造 ResearchApplicationService 时未注入持久 repository，默认 InMemory**；返回 outcome/descriptor/package/ledger 不证明跨进程持久化。调用方要明确保存结果绑定，不能把内存artifact_id冒持久ID。 |
| `research_artifact_repository.py:32/80/265` | 协议：save/save_object/load_by_id/load_by_hash/load_latest/list_versions/verify。InMemory 进程内；Postgres 持久化实现存在，但本轮未连接/迁移/验收。Postgres connection 为懒连接；不要为了readmodel构造后访问 connection。 |
| `research_artifacts.py:189-296` | Identity：scope_type/key/artifact_type/schema_version/as_of/available_at；Envelope：canonical_payload/payload_sha256/evidence_refs/run_id；natural_key=identity+payload hash，**不含 run_id**。相同自然键去重可能返回先前run的同一artifact，关联必须显式，不能依artifact.run_id反查推断完整新run清单。 |
| `sql/20260922_research_artifacts.sql` | research_artifacts / research_artifact_heads / research_artifact_references 已有表；natural_key UNIQUE，head 可变。repository save INSERT ON CONFLICT 去重。SQL没有 append-only UPDATE/DELETE 禁止触发器，不能声称DB物理不可改。无需为本次审计部署DB或迁移。 |
| `application/decision/artifact_bundle.py:18/36` | `export_artifact_bundle` + `ReadOnlyArtifactBundleRepository` 复用离线已导出产物与hash校验；这是只读快照载体，不是第二写库。 |
| `research_runtime_import.py:457/519`；`research_e2e_replay.py:755` | import_runtime_artifacts / semantic_parity_report / run_three_company_replay 是既有导入与有限历史重放入口；导入会写显式repository，不能作为GET动作。不是八模块任意自动重放器。 |

## ModuleRun 字段逐项真实矩阵

| 请求字段 | 现有可绑定来源 | 覆盖/缺口与最小投影 |
| --- | --- | --- |
| runid | task_id；ResearchRunSpec.run_id；batch run_id | 有多命名空间；保留 backend_kind + 原ID，不另生成第二任务身份。 |
| module / type | workflow / mode；artifact_type；model/profile contract | 有局部值，无统一八模块枚举/注册映射。显式 mapping，不按文件名猜。module 与 execution_mode/artifact_type 分开。 |
| symbol | spec.symbol；security scope_key | 直接复用；batch不能伪装单一symbol。 |
| status | 六状态 QUEUED/RUNNING/WAITING_EVIDENCE/SUCCEEDED/FAILED/CANCELLED | task可复用。research/model/gate/business approval状态必须另字段，不能直接同义映射。readview 会因源变化覆写可见status，保留 persisted_status/原record binding；live view未统一提供该字段，投影需保留读出的state状态。 |
| times | created_at / updated_at；batch started_at/finished_at | task没有稳定独立 started_at/completed_at/cancelled_at。可从已验证版本中的状态首次/末次变迁投影，需注明 derived_from_versions；attempt多次时每次区间分开。没有就null，不能把 updated_at 直接称完成时间。 |
| input_manifest | input.json hash；workbench/source_binding；snapshot/context fingerprint；descriptor/input_sha256 | 有；统一暴露 exact ref 列表与 contract/schema，不把JSON本身/任意客户端path当可信输入。 |
| output_manifest / artifacts | checkpoint pilot.json；live roles/returned_responses；outcome stored artifacts；batch artifact_ids | 有分支清单；不是一个全局output manifest。区分 VERIFIED_CHECKPOINT、REJECTED_RESPONSE、RESEARCH_ARTIFACT、未持久化 outcome；失败允许已验证partial。 |
| source_versions | snapshot.evidence / bound catalog / source_binding/context fingerprint | 有局部源hash/时点；显式列出来源，摘要fingerprint不等价完整source manifest；取得时间未知不制造PIT。 |
| code | implementation_sha256 / descriptor model/parser/rule deps | 有局部pin；口径不一（旧raw与新LF源码合同），投影必须携带basis，不把历史raw pin静默转换或用当前HEAD冒历史运行codeSHA。 |
| parent | batch previous_run_id、unchanged_from_run_id；task版本previous | 跨模块 parent_run_id/dependency graph没有统一字段。previous hash是版本前驱，不能冒业务父运行。新调用可记录已验证 parent ref，旧运行null。 |
| events | task version snapshots；live returned_responses/reservations/roles | 可派生状态/检查点事件，非独立领域event store；timestamp只用已有updated_at；全链重验后投影，禁止GET _save。 |
| warnings/errors | error_code；live validation_error；research blockers/gaps、scenario_failures | 可投影；区分warning、输入失效、执行失败与经济未批准，原reason不吞成通用SUCCESS。统一error结构尚缺。 |
| metrics | attempts/provider_requests/usage/new_llm_calls；live成本currency/reserved/settled；batch timing | 可直接取；saved/mock usage不是新LLM花费，configured rate estimate不是实际账单；没有延迟/成本就null非0。 |

## 八个生命周期方法覆盖（可直接实施的薄适配）

| 方法 | 当前可复用 | 真实覆盖 |
| --- | --- | --- |
| create | 两现有service.create | 有幂等/绑定输入；saved与live权限和scope不能合并默认live。 |
| read | 两service.read → _load + _view | 有链校验及当前源重验；read取锁，锁实现可创建/写锁文件，不可笼统称全filesystem零写。投影不要新建目录/重签/修复head。 |
| list | list_for_symbol | 有严格100/20边界，saved/live不同store；聚合必须保留namespace/超限，不静默截断。 |
| run | run → _drive | 有本地排他执行、预算、checkpoint；不是自动恢复worker。 |
| cancel | cancel | 合作式取消，保留已产物，不能撤回已发远程请求或退款；SUCCEEDED不改CANCELLED。 |
| resume/retry | resume | 有界显式requeue/recover；源/实现不符拒绝，不能为了重试重签旧input；不自动paid。 |
| history | _load验证链；artifact repo.list_versions | 底层有历史，缺统一公开task version history方法；bounded只读投影已验证链即可，不新store。list_for_symbol是任务列表不是单任务完整版本史。 |
| diff | envelope.payload_object、canonical hash、input/version bindings | 无统一ModuleRun.diff；最小只对两已验证同symbol/module兼容manifest做结构化差异；源、假设、代码、结果分别列，不能把不同cutoff/币种/期间标成同口径数值变化。 |

## “八方法”业务覆盖的命名边界

用户本次消息没有枚举八个业务方法名；源码没有 ModuleRun/八模块注册合同。不能把上述八个操作或三个模型注册等同八个投资方法全部实现。仓库可直接查到的显式“八项”是 `docs/excel-stage-frontend.md:8` 的八决策检查。若 Root 本轮八模块枚举另有定义，应按其名称做显式映射，禁止猜同名即成功。下表仅报告现有八检查的实际runner/artifact接点，不充当新业务验收：

| 既有八检查 | 现有覆盖 | ModuleRun 缺口 |
| --- | --- | --- |
| financial facts | snapshot/native facts/source contracts、financial_facts artifact | 原件冷重放在相应sourceconsumer，非全局独立持久任务。 |
| business quality | ResearchCase positives/counter/evidence、company profile | 来源画像与质量经济采纳分离；不是运行成功即quality PASS。 |
| model applicability | PROFILES / ValuationRouter / model_validity | router注册3模型族，并非8个估值模型；缺独立模块run投影。 |
| scenario valuation | ResearchApplicationService + v4 runner + valuation_result | 有真实模型路径；部分调用内存repo，不能宣称全持久化。 |
| price bridge | price_bridge / price_attractiveness artifacts | 与估值、当前报价资格分离；无独立通用task。 |
| research gate | research_gate / current_research_status artifacts | 有评价与存储；执行SUCCEEDED不等于经济批准。 |
| portfolio gate | pre_decision_eligibility / minimal_portfolio_preconditions | 有合同；本轮不读私人账户，不判当前PASS或造资产。 |
| final decision | decision_recommendation / investment_decision_review / entry thesis | 有产物类型及上游合同；无据不能批准/交易，始终no_order。 |

## 最小实现建议与必要拒绝

1. 新增小的 application readmodel/adapter，构造 ModuleRun 字段验证与 backend映射；读取现有任务版本/研究产物，不新task目录/indexstore/worker、provider或ResearchCase。
2. 已有task直接以task_id为runid；研究runner以原run_id+显式输出manifest关联，离线复用export_artifact_bundle。需要耐久写入时由授权执行入口显式注入既有repository或保存现有bundle，不在GET调用默认内存runner后声称已持久。
3. history/diff仅做现有已验证记录的有界只读投影。旧任务code/source变化可给 historical_record_integrity 与 current_replay_validity 两层结果；不得为展示历史绕过hash，也不能把当前不可重放的旧SUCCEEDED提升为当前有效研究。
4. 新事件/父关系仅在新执行时沿既有_save扩展或现有artifact元数据绑定；旧input、旧version不回填重写。不从task.previous生成parent_run_id。错误与partial保留原绑定，最新失败不fallback旧success。
5. 权限保留现有route：`presentation/web_api/research_task_routes.py` 的任务列表/read/control都授权；live route公共结果是筛选投影而非所有私有执行细节。公有ModuleRun视图不可泄露raw_response、配置/endpoint、私人workbench路径或账户；不能为便捷绕过权限。

## Root 最小验证清单（本报告未执行）

- 原存储create→run→新service.read / cancel / resume；相同key同input幂等、不同input冲突；source/hash/implementation变动拒绝。
- mock/saved输出不能标LIVE；TEST_ONLY不能经济批准；预算不明预留不清零；GET不调用provider/不_save、不触发resume。
- history链破损/超限显式拒绝；diff匹配symbol/module/期间单位，manifest缺失不可伪装空差异；parent与previous严格区分。
- outcome内存与durable artifact/bundle区分；新进程读取只能靠真实持久载体，不能凭当前Python对象“通过”。
- 直接复用既有测试文件：`tests/test_research_task_execution_v1.py`、`test_operating_task_v2.py`、`test_research_artifacts.py`、`test_research_artifact_repository.py`、`test_research_batch.py`、`test_research_application.py`；Postgres仅源码审查，`test_postgres_research_artifacts.py`非本次实机证据。

未修改源码、config、旧证据、私人pointer；没有测试运行、模型调用、DB连接、生产操作或提交。
