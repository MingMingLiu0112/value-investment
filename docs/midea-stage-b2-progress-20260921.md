# 美的集团 B2 FCFF 进度

日期：2026-09-21；最新增量：2026-09-22。范围：`000333` 的 FCFF 工程与事实准入，不是正式估值、交易建议或回测结果。

## Engineering Status

`FinancialFacts -> FCFFValuationModel -> ValuationResult` 已接通。FCFF 契约要求 EBIT、现金税率、
折旧、资本开支、营运资本变动、WACC、净债务、非经营资产和股本九项输入。任一项缺失会显式
阻断情景计算，不会由 TTM 利润或期末股本推导每股价值。

2026-09-22 补入共享情景算术。`FinancialFacts.scenario_inputs` 可显式提供 bear/base/bull 三套
`FCFFScenarioInputs`，每套包含逐年预测、终值、权益桥接、经营/资产负债暴露分区、普通股数与
证据引用；模型复用 `scenario_valuation.value_scenario`，不再只是输入门禁。三套情景必须齐全，
带日期的情景必须与 `FinancialFacts.as_of` 一致。完整但未获事实验证的输入仍返回
`conditional_research_only`，不生成价格、安全边际、仓位或订单。

该能力仅证明工程算术可运行。美的现有年报载荷仍缺少工业 EBIT、金融业务剥离、适用税率、
WACC、净债务、非经营资产和普通股分母，因此生产路径继续保持 `not_ready`，没有被写入任何
情景值。

## 已核验的一手事实

来源为 `runtime/midea-2025-official.pdf`，SHA-256：
`16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`。

- 第 137 页合并现金流量表：2025 年经营活动现金净额为 533.4593 亿元；购建固定资产、无形资产
  和其他长期资产支付现金为 111.41889 亿元。
- 第 132--133 页合并资产负债表：记录期末现金、借款、债券、租赁负债及一年内到期非流动负债。
- 第 143 页：期末总股本为 7,597,145,346 股，其中 A 股 6,946,296,846 股、H 股 650,848,500 股。
- 第 230 页：所得税费用为 85.65147 亿元，税前利润为 530.85343 亿元。
- 第 234 页现金流量表补充资料：合并折旧及摊销候选值为 93.39695 亿元，应收项目变动为
  -81.12158 亿元、应付项目变动为 113.16620 亿元；仍未完成 FCFF 范围勾稽。
- 第 49--52 页：营业收入 4,564.52 亿元、同比增长 12.11%；家电业务收入同比增长 11.28%，
  商用及工业解决方案同比增长 17.47%；同时两项分部毛利率分别下降 0.08 和 0.58 个百分点，
  洗衣机销量同比下降 6.17%。

这些事实及页码由 `build_midea_fcff_facts.py` 生成到
`runtime/company-research/midea-fcff-facts-20260922/evidence.json`（v2），并有回归测试校验原件 Hash。
经营事实由 `build_midea_business_evidence.py` 生成到
`runtime/company-research/midea-business-evidence-20260921/evidence.json`。它明确是发行人
披露的研究事实，不是竞争优势或管理质量的独立证明。

## EBIT Scope Audit

`build_midea_ebit_scope.py` 已从同一份年报第 135、225、227、229、234、249、250 页完成 EBIT
口径复核，生成
`runtime/company-research/midea-ebit-scope-20260921/evidence.json`。

审计结论：

- 工业口径 FCFF 剥离：`MODEL_NOT_APPLICABLE`
- 合并口径企业价值桥接：`VALUATION_NOT_READY`

原因：

- 年报未单独披露金融业务的利润表、资产负债表、税费、债务、现金和营运资本；
- `other` 分部把金融业务与机器人、绿色能源、医疗等业务混列；
- 合并营业利润同时包含金融与非经营项目，无法直接得到可审计的工业 EBIT；
- 缺少金融业务独立价值与非经营资产证据，不能把合并 FCFF 直接换算为上市权益价值。

因此当前 FCFF 保持 fail-closed：不生成 bear/base/bull、价格桥接、安全边际、仓位或订单。
该证据包由 `test_midea_ebit_scope.py` 回归锁定。

## 2026-09-22 估值适用性登记

`build_midea_valuation_applicability.py` 将“经济画像支持哪类模型”与“当前事实能否适用该模型”
拆成两个独立结论，生成
`runtime/company-research/midea-valuation-applicability-20260922/evidence.json`，证据 SHA-256：
`89e69d6472ff7ac23b467fa5f7a660a4c9d7cd95f4bcc565d91a762a9717fcc5`。

