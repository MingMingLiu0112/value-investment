# 600519 限定财务范围集成独立复核（2026-10-08）

## 结论

**未发现本次 v8/v10 集成将限定财务范围认可偷换为完整财务、正常化盈利或中性主估值批准的错误。G1=true 可以保留，无需退回 partial；G3=false、NO_ACTION 和所有已保留未知不能因此解除。** 本结论只复核这两个精确制品及其封装，不是新增审批、Human receipt、金融重大性或投资准入。

实际 `financial_scope_review` 限定历史财务基础与条件剩余收益研究，五维包含事实解释与未知；主估值、正常化、持续分配、金融尾部重大性和模型有效性均列为未接受。模型参数没有变，三档计算值逐位未变；报告来源仍是冻结原件。允许将这份集成结果作为限定范围的研究材料同步，不能写成“完整财务研究／估值已批准”。本报告未实际验收 Excel 或后续产品渲染。

## 1. 核对对象和方法

| 对象 | 实际 SHA-256 |
| --- | --- |
| [package-v8-financial-scope-bound.json](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json) | `c48e3dbfbe8b643cc71a609a2277f726246a1f32b1ac5dcb4b2da47055ec3d04` |
| [workbench-v10.json](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/workbench-v10.json) | `b88fa501a3bcd76fb538ab633a9ea1f086cc0aa35877e41c2bacf3c996935d2c` |
| [冻结的财务范围报告](D:/GPTProject/value-investment/docs/current/600519-financial-scope-independent-review-20261008.md) | `17266f29a4f64292a631fb47017d72c624367f0bfcb9ae903ac98ef1e4dd9c6c` |
| [比较基准 package-v7](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v7-operating-mechanisms-reviewed-bound.json) | `c9f956834797f8ed8fb34cc7dfeb9ae125d3c7b99ff6a4ffe73cf91b9ac5ef12` |

本轮在内存读取上述 JSON 与既有规则，调用真实 `build_research_case`、`build_quality_facts`、`evaluate` 和共享 `ResidualIncomeEquityValuationModel.value`，无落盘研究运行，无重采财报或网络搜索。核对 v7/v8 输入差异、v10 canonical payload、引用 hash 与冻结报告。复核记录时点 `2026-10-08T14:35:46.719051+00:00`；集成来源时点由 v8 保留，不回填为历史已知材料。

## 2. 限定范围逐项复核

| 核查 | 证据定位及结论 |
| --- | --- |
| 主体／模型／期间 | [v8 L1647](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1647)：`scope=historical_financial_basis_and_conditional_residual_income_research_only`，600519、CNY、`consolidated_parent_ordinary_equity`、余额日 6/30、研究日 10/8、dated-v2。不是母公司单体权益，也不是不同模型通用批准。 |
| 五维不是填空过门 | [v8 L1665](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1665)：盈利、现金、资产负债、成长、资本配置均有理由；同时保留追加正常化、持续分配、金融/存货尾部、未来路径和增量资本回报未知。与冻结报告五维范围一致，没有将“数据不足”删除成强结论。 |
| 正常化仍未知 | [v8 L1664](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1664)：`normalized_parent_profit_cny=null`，利润基础明确为 reported/ex-nonrecurring parent TTM、不是 verified normalized profit。原历史利润桥及会计调整研究与 v7 相同。 |
| 两表差额没有消失 | [v8 L1687](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1687)：H1 8,358,830,124.37 - 8,355,337,252.97 = 3,492,871.40；FY 7,254,499,309.26 - 7,250,789,537.15 = 3,709,772.11，CNY 元。本轮 Decimal 再算一致；counter_evidence 保留原因未识别、不得认证精确自由现金。没有补平或重复扣减现金。 |
| 排除范围明确 | [v8 L1701](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1701)：`not_accepted` 排除 verified normalized parent profit、sustainable future distribution、financial tail materiality approval、neutral primary valuation、model validity、price/investment admission。L1709 明确改为主估值或精确自由现金主张时须重新审阅，不能携带为完整批准。 |
| 来源冻结和时点 | `review_binding` path/hash 与实存报告一致；sources、case.evidence_refs 也引用同一报告。`source_available_at`、`accepted_at`、case.generated_at 均为 `2026-10-08T14:31:10.657078+00:00`。这个 reviewer/integrator 记录是研究范围整合记录，没有变成 Human receipt。 |
| 继任关系 | [v8 L6254](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:6254)：supersedes 指向精确 v7/hash，理由明确 no primary valuation or investment approval；实际 run_id 为新身份。不能仅按文件名或复用的 package_version 字符串识别版本，应继续使用 path/hash/run_id。 |

## 3. 门禁和实际消费者

