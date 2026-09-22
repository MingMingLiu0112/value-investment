# 价值投资 Agent 架构纠偏与长期约束

生效日期：2026-09-21。来源：用户提供的
`A股价值投资Agent_当前架构纠偏与长期约束_Codex立即执行版_20260921.md`，经与当前目标、
外部数据政策和已发布 Excel 基线核对后合入。本文件是短期 P0 架构契约和长期边界；启动入口
仍为 `value-investment-goal-prompt.md`。

## P0 优先级与现状

P0 在恢复 B1/B2 业务研究前完成。保留三家公司研究卡、已归档证据和 Excel 发布成果；不把
“结构已展示”误写为严格研究内容已验收。P0 只修复价值、模型有效性、价格桥接和研究门禁的
职责边界，不新增行业模型、全市场筛选或大量公司专用脚本。

固定数据流：

```text
FinancialFacts -> ResearchCase -> ValuationModel -> ValuationResult
                                                  -> ModelValidity
ModelValidity + QuoteSnapshot ------------------> PriceBridgeResult
ValuationResult + PriceBridgeResult ------------> CurrentResearchStatus -> Excel
```

## P0 合同

1. `ValuationResult` 只表示在指定信息集和假设下的企业价值：情景价值、置信度、假设、敏感性、
   证据、阻断项、状态和模型版本。它不保存当前价格或安全边际。
2. `PriceBridgeResult` 只负责把已验证模型与 QuoteSnapshot 比较。无行情时返回
   `PENDING_EXTERNAL_DATA`，不得清空或降级既有估值结果；安全边际只在合法桥接时计算。
3. `ModelValidity` 判断模型在报价日期是否仍有效，而不是机械要求模型日期等于报价日期。新财报、
   重大资本结构变化、收购处置或影响价值的重要公告使模型 `STALE` 并触发重估。
4. `ResearchGate` 固定为 G0 证据、G1 财务、G2 Thesis、G3 估值。G2 必须检查论点、回报来源、
   错价假说、支持与反证、Thesis Breakers 和下一事件；空壳内容不能通过。价格桥接不属于 G3。
5. 所有实时里程碑拆成 Engineering Implementation、Snapshot Validation、Production Validation。
   外部数据只允许使最后一项 `PENDING_EXTERNAL_DATA`，不阻塞工程或下一家公司工程。

## P0 验收与依赖

- B1-E1 至 B1-E6（模型、情景、反向估值、Excel、价格桥接、快照验证）完成并通过后，允许开始
  B2 Engineering；B1-P1 Current Production Validation 可以独立等待真实数据。
- 未稳定的共享合同、会计口径或模型数学可以阻塞 B2；等待今日收盘、第三方行情或未来披露不能阻塞。
- `build_company_valuation_result.py` 必须显式选择模型或重命名为 FCFF 专用脚本；未知模型必须拒绝。
- P0 完成前不新增银行、保险、完整周期分析、市场情绪决策、全市场筛选或专用公司流水线。

## 2026-09-22 路由器实施状态

新增 `src/value_investment_agent/valuation_router.py`。`ValuationRouter` 只接收显式
`ResearchProfile`，不接受股票代码。当前注册 `fcff -> FCFFValuationModel / FinancialFacts`
、`cyclical_normalized -> CyclicalNormalizedValuationModel / CyclicalFacts`，以及
`residual_income_or_equity_value -> ResidualIncomeEquityValuationModel /
QualityCompounderFacts`。质量复利画像由此返回 `SUPPORTED`；交叉检查模型和未授权模型
仍返回 `MODEL_NOT_APPLICABLE` 或 `UNSUPPORTED`，不得静默替换主模型。

通用残留收益引擎位于 `valuation_models/residual_income.py`。茅台旧适配器不再保留一份
私有算术，而是从该引擎导入 `scenario_value`、`current_projection` 与 `current_value`；
通用模型只允许验证后的权益基数与 bear/base/bull 情景产生
`conditional_research_only`，不产生价格、安全边际、仓位或订单。

`build_moutai_valuation_result.py` 在读取任何模型或行情证据前先通过
`quality_compounder -> residual_income_or_equity_value` 路由，并把该路由策略写入
`valuation_route`。这一步只补充模型选择的显式证明，不改变既有 bear/base/bull、
置信度、价格桥接、反向估值或准入状态。

`scripts/build_company_valuation_result.py` 支持可选 `--profile-id`，并把通过的路由策略写入
输出。`scripts/build_shenhua_cyclical_valuation_result.py` 作为第三案例已在计算前强制通过
`cyclical_cash_return` 路由。该路由只决定模型合同，不决定事实是否验证、估值是否批准、模拟
或交易状态。

