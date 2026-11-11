# VALUE-MAINLINE-P0：D2 / F1 / F2 独立只读审计

审计基线：`283c7212d832f52118705bb095e046e0c36dcbfc`（vf1）。本报告只核源码、注册入口、实际留存原件/回执及本次独立调用。未联网、未付费、未读取凭证/私人账户/DB、未部署、未改经济模型或阈值。文档和前端阶段目录仅用于确定D2/F1/F2名称，不作为完成证据。Root负责基线/合同总审；本报告不代替其结论。

## 1. 结论与决定性缺口

1. **D2有真实来源及实际消费者，但有两种不同能力。** 600519/600887为“原件历史重放 + 已有source-bound假设/资本路径校验”，不是本次LLM重新研究；000568另有真实F/C/Event新假设、逐项来源绑定及确定性driver bridge。不能把前者三branch当作三角色，也不能把000568一例视为三家公司均已自动研究。
2. **F1已经真实贯通到共享模型。** 两个既有候选及000568季度重验均可由本次独立调用重算出条件值；不是只读saved response。F1证明条件现金/权益及终端算术可消费，不证明主区间经济采用、全额股息可持续或当前决策资格。
3. **F2有接口、校验器、消费者和真实拒绝，尚无本范围三家公司当前决策成功闭环。** 600519五维检查均阻断；600887缺精确候选alignment；000568独立main路径明确current=false、main_adopted=false、无numeric价格阈值。不能把F1有价格数值、同基准参考线或可渲染Web称为F2完成。

本轮唯一决定性业务断点是：**尚无“已经济选用的确切候选 + 对同一候选闭合的当前股本/分配/材料性/财务更新 + 合格最新报价”的联合正例。** 缺口并非没有估值内核，也不能通过修改日期、把UNKNOWN补零、套默认安全边际或新增模型来解决。允许交付LOW条件研究工作候选；主采用与当前决策仍须明确拒绝/待审。

## 2. 源码入口与实际消费链

以下路径均相对vf1根，行号以本次读取为准。

### D2：现有假设adapter

- `application/research/operating_assumption_draft_v1.py:123` `load_operating_assumption_draft`；`:290` `build_operating_assumption_draft`只是转发。
- 输入默认是`config/research-assumptions/{symbol}-joint-capital-cash-path-v4.json`及`config/research-proposals/{symbol}-joint-capital-cash-path-v4.json`；显式binding必须exact relative path/SHA256。两者均为版本化JSON，前者`joint-capital-cash-path-inputs-v4`，不是一个自由自然语言prompt。
- `operating_earnings_bridge.py:108 extract_statement`及`:271 research_from_retained_sources`冷解析两份官方PDF；`:176 build_operating_earnings_bridge`生成历史/TTM及normalization open items。adapter的`STATEMENT_FIELDS`逐字段核对历史观察和proposal实际输入，并重放`neutral.compile_joint_cash_choice_v4`生成资本路径。
- `operating_assumption_draft_v1.py:31 _source_times`核消费来源时间/身份；`:259`的`NORMALIZATION_NOT_ESTABLISHED`表达正常化未被证明，不谎称现有情景参数不存在。
- `presentation/web_api/operating_assumption_routes.py:10 register_operating_assumption_routes`提供GET `/api/v1/research-assumption-drafts/{symbol}`；读取不发LLM、不写事实/批准/估值。缺字节返回MISSING_SOURCE，坏hash/错公司/未来时点/场景不一致拒绝，不回退旧包。

### D2：真实新假设与确定性桥（当前注册真实样本000568）

- `agent_review/operating_sources_v1.py:17 build_operating_source_context` → `infrastructure/filings/first_research_fact_replay_v1.py replay_first_research_facts`：按native manifest原件页/行/单位/主体/时点冷核，再提取有marker、页码和hash的经营excerpt。source context不提供旧thesis/预测/最终估值。
- `agent_review/operating_driver_draft_v2.py:90 build_request`、`:168 validate_response`；prompt版本`operating-driver-prompts-v2-calendar-locked`。复用`operating_draft_v1.py:192 build_request`及`:264 validate_response`的来源/输出合同；COUNTER/EVENT携带本次F作为不可信新提案，不将其升级为事实。
- `agent_review/operating_task_v2.py:85 LiveOperatingTaskService`；`_load`校验hash链，`_context`重建源，`_view`重新验证实际response/request/context；`execute`才是paid入口，本次未调用。`research_context`只投影证据上下文，provider请求保留模型与usage。
- `domain/research/operating_driver_bridge_v1.py:30 build_basis`、`:89 calculate_path`、`:154 build_thresholds`、`:168 evaluate_condition`：同期间历史比较、七维角点及阈值由代码算，不以LLM叙述代替数值。driver范围仍是FORECAST假设，investment/funding/terminal可合法UNKNOWN。
- 真实task `rt-eac1c74997d17510398ce1fe1e5bea9e`本次`_load(recover=False)+_view`成功：三role均可重验，21drivers、三path×128corners、6derived；原第一次C缺invalidation的拒绝仍留存，4次真实调用不伪称3次无失败。SOURCE/FORECAST合法不等于每句AI解释经济正确。

