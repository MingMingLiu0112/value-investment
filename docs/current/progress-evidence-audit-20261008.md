# 2026-10-08 项目进度证据审查

阅读顺序：本文保留本日不同工作时点的审查记录。当前结论以末尾“本轮续查：真实 v2 链与原表交付差距”为准。旧 optional-payload 重放失败已修复，真实 v2 研究已成功运行；旧失败包仍是历史证据。最新针对性测试仍有两项失败，但现为证据引用哈希漂移拒绝失败。各轮测试范围不同，不相加当作全量回归、产品验收或投资有效性验证。

本轮为只读业务审查：未修改正式 Excel、研究结论、服务器、数据库或目标合同。
审查的是本机当前工作树与本地制品，未登录服务器核验当前生产服务。
HEAD 为 5ba570920f588f4660e91439dedb5ab6f32ff1fe；工作树有正在修改的研究、价格桥接和展示文件。
提交说明和历史测试汇总不作为本轮产品完成证据。

## 判断

当前具备有来源约束的研究展示、条件性估值、价格桥接和决策拒绝机制。
尚未证明存在一只真实公司，在当前有效时点跑通官方事实、研究审查、有效估值、价格桥接、组合风险和买卖建议的完整闭环。
不能宣称正式 Excel 已经能够指导实盘买卖，也不能宣称历史策略效果已验证。
工程覆盖率不能替代产品完成率，本轮不提供没有统一验收分母的完成百分比。

## 当前目标

当前合同为 docs/current/advisory-sentiment-satellite-goal-v1.md。
它在价值投资辅助之外增加独立情绪卫星仓，D2 单公司纵向闭环优先，D1 不得先扩展全市场。
D3 包含买卖和组合指导；D4 是持续跟踪；D5 需要真实情绪特征、样本外验证、成本和 Shadow；D6 为运营与用户交付。
旧 M2-M7 的完成记录保留，但不能直接证明新目标 D2-D6 已完成。

## 实际证据

| 能力 | 本轮检查 | 判断 |
| --- | --- | --- |
| 正式 Excel | 原文件 SHA-256 与 config/current-trial-workbook.json 一致；62 张表，7 张可见；文件修改时间 2026-10-02 10:08:57 | 正式入口可定位，不能由文件存在推出买卖建议可用 |
| 单票研究接口 | run_company_research.py 接入共享 ResearchApplicationService，可导出 valuation/model_validity/price_bridge/decision_recommendation/artifact_bundle | 共享路径存在，真实公司完整准入尚未证明 |
| 伊利真实研究产物 | runtime/d2-real-negative-20261007/600887-existing-read.json 为 READ_EXISTING_ONLY；9 份来源文件当前 SHA-256 全部一致 | 已有低置信度条件估值；不是新研究或正向推荐 |
| 伊利当前状态 | Bear/Base/Bull 8.0476/11.0234/13.1335；基准日 2026-06-30；ModelValidity NOT_ESTABLISHED；价格与报价日为空；strict_pit NOT_PROVEN；suggested_state NOT_READY | 这些数值不能直接作为当前买点或卖点 |
| 美的/神华展示 | 正式表内六项报告事实和缺项可查看；没有 Bear/Base/Bull 和有效价格桥接 | 事实展示存在，完整研究估值尚未闭合 |
| 建议生成器 | application/decision/build_decision_recommendation.py 只分支到 BUY_CANDIDATE / NO_ACTION；reduce_zone=None；position_guidance=None | 当前共享建议生成器尚非完整买/加/持/减/卖引擎；其他历史模块的状态不能自动替代该集成 |
| 买入区间 | 正向分支使用 Bear 到 Base，basis 明确为 approved_research_value_band_not_execution_threshold | 是研究价值带，不是已验证的成交择时规则 |
| 正式前端事件 | 05_事件 显示当前没有已分类用户事件；后台保留 public-event-followup-20261002 的伊利新披露解释 | 原件、解释、重大性批准、正式用户提醒之间存在集成缺口；不据此自动升级研究状态 |
| 行情采集 | 10 月 7 日 bundle 仅含 600519，status=collected_not_verified；10 月 3 日三公司 bundle 同样待验证 | 不能将采集日期等同报价日期或价格桥接完成；假期采集不证明新交易日 |
| 历史回放 | 600519 historical-company-closure 的 9 项来源绑定全部哈希一致；结果为 NOT_READY，strict_pit_admitted=false，historical_execution_validated=false | 确有真实历史素材和回放工程；不能声称策略获利能力验收通过 |
| 历史成交核对 | historical-fill-bar-audit-20261003/audit-v3.json 核对 4 笔模拟成交日线区间，execution_admitted=false | 只是必要成交条件，不证明真实可成交或样本外有效 |
| 情绪卫星仓 | domain/portfolio/sentiment_contracts.py 明确 synthetic-only，拒绝生产情绪输入 | 接口/隔离边界存在；真实波段策略尚未实现及验收 |
| Shadow | personal_shadow_governance.py 为 DEPENDENCY_PLAN_ONLY；本轮检查的离线记录 NOT_ADMITTED、真实会话计数 0 | 没有证据支持本次审查计入真实观察会话；不据此推断所有远端状态 |
| 恢复 | real-server-database-restore-20261001/receipt.json 声明 14 张表核对匹配、20 份证据校验；PG16 dump 在本地 PG18 恢复 | 已有实际恢复工作；本轮只读取回执，未再次执行恢复。完整系统、同主版本、异地加密备份仍未通过 |