- `mature_manufacturing -> fcff` 经济路线为 `SUPPORTED`；
- 工业口径 FCFF 剥离为 `MODEL_NOT_APPLICABLE`；
- 合并企业价值桥接为 `VALUATION_NOT_READY`；
- FY2025 会计 EPS 分母为 `DISCLOSED_NOT_REGISTERED`，当前估值股本范围为 `NOT_REGISTERED`。
- 合并归母普通股权益/利润已披露，但剩余收益/权益价值路线仍为
  `CANDIDATE_NOT_REGISTERED`。
- 财务公司规模观察已登记为 `OBSERVATION_NOT_MODEL_INPUT`，不解除工业 FCFF 阻断。

因此 `registered_valuation_model=null`、`registered_valuation_inputs={}`，不登记算术模型、
不生成 bear/base/bull。生产入口
`build_company_valuation_result.py` 新增 `--applicability-path`，把 `valuation_route` 与完整
`valuation_applicability` 同时写入 `runtime/valuation-results/000333-fcff-stage-b/evidence.json`；
FCFF 结果仍为 `not_ready`，价格桥接仍为 `PENDING_EXTERNAL_DATA`。

FCFF facts 已升为 v2，路径为
`runtime/company-research/midea-fcff-facts-20260922/evidence.json`，SHA-256：
`106dea6c9555f48badf9fa8d2a1c7b2464794d7e78ba8250788b100091fc3a42`。旧
`20260921` 生产路径已从统一 FCFF 测试和 Excel 研究案例构建器移除。

## 2026-09-22 会计每股收益与期末 A/H 股本范围

`build_midea_2025_share_basis.py` 从同一份 Hash 锁定年报第 4、143、219、220、223、
231 页生成独立证据包
`runtime/company-research/midea-2025-share-basis-20260922/evidence.json`，证据 SHA-256：
`f31dfaddf00a42d227107932a3eecdc8b1de9b44860f383c9157b321046c2113`。

已核验并区分三类事实：

- 2025-12-31 期末已发行 A/H 总股本 `7,597,145,346` 股，其中 A 股 `6,946,296,846`、
  H 股 `650,848,500`。
- FY2025 会计每股收益分母：归属于母公司普通股股东的合并净利润 `43,829,974` 千元；
  发行在外普通股加权平均数 `7,559,265` 千股，稀释后 `7,608,132` 千股；基本 EPS
  `5.80` 元/股，稀释 EPS `5.76` 元/股。
- 年末库存股只披露账面金额 `8,151,117` 千元及增减变动，未披露库存股股数。

该包明确 `share_basis_approved=false`、`valuation_approved=false`、
`trade_approved=false`，且没有注册 `ordinary_shares` 模型输入。FY2025 会计加权分母
可以用来核验披露的 EPS，不能作为未来估值日的每股价值分母；期末总股本同样不能当作
FY2025 加权分母。

## 2026-09-22 合并权益口径与候选权益价值路线

`build_midea_consolidated_equity_scope.py` 从同一份 Hash 锁定年报第 133、135--137、143、
185、246 页生成 `runtime/company-research/midea-consolidated-equity-scope-20260922/evidence.json`，
证据 SHA-256：
`190f7cb5fbe07a47b81a59ae7f04d02ba9f514bb3a8327272cc62a682150c360`。

该包只记录发行人披露的股权与利润范围，不批准任何模型：

- 2025 年末归母普通股权益 `223,221,305` 千元，少数股东权益 `13,202,918` 千元；
- 2025 年归母普通股净利 `43,945,411` 千元，少数股东损益 `574,785` 千元；
- 财务公司直接/间接持股分别为 `95% / 5%`，年报可见法定/超额准备金、同业款项、贷款和吸收
  存款等金融业务项目，但仍无独立金融业务利润表、资产负债表和税费/资本口径；
- 年末库存股仍只有账面金额，没有股数，当前估值普通股范围未注册。

因此该包把 `residual_income_or_equity_value` 登记为 `CANDIDATE_NOT_REGISTERED`：
预测 ROE、带日期的权益成本、派息/资本配置政策和扣除库存股的当前普通股分母均未独立证明。
它没有生成 bear/base/bull，也没有改变 FCFF 主路线。适用性证据链已把该包纳入
`evidence_refs`，美的 ResearchCase 与 Excel 研究卡也显示该候选路线及其阻断条件。