### F1：共享现金与估值

- `domain/valuation/joint_capital_cash_path_v4.py:325 _step`：利润→可达/未上划→维护/WC/commitment→受cash/floor/capacity约束的新分配→权益与净资本结转；`:375 compile_joint_capital_cash_path`编译十年；`:40 TerminalEconomicContract`与`:216 value_terminal_economic_contract`处理单独终端。
- `valuation_models/residual_income_path_v4.py ResidualIncomeContractDispatcher`消费typed scenario；显式期retention仍限定[0,1]，不能表示超当期利润的新分配。目标派息不是现金能力证明。
- `application/product/pending_research_candidate.py:956 verify_pending_research_candidate`冷核源/实现/实际choice，再`build_v4_descriptor → build_research_run_spec → ResearchApplicationService`，不是只返回candidate中的旧数值。
- `application/research/value_research_analysis.py:103 project_value_research_analysis`及`:207 load_current_value_research_analysis`重算并核descriptor、joint review与三情景数值相等，再公开消费。
- 000568另走`main_valuation_revalidation_v1.py:87 read_main_valuation_revalidation` → `_consume` → `period_earnings_assembly_v1` → `operating_profit_cash_path_v1.compile_operating_profit_cash_path` → `explicit_cash_research_runner_v1.py:47 run_explicit_cash_research` → `ResearchApplicationService:561 run_company_research` + `v4_valuation_router.build_v4_valuation_router`。
- main的原件Q3=9M-H1仅一次，Q4=FY25-9M25基数条件迁移，H1next明确预测，第一完整模型年Jul26-Jun27。`liability_settlement_schedule_v1.compile_liability_settlements`将carrying debt4,511,807,421.96与declared dividend6,501,567,650.57仅Y1支付，总11,013,375,072.53；对应floor去重，不算新分红/CapEx、不赠送利息节约，非生产净资本无新增收益/释放。

### F2：实际价格对齐及拒绝

- `pending_candidate_alignment.py:899 load_pending_candidate_alignment`、`:1042 attach_pending_candidate_alignment`：quote、capital_structure、distributions、material_events、financial_updates五维；`:524 _qualified_quote`、`:549 _event_windows`、`:744 _materiality`、`:800 _assess`分别消费来源，不因来源列表非空就准入。
- 跨日资本/分配算术可重建，但源码明确`current_price_basis_compatible = same_basis`；现有跨日期有效行动链消费者仍不完整（`:498`说明）。这是实际能力限制，不应一律描述成只差人工签字。相同估值/报价日期仅豁免不存在的跨日期间，事件等门禁仍在。
- `pending_candidate_price_proposal.py:69 project_pending_candidate_price_proposal`、`:195 load_pending_candidate_price_proposal`：绑定确切候选/descriptor的未注册草案；`domain/decision/value_price_policy.py`提供draft/preview/prepare合同，不因数值存在批准执行。
- `model_validity.py:90 evaluate_model_validity`和`application/product/quote_bridge.py:169 quote_compatibility_ladder`为现有依赖；不是D2语言模型提供的投资意见。

## 3. 十二项准则矩阵

