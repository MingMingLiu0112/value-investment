# TL11-P5 C 价值模型核查与价格政策草案

本轮只复用600887既有研究。未改估值参数、packet、API、Web、私人数据或历史冻结原件，未代签G3、事件批准或用户价格政策。所有输出保持`action=no_order`。

## 为什么估值约10元，市场参考收盘是28.13元

当前模型为`residual_income_or_equity_value`，版本`residual-income-equity-shared-dated-v2`，估值输入版本`876bfdf7829c1e8225e3338bd090dd102965ebce8049edc2628bae90c0264b68`。2026-10-11的条件研究估值为Bear 9.7976411844、Base 10.0751373531、Bull 10.3006925010元，文件保留完整精度。2026-10-14参考收盘28.13已经双源核验，但行情晚于研究截止，正式价格比较资格仍为false。

最主要的差别是盈利优势的持续时间，而不只是折现率。当前消费`short-advantage`：盈利条件维持一年，随后全资本ROE三年衰减到权益成本，终端增长为零、终端ROE等于Ke。因此终端超额收益为零，但终端股票权益价值不是零。模型较接近每股账面归母权益约8.49元加有限期超额收益。

旧条件基线的10.37/17.02/24.07元包含更高的终端剩余收益贡献（约10.9%/35.5%/47.8%），不可以当成同一已批准模型的当前三档值。当前三档Ke为10%/9%/8%，ROE和留存率也不同，所以情景差异不能全部叫作资本成本敏感性。另一个既有、未批准的隔离敏感性结果将Ke改为行业参考7.7417%，Base仅从10.0751到10.2646元，增加约1.88%，无法解释到28.13元的差距。本轮未重跑敏感性或提高增长、延长优势期来制造买点。

## 财务口径与模型适用边界

基期为2026-06-30：合并归母权益537.11亿元、历史披露普通股6,325,360,667股、扣非归母TTM利润96.48亿元。分母是历史总股数，不是已批准的当前稀释/回购调整股数；模型使用从财务基期滚到估值时刻的条件现金流时点，不是10月实测净资产。正常化利润没有批准。本轮没有发现通过复权或将企业价值误当每股权益来解释差距的直接证据，但当前分母及经济模型有效性仍须完成现有门。

剩余收益方法能组织净资产、盈利和资本成本的条件研究；会计对账不等于未来clean-surplus、必要维护投入、资本效率与可分配现金已获批准。H1扣非归母利润下降20.25%、减值、项目效益及融资约束是实际反证。已入账减值不得再次扣减或直接全额加回正常化利润。市场可能隐含更长优势或复苏，现有研究尚不能证实，也不能仅凭价差宣布市场错误。

直接原件核查覆盖explanation、年报、中报、proposal、权益成本evidence、financial-rebase manifest共6个已绑定对象，全部hash匹配；另对既有隔离敏感性结果记录本次观察hash，并绑定router与模型实现代码，共9项。敏感性仅作补充研究，不冒充已批准模型输入。检查结果及精确数值见`artifacts/current/tl11-p5-20261014/value-600887-model-review.json`。

历史`cninfo-index.json`不匹配仍属继承审计分支，不在当前ValuationResult直接原件中。未修改旧hash或冻结原件，也未据此声称完整历史恢复链通过。

## 分红覆盖与普通人的复核问题

保留的事实包括FY2025末期每10股9元现金红利，以及2025—2027分红率不低于75%、每股不低于1.22元的已披露政策。政策不是未来股息保证。代数股息路径与估值一致只说明算术一致，不能证明母公司可分配现金覆盖；模型留存比例也不是已批准的未来分红比例。

应继续核对利润恢复、经营现金流、维护投入、债务续作和现金期限/限制，及回购、担保对分红资金的竞争。未来可持续股息、现金覆盖和个人股息目标贡献保持未知。本轮不消费个人持仓或IPS。

## Root集成接口

Domain：`value_investment_agent.domain.decision.value_price_policy`

```python
draft_value_price_policy(
    plan, *, draft_id, policy_id, rule_version, profile_id,
    effective_from, effective_through, rationale,
    dividend_coverage_risk, rules=(), thesis_reviews=(),
)
preview_draft_prices(draft)
```

规则显式包含`action/scenario/value_fraction/comparison/rationale`，沿用现有`ValuePriceRule`校验。不存在默认安全边际。空规则允许保存草案，所有草案动作价为null。预览只能标识为未批准草案算术，不能覆盖ValueActionPlan正式动作价；独立论点减仓/退出仍走原Entry/Consistency规则。

Application：`value_investment_agent.application.decision.value_price_policy`

```python
prepare_value_price_policy(root, draft, *, now)
confirm_value_price_policy(
    root, prepared, *, confirmation_binding,
    authorize_confirmation, now,
)
```

prepare只读核验所有草案原件hash，重新读取当前已绑定ValueActionPlan，检查证券、研究版本、估值输入hash、模型身份/版本、profile、有效期和显式规则。返回`value-price-policy-prepared-v1`，状态为`BLOCKED`或`PREPARED_PENDING_USER_CONFIRMATION`，包含draft及prepared内容hash、草案价、政策阻塞和独立existing_research_blockers。prepare不批准G3，不登记政策。

