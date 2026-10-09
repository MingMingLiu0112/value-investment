# 价值投资建议与情绪卫星仓：新会话 Goal Prompt

本文件是可以直接粘贴到新会话的启动 Prompt。它不是新的 Roadmap，也不能覆盖
`LONG-TERM-GOAL.md`、`AGENTS.md`、`docs/current-stage-goal.md`、
`docs/current/advisory-sentiment-satellite-goal-v1.md` 或任何不可变 receipt。

## 0. 启动时先做基线核对

1. 先执行 `git fetch origin`，记录 `origin/main` 和当前 `HEAD`，不要假定 Git
   提交记录等于真实完成度。
2. 检查工作树。若存在未提交修改，先分类为当前 Goal 工作、用户修改、历史工作
   或无关变化；不得 reset、checkout、批量暂存或覆盖未确认的用户工作。
3. 依次读取：
   - `AGENTS.md`
   - `LONG-TERM-GOAL.md`
   - `docs/current-stage-goal.md`
   - `docs/current/advisory-sentiment-satellite-goal-v1.md`
   - 当前阶段的 handoff、receipt、manifest 和 current pointer
4. 以实际代码、测试、数据库/runtime 产物和可复现 receipt 为事实源；文档只能
   说明意图，不能证明能力已经实现。代码与文档冲突时，明确报告冲突并修正最小
   必要范围。
5. 恢复当前 Goal 的唯一阶段状态，然后只选择一个有产品价值的端到端工作包。

## 1. 总目标

Goal ID：

```text
VALUE-INVESTMENT-ADVISORY-AND-SENTIMENT-SATELLITE
```

最终产品是一个可审计、可持续运行的 A 股个人投资辅助系统。它必须逐步做到：

1. 自动维护 A 股研究池和市场漏斗；
2. 对每个准入候选建立可追溯的 `ResearchCase`；
3. 按公司经济结构选择适用估值模型，而不是所有公司默认 FCFF；
4. 输出 `BUY_CANDIDATE`、`ADD_CANDIDATE`、`HOLD`、`TRIM_CANDIDATE`、
   `SELL_CANDIDATE`、`NO_ACTION` 六类研究建议及理由、反证和失效条件；
5. 在用户提供真实 IPS/组合/现金/风险约束后，给出目标仓位区间、单股上限、
   分批规则、现金底线、风险预算和再平衡建议；
6. 持续跟踪财报、公告、估值、重大事件、论点破坏和模型有效性；
7. 研究一个独立的“价值 + 情绪”波段卫星 sleeve；
8. 通过样本外验证、Shadow、费用/滑点/流动性建模和用户验收后，才进入有界
   辅助使用。

系统输出永远是研究建议，不是订单，不得连接自动下单。永久语义边界：

```text
action = no_order
Recommendation != Order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Margin of Safety != Position Size
Current Price != Intrinsic Value
Historical Return != Future Return
Backtest != Shadow
Good Backtest != Buy Signal
```

## 2. 当前实现快照（每轮必须重新核准）

不要把下面内容当成新的永久事实；它只是启动指针：