| 准则 | D2实际状态 | F1实际状态 | F2实际状态 |
| --- | --- | --- | --- |
| 1 domain | 历史bridge、driver角点、阈值与同期间比较存在 | 现金/权益/typed terminal存在并被消费 | 五维、model validity、价格政策存在；跨日basis存在明确未实现边界 |
| 2 app | 旧source adapter与新三role任务两条入口 | 候选verify/public analysis与新季度runner真实接共享service | alignment/price proposal被public analysis调用；不是孤立脚本 |
| 3 in/out schema | 旧v4 inputs/proposal；新source context、LLMResponse、operating paths；输出NOT_ADMITTED | exact descriptor/spec + typed scenario，输出年度ledger/conditional valuation | exact candidate+quote/action/event原件→五维结果/草案或拒绝 |
| 4 independent run | 本次两旧D2成功；000568真实task冷重验成功；000568旧adapter缺源 | 本次三公司共享v4重算成功 | 本次两旧公司current alignment均BLOCKED；000568main current=false |
| 5 tests | 有错hash/主体/时间/field/一致性/缺源/GET零写测试；实测项见第6节 | 有terminal、两公司real、main real及拒绝测试 | 有真实原件字段、同日正例、跨日拒绝、 stale quote、材料性反例 |
| 6 real case | 600519/600887历史52/50锚点；000568三role是另一真实链 | 675.10/799.20/930.01；13.00/16.09/20.24；6.20/16.85/27.22，各有不同日期 | 有真实partial及拒绝；没有由本次证据证明的三公司当前决策正例 |
| 7 errors | 精确缺源/错源/未来/错场景拒绝；原C缺字段失败保留 | not_ready/partial cash失败不得冒完整成功；旧first-input失败回执不升级 | 最新交易日拒绝、资本/股利/材料性/更新缺口明示，不机械减价格 |
| 8 provenance | PDF hash/page/field/PIT语义与提案binding，历史重放≠正常化 | 实际输入一致校验；000568当前source-only LF实现指纹与原件raw hash分开 | 原生报价、有效日、股利字段、精确候选材料性，报告检查点不替代行动完整链 |
| 9 web | API+DecisionDetail OperatingAssumptionDraftPanel、LiveOperatingResearchPanel | analysis公司接口及MainValuationRevalidationPanel实际源码接线 | CandidatePriceDraft展示alignment；本次未验8001进程/部署/浏览器 |
| 10 hardcoded | 旧两公司配置+000568native/摘录注册；非所有证券自动采集 | 内核无本次三公司价格常量；母义务源adapter含case特定页/金额 | 600519有case特定reconciliation；不泛化为市场级能力 |
| 11 defaults | max tokens4096/固定calendar是工程约束；经济UNKNOWN不补事实 | payout/access/reserve/floor/维护/WC/10年/终端是显式研究选择 | 不默认20/30/40%安全边际；main rules=()，threshold NOT_PREPARED |
| 12 dependencies | 原件/native parser、issuer身份、case config；新生成需授权provider/预算 | profile/type、源合同、权益/股数、模型spec、资本假设 | 选用研究+当前合法报价+资本/分配完整链+事件/财务影响+相应人工/私人门禁 |

## 4. 本次独立输入→输出实测

固定审计clock为`2026-11-01T16:00:00+00:00`，只作显式重放截止，不声称资料在此时之前任何历史日已被取得。调用未写注册状态或LLM台账。

| 实际入口 | 600519 | 600887 | 000568 |
| --- | --- | --- | --- |
| load_operating_assumption_draft | SOURCE_BOUND_D2_DRAFT，3branch，52anchors，8bindings | SOURCE_BOUND_D2_DRAFT，3branch，50anchors，6bindings | MISSING_SOURCE：不存在该旧adapter的公司假设文件；不是其独立新链不存在 |
| verify_pending_research_candidate | PENDING_REVIEW；共享模型成功 | PENDING_REVIEW；共享模型成功 | 未注册至旧pending_candidates，不伪造candidate运行 |
| load_current_value_research_analysis | CONDITIONAL_ANALYSIS_VERIFIED，descriptor 3f9d…；current BLOCKED | CONDITIONAL_ANALYSIS_VERIFIED，descriptor 4dd9…；current BLOCKED | None；当前注册为独立firstinput/live/main链，不静默升级旧入口 |
| read_main_valuation_revalidation | 未声称注册此新case | 未声称注册此新case | CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW；descriptor 292415…；LOW；current/main/formal=false、quantity=null |

600519 F2真实拒绝：归档quote日2026-10-29，最新已完成交易日2026-10-30，`QUOTE_NOT_LATEST_QUALIFIED_CLOSE`且current_price=null；资本/分配检查含`CURRENT_SHARE_COUNT_AND_EFFECTIVE_ACTION_CHAIN_NOT_RECONCILED`、`REPORT_AND_IMPLEMENTATION_DIVIDEND_AMOUNT_DIFFER`、`INTERIM_DISTRIBUTION_AUTHORIZATION_FOLLOWUP_NOT_RECONCILED`；另有`EXACT_CANDIDATE_MATERIALITY_REVIEW_NOT_BOUND`、`FINANCIAL_UPDATES_NOT_RECONCILED_TO_EXACT_CANDIDATE`。不是简单“行情过期一项补齐即完成”。