## 正式 Excel 的产品缺口

- 数据截止和展示内容停在 10 月 2 日；本轮未发布 10 月 7 日新增读取结果。
- 研究、估值、有效行情和建议状态没有形成用户可比较的横向决策表。
- 公司卡和决策过程重复较多长说明，重要原因被内部术语和多重门禁淹没。
- 已取得公告解释与已分类事件提醒尚未闭环；缺项可能仍沿用旧研究版本。
- 私人组合尚未接入；缺私人输入只阻塞个性化容量和仓位，不应阻塞公共研究推进。
- 尚未进行本轮新的 WPS 视觉验收；以上判断来自真实单元格读取，不冒称截图审查。

## 本轮验证

对建议生成、既有估值读取、价格桥接和离线观察四组测试执行：82 passed，1 条既有 openpyxl 弃用警告。
命令：

```powershell
$env:PYTHONPATH = 'D:\GPTProject\value-investment\src'
$env:TEMP = 'D:\GPTProject\value-investment\.tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
& 'D:\APP\Python313\python.exe' -B -m pytest -q -p no:cacheprovider `
  --basetemp=.tmp/audit-progress-tests-20261008 `
  tests/test_decision_recommendation.py tests/test_existing_valuation.py `
  tests/test_price_bridge.py tests/test_personal_shadow_observation.py
