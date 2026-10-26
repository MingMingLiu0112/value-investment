# 2026-10-09 开源项目代码借鉴审查

## 2026-10-25 数据源专项复核

本节是源码/接口文档审查，不表示新源已完成本机请求、质量验证或正式准入。
既有AKShare依赖与官方原件链继续复用；不安装整套替代平台。

| 对象与固定版本 | 实际核对的接口 | 本项目采用边界 |
| --- | --- | --- |
| [AKShare 2ea08ff44512a9b0c008cd4ff77463b940959c7e](https://github.com/akfamily/akshare/tree/2ea08ff44512a9b0c008cd4ff77463b940959c7e)，MIT | stock/stock_info.py::stock_info_bj_name_code；stock_fundamental/stock_finance_sina.py::stock_financial_report_sina；stock_feature/stock_hist_em.py::stock_zh_a_hist_min_em | 优先借鉴现有适配器缺项。北交所仍请求nqxxController/nqxxCnzq.do，不是当前307问题的独立备源。三表字段需本项目单位/来源/归属核验 |
| [efinance c8fd370a3109b2d14a121e3a32a86e9c8354b01b](https://github.com/Micro-sheep/efinance/tree/c8fd370a3109b2d14a121e3a32a86e9c8354b01b)，仓库MIT | stock/getter.py::get_quote_history和common/getter.py::get_quote_history_single | 支持15/60等周期参数；与AKShare部分行情同用push2his.eastmoney.com，不能计独立双源。默认fqt=1前复权，执行研究必须显式核对口径，不直接引入整库 |
| [BaoStock官方发行0.9.4](https://pypi.org/project/baostock/0.9.4/)，包元数据BSD | query_history_k_data_plus、query_trade_dates、query_all_stock为小样本验证候选；官方网页本次无法完整提取 | 包源发行Hash为54dd26ec53100da02dcd47a21fc487ed5b2e12a4124af7961143d8ca0bc682e9。先核对包源码/许可证及真实缺失区间返回，不预先承诺历史PIT或盘中交易状态完整 |
| [zxygithub/baostock 98cb65162c2c7dba63d80292f40759a617630b4e](https://github.com/zxygithub/baostock/tree/98cb65162c2c7dba63d80292f40759a617630b4e)，仓库MIT | README及docs/pythonAPI.md | 这是第三方数据下载器，不是官方SDK；文档展示5/15/30/60分钟查询。仅作候选线索，不采用其SQLite/定时/网盘备份系统；仓库许可不能代替SDK与数据服务许可 |

核对要点：实际日期/时区、已完成K线、量额单位、不复权/复权因子、停牌/特殊状态、
源级独立性、known-at与真实采集时间。金融摘要和分钟历史能提高覆盖，不能证明
正常化利润、可分配现金、当时候选全集、预先冻结策略、OOS或自然时间Shadow。
同源换库失败不再重复搜索；有明确新接口/字段证据才重开。下一步只为既有D/H工作包
做有界真实请求，采用或拒绝及原因写回现有台账，不新建Provider治理平台。

以下保留2026-10-09多Agent框架审查，当前不派发相关平台扩展任务。

审查方式：`--depth 1` 克隆到 `.tmp/oss/`，读源码而非读 README 结论。
所有结论只作为**候选借鉴**，不改变任何现有合同、阈值或准入标准。

| 项目 | 审查版本 | 性质 |
| --- | --- | --- |
| TradingAgents | `1394a3f` (v0.6.0) | 多智能体交易图、PIT 数据窗口 |
| ai-hedge-fund | `78b779c` (v2.5.0) | 信号/组合/风控/回测/纸交易分层 |
| FinRobot | `2717499` | 券商研报式多智能体 + 估值引擎 |
| OpenBB | `ae02687` | Provider 注册表与多消费面数据平台 |
| langgraph | `bfcfea5` | 持久化执行、checkpoint、HITL interrupt |
| deepagents | `efd88ff` | 子智能体隔离上下文、文件系统后端抽象 |

## 1. TradingAgents

**值得借鉴（可落到我们代码）**

1. PIT 日期窗口合同
   `tradingagents/dataflows/date_window.py:23` `in_window()`：时间戳统一 UTC，窗口取半开区间
   `[start, end + 1天)`；**无日期条目只在窗口延伸到当下时保留**，理由是"回测无法证明它
   不是来自未来"。`:78` `as_of()` 把工具请求日期钳制为不超过运行日，`:91`
   `as_of_window()` 钳制窗口末端。
   落点：`src/value_investment_agent/infrastructure/evidence/`、`filings/`。我们已有
   `available_at` 与 PIT 准入，但**没有显式的 coverage_gap 语义**。
2. "抓不到"不等于"没有"
   `:44` `coverage_gap()`：数据源未覆盖的窗口记为**不可用**，而不是记为空值。
   这是对我们 fail-closed 原则的一个具体补强：区分 `数据为空` 与 `我们没看到`。
3. 历史回放时抑制实时快照
   `:108` `withhold_live_profile()`：历史运行不返回当下的公司画像，避免把今天的口径
   灌进过去。
4. 每分析师独立子图 + 工具轮次上限
   `tradingagents/graph/setup.py:45` `_analyst_graph()`：每个分析师有自己的消息历史，
   只回传最终报告（旁路分析员不会写同一个 state key）；`max_tool_rounds` 之后强制
   产出报告，文档说明"模型持续调工具也不会把图跑到递归上限"。
5. 运行签名与断点续跑
   `tradingagents/graph/checkpointer.py:28` `thread_id(ticker, date, signature)`：把会改变
   图结构的选择折进 checkpoint id，避免换了模型还复用旧断点；`trading_graph.py:46`
   `_NOT_IN_SIGNATURE` 把"只影响文件位置/重试次数"的配置排除出签名。
6. 日期规范化与安全化工具名
   `trading_graph.py:33` `_validate_trade_date()`：拒绝非规范格式与未来日期；
   `dataflows/symbols.py` 的 `safe_ticker_component()` 防止 ticker 逃出目录。

**明确不采纳**
- bull/bear 辩论 → research manager → trader → 风险辩论 → 组合经理这套**辩论式打分**。
  它的产物是交易决策，我们的产物是可追溯研究结论与门禁；引入辩论会把"说服力"变成
  证据强度，是方法倒退。
- 五位分析师平票合成最终评级：与我们 G0-G3 逐级门禁冲突。

## 2. ai-hedge-fund

**值得借鉴**

1. 信号与仓位严格分离
   `hedge_fund/signals/base.py:39`：AlphaModel 只输出 `conviction ∈ [-1, +1]`，并写明
   "只使用该日期或之前可获得的信息"；无法形成观点时置 `metadata["abstained"]=True`。
   `:22` 每个模型自带 `investment_approach` 权限元数据（是否允许做空），与观点本身
   独立记录。
2. 风控是不可协商的钳制，且钳掉的部分回现金
   `hedge_fund/risk/limits.py:1`：文件头即声明"硬上限，分析师不能覆盖"；
   `:8` **被钳掉的敞口不再分配给其他标的，留在现金**，理由是重新分配等于让风控层
   加仓，角色倒置。`:34` 每次钳制记一个 `ClampEvent`，可解释。
3. 两阶段流水线，天然无未来函数
   `hedge_fund/pipeline/stages.py:4`：`assess_fund` 只在"已完成的交易日"上形成目标权重，
   产出 `DecisionRecord`（无订单、无券商）；`:120` `execute_decision` 在**之后的**交易日
   用真实收盘价成交，产出 `CycleRecord`。
4. 组合层不把 conviction 当收益
   `hedge_fund/portfolio/construction.py:45`：明确写"相对仓位不等于把置信度校准成预期
   收益"；`:39` 弃权样本同时被排除在平均数与分母之外。
5. 用百分位而非绝对金额做规模归类
   `hedge_fund/features/breakpoints.py:1`：把市值放到**公布过的历史分位表**里得到
   "高于第 95 百分位"这类秩，而不是"3.2 万亿"，说明秩是平稳的且无生存者偏差；
   同时指出月末数据在当月不可知，所以只能用**严格早于当月**的已发布行。

**明确不采纳**
- 把 LLM 分析师观点直接 blend 成权重：适合对冲基金式多头/空头组合，不适合以内在
  价值为准绳的辅助系统。
- PEAD 等短周期 alpha 模型进入价值核心。若将来做情绪卫星，只能进独立 sleeve。

## 3. FinRobot

**值得借鉴**

1. 多方法并列的 football-field 表达
   `finrobot_equity/core/src/modules/valuation_engine.py:284` `generate_football_field_data()`
   把 EV/EBITDA、Peer、DCF 各自区间并列，并附 `current_price`；
   `:312` `synthesize_valuation()` 再做合成。
2. 敏感性作为显式结果对象
   `sensitivity_analyzer.py:22` `SensitivityResult` 记录 metric / base / low / high /
   range / impact%，而不是只留一段叙述。
3. 研究报告 Agent 与数字分离
   `equity_agents/agent_manager.py` 把 LLM 研报写成固定小节（overview / valuation /
   risks / takeaways），数字来自前置数据处理与估值引擎。

**明确不采纳**
- 以叙事合成价格作为主估值。我们的主估值必须来自可复算模型，叙事只能解释。
- 报告 Agent 自由调用数据源：会破坏证据绑定与 PIT。

## 4. OpenBB

**值得借鉴**
- Provider 作为扩展入口：`openbb_platform/core/openbb_core/provider/abstract/provider.py`
  用 `name / credentials / fetcher_dict` 描述一个数据提供者，凭据按
  `provider_field` 命名；`provider/registry.py` 统一注册。
- 一份数据向 Python / REST / Excel / MCP 多消费面输出——与我们"Domain → Read Model
  → Excel，未来 Web 复用同一 Read Model"方向一致，可作为将来 D1/D6 的参考。

**明确不采纳**
- 引入其完整平台依赖。我们只需要"适配器注册 + 一份 read model 多消费面"这条原则。

## 5. langgraph / deepagents

**值得借鉴**
- 持久化执行与断点续跑、HITL interrupt 语义（langgraph README 中的 durable execution /
  interrupts）。这与我们的研究运行、恢复、人工门天然对应。
- deepagents `libs/deepagents/deepagents/middleware/subagents.py`：子智能体以
  `task` 工具委派，父状态中显式排除不该被继承的键（`_FORK_EXCLUDED_STATE_KEYS`），
  并阻止递归委派。这正是我们"子智能体不得改同一核心文件、Root 独占集成"的机制化版本。
- `backends/protocol.py`：把"文件存哪里"抽象成后端，调用方不关心本地/沙箱/远程。

**明确不采纳**
- 直接引入 LangGraph 作为编排层。我们目前是确定性 DAG + 文件证据链，引入图框架会
  增加状态黑盒与依赖，而收益（断点续跑）可以先用现有 `run-once + receipt` 模式实现。

## 6. 结论：三个真正值得落地的借鉴点

结合我们已完成的 `ValuationResult` / `PriceBridge` / `ModelValidity` / G0-G3 分层，
上述六个项目里**没有**推翻我们架构的东西；有价值的是以下三处具体补强：

1. **Evidence coverage 语义**（来源：TradingAgents `date_window.py`）
   在证据层区分 `EMPTY`（已覆盖且无数据）与 `UNCOVERED`（来源未覆盖该窗口），
   并在快照/报告中显示为"不可用 + 原因"，而不是空值。落点：
   `src/value_investment_agent/infrastructure/evidence`、`filings`。
2. **两阶段评估/执行合同**（来源：ai-hedge-fund `pipeline/stages.py`）
   D3/D4 的仓位建议与后续任何模拟执行必须分开：评估在已完成交易日形成目标区间，
   执行只允许在之后的会话用真实价格，且执行结果与决策记录分开存证。落点：
   `application/portfolio`、未来的 D5 replay/Shadow。
3. **风控钳制记录与"钳掉即回现金"**（来源：ai-hedge-fund `risk/limits.py`）
   D3 一旦接入真实组合：单股/行业上限触发时必须记录 `clamp` 事件，且被削掉的敞口
   不重分配。落点：`application/portfolio` 的目标仓位求解。

**不适用**：辩论式多智能体、LLM 观点直接加权成仓位、叙事合成价格、以技术指标
回测拟合未来走势作为主决策依据。

**本轮未做任何代码、合同、阈值或准入变更**；`action = no_order`。

## 2026-10-25: adopted bounded paired-bootstrap statistics

This dated addendum supersedes the preceding no-change statement only for this
specific adoption. `arch==8.0.0` supplies `StationaryBootstrap` for paired daily
strategy-minus-cash and strategy-minus-fixed-pool excess-return diagnostics.
It is not a trading strategy, market-data provider or proof of profitability.

- Reviewed upstream tag: https://github.com/bashtage/arch/tree/v8.0.0
- Dependency metadata: https://raw.githubusercontent.com/bashtage/arch/v8.0.0/pyproject.toml
- License: NCSA, https://raw.githubusercontent.com/bashtage/arch/v8.0.0/LICENSE.md
- Python >=3.10; upstream requires numpy, pandas, scipy, statsmodels and packaging.
  The project adds only an optional `strategy-validation` extra and the Core CI
  installation/check; no server or global Python installation is changed.
- Reviewed Windows cp313 wheel SHA256:
  `bd73bd2d811bcf0551443b6e0a10bc25af002e9eb146aff164897c70aac35e85`.
  Actual local runtime versions are retained in the integrated replay receipt.
- Existing application/domain consumers use paired rows, frozen seed/block size,
  2000 resamples and marginal one-sided mean-daily-excess bounds. Bounds are not
  cumulative-return forecasts or joint confidence guarantees. Short dependent
  histories remain INSUFFICIENT; two reset portfolios cannot be stitched into a
  continuous validation window. These settings remain an unapproved research
  policy, not an industry-standard admission rule or personal IPS.
- Actual Root replay:
  `runtime/hotspot-shared-integrated/20261025T095011506832Z/receipt.json`.
  All six fold/cost cases remain INSUFFICIENT with negative excess lower bounds.
  Real retained market observations plus hypothetical execution do not prove
  strict historical PIT, prospective OOS or elapsed natural-time Shadow.

No data redistribution permission, strategy approval or order authorization is
inferred from the software license. `action=no_order`.
