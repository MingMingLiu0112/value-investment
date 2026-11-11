# 价值策略 Specification v0.1（待用户确认）

基线：`de66fdd5341dd1efc97856184a6ddb62ffdac5d9`，2026-10-23；仅说明已存在的价值研究/人工复核路径，不批准策略。`action=no_order`。目标是发现值得研究的企业及解释持仓变化，不保证收益、不自动下单。模拟、研究排序、正式研究、价格准入和个人仓位必须分层。

## 1. 实际实现索引与输入合同

源码前缀 `src/value_investment_agent/`。下表H16为**Git基线文件原始字节SHA-256前16位**，不是全Hash；完整文件由上述精确提交固定。已核工作区内容与基线一致，除部分CRLF/LF不同；不混入并行cp1修改。无独立规则版本常量者，以提交和文件Hash识别，不能臆造版本。

| 编号 | 文件；核心函数/合同 | 规则/模型版本；H16 |
|---|---|---|
| A | `domain/discovery/value_candidate_selection.py`；`observation_conditions/rank_research_candidates` | `value-observation-research-priority-v1`；49208054c2545fe6 |
| B | `application/discovery/value_candidate_selection.py`；`select_current_value_candidates/select_value_candidates` | 同A；1b06d770adae49ab |
| C | `m2_discovery_engine.py`；`M2ScreeningPolicy` | `m2-multi-channel-cheap-screen-v2`；78b61b87d944b476 |
| D | `financial_quality.py`；`evaluate_financial_quality` | `financial-quality-general-v1`；00591b72f7f45250 |
| E | `domain/research/research_gate.py`；`evaluate_with_human_approval` | G0–G3；84e867ce1449aa43 |
| F | `domain/research/research_profile.py`；`PROFILES` | 画像合同；f458b7cad0986f43 |
| G | `valuation_router.py`；`ValuationRouter.route` | 显式注册路由；23f187da65268070 |
| H | `valuation_models/residual_income.py`；`scenario_value` | `residual-income-equity-shared-dated-v2`；090bb42f00300662 |
| I | `valuation_models/fcff.py`；`FCFFValuationModel.value` | `fcff-shared-scenario-v1`；3431070158fab7d9 |
| J | `valuation_models/cyclical.py`；`CyclicalNormalizedValuationModel.value` | `cyclical-normalized-equity-v1`；d3da6417465b608c |
| K | `m1_reverse_valuation.py`；`reverse_for_descriptor` | 有界反向诊断；52d78768072528fd |
| L | `price_bridge.py`；`bridge_with_quote` | `c0-v1`；43843b6bfa169dcd |
| M | `price_attractiveness.py`；`assess_price_attractiveness` | 画像价格分层；3b42df6367dca7f3 |
| N | `domain/decision/value_action_plan.py`；`build_value_action_plan` | `value-action-plan-projection-v3`；10e3a3a90edc16bc |
| O | `application/decision/current_value_plan.py`；`load_current_value_action_plans/revalidate_current_value_plan` | N的读时重验；e99b7818ed2b6794 |
| P | `domain/decision/recommendation_rules.py`；`evaluate_recommendation_action` | `recommendation-rules-v1`；c7c94fa302048a8b |
| Q | `domain/decision/decision_recommendation.py`；`DecisionRecommendation` | v3合同；b773d6885aa131ce |
| R | `investment_decision.py`；`EntryThesisSnapshot/InvestmentConsistencyReview` | 买卖一致性合同；e36749583c0363a4 |
| S | `application/portfolio/personal_entry_thesis.py`；`owned_entry_context` | `personal-entry-thesis-binding-contract-v1`；2f720ae0143f4edb |
| T | `application/portfolio/held_continuity.py`；`evaluate_owned_held_advisory/owned_held_action` | 已有持仓复核；0c569f91ae84d658 |
| U | `domain/portfolio/dual_sleeve_risk.py`；`review_dual_sleeve_risk/_core_review` | 双策略共享风控；3ddff2c93321ea6c |
| V | `domain/portfolio/private_policy.py`；`normalize_policy/validate_policy_confirmation` | 显式IPS；a4d7874a57a46d51 |
| W | `application/portfolio/private_risk_preview.py`；`_current_value_plan/preview_private_core_risk` | 当前计划→个人复核；253075a7dcb8f885 |
| X | `model_validity.py`；`evaluate_model_validity` | 事件/有效性合同；c3946a61a41c5e16 |
| Y | `application/decision/build_advisory_decision_recommendation_v3.py`；`derive_recommendation_rule_inputs` | 证据→v3动作；1d51a2d22fa94e51 |
| Z | `position_guidance.py`；`PositionTierPolicy/build_position_guidance` | `m4-position-guidance-v1`；20e21af8e7ad931a |
| AA | `domain/valuation/reverse_valuation.py`；`solve_bounded_monotonic` | 通用有界求解；4d8620faf3b7c3ee |