## 2026-09-22 权益回报历史候选序列

`build_midea_2014_2024_equity_return_candidate_series.py` 逐年锁定 2014--2024 原始年报的
归母普通股权益、归母净利、现金分红和按现金回报口径计入的回购，生成
`runtime/company-research/midea-2014-2024-equity-return-candidate-20260922/evidence.json`，
证据 SHA-256：
`6726e821972d0490753a6cc718f6f54515ccbfbb53341f081900af208eab7ea1`。

每行都有来源路径、URL、PDF SHA-256、原报页码和点时发布信息；2024 年现金分红
`26,711,662,411` 元，2019 原报其他现金回报为 `0`，2020 比较表又披露该年度回购
`3,200,000,000` 元，因此仍按原始披露分别保留时点差异。序列状态为
`equity_return_candidate_series_compiled_not_reviewed_or_registered`，每一行
`model_input=null`。

该序列证明公司历史上有持续的权益、利润和现金回报披露，但不能证明未来 ROE、权益成本、
派息政策、当前普通股分母或干净盈余权益滚动对账。适用性包因此把历史序列列为
`COMPILED_CANDIDATE`，仍把预测 ROE、带日期的权益成本、注册的派息/留存政策、当前普通股
分母和干净盈余对账列为下一证据；不把历史序列注册为模型输入。

## 2026-09-22 财务公司规模观察

`build_midea_finance_co_size_observation.py` 将科陆电子与合康新能关于美的集团财务有限公司
的关联披露封存为规模观察，生成
`runtime/company-research/midea-finance-co-2025-size-observation-20260922/evidence.json`，
证据 SHA-256：
`2b3069bc617167dce2ee60730da52cf3da29483e6515adc428a58bd905fb1714`。

三份原件分别为：

- 科陆电子 2026-03-21 风险评估报告，2025 年末五项指标为未审计口径；
- 合康新能 2026-03-21 风险评估报告，披露同一组未审计数值，作为引用值交叉检查；
- 科陆电子 2026-08-27 关联交易公告，披露经审计的 2025 年末五项指标。

经审计口径中，财务公司总资产 `44,464,130,600` 元、净资产 `7,858,593,400` 元、净利润
`410,528,300` 元。相对于美的合并归母普通股净利润 `43,945,411,000` 元及归母普通股权益
`223,221,305,000` 元，候选规模比分别约 `0.93%` 和 `3.52%`。这些比例仅证明财务公司在
合并规模上不具数量主导性，不是工业 EBIT、金融业务剥离、税费/债务/现金/营运资本分配、
WACC、净债务、股本或可转让上市权益价值的输入。

因此该包保持 `OBSERVATION_NOT_MODEL_INPUT`、`VALUATION_NOT_READY`、
`registered_valuation_inputs={}`，并将适用性证据链新增为
`midea_finance_company_size_observation`。工业 FCFF 与合并企业价值桥接的阻断条件均不变。

## 2026-09-22 HKEX 公告日股本证据

`build_midea_20260330_hkex_share_basis.py` 将 HKEX 2026-03-30 全年业绩公告的原始 PDF
锁定为 `runtime/midea-hkex-20260330-annual-results.pdf`，SHA-256：
`c79bef69e4e0629f46987159698bca4a6a5cbfad0fdea596242580b42a813b2a`。

公告第 15 页以总股本 `7,603,276,186` 股剔除已回购 A 股 `80,412,541` 股后的
`7,522,863,645` 股作为末期股息基数；第 94 页明确该 `80,412,541` 股是
“截至本公告日期”的 A 股库存股份，且库存股无权获付股息。对应证据包为
`runtime/company-research/midea-20260330-hkex-share-basis-20260922/evidence.json`。

该公告补上了“公告日库存股股数”这一时点事实，但没有补出 2025-12-31 年末库存股股数，
也没有把公告日范围变成 2026-09-22 估值日普通股分母。因此状态保持
`announcement_date_share_basis_disclosed_not_registered`、
`share_basis_registered_for_current_valuation=false` 与 `VALUATION_NOT_READY`。
适用性包新增 `announcement_date_share_scope=DISCLOSED_NOT_REGISTERED`，而
`current_valuation_share_scope` 仍为 `NOT_REGISTERED`；FCFF 阻断项不变。

## ResearchCase Status