```

托管 Python 缺 pytest，首次测试命令未执行测试；后使用现有项目开发 Python 成功运行。
该验证不覆盖全部工作树、不重新证明官方原文含义、不证明金融模型适用性或投资收益。
正式文件哈希：5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8。
伊利读取产物哈希：1d1eaaab293007aacec26381962a251087649303fcb243bcbb7e9ed138c5e2e4。

## 剩余工作与时间估计

应先完成以下工作，不新增平行框架：

1. 一只公司的当前事实、重大事件、估值假设和有效模型版本闭合；低置信度结果须经过适用性复核。
2. 将最近有效交易日的核验行情接入同一研究结果，形成正式 PriceBridge 和 DecisionRecommendation；缺项保持拒绝。
3. 把 ADD/HOLD/TRIM/SELL、原始持仓论点、退出触发和状态失效真正接入共享建议服务；个性化仓位仍需确认的 IPS/组合。
4. 冻结规则并完成真实输入的历史与样本外检验，覆盖成本、停牌、涨跌停、分红和可成交性；报告失败情景，不能为产生交易而调参。
5. 同一产品包发布正式 Excel、形成日级跟踪和真实观察证据、完成恢复及用户验收。

这是规划估计，不是已测量吞吐量或交付承诺：

- 前端整理和最新解释同步：约 2-4 个集中工程日。
- 单票条件决策工作台：约 5-10 个集中工程日，前提是现有公开证据足够关闭必要模型/事实缺口。
- 买卖/加减仓规则集成、真实历史检验和多票复用：再约 10-20 个集中工程日；与前端可部分并行。
- 已授权且有效 Shadow 启动后，20 个连续真实交易会话至少约 4-5 个自然周；不能从首个编码日直接起算，失败或缺覆盖会延长。
- 价值投资核心达到经验证的有限辅助使用：按以上条件约 6-10 周是规划窗口，不能承诺固定日期。情绪卫星仓另有实质开发和样本外验证，不包含在此核心窗口内。

外部证据不能由编码保证取得，正向建议也不能由工期保证出现。系统完成后某只股票仍可合理输出 NO_ACTION。
此前给出的确定性日期、未经实测的完成比例，以及将完整目标默认为单票交付的估计不应继续作为承诺。
action=no_order；本次没有生成买卖建议。

## 本轮直接复核补充（2026-10-08）

以下来自重新读取本机文件、源代码与执行测试，不沿用提交注释作为证据。

### 全市场筛选的实际覆盖边界

直接读取 `runtime/m2-live-20260923-v3/receipt.json` 和 `manifest.json`，
并重新计算 manifest 内全部 8 个文件的 SHA-256，全部匹配。
该批次 as_of 为 2026-09-23，不是 2026-10-08 当前市场运行。

| 通道 | 证券分母 | 通过 | 数据缺口 | 未评估 | 预算排除 | 不支持 | 拒绝 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Quality | 5568 | 0 | 4672 | 0 | 0 | 121 | 775 |
| Value | 5568 | 50 | 1465 | 0 | 351 | 121 | 3581 |
| Dividend | 5568 | 50 | 0 | 1946 | 369 | 106 | 3097 |
| Cyclical | 5568 | 50 | 692 | 3059 | 1535 | 121 | 111 |

各行分类之和均为 5568。不同通道的通过者可以重叠，不能相加声称 150 家独立
推荐。`data_health.status=COMPLETE` 的行情勾稽为 matched_quote_count=5568、
missing_quote_count=0；同一数据包 financial_evidence_count=873。
因此行情完整不能用作全市场财务证据完整或全市场质量分析完成的证明。

### 官方原件和当前前端的断点

- 重新核算伊利既有读取产物 `source_records` 的 9 项本地来源，全部哈希匹配。
  其中既有原件当前观测标记不证明历史当时已可用；哈希匹配也不是本轮重新核验
  每一个财务口径或估值假设。
- 重新核算 `public-event-followup-20261002/event-scan.json` 的两份公告原件，
  全部哈希匹配。扫描自身为 `INCOMPLETE`、`PENDING_HUMAN_REVIEW`，只覆盖
  10 月 1-2 日，不能代替从估值日到决策日的完整事件覆盖。
- 正式表 `决策过程!D11` 仍描述融资券到期结果尚未核实，而后台原件解释已
  记录正式兑付披露。应更新该事实说明；兑付后的现金债务桥接、担保重大性和
  完整模型有效性仍未知，不能顺带升级为可买入。
- `05_事件!A4` 仍显示没有已分类用户事件。此处仅证明后台解释到正式用户
  提醒没有完成；本轮没有改写原表，也没有进行新的 WPS 屏幕或视觉验收。

### 共享代码的集成边界

`research_application.py` 实际调用建议生成器并存储建议制品，
`application/product/workbench.py` 在展示前还原并核验其依赖，说明共享链路
已存在。`application/decision/build_decision_recommendation.py` 实际仅生成
BUY_CANDIDATE / NO_ACTION，entry_zone 是研究 Bear/Base 价值带，
reduce_zone 和 position_guidance 保持 None。
因此旧决策或组合模块即便独立具备更多状态，也不能直接算作当前共享用户链路
已完成买、加、持、减、卖集成。

当前目标文档写 D2=READY_TO_START，但工作树已包含 D2 建议合同、服务调用和
测试增量。按实际进度应描述为 D2 工程部分实现、真实产品验收未完成；本轮没有
修改目标状态来制造完成记录。

### 独立代码审查发现的具体断点

SubAgent 完成独立调用链检查后，Root 再读取相关代码核对，确认以下静态问题。
它们属于可继续修复的工程项，不应归咎于没有行情接口或等待下一个交易日。

1. 估值批准状态没有贯通。`valuation_models/residual_income.py:456`、
   `fcff.py:192`、`cyclical.py:350` 返回条件性研究结果；共享服务评估研究批准，
   但没有创建带独立批准绑定的后续估值状态。
   `application/decision/build_decision_recommendation.py:254` 却要求估值状态为
   approved_research_only/ready，因此内置模型的条件输出会在此被拒绝。
   解决不能是直接修改封存估值标签，必须复用已绑定的批准语义。
2. `application/product/workbench.py:91` 调用共享单票研究时没有透传报价、
   事件、研究审阅和重开请求。研究服务已有这些入参，当前工作台入口没有完全
   暴露它们，不能将研究 CLI 支持等同用户工作台已连通。
3. `price_attractiveness.py:21` 定义 WAITING_FOR_BETTER_PRICE，
   `application/product/decision_surface.py:18` 登记 WAIT_FOR_BETTER_PRICE；
   同文件约第 100 行会拒绝未登记的价格状态。合法等待价格的结论存在产品
   投影失败路径。
4. `application/product/decision_surface.py:203` 保留已有 decision_process，
   只更新 valuation、price_bridge、decision_gate。其余步骤没有同时绑定新
   依赖版本，可能沿用旧阻断或旧通过结论；此项为代码风险，未声称正式表已
   出现错误 PASS。
5. `presentation/read_models/existing_research_report.py:205` 的当前报告渲染器
   仅接受 suggested_state=NOT_READY，而工作台非停止路径已输出
   NO_ACTION/BUY_CANDIDATE；该路径使用报告输出会被拒绝。

上述为代码实查，不是完整真实正向场景的运行复现。现有 38 项测试通过没有
覆盖或证明这些组合状态已经正确衔接。应补齐共享链路再做真实单票验收，而非
用 synthetic 正向测试或既有结果只读模式替代 D2。

### 本轮新执行的验证

命令使用现有开发 Python，基于当前工作树执行：

```powershell
& 'D:\APP\Python313\python.exe' -B -m pytest -q -p no:cacheprovider `
  --basetemp=.tmp/progress-product-chain-audit-20261008 `
  tests/test_research_application.py `
  tests/test_company_research_export_current_status.py `
  tests/test_product_workbench_excel.py
