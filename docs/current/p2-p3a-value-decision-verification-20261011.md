# P2/P3-A 价值审核与公共决策解释交付

本包只新增解释应用模块、独占测试和操作说明，不修改审批协议、阈值、research_reviews、read-model、renderer、正式registry或CI；不提交。永久`action=no_order`。synthetic测试不是本人审核，两家公司真实v5仍为NO_ACTION。

## Root接入接口

新增`src/value_investment_agent/application/product/value_decision_explanation.py`，导出：

```python
project_value_decision_explanation(
    verified_decision: RestoredDecisionRecommendation,
    *, evidence_scope: str,  # RETAINED_RESEARCH or SYNTHETIC_TEST
) -> dict
```

输入必须由现有`verify_decision_recommendation_payload(repository, payload=...)`、`restore_decision_recommendation(...)`或`verify_current_decision_workbench(workbench)`生成；Root先核对来源path/Hash和版本，再调用本接口。它只复制现有typed结果，不接受任意JSON、不调用估值/动作选择/审批，不是新的认证或准入入口。typed对象和verification标志不是防伪签名，不能由调用方手工构造来跳过前面的验证。

输出schema为`public-value-decision-explanation-v1`。可直接用的字段：`candidate_action/candidate_explanation`、`research_version/decision_as_of/financial_period`、`thesis/return_driver/mispricing_hypothesis/support/counter_evidence/thesis_breakers/next_events`、`recommendation_reasons/blockers`、`valuation_range/valuation`、`model_validity/pre_decision/human_approval/event_materiality`、`entry_thesis/investment_consistency_review/thesis_consistency_status/exit_conditions`以及完整`decision_dependency_refs/verification`。支持和反证保留原文与evidence refs，不再拼一套无来源投资故事。

`price_context`保留PriceBridge/PriceAttractiveness原对象。`formal_comparison`只在现有PreDecisionEligibility的`positive_price_review_eligible=true`时复制current_price/MOS/entry_zone/reduce_zone，否则null；不从观察报价、条件估值或退出候选重新推导价格准入。`position_guidance=null`、`portfolio_input_status=BLOCKED_PRIVATE_INPUT`，不得借证券级ADD候选推算个人数量。嵌套数据深拷贝，不修改被验证对象。

调用方应把当前待审candidate身份与历史baseline分开展示；解释绑定的是传入决策的research_version和依赖Hash，不猜最新文件。缺报价时有证据的TRIM/SELL路径仍可以人工复核，不能为它们补造价格比较，也不能把NO_ACTION翻译成HOLD。

## 第一家真实闭环：优先茅台，但不是宣布更值得买

| 项目 | 600519 | 600887 |
| --- | --- | --- |
| 已有事件对象 | 七公告七项，399关联追溯、57实际字段 | 33公告八机制，融资/担保/兑付/回购/股息与经营多链 |
| 已有经济输入 | EARNINGS、DURATION、DISTRIBUTION、COST_TERMINAL、EVENT_MODEL五组 | EARNINGS_IMPAIRMENT、CASH_FINANCING、CAPITAL_DURATION、EVENT_MODEL四组 |
| 盈利与资本未决 | 扣非TTM非正常化；成本、直营净贡献和维护投入未拆分；十五年存量/新增资本机制待审 | 澳优减值/恢复、库存与归母盈利桥、内部票据/外部银行义务、母公司现金及融资来源未闭合 |
| 成本与期限 | 已绑定国债/beta/ERP研究，异步代理与十年+五年寿命解释待审 | 当前实际blocker仍为issuer-specific beta missing、generic beta=1；ROIC及incremental ROIC未核；1+3并不证明优势期 |

优先600519的客观理由是现有完整事件集更小、逐字段可追溯且成本研究有已绑定输入，较容易组织一次精确版本审核。反面是15年期限比伊利1+3更难证明，五组也比伊利四组多；选择茅台只是集中人类审核工作量，不证明其经济假设可接受或任何买点。若本人拒绝存量盈利持续性或分配用途，应保留拒绝，而不是调参转向更高估值。

现有依据，不重取PDF：

- 茅台`runtime/d2-600519-event-review-closure-20261011-v1/review-items.json`，SHA `32c4caa45ea539db8fa5ce37e2c16ec25af848abbf969a53807e064851e47834`；`operating-countercases.json`，SHA `3f2d8cc58c022f8a5ae029e16f6c76467f9124365c53e7fe4ab86d21271f4e67`。FY2025物理p9-11/H12026 p7-9的原文与机制分开，提价/渠道收入不等于公司利润或确定寿命。
- 伊利`runtime/d2-600887-event-review-closure-20261011-v1/event-review.json`，SHA `27bac56b48e6aabcb6144d75d8bf8fd4bde026dbad3f5c7e20825e3bb4912fb7`；`operating-review.json`，SHA `f47d9df8ca07b03b9e7b099a8f1ab465e3b0d57606b0ed70e45458504b6df4d4`。FY p15/H1 p11-12、经营公告p1-2支持渠道增长的事实，不证明净贡献；股息政策/实施原页不证明未来现金能力。页级来源沿用该目录`evidence-pages.json`和`mechanism-fact-anchors.json`，保留PDF path/URL/Hash。

双方候选与扫描valid_from差异、旧模型裁决不能迁移及每ID NOT_ASSESSED状态全部保留。本包不创建事件判断或另一EventScan。真实ModelValidity目前UNKNOWN、G3/材料性缺失；10/9观察收盘不能强接10/11新候选。