美的 ResearchCase 现有八条可追溯支持证据、五条反证和五条 Thesis Breakers；`G2_商业论点门`
通过。`G0_证据门`、`G1_财务门`及 `G3_估值门`仍不通过，因此结论仍为“数据不足”，不生成
合理价、价格桥接、安全边际、仓位或订单。研究卡证据链已新增
`midea_equity_return_history`、`midea_finance_company_size_observation` 与
`midea_hkex_share_basis`，并明确历史现金回报、财务公司规模披露及公告日库存股股数都不是
当前估值日普通股分母或模型输入。

## 不可越过的缺口

- 期末已发行 A/H 股本和 FY2025 会计加权普通股已披露，但都还不是后续估值日的
  每股估值分母。
- 第 220 页库存股只有账面金额，没有股数；年报未披露加权计算的逐日公司行动权重。
- HKEX 公告已披露 2026-03-30 公告日 A 股库存股 `80,412,541` 股，但该范围不是 2025-12-31
  年末库存股，也不是后续估值日的当前普通股分母。
- 合并口径含金融业务；不得把合并现金减全部借款、债券和租赁负债直接称为工业 FCFF 净债务。
- EBIT、现金税率、折旧、营运资本变动、WACC、适用净债务和非经营资产尚无完整、可复算的同口径证据。
- 合并归母权益与归母利润已披露，但剩余收益/权益价值路线的 ROE、权益成本、派息政策及
  当前普通股分母尚未注册，不能从合并权益或利润直接推导普通股价值。
- 2014--2024 权益回报历史序列已经逐页归档，但仍是候选事实；预测 ROE、权益成本、派息/
  留存政策和干净盈余滚动对账尚未注册，不能把历史现金回报直接外推成模型输入。
- 财务公司经审计规模已封存，但只证明其在合并规模中不占数量主导；它不是独立金融业务
  利润表、资产负债表、税费/债务/现金/营运资本分配或可转让上市权益价值。
- 经营事实仍主要来自发行人年报，尚未完成独立的竞争、治理及行业证据链；这不允许将 G2 通过
  解释为公司质量已被证实。

## Current Data Status

`VALUATION_NOT_READY`。当前输出保留 `not_ready` FCFF 结果、独立
`PriceBridgeResult=PENDING_EXTERNAL_DATA` 与 blockers；不生成 bear/base/bull、当前价格、
安全边际、仓位或订单。统一状态行显示 `工程 READY / 数据 PENDING_EXTERNAL_DATA`，研究结论
仍为“数据不足”。

2026-09-22 再新增 HKEX 公告日股本证据包后，聚焦 Midea、路由与展示层测试
`20 passed`。候选路线、历史序列、规模观察与公告日股本接入没有
改变任何估值、价格桥接、仓位、订单或
实盘准入状态。统一 FCFF 结果 SHA-256：
`5ad0052e676ffacb4141d8c01b11799026550f0bc7a3d39d6a52916dd2523255`。

WPS 原表已完成真实只读导航、源单元格保留和原子发布，发布后 SHA-256：
`BC011BFE5EE4CF583F303FE6EEBA0F5615E930C0F26AC986F9CF775551078FD3`。

## B2 Engineering Acceptance

见 [midea-stage-b2-engineering-acceptance-20260921.md](midea-stage-b2-engineering-acceptance-20260921.md)。
FCFF 入口已达到可验收的阻断状态：真实缺口已被定位并封存，而不是用近似净债务继续计算。

## 下一唯一工程任务

美的适用性登记、合并权益口径、2014--2024 权益回报历史候选序列及 HKEX 公告日股本证据
已完成。下一项不是继续扩展年报附注，也不是制造 FCFF 或
权益价值情景值；唯一工程任务是按目标文档完成一次大节点客观评估并发布本轮研究卡：确认美的 B2 应保持
“事实准入待披露”的 fail-closed 状态，还是在不放宽事实边界的前提下转交下一阶段。在预测
ROE、权益成本、派息/留存政策、当前普通股分母和干净盈余对账注册前，FCFF 与权益价值结果
都保持 `not_ready`，不构造工业净债务、WACC 或每股情景值。

## 2026-09-22 收敛节点已完成

本大节点客观评估已完成，结论见
[midea-stage-b2-convergence-assessment-20260922.md](midea-stage-b2-convergence-assessment-20260922.md)。
美的继续保留研究卡可见的 fail-closed 状态；不生成情景值、价格桥接数值、仓位或订单。
下一工程主线转交中国神华正常化估值收敛。