```

结果：**38 passed in 10.71s**。这是共享服务、导出和展示契约的针对性测试，
不是全量回归，不是官方原件金融含义的独立审查，也不是真实股票正向准入证明。
此前 82 项验证保留原范围，不将两批数字包装为整体策略或收益验证。

### 产品可用性的四层结论

| 层次 | 当前结论 |
| --- | --- |
| CODE_IMPLEMENTED | 有共享研究/估值/桥接/建议基础，完整建议状态和生产闭环仍部分实现 |
| AUTOMATED_TEST_PASSED | 本轮 38 项针对性测试通过；没有重新证明全部工作树 |
| REAL_DATA_ADMITTED | 本轮未证实一只真实公司在有效时点完成 D2 的全部必需依赖准入；已有真实原件和条件估值不等于无数据 |
| USER_ACCEPTED | 本轮未进行最终用户使用验收；正式表保留未通过状态 |

开发路径应优先闭合一个可复用的真实公司研究到建议流程，再接完整买卖与仓位
规则及日级跟踪。缺 IPS 只阻塞个性化金额和容量，不是阻止公共研究的理由。
对未披露的内部口径，研究上应区分必需事实、有依据可估计的区间假设与模型
确实不适用的情况，而不是无限搜集或用无依据数字解除限制。
不会为了显示 BUY 调整规则；有充分证据的 NO_ACTION 也是合法的可用结果。

## 最新工作树与当日运行产物复核（2026-10-08）

本次响应用户“客观分析进度”而执行审查，不继续开发新功能。重新读取当前目标、
实际业务代码、WPS 原表 OOXML、真实运行 JSON 与来源绑定，并运行当前工作树测试。
未修改业务代码、正式 Excel、目标合同或远端服务；只保存本记录和项目内审查辅助文件。
没有通过提交说明来推断功能完成，也没有新作 WPS 原生视觉验收。

### 新执行验证

当前工作树以下 11 组针对性测试为 **173 passed, 1 warning in 17.12s**：

```text
test_decision_recommendation
test_d2_workbench_decision_projection
test_product_cli_entrypoints
test_research_application
test_current_decision_surface
test_current_decision_report
test_product_workbench_excel
test_existing_valuation
test_price_bridge
test_d5_satellite_contracts
test_personal_shadow_observation
```

执行使用开发 Python 3.13，PYTHONPATH=src，pytest 临时目录限定为
`.tmp/progress-current-recheck-20261008`。一条警告为既有 openpyxl 命名区域 API 弃用。
本次不是全量回归；合成正向用例通过不证明真实公司准入、严格 PIT 或收益有效。

### 已修复的工程断点

直接复读代码确认：新版建议序列化使用 `recommendation_type`，并独立保留
`action=no_order`；旧版负载可按原 schema 还原。条件估值可通过精确绑定的合格
研究批准参与后续评估，不篡改原估值标签。工作台透传报价、事件、研究审阅和
调度请求；价格等待状态名称与上游一致；当前报告接受合法建议状态，并重放依赖。
决策过程八步已按新依赖刷新；公开研究投影不直接覆盖用户原始持仓论点。
这些属于工程衔接进展，不能据此把 D2 真实产品验收标记完成。

### 不能再笼统归因于没有行情

读取 `runtime/quote-sessions/20261008T090505876967Z/bundle.json`，
重算 bundle 与 3 份原始文档字节 SHA-256，全部匹配；调用现有
`quote_snapshot_from_bundle_file` 重放腾讯、新浪和上交所日历：

```text
symbol = 600519
quote_date = 2026-10-08
current_price = 1255.79
status = verified_close
blockers = []
```

这只是该股票、该会话的行情核验，不是正式买点，不证明三公司行情全部准入，
也不证明当前共享研究闭环已完成。不能仅因原始 bundle 写 collected_not_verified
就忽略后续转换器的实际结果。

### 当日茅台研究资产与适用范围

实际读取 `runtime/company-research/600519-current-valuation-admission-20261008T090507Z/evidence.json`，
重新核验其直接引用的 8 项来源文件，8/8 哈希匹配。它同时声明：

```text
p1_current_model_admitted = true
allowed scope = bounded current paper research
valuation_approved = false
formal_fair_value = null
trade_approved = false
daily_simulation_policy_implemented = false
```

新产物 `600519-current-assumption-diagnostic-20261008T090508Z/evidence.json`
将当前路径诊断为 `strong_fade_stress_scope_only_not_neutral_primary`。
因此有当日条件模型和反证研究，不能把有界研究准入简写为正式估值、投资建议
或策略完成。哈希匹配只证明输入字节，未在本次重新审查每一项财务原文与假设。

SubAgent 独立核对后，Root 再读相关调用片段：茅台当前 admission/thesis/diagnostics
由专用审计和 simulation closure 消费，并未生成共享 D2 的 DecisionRecommendation。
专用估值导出虽然已采用部分共享模型合同，输出仍是 moutai-stage-b-valuation-result-v2；
专用每日模拟使用 simulation_state.DecisionInput/evaluate，与 research_application 的
共享推荐生成器是不同消费者。因此“茅台脚本有当日结果”不能自动算作可复用
单票产品链已贯通。这是适配/集成缺口，不能以公司数据全部缺失来解释。

### 正式入口仍落后于后台

重新读取唯一 C 盘原表：哈希仍为
`5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`，
与 pointer 一致；62 张表、7 张可见，55 张历史/保留页隐藏。
`01_今日!B4` 写 2026-10-02 01:48，`决策过程!A2` 的截止日也是 10 月 2 日。
三公司展示均未形成当前建议；伊利展示低置信度 8.05/11.02/13.13 条件情景，
其现有只读研究 JSON 的 9 项来源再次核验全部匹配。

7 张可见表的 OOXML 均没有公式，是应用写入的结果快照；这不代表隐藏历史页
没有公式，也不代表后台没有计算。改变单元格不能代替后台依赖重算和受保护发布。
未发现这些可见表中的缓存错误单元格；未重作原生 WPS 重算或布局验证。

`05_事件!A4` 仍为空事件说明，`决策过程!D11` 保留融资兑付尚未核实的旧表述。
后台 10 月 2 日解释已记录正式兑付披露；event-scan 的 5 项直接/重复来源绑定
本次全部哈希匹配，但事件覆盖仍为 INCOMPLETE，仅 10 月 1-2 日。应更新事实
说明和提醒，不应因此把兑付后流动性桥接、担保影响或模型有效性自动判为通过。

### 仍需开发与验收的核心功能

1. D2：真实公司共享链路的必要事实、假设审阅、事件覆盖、ModelValidity、
   PriceBridge、建议产物及正式 Excel 接入仍未获完整产品验收。
2. D3：当前建议生成器实际只产生 BUY_CANDIDATE / NO_ACTION；
   entry_zone 是批准研究 Bear/Base 价值带，不是成交择时阈值；reduce_zone
   恒为 null。ADD/HOLD/TRIM/SELL 仍未接入当前共享建议合同和消费者。
3. 个性化组合：合同目前仅允许 BLOCKED_PRIVATE_INPUT、position_guidance=null。
   需要真实 IPS/持仓后再验收金额、加减仓、集中度、现金底线和退出一致性；
   此项不阻塞公共研究或非个性化候选推进。
4. 跟踪：公告采集和部分解释存在，但重大性、模型失效、重算、建议撤销与
   前端提醒尚未证实一条真实持续运行闭环。
5. 策略与运营：历史回放不是严格 PIT/样本外收益证明；本次读取的离线观察
   ledger 为 NOT_ADMITTED、真实会话计数 0，不能据此推断全部远端状态。
   恢复回执表明数据库检查结果，但本次未重做恢复；完整系统恢复仍未通过。
6. D5：情绪合同明确 synthetic-only，真实情绪模型、样本外与成本验证未完成。
   开源 sidecar 报告已完成五库有界源码/许可审查，但它是设计资产，不是模块集成。

M2 的 9 月 23 日真实批次与 manifest 8 项哈希本次再次核验通过，分母 5568。
Quality 通过 0、数据缺口 4672；另外三通道各通过 50，但有重叠且是研究线索，
不构成 150 只独立可买推荐。行情完整也不意味着财务证据完整。

### 客观阶段判断与收敛建议

CODE_IMPLEMENTED：共享研究、模型、报价转换、拒绝及展示基础已具备，建议和
持续运行集成仍部分实现。AUTOMATED_TEST_PASSED：本次 173 项针对性检查通过。
REAL_DATA_ADMITTED：存在真实来源和局部准入，未证实完整 D2 当前产品准入。
USER_ACCEPTED：最终产品实际使用验收未通过。总 Goal 仍不应标记完成。

当前目标中 D2=READY_TO_START 落后于实际工作树，正确评估是工程部分实现、
真实闭环/产品验收未完成；本轮不修改目标合同，也不降低它的退出标准。

最快路径是先交付一家公司可复用、可解释的真实共享结论（允许是有充分依据的
NO_ACTION），同步原表，再贯通完整买卖/加减仓及日级跟踪。不要先扩大股票数、
另建框架或让情绪卫星研究替代价值核心交付。
单票、完整交易辅助和全目标应分别估时；此前 5-10/10-20 工程日只能作为有条件
规划窗口，尚无实测吞吐量支持固定交付日期。20 个有效真实交易会话从获准且
通过输入准入的观察启动日计，通常至少约 4-5 个自然周，不能靠历史回放压缩。
当前证据不足以声称系统能够稳定盈利。action=no_order。

## 用户再次要求客观分析：最新实测

本节直接重新读取工作树、C 盘唯一 Excel、实际运行 JSON，并执行测试和来源/行情转换核验。只增加本记录与项目内只读审查脚本，没有修复业务代码、改变研究批准、更新正式 Excel 或操作服务器。本机工作树 HEAD 仍为 `5ba570920f588f4660e91439dedb5ab6f32ff1fe`，存在未提交和未跟踪的集成修改；因此 HEAD 和提交说明不能代表实际运行版本。

### 当前结果及可复现失败

执行以下当前工作树测试：

```powershell
$env:PYTHONPATH = 'D:/GPTProject/value-investment/src'
$env:TEMP = 'D:/GPTProject/value-investment/.tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
& 'D:/APP/Python313/python.exe' -B -m pytest -q -p no:cacheprovider `
  --basetemp=.tmp/objective-progress-final-20261008 `
  tests/test_source_bound_research_inputs.py `
  tests/test_d2_conditional_shared_service.py `
  tests/test_residual_income_valuation_timing.py `
  tests/test_decision_recommendation.py `
  tests/test_d2_workbench_decision_projection.py `
  tests/test_current_decision_surface.py `
  tests/test_current_decision_report.py `
  tests/test_research_application.py `
  tests/test_product_workbench_excel.py `
  tests/test_d5_satellite_contracts.py
```