600887 F2真实拒绝：`EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING`，quote缺失、五维MISSING；conditional price为rejected。600519草案仍researcher_proposal，registered/user_approved/formally_prepared均false。

000568 main真实值精确前三情景为6.195160958628… / 16.851493699182… / 27.222843248711…；financial_basis June30，latest_actual Sept30。85亿元财政政策未完整建模；主区间未采用；没有numeric threshold规则时NOT_PREPARED，不能把这三个估值数直接当买卖线。

## 5. 原件与真实回执指纹

SHA256均本次实际读取；input fingerprint/descriptor不与文件SHA混淆。当前main选择已变为source-LF-v2，不能用旧c4676/b1919版回执当HEAD283c版本证明。

| 文件（相对根） | SHA256或实际input identity |
| --- | --- |
| runtime/d2-assumption-acceptance/1efced4b306e/receipt.json | 文件2830c5a705117554578d3e89d50a3a82cdc3e900068e883776d30bb6de8f2d6b |
| 同目录600519.json | 文件8e8ba4d1f32fad6bc10a0f4a9665209d35af015076d232a7ab599c48948d67a3；本次重放input f0b311b32c7a65f5e6a240ddccd1aa12cd38bd9ec218cc51ee668b3abe32b8ae一致 |
| 同目录600887.json | 文件0bfca32b4c779c6b08269307fbb585e9fdef07b0534b79ed97eaa7523d757000；本次input c0c68808c56f0bf1801ea04e3b538aca034e134759ddeb6ee49b4c3880cfcb80一致 |
| runtime/joint-cash-v4-current/20261028T044953763337Z/600519/candidate.json | 97a83c496feab701fe3f4718d8c09535ce18226729210bc2deac5f625f930086，等于当前registry |
| 同600519/consumed-review.json | 文件2d1941594bf0f0707ae9690d452b998121de0b0d51eca0fd7839241146dc0cfd；descriptor 3f9d04f77d6fb04ddfc6eb21f493730ccae90c2f5bfb991da5c4a1660604d417，本次analysis一致 |
| 同600887/candidate.json | 96e5894b08dd1342139c6a8dd88867619334f77807f7bf6fc28af64067fd6f42，等于当前registry |
| 同600887/consumed-review.json | 文件021a1f41783a9f1278fab62b57175778095f29bf1a5a2f95f836c4e4b6729a74；descriptor 4dd9a39131932c48a737ce19c7a485b2807218b1b24bbfb99a5dff93d4269436，本次analysis一致 |
| runtime/d2-operating-driver-20261101/rt-eac1c74997d17510398ce1fe1e5bea9e-recovered.json | a67e83372f41f5a3ea5c084691f3e1c08856d324b3d6c76c5f37a74931bd15ed；4calls，usage86311prompt+6282completion；不是本次新付费 |
| 上task FUNDAMENTAL role响应 | ce12838d46f2d4ae77911ac90bae5cf179c3532e4654aec65f0ce278e6c3c540 |
| 上task COUNTER_EVIDENCE响应 | 693013a525aa21dca1b3c6a49e297c8905362517ba50352cf39c65f0f7171912 |
| 上task EVENT响应 | 6886b24f91c22046a188a58432aaa11e90b02fefcf378f14f206c2b1da0f1f80 |
| runtime/e2-first-input-000568-20261031/native-facts-v5.json | 223dc8bf4c8d0ad4d74f8ae10db3a8fecafab46189ef9301e4d1d0497b9882f9 |
| artifacts/current/value-main-revalidation-20261101/research-spec-source-lf-v2.json | 2c09f05fd525b950e7245944a996b96a2e34f1bdd3927f3760c2a1066f9f7b89，当前cases000568.main_revalidation实际绑定 |
| runtime/value-main-revalidation-20261101/acceptance-source-lf-v2.json | 文件982cde55d1d56ff42ed9ba8adef7e80683b31f6f9c820ee4f55818d4bbd055ea；descriptor 2924150ad1eae2ab65e09bd9676a38ae961dcb9dd931aa0a2d4a7819d01c3487，本次独立重放一致 |
| .tmp/value-followup-acceptance/real-business-receipt.json | 77dd113fbccfaab8638cd0fffa50cfa797176ebbd0c6e03acfa0863fa5cab7ab；是既有partial/rejected证据，不是当前F2正例 |

实际消费官方PDF身份：600519 FY/H1为cninfo1225114741 / 1225475868，raw hash分别474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288 / 0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6；600887为1225259562 / 1225511409，hash d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac / 423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2。000568 FY/H1/Q3为1225240660 / 1225501255 / 1225639079，原页经native/季度/helper冷消费，不依赖source receipt自述PASS。