## 真实身份注册准备：最小待办

现有`config/authorization-trust-roots-v1.json`固定白名单为空。view、review只读预览、未签名草稿、公共反证/事件研究可继续；正式签名消费与经济准入不能由Agent代替。

1. 由本人确认真实reviewer_id、公钥归属和审核责任，私钥仅由本人掌握。本包没有生成真实密钥、把synthetic身份注册到正式文件或提供伪造签名命令。
2. 最小先只授权`symbols=["600519"]`。组审核权限为`human_group_research`；确需整模型时再加`human_whole_model`。这两个scope不授权订单、私人组合、生产运行或公告材料性；不要给无关证券权限。
3. 真实trust root严格使用已有`research-review-transport-trust-root-v1`字段：schema_version/reviewer_id/public_key/scopes/symbols/valid_from/valid_until。公钥为Ed25519原始字节hex，起止时点含时区。经明确审查后由负责注册的Root按既有固定registry流程pin规范化指纹；文件字节SHA与规范化指纹不同。不能通过环境变量/CLI自选registry。
4. 本人逐组填写现有九组中被选公司范围、结论和理由。具体用途VERIFIED不等于whole_model_approval；拒绝/证据不足保留相应阻塞，不能确认一组便批准整模型。签名覆盖现有purpose真实零字节加canonical_contract_payload(payload)的UTF-8字节；不签随意格式化JSON。
5. 首次或后续回应走现有统一review入口；后续必须同reviewer、同候选、指向最新认证前驱且时间更晚。准确例式：`use_trade_assistant.py --mode review --symbol 600519 -- --signed-review-response PATH --review-trust-root PATH`。只在注册/真实签名存在后消费；续接前驱和中断恢复依已有CLI合同，不能换目录重放同签名。
6. 各公告材料性仍需既有v2 exact model_context/scan/每ID原件typed审核；组/整模型trust scope不能代替此合同。人类完成后Root通过既有应用重新验证ModelValidity、PIT、价格桥及决策；本包不改valid_from、清blockers或登记经济批准。私人IPS/持仓和风险预算独立提供，公共研究闭环不冒称组合闭环。

本人当前只需先确定真实审核身份及公钥归属，并选择茅台是否作为首家审核；其余工程准备已可独立检查。真实结论接受与否留在现有输入，不预填。

## Synthetic与真实验证证据

新增测试`tests/test_value_decision_explanation.py`复用现有v3/decision fixtures，使用InMemoryResearchArtifactRepository存实际FinancialFacts/ValuationAssumptionSet/审批/事件/门禁对象，将审批Hash绑定到真正存储对象，复算现有PreDecisionEligibility并由现有restore API完整回放。六种动作均验证实际依赖，不是手写六个输出字符串：

| 状态 | 原合同路径 | 价格与持仓边界 |
| --- | --- | --- |
| BUY_CANDIDATE | 完整正向准入 | 仍需本人复核，position_guidance为空 |
| ADD_CANDIDATE | 原Entry + FULFILLED增量证据 + 完整正向准入 | 不是单凭跌价；不生成数量 |
| HOLD | 原Entry + CONSISTENT + 当前事件/有效模型 | 不等于买入资格，可无报价 |
| TRIM_CANDIDATE | 原Entry + WEAKENED + 减仓证据 | 可以无报价，只触发人工复核 |
| SELL_CANDIDATE | 原Entry + BROKEN + 退出条件/证据 | 可以无报价，不生成订单 |
| NO_ACTION | 缺正向前置且无其他合法路径 | 不伪造价格/MOS或改成HOLD |

现有v3 tests同时覆盖缺Entry、仅价格加仓、反证无来源、stale模型风险减少、回放篡改等拒绝路径。新增`tests/test_value_review_admission.py`复用现有synthetic signed fixture，检查已pin身份仍因证券权限/过期拒绝，以及同签名换目录重放拒绝。现有signed tests覆盖签名篡改、unpin、自签、整模型权限、context/估值/范围漂移、前驱/撤销/中断恢复；正式registry始终未修改。

签名消费/typed attach测试与六动作的合法仓库回放是两组各自完整的证据，不宣称已有一条真实人类签名→当前公司BUY的运行。synthetic即使使用fixture证券代码也不是该发行人的真实批准。

本轮定向：六个文件合计99 passed，JUnit保留`runtime/p2-p3a-value-decision-verification-20261011-v1/tests.xml`。临时文件与test trust registry全部位于repo `.tmp`；测试时TEMP/TMP指向repo `.tmp`满足既有test-only registry路径约束，不改正式registry选择。

同目录六份`synthetic-*.json`保留实际决策和解释，真实`600519-real-pending-explanation.json`/`600887-real-pending-explanation.json`保留精确candidate/workbench path+Hash及实际NO_ACTION阻塞。两份真实结果均human_approval=null、formal_comparison=null，未补当前报价或估值。索引`verification.json` SHA `ee933fa154c825eeff8b1358326bd7674e459ef0cd28e303c1ec928a0905ae4e`列各产物Hash及正式registry Hash。生成脚本`.tmp/p2-p3a-value-decision-evidence-20261011.py`只消费已有原件/候选与fixtures，无网络、无模型新建、无正式审批、无Canonical写入。

Root最小集成：验证workbench → 调上述投影 → 将candidate_action、支持/反证、实际blockers、price_context和thesis变化挂到既有详情/下钻；为synthetic严格保留SYNTHETIC_TEST标签。不得跳过来源验证，或只取候选动作忽略版本、真实阻塞和私人输入边界。