实际结果：**128 passed, 2 failed in 9.42s**。这是十组针对性测试，不是全量回归。
失败均为 `test_synthetic_conditional_approval_chain_and_bundle_replay` 的 missing-approval 场景，分别通过 shared_service 和 product_entry 调用。
两者正确生成 NO_ACTION，但在证据包还原时抛出 `Decision recommendation failed full repository replay`。
`application/decision/restore_decision_recommendation.py:230` 在没有 human_approval 制品时将 research_case/facts/assumptions 载荷置为 None；与原计算保留的载荷不一致，导致重放结果不同。
`application/product/workbench.py:122` 在展示前必须重放建议，因此这是可影响共享工作台拒绝结果展示的工程缺陷。没有发现该失败产生错误 BUY；也不能因为拒绝正确而声称整条链路可用。

### 新建真实茅台包未完成共享运行

重新读取 `runtime/d2-source-bound-current-20261008/research.json`，结果是：

```text
status = BLOCKED_BY_RESEARCH_SCHEDULER
blockers = [BLOCKED_NO_REGISTERED_SCOPE]
run_id = null
action = no_order
```

该文件没有 ValuationResult、DecisionRecommendation 或 artifact_bundle。命令返回成功并写出拒绝 JSON，不代表业务流程执行成功。
适配记录中的 expected_conditional_values 是预期比较值，不是该次共享服务已计算的结果。此时阻塞首先是缺注册研究范围；注册后仍须处理已有财务/商业研究、假设适用性和事件覆盖缺口，不得绕过这些门。