同日新增 `valuation_confidence.py`，把低/中/高置信度改为显式规则而非调用方手写：
数据完整度、商业稳定性、参数敏感度、周期性、预测跨度、终值占比和交叉检查分歧均需
命名证据；未知、未测量或越过中位政策阈值时失败关闭为低置信度。FCFF 与周期模型可选
携带 `ConfidenceEvidence`，计算后置信度只改变展示信息，不改变
`conditional_research_only` 的研究准入边界。

同日新增 `current_research_status.py`，把 `ResearchGate`、`ValuationResult` 与
`PriceBridgeResult` 聚合成只读的 `CurrentResearchStatus`。聚合层分别输出研究结论、
估值状态、价格桥接状态、工程状态和当前数据状态；低置信度、未完成估值、条件估值以及
失效的价格桥接均失败关闭，不得升级为 `估值具备研究吸引力`。`PENDING_EXTERNAL_DATA`
只改变当前数据状态，保留既有研究结论与估值结果，不输出交易、订单、仓位或实盘状态。
`workbook_simple_overview.py` 通过 JSON 载荷适配器接入该对象，Excel 卡片增加派生状态行，
不替代原研究门禁、估值明细或证据展示。

2026-09-22 完成三公司贯通：`pending_price_bridge_for_incomplete_valuation` 为尚未形成
情景价值的 `ValuationResult` 生成只读 `PENDING_EXTERNAL_DATA` 桥接，不虚构 `ModelValidity`、
行情或安全边际。美的 `unified-company-valuation-result-v1` 与神华
`601088-cyclical-stage-b-latest.json` 均输出独立 `price_bridge`，并接入同一
`CurrentResearchStatus -> Excel` 卡片。未完成估值仍保持 `not_ready`，研究结论不升级，
不输出订单、仓位或实盘状态。

同日美的增加 `build_midea_valuation_applicability.py`，把经济画像路由与事实口径适用性拆开：
共享 FCFF 路由可被经济画像支持，而当前披露仍可登记为 `MODEL_NOT_APPLICABLE /
VALUATION_NOT_READY`。生产结果保留 `valuation_route` 与 `valuation_applicability` 两段证据，
不发生“画像支持”到“估值可用”的隐性升级。

同日美的再增加 `build_midea_consolidated_equity_scope.py`，把合并归母/少数股东权益与利润、
可见金融业务口径和财务公司持股从同一份年报中独立封存。合并权益事实不得直接推导普通股价值；
`residual_income_or_equity_value` 在适用性包中保持 `CANDIDATE_NOT_REGISTERED`。候选路线、
阻断项及所需下一证据只进入证据链和研究卡，不进入模型输入。

同日美的再增加 `build_midea_2014_2024_equity_return_candidate_series.py`，把 2014--2024
逐年的归母权益、归母利润、现金分红和回购式现金回报按原始年报页码锁成候选序列。历史序列
只证明当时披露的权益、利润和现金回报事实；它不得替代前瞻 ROE、权益成本、派息/留存政策、
当前普通股分母或干净盈余权益滚动对账。适用性包明确 `COMPILED_CANDIDATE` 与
`model_input=null`，下一证据只要求可验证的前瞻与当前范围，不再把“历史证据缺失”当作候选
路线未注册的原因。

## 长期扩展约束

系统统一研究流程，不统一行业经济假设。所有行业共享 Evidence、FinancialFacts 基础契约、
ResearchCase、ResearchGate、ValuationResult、PriceBridgeResult、漏斗状态和 Excel 展示；
财务指标、估值模型、周期变量、关键风险、Thesis Breakers 与参数按 Profile 区分。

从第三个案例开始，估值选择必须通过 `ResearchProfile` 和后续 `ValuationRouter` 按行业、商业模式、
投资路径、生命周期和资本结构决定；股票代码不能成为核心路由条件。市场情绪、流动性和相对估值
永久作为 Market Context 旁路：可影响研究优先级和风险提示，不得直接改写内在价值情景或生成交易。

全市场漏斗采用分类后的多通道筛选，再汇入统一候选池；不做全市场单一评分排行榜，也不追求每只
股票都有目标价。允许并应明确输出 `UNSUPPORTED`、`MODEL_NOT_APPLICABLE`、`DATA_INCOMPLETE` 和
`VALUATION_NOT_READY`。

## 维护约束

- 公司专用脚本只可作为首例迁移层或生产适配器；出现复制需求时先补通用接口。
- 不为目录美观大规模重写；每次删除或迁移先核对引用、测试和运行入口，并保留证据追溯。
- P0 通过后加入最小 GitHub Actions：push / pull request 运行 `pytest`。
- 每轮汇报必须分别给出 Engineering Status、Current Data Status、用户可见变化、架构变化、测试、
  blockers、下一唯一工程任务和等待的 Production Validation。