confirm要求Root提供hash-bound的`value-price-policy-user-confirmation-v1`回执，字段为`decision=CONFIRM`、`draft_sha256`、`prepared_sha256`、`confirmed_at`、`action=no_order`。Root注入可信的`authorize_confirmation(receipt)`，核验真实已认证且有权的用户身份。不能把研究员提交的布尔值、actor字符串或SHA当作本人授权；回调不接受来自公开请求body。确认前重新检查源hash和当前研究基准。

成功仅返回与现有loader兼容的`registered-value-action-policies-v1`候选payload，policy行保留原研究基准和confirmation_binding。Root负责把它写成不可变登记原件、加入现有publication extension `value_action_policy_registry`、绑定hash及发布pointer；应在同一发布边界再次验证用户授权和基准。不得覆盖其它已登记证券政策：返回值只是单证券候选，Root合并已核验registry后发布。不得把结果当作G3、事件审批、订单、个人仓位或正式证券资格。

## 当前真实草案

`value-600887-policy-draft.json`的拟议有效期为2026-10-15至2026-11-14，仅供审阅；没有已选动作比例。`value-600887-policy-preparation.json`状态为BLOCKED：明确动作规则未选择。原公开model_id=null确认为字段未接通：现有ValuationModelRegistry按type明确登记`residual_income_or_equity_value`，已登记实现声明`residual-income-equity-shared-dated-v2`，且quality_compounder路由支持。新application `value_model_identity.py`只在身份缺失时核对type、声明version及profile后补入登记ID，附router/实现hash证据；不改原对象、不覆盖typed恢复身份，不把catalog身份当成模型有效性或G3批准。

本轮未调用真实confirm、未生成用户确认回执或登记pointer。只有之后有权用户明确选择规则并确认、原件及模型身份匹配，才可准备登记；实际证券和个人组合资格仍分别由既有门决定。

## 验证与交付文件

相关回归在补充catalog、review loader与隔离重算测试后重跑，共143项通过。新增测试覆盖空规则无默认价、缺model_id、明确比例预览、prepare不清除G3、外部授权确认、篡改和研究基准变化、有效期及现有registry loader兼容；所有确认均为隔离synthetic fixtures。

新增模块为domain/application的`decision/value_price_policy.py`、application的`value_model_identity.py`及`value_review_replay.py`；既有application/domain `value_action_plan.py`补catalog身份投影、身份依据与公开`profile_id`。新增测试为`test_value_price_policy.py`、`test_value_model_identity.py`、`test_value_policy_review.py`、`test_value_review_replay.py`。公开审阅材料为本说明及`artifacts/current/tl11-p5-20261014/`下5份value JSON（model review、draft、preparation、manifest、隔离replay receipt）。未修改packet/API/Web/私人routes，未commit。

## Web只读消费合同

```python
from value_investment_agent.application.decision.value_price_policy import load_value_policy_review
review = load_value_policy_review(root, symbol, now)
```

返回`{model_review, draft, preparation, source_bindings}`。只读从`artifacts/current/tl11-p5-20261014/value-policy-review-manifest.json`读取明确三角色binding，核对文件hash、schema、issuer、当前研究basis、catalog代码身份、直接源hash、时点、draft/prepared相互hash及草案价。source_bindings含manifest和三文件hash，以及model_review中可选的隔离replay receipt binding（实际600887共有5项），供Root纳入identity；manifest是public材料索引，不是投资政策登记pointer。replay receipt必须精确匹配当前valuation input hash。

文件缺失、未收录symbol、篡改、私人源引用或研究基准变化抛`ValueError`，Root映射failclosed错误；不自动刷新材料、不触发prepare/confirm/登记。Web展示`model_review.findings/dividend_review`解释、`draft.rationale/effective_from/effective_through/basis/rules/thesis_reviews`和`preparation.blockers/draft_prices/price_scope`。空规则时四类draft_prices保持null，须标识“待本人选择并确认”，不能退回Bear/Base/Bull充当动作价。安全验证不代表经济批准。

## 真实直接输入隔离重算

应用函数`replay_value_review_inputs(root, *, package_binding, explanation_binding, isolated_root)`仅用于当前quality-compounder直接输入算术恢复。使用既有typed builders、ValuationRouter和共享模型；要求新隔离目录位于repo `.tmp`，只复制package、explanation及其ValuationResult/ResearchCase/Facts直接path引用，不递归所有source目录，每个文件小于32MiB。

实际600887复制6文件、3,106,146字节（约2.96MiB）：候选package、已绑定explanation、valuation proposal、权益成本evidence、年报、中报。从复制的payload恢复ResearchCase和QualityCompounderFacts，检查其canonical artifact fingerprints分别等于`57eb3321...`与`c8385040...`，再重新计算ValuationResult。模型精确完整payload hash为`876bfdf7829c1e8225e3338bd090dd102965ebce8049edc2628bae90c0264b68`，与当前已消费valuation完全一致；三档、日期、版本、状态均匹配。

小回执为`value-600887-isolated-replay-receipt.json`，包含源/复制hash、输入fingerprints、输出和完整payload比较。未重建完整ResearchInputDescriptor、事件/历史source graph、G3或portfolio，也没有重新解析PDF提取事实；这是已消费typed输入与共享算术恢复，不是重新验证全部财报解释、经济批准或严格历史PIT。未复制371MiB继承资产、未改冻结原件。隔离copies仅留repo `.tmp`，本轮无需把年报等继承原件重复上传；Root可直接使用小回执验收。