直接调用 `verify_package_local_sources` 核验新包 9 项本地来源，全部字节哈希匹配。调用 `quote_snapshot_from_bundle_file` 重放当日真实行情，三份原始文档哈希全部匹配，600519 的 `quote_date=2026-10-08`、`current_price=1255.79`、`status=verified_close`、`blockers=[]`。这证明当前行情资产存在，不证明完整研究/模型/建议准入。
`event-scan.json` 仍为 INCOMPLETE / PENDING_HUMAN_REVIEW；扫描只覆盖 9 月 14 日至 10 月 8 日的有界资本查询，不能证明从权益基准日至决策日的完整重大事件覆盖。

### 原表和策略资产仍有真实差距

本轮重新执行 OOXML 审查：原表 SHA-256 仍为 `5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`，匹配当前 pointer；62 页、7 可见、55 隐藏。`01_今日!B4` 和 `决策过程!A2` 仍截至 10 月 2 日，三家公司均无当前准入建议；事件页 A4 仍为空事件说明。决策过程 D11 保留偿付尚未核实的历史问题，不能当作更新后的完整流动性结论。
七个可见页没有公式，是后台发布的结果快照；正常使用依赖后台更新和正式发布。没有缓存错误不证明当前金融结论正确，本轮也没有原生 WPS 布局或重算验收。

当前共享建议合同枚举 BUY/ADD/HOLD/TRIM/SELL/NO_ACTION，但 `D2_IMPLEMENTED_ACTIONS` 和实际生成器只实现 BUY_CANDIDATE / NO_ACTION。`build_decision_recommendation.py:405` 的 reduce_zone 和 `:418` 的 position_guidance 为 None。完整退出、加减仓、实际组合容量尚未接入当前共享产品链；私人输入缺失只阻塞个性化指导，不能解释公共研究停滞。

重新核算 M2 9 月 23 日批次 8 项 manifest 文件，全部匹配：证券分母 5568，Quality 通过 0、数据缺口 4672，另外三通道各通过 50 且可能重叠。这是已完成的候选发现资产，不是当前完整财务覆盖或股票买入建议。
重新核算 600887 现有研究九项来源和 600519 历史闭环九项来源，全部匹配；历史闭环明确 `strict_pit_admitted=false`、`historical_execution_validated=false`、`performance_claim_allowed=false`，不能以其历史虚拟收益证明策略有效。
本轮读取的 `personal-observation-offline-20261003/000001.json` 为 NOT_ADMITTED / LOCAL_OFFLINE_ONLY，真实会话计数 0；只代表这个离线台账，没有登录服务器，不推断所有远端计数。
实际数据库恢复回执可读，table_checks_match=true、verified_evidence_count=20；full_system_restore_passed=false、same_major_restore_verified=false。没有重新执行真实恢复，完整系统恢复不能报通过。