实现身份界限：D2 adapter raw hash1efced4b306ebadf0442eeed0da9fd7b588b612691dcdd7679338cd295d5d1b5；v4内核raw730769d6094a9e6860e05fcde33f3e14bbff887fe6b7a313dfd128b6ce951b68；main当前raw81ad1f0e970b394c926ddfd33faed092e34c917f3baf2f1b9b1e2d93e851c07a、LF canonical7093d350f6a8e977035f738a4cc726838f55fe1dc870947b7dac660653c8ea6a。当前main明确SOURCE_CRLF_TO_LF_SHA256_V1，PDF与JSON binding仍raw bytes，不把代码换行归一化扩及财务原件。

## 6. 测试、默认值与不可越界的完成声明

测试源码已核：`test_operating_assumption_draft_v1.py`的真实两公司及一致重签历史/时钟拒绝；`test_joint_cash_v4_two_company_real_replay.py`的同共享链与跨公司隔离；`test_terminal_economic_contract_v4.py`；`test_main_valuation_revalidation_v1.py`真实季度/现金/模型与坏receipt/DA原页反例；`test_pending_candidate_alignment.py`真实股利字段/跨日拒绝/同日正例/stale quote；对应web_api tests验证接线。可选real-root缺失时skip不算真实通过。

本次另外选择四个实际测试项（两公司参数化占两项）：D2 real两公司、main real完整链、F2 real原件现金语义。最终结果 **4 passed in 17.07s，0 skipped**，exit0。没有以CI或历史18passed代替本次实测。

可复现命令（PS7，PYTHONPATH=仓库src，PYTHONDONTWRITEBYTECODE=1；三个真实root环境变量均指vf1）：

```text
VALUE_OPERATING_ASSUMPTION_REAL_ROOT=D:/GPTProject/value-investment/.tmp/vf1
MAIN_VALUATION_REVALIDATION_REAL_ROOT=D:/GPTProject/value-investment/.tmp/vf1
VALUE_ALIGNMENT_REAL_ROOT=D:/GPTProject/value-investment/.tmp/vf1
TEMP=TMP=D:/GPTProject/value-investment/.tmp/vf1/.tmp
python -B -m pytest -q -p no:cacheprovider --basetemp .tmp/value-mainline-p0-test-3
  tests/test_operating_assumption_draft_v1.py::test_real_two_company_originals_and_capital_path_replay
  tests/test_main_valuation_revalidation_v1.py::test_real_complete_quarters_obligation_cash_model_and_price_draft
  tests/test_pending_candidate_alignment.py::test_real_native_original_and_cash_semantics_end_to_end
```

首次sandbox执行因仓库.tmp写权限在setup失败；取得允许测试scratch权限后，第二次因trust-registry fixture要求basetemp位于tempfile.gettempdir之下而setup失败。最终只将该测试进程TEMP/TMP与仓库.tmp对齐后通过；前两次不计测试通过或业务缺陷，未放宽产品信任门禁，未修改源码/生产配置。这里只产生测试临时文件和本报告。

必须保留的能力边界：

- D2 input_fingerprint包含自己的实现hash、来源closure和重放历史；它不是所有下游编译器源码或完整输出的传递闭包版本。仅凭相同D2 fingerprint不能宣称全部后续经济输出实现未改变。
- native facts、官方excerpt是证据；LLM带合法evidence_id只证明引用可追踪，不自动证明论断、份额方向或单位换算正确。旧误述原文和独审处置必须保留。
- 母source adapter包含具体历史页码/账面金额，限定该case；source cold核验不等于通用母到期合同抽取或当前资金预测。净维护gross-DA与后续WC0也是明确代理/条件，不是被原件证明的未来事实。
- 新main的6bn buffer、access/payout/reserve、税/NCI点、十年利润冻结及terminal持续率是case研究选择，不是隐式内核默认或经济批准。资本UNKNOWN没有被新数值消费静默关闭。
- 当前源码有DecisionDetail/公司analysis/Live面板消费者；本次未验证8001实际进程版本、HTTP、浏览器展示或用户验收，不能写“已部署/用户已采用”。

最终可交付为“来源可追踪且实际消费的有限D2/F1条件研究 + F2真实拒绝与待补绑定”。不得交付“三家公司通用自动研究完成、主估值已采用或当前交易决策可用”。本报告不建议新模型、新阈值或无限扩取证。