```text
AUTHORITATIVE_STAGE = D2_CANONICAL_COMPANY_DECISION_SLICE
D0 = COMPLETE
D1 = INTERFACE_ONLY_NOT_EXPANDED
D2 = IN_PROGRESS
D3_RECOMMENDATION_V3 = EXPLICIT_OPT_IN_ENGINEERING_READY / DEFAULT_STILL_V2 / NOT_PRODUCT_ACCEPTED
D4 = NOT_STARTED
D5 = INTERFACE_FROZEN_NOT_IMPLEMENTED
D6 = NOT_STARTED
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

当前权威目标仍要求先收口 D2：用一家公司完成真实证据、当前有效报价、
事件覆盖、`ModelValidity`、`PriceBridge` 和 `DecisionRecommendation` 的完整
纵向链。D2 未通过前，D3 只能作为未提交的前置契约开发，不能宣称已经进入
正式阶段或已经能给用户输出买卖建议。

D3 v3 建议合同、纯规则求值、生产主路径显式 opt-in、六个 action 的产品展示、
无报价风险动作和私人组合缺失时的 blocked 状态已通过工程实现与自动化测试，
并使用真实 600519 包完成一次数据绑定的 v3 replay（结果为 NO_ACTION /
BLOCKED_PRIVATE_INPUT / position_guidance=null）。默认路径仍是 v2；v3 目前是
`CODE_IMPLEMENTED + AUTOMATED_TEST_PASSED + REAL_DATA_BOUND_REPLAY`，不是
`PRODUCT_ACCEPTED`。仍未取得真实私人 IPS/组合，因此不得输出买多少/卖多少。

## 3. 产品语义和卖点

### 3.1 “买什么”和“卖什么”

系统必须把研究结论和交易动作分开表达：

- `BUY_CANDIDATE`：研究条件满足，进入人工买入复核，不是自动买单。
- `ADD_CANDIDATE`：已持仓且论点仍成立，可进入人工加仓复核。
- `HOLD`：继续跟踪，不改变当前研究结论。
- `TRIM_CANDIDATE`：论点弱化或风险升高，进入人工减仓复核。
- `SELL_CANDIDATE`：论点破坏或退出条件触发，进入人工卖出复核。
- `NO_ACTION`：证据不足、数据未准入、模型失效或风险门未通过。

每个 action 必须带有：证据引用、模型/行情有效期、反证、论点破坏条件、
下一次复核触发条件、缺失项和人类复核要求。不得只返回一个标签。

### 3.2 “买多少”和“卖多少”

个性化仓位是 D3 的一部分，但必须先取得用户真实私人输入：

```text
真实 IPS
当前持仓
现金
总资产和可投资资产
风险承受与最大回撤容忍
投资期限
税务/流动性/行业限制
是否允许杠杆、衍生品和做空
```

在真实输入缺失时，生产输出必须保持：

```text
portfolio_input_status = BLOCKED_PRIVATE_INPUT
position_guidance = null
```

可以为了工程测试使用明确标注的 synthetic fixture，但不能把合成组合、示例仓位
或回溯结果冒充用户个人建议。

当 D3 的仓位合同、输入校验和合成测试已经完成、只缺真实私人数据时，Root 应
一次性输出 `Private Portfolio Input v1` 模板并暂停个性化仓位分支，不要在每轮
开发中零散询问。模板至少包含：

```text
total_investable_assets
current_cash
current_positions_and_cost_basis
instrument_type_and_account_constraints
target_return_and_horizon
maximum_portfolio_drawdown
maximum_single_stock_weight
maximum_sector_weight
liquidity_and_tax_constraints
allowed/forbidden instruments
rebalance_frequency
```

真实输入必须保存在 Git 之外的受保护位置，不能写入仓库、日志或公开 artifact。
输入通过隐私/完整性校验后，系统才允许生成个人化 `PortfolioGuidance`。

拿到真实输入后，仓位计算必须是确定性的、可解释的，并至少同时考虑：

- 组合风险预算和最大回撤容忍；
- 单股、行业、市场暴露和跨 sleeve 集中度；
- 流动性容量、涨跌停、停牌、成交额和滑点；
- 估值安全边际、模型 confidence、thesis 强度和反证；
- 分批建仓/退出、现金底线、税费和交易成本；
- 组合已有持仓与相关性，而不是孤立判断单只股票。

安全边际不得直接等同于仓位；系统必须分别计算估值判断和组合风险预算。

### 3.3 用户可见输出合同

系统最终必须在一个用户可读页面或 Excel 工作台中，对每只进入研究池的公司直接
回答：

```text
买什么 / 卖什么
为什么买或卖
买入或卖出的研究区间
在真实私人组合输入后，建议买多少或卖多少
建议分几批、在什么条件下执行人工复核
什么事件或估值变化会触发表述复核
什么条件会推翻论点、必须停止继续持有或加仓
当前证据、报价、模型有效性和数据缺失分别处于什么状态
```

“直接告诉”指系统给出明确、可读、可追溯的辅助建议，不是自动下单。只有当
真实私人 IPS/组合输入通过校验后，才允许生成个性化数量和仓位区间；在此之前，
买卖候选可以研究展示，但数量字段必须明确为
`BLOCKED_PRIVATE_INPUT`，不能给出伪装成个人建议的示例仓位。

## 4. 分阶段执行顺序

### D2：先完成真实公司纵向闭环（当前权威优先）

1. 以真实官方证据、`FinancialFacts`、ResearchGate、公司适用估值、
   `ModelValidity`、当前有效 `PriceBridge` 和 `DecisionRecommendation` 为
   同一家公司的完整验收对象。
2. `NO_ACTION` 是合法验收结果；不得为了出现 BUY 调整参数、放宽 PIT 或伪造
   行情/规则/人工复核。
3. 最新真实候选必须明确 `current_price_bridge`、`strict_pit`、事件覆盖、
   模型有效性和用户验收各自的状态，不能把工程通过当成投资准入。
4. D2 通过后再进入 D3；不要等待自然时间或重新搜集已经冻结的证据来拖延
   可独立完成的工程。

### D3：买卖与仓位建议（紧随 D2）

当前代码基线若仍与本 Prompt 一致，最高优先工作包是
`WIRE-D3-V3-PRODUCTION-OPT-IN`：先让 v3 建议协议能在显式 opt-in 下由正式研究
主路径生成，默认 v2/v1 payload 与 descriptor Hash 保持字节级不变，再用同一
真实研究结果贯通报告层、Excel read model 和用户入口。不要为了等待 D2 的
自然时间或外部证据数据，停止可独立完成的 D3 工程；但 D3 工程通过不得自动
升级为真实投资建议或生产验收。

1. 收口 `advisory-decision-recommendation-v3` 的 domain contract 和纯规则。
2. 打通 `research_application.py` 的生产主路径：只有显式 opt-in 才生成 v3
   artifact；默认 v1/v2 payload 和 Hash 不得漂移；entry thesis 存在本身不得
   隐式升级 schema。
3. 打通 `research_input.py`、`m1_valuation_package_builder.py` 和现有 report
   adapter，字段为空时不得改变旧 descriptor hash。
4. 打通 `decision_surface.py`、`existing_research_report.py`、Excel read model
   和当前用户入口，让六个 action、无报价风险动作、缺失原因和人类复核边界可见。
5. 实现私人组合 intake、仓位约束合同和 model-based envelope；真实个人建议
   仍等待私人输入。
6. 增加合同、反例、PIT、无报价、状态升级、Hash 和产品级回归测试。
7. 在动作选择前校验 entry/review 的证券身份、`entry_id` 绑定、
   entry 类型和 `available_at`/decision time；跨证券、模拟或重构 entry、
   未来日期必须 fail closed，不能只在 replay 层事后校验。
8. 将 ADD/TRIM/SELL 绑定到该动作实际引用的证据；不能用一个布尔标志、
   一段无证据文本或一条无关 comparison 证据满足证据门。
9. 修复无报价 HOLD/TRIM/SELL 从 `decision_surface` 到
   `existing_research_report`/Excel 的完整消费链，禁止报告层无条件读取
   `price_attractiveness`。

### D4：持续价值投资跟踪

实现 `ThesisMonitor`、事件及重大性跟踪、依赖失效、bounded recalculation 和
恢复/去重。每条事件必须有来源、发布时间、available-at 时间、source hash 和
版本；禁止未来数据泄漏。持续跟踪不是不断扫描全部信息，而是在可改变论点、
估值、模型适用性或风险结论的触发条件下复核。

### D5：价值 + 情绪卫星仓

卫星仓必须独立预算、独立台账、独立退出规则，且先通过 value gate。真实 D5
建议出现前必须完成：

- point-in-time 情绪特征和可复现数据源；
- 预注册规则、walk-forward 和 untouched out-of-sample；
- 费用、印花税、滑点、换手、流动性和容量模型；
- 涨跌停、停牌、拒单和不可成交建模；
- Sharpe、最大回撤、恢复时间、命中率、盈亏比和失效区间；
- 独立 replay、Shadow 和真实自然时间观察；
- 用户单独授权的 tactical budget。

在这些条件满足前，合法结果只能是 `NO_TRADE`、`NOT_PROVEN`、
`INSUFFICIENT_EVIDENCE` 或 `SHADOW_REQUIRED`。情绪信号不得修改内在价值，
只能影响时机、优先级和研究复核。

### D6：Shadow 与产品交付

建立产品 read model、Excel/未来 Web 展示、Shadow 证据、用户试用和验收。
生产授权、数据库 migration、scheduler、通知、真实账户导入和最终投资决定都是
独立用户门。

## 5. 每轮执行合同

1. 每轮从真实基线和现有工作树开始，不重复建设已经满足的依赖。
2. 每轮只选择一个端到端工作包，先写清输入、缺失能力、输出、验收和停止条件。
3. `Engineering`、`Research Admission`、`Production`、`User Acceptance`
   分开记录，不能互相替代。
4. 外部数据缺失只阻止依赖该数据的投资结论，不阻止独立工程继续。
5. 遇到缺口必须分类：`CODE_GAP`、`EVIDENCE_GAP`、
   `PRIVATE_INPUT_GAP`、`NATURAL_TIME_WAIT`、`AUTHORIZATION_GAP`。
6. 不伪造行情、财报、公告、规则版本、人工复核或回测结果。
7. 不通过调参数制造 BUY，不让历史收益替代样本外验证。
8. 完成后运行相关测试、集成测试、Core Gate；代码实质变化时验证 CI。
9. 每轮结束报告实际产品增量、可执行命令、产物路径、测试范围、未通过结论和
   下一工作包。

## 6. SubAgent 协作规则

Root 是唯一 Goal 状态持有者、核心合同作者、最终集成者和提交者。最多并行
2 到 3 个有界 SubAgent。只在任务互相独立、文件写入不重叠时并行。

Root 必须亲自完成：

1. 核心 domain contract 和跨模块 schema 的最终决定；
2. 跨 D3/D4/D5 的依赖与冲突处理；
3. 最终代码集成、全量回归和 Core Gate；
4. commit、push、current pointer 和正式状态更新；
5. 用户门、Checkpoint 和验收解释。

推荐 SubAgent 角色：

| 角色 | 可以做 | 不可以做 |
| --- | --- | --- |
| Repository / Dependency Agent | 只读扫描模块、合同、调用链、测试、artifact，输出依赖图和冲突点 | 擅自改核心设计 |
| Screening & Data Agent | 实现 universe、ResearchProfile、数据适配器 | 修改估值/决策阈值 |
| Valuation & Decision Agent | 实现模型路由、估值和决策合同 | 修改组合风险政策 |
| Portfolio & Risk Agent | 实现仓位区间、风险预算、集中度、流动性约束 | 读取或编造真实私人数据 |
| Sentiment & Backtest Agent | 实现 PIT 特征、walk-forward、OOS、成本和容量测试 | 修改核心价值模型 |
| Adversarial Reviewer | 寻找未来数据、状态误升级、Hash/PIT/门槛绕过和过拟合反例 | 批准发布或放宽门槛 |
| Test Engineer | 在 Root 固定 contract 后补边界、反例、恢复和回归测试 | 修改投资准入标准 |

每个 SubAgent 必须返回：

```text
task_id
scope
files inspected / files changed
evidence with file:line
tests or commands run
remaining uncertainty
recommended next action
```

同一核心文件同一时间只能有一个写入者。SubAgent 不得自行创建新 Goal、新
Milestone 或平行分支；Root 负责挑选、集成和删除无效工作。

建议每轮调度：

1. 先并行启动 2 到 3 个只读审计 Agent，分别审查 D3、D4 和长期风险。
2. Root 冻结合同后，再给两个写 Agent 分配互不重叠的文件集。
3. 写完后由独立 Adversarial Reviewer 和 Test Engineer 复核。
4. Root 做最终集成、全量测试、状态记录和 commit。

## 7. 用户门：只在这些情况下停止

只有以下事项需要用户输入或授权：

1. 真实私人 IPS、持仓、现金、风险偏好和税务/流动性限制；
2. 生产数据库 migration、scheduler、通知、真实账户或密钥；
3. 需要真实自然时间形成的 Shadow 观察；
4. 不可逆操作、生产停机、删除不可恢复资产；
5. 最终生产授权和最终投资决定。

除此之外，工程实现、测试、合同设计、只读审计、模拟数据、文档和可回滚修复
均自行推进，不因缺少外部数据而停止整个 Goal。

## 8. 完成定义

总 Goal 完成的唯一标准是：

```text
市场覆盖
-> 逐层筛选
-> 可追溯 ResearchCase
-> 公司类型适用的估值模型
-> 六类 DecisionRecommendation
-> 私人组合输入后的仓位/风险预算
-> 持续跟踪和论点失效重算
-> 独立价值+情绪卫星仓验证
-> Shadow 和用户验收
-> Excel 或未来 Web 只呈现少量真正值得研究的标的
```

任何阶段都不能因为文件已生成、测试通过或 Excel 能打开，就声称投资就绪。
完成报告必须明确区分：

```text
CODE_IMPLEMENTED
AUTOMATED_TEST_PASSED
REAL_DATA_ADMITTED
PRODUCTION_VERIFIED
USER_ACCEPTED
```

永久保持：

```text
Human makes the final investment decision.
action = no_order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Margin of Safety != Position Size
```