### 当前交付判断与优先级

当前产品定位应为“具有真实原件和确定性计算基础的研究原型，共享交易辅助链路仍在集成”。不能称只剩 Excel 排版，也不能把专用公司产物、合成正向测试和正式产品验收合并计算完成度。

1. 先修复建议证据重放，补齐真实输入/假设/时点语义和研究范围登记，通过当前单公司共享链。
2. 闭合必要研究和完整事件覆盖，明确模型适用性；低置信度强衰减压力情景不能直接当中性主估值。
3. 将同一真实输入包、行情、明确结论和缺口接入原表；当前真实链路尚未获得此项交付证据。
4. 然后完成共享退出、加减仓、真实组合约束、事件撤销/重算/提醒及跨公司复用。
5. 独立完成规则冻结、PIT/OOS/费用/可成交性验证、真实观察和恢复/用户验收；情绪卫星仓不能挤占 D2 首个产品交付。

时间只能作有条件规划：最新原表和解释整理约 2-4 个集中工程日；可复用单票真实研究/决策试用约 5-10 个集中工程日，前提是公开证据可支撑必需研究结论。单票试用仍可能合理输出不操作，不保证出现买入候选。

独立子代理按剩余领域工作给出粗粒度预算：D1 后续扩展 4-7、D3 10-18、D4 7-12、D5 18-30、D6 6-10，以及集成/回归/独立验收 5-8 个工程日；合计 50-85 个工程日，不包含 Root 的 D2 和原表工作。这是对完整扩展目标的估算，不是实测吞吐量，也不是必须串行逐项相加的关键路径计划。
综合范围区别后，完整价值核心的买卖、组合和持续跟踪应保守预算约 6-10 个工程周，真实观察与最终验收另计；此前本记录的 6-10 周“已经验证可用”窗口偏乐观，不继续作交付承诺。完整含情绪卫星仓的目标可按约 4-6 个月粗预算审视，仍可能因数据/研究/策略检验失败而延长。
获准并具备输入准入的有效观察启动后，20 个连续真实交易会话通常至少 4-5 个自然周；可以与不改变冻结观察规则的独立工作重叠，不能从今天直接算已经启动。没有真实 IPS、生产授权或最终验收时，工程完成不能代替相应用户门。

当前没有稳定盈利证明，没有产生本轮投资建议，没有改变长期 Goal 状态。action=no_order。

## 本轮续查：真实 v2 链与原表交付差距

响应用户再次要求客观分析，本轮重新读取目标、工作树、真实 v2 输入与结果、正式 Excel OOXML，重算来源哈希，执行冷重放和 11 模块测试，并由两名 SubAgent 分工只读审查。审查未改变业务代码、研究批准、正式 Excel、生产服务或总 Goal 状态。只保存本文和 `.tmp/progress-audit-fresh-20261008.json`；没有进行本轮原生 WPS 视觉检查、服务器登录或真实恢复。

### 实测判断

项目已具备真实原件、可复用计算与拒绝机制的研究原型，但没有完成可依赖的交易辅助产品。当前 D2 应理解为部分实现，而不是目标文件仍写的 READY_TO_START，也不是产品已验收。缺口同时涉及研究有效性、共享建议状态、前端交付和运行验证，不能简化为只差排版或只差数据源。