实际构造 v8 ResearchCase 后执行 `evaluate`，与 v10 research_gate canonical payload（[L1544](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/workbench-v10.json:1544)）一致：**G0=true、G1=true、G2=true、G3=false，结论“估值未就绪”**。[v8 L1905](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json:1905) 同时保持 valuation_status=not_ready、research_status=financial_scope_approved，blockers 首项明确“仅认可历史财务与条件剩余收益范围”。

[research_gate.py L86](D:/GPTProject/value-investment/src/value_investment_agent/domain/research/research_gate.py:86) 仍只是 G1 状态字符串检查，不自行解释范围；本次正确性来自同一 case 的来源绑定、明确范围和未解除依赖结论。L39 的全门条件不成立，所以 G1=true 没有产生研究与估值整体 READY。G2=true 是既有字段/引用规则的结果，本轮没有另行批准商业论点。

v10 封装的 ResearchCase 完整保留 `financial_summary.financial_scope_review`，与 v8 对象深度相等；11 个 canonical payload 的 UTF-8 SHA-256 均与注册 payload_sha256 一致。封装内 valuation_assumptions=PARTIAL、valuation_result=conditional_research_only、model_validity=UNKNOWN；没有 approval/Human approval 制品。顶层 valuation 和 decision_recommendation 与对应 canonical 对象深度相等，未发现顶层与封装层批准状态矛盾。

## 4. 参数、数值和行动边界

v7/v8 的 `facts.operating_inputs`、全部 `scenario_inputs`、`valuation_timing`、`model_validity_input` 和 quote 深度相等。14 个 assumption names、单位、bear/base/bull 数值和 ordering 全部相同；唯一假设解释变化是 cost_of_equity 的 rationale/evidence_refs，引入已有成本审阅。三条 cost_of_equity bindings 仅增加该来源引用，field_path/expected_value 均未变；其他 bindings 未变。

用同一共享求值器分别重算 v7/v8，以下每股 CNY 字符串逐位相同，亦与 v10 valuation 相同：

- bear：`404.823132132816367214176193740640474114918106347`
- base：`479.879911433847652558589785173641417018371446840`
- bull：`572.738699601067929287663493493359619190129799284`

以上是条件压力计算值，不是批准的主估值范围。计算结果仍为 conditional_research_only；原算式明确排除“股利代数交叉核对证明可分配现金／持续分红”的含义。

[v10 L831](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/workbench-v10.json:831) pre_decision_eligibility=null；L837 recommendation_type=NO_ACTION；L851/L852 entry_zone、reduce_zone=null；推荐中的 current_price、margin_of_safety 两项及 position_guidance 也为 null。顶层 [L2622](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/workbench-v10.json:2622) suggested_state=NO_ACTION、position_guidance=null、canonical_workbook_written=false；action=no_order。exit_conditions 有研究失效／重开文本，未变成退出交易指令。

[v10 L1200](D:/GPTProject/value-investment/runtime/d2-model-bound-followup-20261008/workbench-v10.json:1200) 推荐理由和 blockers 仍含 research_case_valuation_not_approved、model_validity_unknown、event_materiality_review_unavailable、predecision_eligibility_unavailable、human_research_approval_not_resolved。研究 receipt（L2626）的 valuation_package hash 精确指向本次 v8；source_verification（L2638）也明确 byte integrity 不等于事实语义或投资批准。`COMPLETED_WITH_BLOCKERS` 是带阻断的命令完成状态，不是 D2 完成或真实投资准入。

## 5. 文本／标志处置与未验证范围

**当前 JSON 不需回滚 G1，也未发现必须改成完整批准的其他标志。** 产品同步应保留“限定财务范围已审阅；主估值未就绪”的区分，不能将单个 G1 绿色状态展示为“财务／研究全部批准”。三档数字应标为“条件压力研究值”；decision_recommendation.valuation_range.basis 的通用 `valuation_result`（v10 L839）本身不能独立证明主估值批准，必须连同当前 thesis、blockers、conditional 状态展示。当前 JSON 已有这些限制，本轮没有发现它已输出中性合理价或买卖区间。

若主张精确可分配现金、正常化盈利、金融尾部不重大，或切换到主估值／另一模型，重新审阅受影响范围并形成新版本；不能仅继承 G1 字符串或 reviewer/accepted_at。当前未取得投资批准不是原件不存在，不应通过继续重采同一套财报绕过模型／重大性门。

本轮没有重读整套 PDF、重新评价经营路径／权益成本经济结论、核服务器、运行完整 tests、发布或验收产品页面。实际值重算只验证共享模型输入和算术保持，不能替代模型有效性、策略收益或用户验收。唯一写入是本报告；旧财务范围报告、前瞻／经营／成本来源、v7/v8、v10、模型和审批均保持不变。