**可视流程合同：**官方Universe＋来源绑定观察 → C四通道线索 → A/B研究排队 → E研究门 → F/G适用模型→H/I/J三情景 → K反向预期解释 → L/M价格判断 → N/O/P/Q价值动作复核 → R/S/T原始买入逻辑对照 → U/V/W共享资金/股数复核 → 人工决定与人工成交记录。注意：这是逻辑依赖图，不代表已自动完成每一关；反向诊断是独立解释工具，并非当前所有动作的强制串行审批门。

**确定输入：**证券/画像/财务范围、报告期、原件URL/Hash/页码、`available_at`、抓取时点、解析/公式版本；金额统一CNY、股数为股、每股值及价格为CNY/股。观察指标`percent`中10表示10%，模型Ke/g/留存用小数0.10表示10%，不能混用。现金与完整有息债同单位、CFO/净利同期间和范围；TTM=上年全年＋本年累计－上年同期。`known-at`不得用报告期末或文件修改时间冒充；后来取得的公开原件不证明历史PIT。Quotes另记交易会话/可得时点/双源状态，估值日不必等于报价日。

## 2. 阈值、排序、动作与适用边界

| 环节 | 已实现数值与来源；性质 |
|---|---|
| A观察条件 | 最近同一年度：加权ROE≥10%、毛利率≥15%、营收同比≥0、归母净利同比≥0；只选年度，5月起至少前一年、此前至少前两年。缺值/冲突/过期不填零。继承D最低正分带，**研究假说，不是行业标准/交易门槛**。 |
| A排队 | 无金融专用标记、ST风险、价格冲突、观察冲突/过期，且至少一项有利或一个M2通道线索；按可排队、有利项降序、不利项/缺值升序、通道数降序、代码升序。不是财务总分，更不是收益排序；缺部分字段仍可成为待研究线索。 |
| C四通道 | Quality分≥60、覆盖≥0.5；Dividend参考收益率≥2.5%、市值≥20亿元；Value正PE≤15、市值≥20亿元、PB/PE代理≥3%；Cyclical已标周期行业、正PE及市值≥20亿元，正常化仍待研究。每通道最多50；Quality按分、Dividend按收益率/DPS、Value/Cyclical按盈利收益率排研究优先。全部是继承政策假说。 |
| D完整质量评分 | 盈利35/现金25/负债20/成长20分：ROE≥15/10→15/10分；毛利≥25/15→10/5；净利率≥10/5→10/5；CFO/净利百分比≥100/80→15/8；现金≥完整有息债→10；负债率≤40/60→20/10；营收、净利同比各≥5/0→10/5。未达最低带为0分，**缺证不是0分**。9字段需同年且通过实际验证，不能仅凭C的0.5覆盖就绕过。非跨行业通用真理。 |
| C数据门 | 双源价格差容忍0.02、报价至少5000、官方Universe匹配≥98%，是继承覆盖/一致性参数，不证明价格真实或投资有效。须保留原始报告与消费receipt，不读取未绑定“最新目录”。 |
| E研究门 | G0实际证据verified；G1财务范围批准；G2 thesis/return_driver/mispricing、各至少3条有证据的支持/反证/breaker、下一事件；G3精确估值及依赖版本的有效人工批准。条数是工程完整性约束，非论点真实性证明。 |
| L/M价格 | 有效模型、事件扫描覆盖报价日、verified_close才能READY；安全边际=(情景价值−价格)/情景价值。质量复利路径当前要求非LOW且价格不高于bear，才可能“研究吸引”；制造/周期默认仅重点观察、其价格规则未登记。该保守规则是项目政策，不是学术公认买点。 |
| N动作价 | 只用明确登记且适用的`scenario × value_fraction`；entry/add为≤，reduce/exit为≥。比例、理由、有效期、画像/模型/币种/股本基础必须随政策Hash绑定；缺政策无动作价。**没有全局默认30%安全边际**；显示估值区间不等于已登记操作区间。 |
| P/Q持仓动作 | 新买需完整积极门；加仓还需原Entry、一致性与新增证据，v3实际派生要求FULFILLED及对应理由/证据。持有需有效事件/模型及持有逻辑；减仓WEAKENED＋原理由/反证；退出BROKEN＋退出理由。单纯涨跌不触发。T另有浓度风险减仓复核，不能伪称thesis已破坏。LOW禁止积极BUY/ADD候选；仍可展示研究或合法风险降低提醒。 |
| U/V/W仓位 | 金额/集中度/现金底线/分策略预算/同股行业因子暴露/单次金额等来自**用户有效确认IPS**，非估值公式默认值；费用/滑点由确认成本假设，交易单位/停牌涨跌停由验证市场规则。资本额度取共享现金、预留底线、策略/同股/行业/因子/周期限额及单次预算的最小剩余额；含费用按整交易单位向下求股数。无权限或不足一手不制造仓位。CORE无机械价格止损强制，按基本面/流动性复核；跨策略不能重复花同一现金。 |