| 能力 | 本轮直接证据 | 当前边界 |
| --- | --- | --- |
| 原表 | SHA-256 仍为 `5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8`；62 页、7 可见、55 隐藏；今日 B4 与决策过程 A2 截止 10 月 2 日 | 10 月 8 日后台结果未发布；七可见页为无公式结果快照，依赖后台生成/发布更新 |
| 全市场发现 | `runtime/m2-live-20260923-v3/manifest.json` 的 8 个文件哈希本轮全部匹配；5568 分母；Quality 通过 0、缺口 4672；其余三通道各通过 50 | 历史候选线索批次，有通道重叠，不是当前全市场完整财务研究或可买名单 |
| 茅台共享链 | `package-v2-current-model.json` 的 16 项本地来源哈希匹配，42 条情景绑定；`workbench-v2.json` 的真实制品本轮冷重放通过，独立代理亦核对 research/workbench 决策一致 | 官方 PDF 与研究/规则文件混合来源，不是 16 份全部官方原件；字节绑定不等于财务语义和模型批准 |
| 行情 | 从绑定 bundle 重新转换，600519 报价日期 2026-10-08、价格 1255.79、verified_close、blockers=[] | 原始行情已存在；有效价格桥接仍缺模型/研究条件，不能说等待下一交易日 |
| 实际输出 | `research_status=COMPLETED_WITH_BLOCKERS`、recommendation_type=NO_ACTION、ModelValidity=UNKNOWN、PriceBridge=INVALID、price=NOT_ASSESSABLE；entry/reduce/position=null | NO_ACTION 表示研究依据不足以形成买入候选，不是已完成估值判断后认为股价昂贵 |
| 估值 | 共享 dated residual-income 结果约 404.82/479.88/572.74，conditional_research_only、低置信度 | 强衰减压力情景尚未作为中性主估值批准，不能称合理价值或买入区间 |
| 事件 | 新扫描宣称已取得有界窗口全部 7 份原件；各条仍为 PENDING_HUMAN_REVIEW | 取得原件和扫描 COMPLETE 不等于逐条重大性、模型吸收或全网站历史覆盖证明 |
| 建议状态 | `build_decision_recommendation.py:333` 只生成 BUY_CANDIDATE/NO_ACTION；reduce_zone 在 :405 固定 None，position_guidance 在 :418 固定 None | ADD/HOLD/TRIM/SELL 和私人组合尚未接入这条共享产品链，旧独立模块不能替代集成 |
| 产品消费者 | `decision_surface.py:133` 要求公司已存在于两种产品视图；当前产品三公司无新茅台；历史 candidate CLI 无新 decision-workbench 参数，正式 publisher 有相关参数 | 不能泛称所有发布入口均不存在，但当前新公司到既有产品视图的注册/保留/投影仍有工程缺口 |
| 前端一致性 | 公司页 B130 已描述伊利兑付披露；决策过程 D11 仍保留偿付未核实旧文字；事件 A4 仍无已分类事件 | 正式产品内部解释不同步；兑付披露也不自动证明完整现金债务桥接或可买 |
| 运行与恢复 | 读取离线 000001 ledger 为 NOT_ADMITTED、有效真实会话 0；真实恢复回执 14 表检查匹配、20 份证据、full_system_restore_passed=false、same_major_restore_verified=false | 本轮未核查全部远端计数、未重新执行恢复；旧回执不证明完整系统恢复和连续运营 |
| 情绪卫星 | sentiment_contracts.py 明确 synthetic-only、无真实模型/策略 | 接口资产，真实情绪、样本外、费用和观察尚未验收 |

### 当前测试缺陷

本轮在当前工作树执行以下 11 模块，结果为 **226 passed, 2 failed in 6.53s**：

```text
test_d2_source_bound_package_contract
test_d2_optional_payload_replay
test_d2_conditional_shared_service
test_decision_recommendation
test_d2_workbench_decision_projection
test_source_bound_research_inputs
test_current_decision_surface
test_current_decision_report
test_research_application
test_product_workbench_excel
test_residual_income_valuation_timing
```

两个失败均位于 `tests/test_d2_source_bound_package_contract.py:231`：binding-evidence-hash-drift、assumption-evidence-hash-drift 应拒绝却未抛 ValueError。源码 `source_bound_inputs.py:140` 对这些引用检查 source ID，没有验证引用中声明的哈希是否与来源目录一致。该缺陷不表示本轮真实 16 项原件哈希已损坏，也不表示观测到错误 BUY；它表示源合同缺少一项拒绝能力，不能声称全绿或完整来源完整性验收。

旧 optional-payload missing-approval 重放问题本轮未复现，实际 v2 冷重放成功。独立代理 3 模块结果为 113 passed、相同 2 failed；与 Root 测试有重叠，不相加。上述均为针对性工程检验，不证明财务含义、模型经济适用性或策略盈利。

### 剩余开发及估时边界

最短路径依次是：修复引用哈希拒绝；核定单票财务/商业论点、情景经济含义、事件重大性和模型有效性；将同一真实共享结果接入并发布原表，保留私人手工记录；再接完整买卖/加减仓、Entry Thesis、组合风险及事件失效/重算/提醒；分别完成历史/样本外、真实观察、恢复和实际用户验收。公开研究审查可以委派，缺私人输入不阻塞这部分工程；不能为产生 BUY 调参或伪造批准。

以下仅为有条件工时预算，不是依据测得速度的交付承诺：

- 引用哈希校验和有界回归约 2-6 小时。
- 单票研究、7 份公告、假设/模型与批准链处理约 16-40 小时，前提是现有原件足以支撑结论，不新建模型，不包含生产和最终验收等待。
- 正式 Excel 同步、解释一致性和原生展示核验约 2-4 个集中工程日，可与研究并行。
- 单票原表条件试用可按 5-10 个集中工程日预算，但研究若需新增披露会延长，合法结果可能仍是不行动；不能等同完整交易辅助已可用。
- 完整买卖、私人组合和持续跟踪仍为多项实质集成，属于数周工程量级。现有材料不足以给可靠固定日期或统一完成百分比。
- 获准且输入合格的观察启动后，20 个连续真实交易会话通常至少 4-5 个自然周。历史回放不得替代计数；可与不改变冻结观察规则的独立工程重叠。完整情绪卫星目标另需研究和验证，不能混入单票试用工期。

当前可辅助阅读财报、条件情景及研究缺口，尚不可声称可靠给出买卖点、个性化加减仓或稳定盈利。总 Goal 未完成，`action=no_order`。