**跨行业：**G显式注册质量复利RI、成熟制造FCFF（允许经授权RI替代）、周期正常化权益；不能所有公司默认DCF/FCFF。银行/保险/券商标记专用研究，缺注册模型即不支持；一般制造CFO/毛利门槛不得套金融企业。高股息需正常化分配、资本约束和母公司上划研究，不能直接买入或分配仓位。

**兼容路径不混权：**Z的LOW→starter只表示在其他准入通过后的已确认上限，不绕过Q的积极动作限制；starter/normal/max数值必须显式确认、递增，缺政策不是默认仓位。R旧M3的人工减仓/退出意图与P/Y的证据驱动v3推荐是不同入口，不把手工意图当作自动策略证据。X过期/重大变化只阻断受影响的价格或积极动作；已有估值不因行情缺失被清空，旧thesis风险也不能因等待报价而静默消失。

**模型/反向边界：**H/I/J的熊/基/牛、资本回报/再投资/派息/终值为有证据理由的假设，未来不确定不等于禁止条件估值。终值g需低于相应折现率，现金不得重复加回。K冻结其余输入，在情景端点内反解terminal ROE/ROIC；继承Ke范围6.82%–9.18%、WACC7.32%–9.68%只是M1包络，不是全市场标准，也不能原封套CC1；新候选须重验适用边界，区间外报告无有界解，不追价扩区间。`domain/valuation/reverse_valuation.py:solve_bounded_monotonic`另有100步、金额误差1e-6的数值容差，不是投资阈值。

## 3. 当前证据、固定验证方案与用户确认

**已核查而非实盘证明：**以上调用/拒绝逻辑与基线内容一致；存在对应`test_value_candidate_selection/test_research_gate/test_valuation_router/test_m1_reverse_valuation/test_price_bridge/test_value_action_plan/test_personal_entry_thesis/test_held_continuity/test_dual_sleeve_risk`。本次不跑大回归，不声称该提交CI新验收。历史全损益/资本现金桥独立算术已通过；CC1导出RI可重放且仅获`ACCEPT_FOR_CONDITIONAL_PRIMARY_REVIEW`，LOW仍不解锁积极动作。CC1脚本Hash=`12c640c4cac89a976f29828234d15f03db0590386e5011513e93ae6337cd42b0`，是未登记研究产物，**不是本策略正式参数**。

**未证明/失败：**provider观察不是正式财务准入，当前排序不证明选股超额收益；历史采集日期不证明PIT、全市场覆盖也不证明无退市偏差；反向有解不证明市场错误。CC1约77%终值及约29.1%终端边际回报是强假设；80%现金转换原派息路径第4年负、第5年−174.63亿元，`FAILED_CASH_FEASIBILITY`必须保留，不能用重复现金缓冲修复。正式经济、模型/事件/价格/策略及用户授权仍分别验收，不能把研究员或agent复核当作用户批准。

**固定验证包（先冻结，后跑，禁止按收益调参）：**
1. 固定此提交、参数/规则Hash、Universe及原件available_at；固定20家跨画像分层样本及观察/缺证/拒绝代表，名单与截止日先登记，不只选入选或存活公司。核初筛→研究资料→适用模型→反向包络→桥→解释→模拟仓位，报告每关覆盖/拒绝原因，0入选合法。
2. 对ROE/毛利等阈值预设边界值、正负基数、缺失/重复冲突/未来发布、金融不适用、重大事件/过期报价/模型变更/LOW、未批准政策逐项对抗；核Entry新增证据、原论点破坏、同股双策略现金和T+1/可卖数量。测试只证明合同行为。
3. 先做固定时点重放，严格按当时可得资料；缺历史原件者标PIT未证，不以今日补采替代。若评估策略经济有效性，另冻结持有/再平衡/卖出/成本/基准及时间切分，以完整上市退市样本做独立样本外/前瞻观察；同时报告收益、回撤、换手、不可成交、集中度及基准差。未完成前不宣传选股有效；不以历史最高收益选参数。

**用户版本确认清单：**确认本策略是“研究排序＋有理由的人工复核”，逐项接受/修改上述假说；确认适用画像与排除范围；确认经济候选与价格政策是两次独立决定；确认LOW不生成积极BUY/ADD、等待与现金合法；在本地单独确认真实IPS/费用/账户，模拟不得转实盘；最终确认精确版本Hash和验证证据。修改规则需新版本、反证/敏感性重验，agent不可代签，始终`no_order`。

**依据及限制：**[Damodaran增长与增量回报](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/growth.htm)支持增长/再投资联动及平均与边际回报区分，不支持本项目ROE/CFO分档；[茅台2024–2026分红公告](https://www.moutai.com.cn/mtgf/attachDir/2024/08/2024080910064576661.pdf)仅有限期已报告归母利润分红政策，不是长期现金保证。复用`docs/current/open-source-code-borrowing-review-20261009.md`固定审查：TradingAgents `1394a3f`、ai-hedge-fund `78b779c`、FinRobot `2717499`仅参考证据/风控分层，不继承收益或策略批准；本次未重新克隆。方法论依据`docs/research-methodology.md`（Git SHA-256前16：8754ffc4564b6109）、证据政策（d7c7b0cefd34b6aa）；代码借鉴审查（b7a07c0f643eba69）。


## 4. 2026-10-24 集成进展（不改变上述规则版本）

上述固定源码索引仍指 de66fdd5 的历史规则字节，不把后续传输或展示修复冒充规则验证。主集成树已经接入 CC1 联合经营、资本、分配条件路径及三情景年度账；候选 SHA-256 为 5ab18cbc1fab4aca44a65e2ad0dd7b0e9279ab4969bd880d7d42522ec7703af2。600887 的精确输入回放保持原模型基准与研究时点，另记实际回放时点；其压力情景仍不是中性主估值。当前公开资料整理、算术、独立条件研究复核与正式 G3/用户版本确认分别验收。

600519 联合条件模型、600887 压力候选及 000333 MJ1 条件研究均不构成本策略已验证有效。MJ1 尚有普通股收益权、可转债与终端现金持续期问题，未登记为当前 primary。程序构建、完整 Core、8001 发布状态只以唯一执行台账和运行版本核验为准，不由本规格倒推。新增窗口/日期适配修复不放宽模型、事件重要性、报价、组合或人工门。ENGINEERING、RESEARCH、STRATEGY_VALIDATION、USER_APPROVAL、ACTUAL_ACCOUNT_ADMISSION 必须分开报告。

正式辅助策略仍未启用；本文件只将原有规则与待确认事项归档成可审查合同。任何版本确认都不能替代其缺失的独立经济有效性证据。所有输出 action=no_order。
