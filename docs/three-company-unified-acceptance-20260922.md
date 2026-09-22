# 三公司统一验收与冻结

日期：2026-09-22。范围：600519、000333、601088 在阶段 A 与 P0.5 后是否共用同一研究、
估值、价格桥接与 Excel 展示合同，并冻结当前 MVP 范围。

这不是阶段 B 正式估值通过、历史策略有效性、模拟组合或实盘准入验收。

## Executive Summary

三家公司已经进入同一 `ResearchCase -> ResearchGate -> ValuationResult -> ModelValidity ->
PriceBridgeResult -> PriceAttractivenessAssessment -> CurrentResearchStatus -> Excel`
流程，且边界没有被放宽：

- 贵州茅台：条件研究 `conditional_research_only`，同日价格桥接 READY，但置信度低、
  研究门 G3 未通过，价格吸引力仍为 `NOT_ASSESSABLE`。
- 美的集团：FCFF 经济路线 SUPPORTED，事实口径仍 `MODEL_NOT_APPLICABLE`，估值
  `not_ready`，价格桥接 `PENDING_EXTERNAL_DATA`。
- 中国神华：周期正常化路线 SUPPORTED，正常化输入尚未注册，估值 `not_ready`，价格桥接
  `PENDING_EXTERNAL_DATA`。

```text
THREE_COMPANY_UNIFIED_ACCEPTANCE = PASSED_FOR_FREEZE
THREE_COMPANY_ENGINEERING_STATUS = READY
STAGE_B_FORMAL_VALUATION = NOT_PASSED
FORMAL_FAIR_VALUE = NULL
TRADE_APPROVED = FALSE
LIVE_ELIGIBLE = FALSE
```

冻结的是三家公司 MVP 的研究与工程边界，不是把 B1 条件研究或 B2/B3 工程边界写成研究级估值
完成。三个案例继续在 Excel 中保留可见的阻断项，不生成买卖价、仓位、订单或实盘状态。

## Frozen Baseline

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| 三公司统一 ResearchCase | `runtime/excel-mvp-research-cases/evidence.json` | `156700b16dbd1ac42d8209e05853c724ab347b3c1917d7d6fd03f988acf10bf6` |
| 600519 条件估值 | `runtime/valuation-results/600519-current-equity-stage-b/evidence.json` | `5fd86bd643d958a93462905f32eae57fad3e8a7ee6c8986dce7ba2ef73ee9495` |
| 000333 FCFF 收敛 | `runtime/valuation-results/000333-fcff-stage-b/evidence.json` | `10c8f565647df6bda5eac4eff8c0e9ed4b4d3192e1d5cd1241a1233b5706f5fc` |
| 601088 周期收敛 | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6` |
| 600519 假设映射 | `runtime/valuation-assumptions/moutai-current-20260921/evidence.json` | `a2866d531709f255d1d240791639f19cd82ed54e181c519dba2a3ffb4d9731de` |
| 601088 正常化候选 | `runtime/valuation-assumptions/shenhua-normalized-candidates-20260922/evidence.json` | `ccd86f507d2728ca0e3258cc895da076ab80366a80b0e4548e482312ab9f951c` |
| 000333 Materiality | `runtime/company-research/midea-finance-materiality-20260922/evidence.json` | `22e949f49751ef3a323a43b4b5ad72b929870c62b7eba5c30eaf386a5e51f19c` |
| 当前 WPS 原表 | `C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪/A股价值投资_Agent前端智能跟踪模板.xlsx` | `BD8049F042EED173AFC271C2E88C36F603719DC97F2480093C49335CD9AB22D1` |

当前原表与最新发布备份
`runtime/workbook-backups/frontdoor-20260922T041238343587Z/ready.xlsx` 的 Hash 一致。旧的
`030e702789c37d66580f99ca5769b28289cd820457ad77c0c9196e019c499ef5` 是发布序列中的历史值，
不作为当前冻结 Hash。

## Shared Contract Audit

| 统一合同 | 当前状态 |
| --- | --- |
| ResearchCase | 恰好 600519 / 000333 / 601088，三家均有一句话论点、回报来源、错价假设、支持证据、反证、失效条件和下一事件。 |
| ResearchGate | 三家分别输出 `估值未就绪` / `数据不足` / `研究未完成`；不输出价格相关结论。 |
| ValuationResult | 三家共享 `ValuationResult` 核心字段；当前价格、安全边际均不属于该对象。 |
| ModelValidity | 600519 为同日 VALID；000333 / 601088 因估值尚未形成使用 UNKNOWN，且不伪造模型有效性。 |
| PriceBridgeResult | 600519 READY；000333 / 601088 PENDING_EXTERNAL_DATA，均无虚构报价、边际或仓位。 |
| PriceAttractiveness | 三家均 NOT_ASSESSABLE；低置信度或未完成估值不得输出“估值具备研究吸引力”。 |
| Assumptions | 600519 READY 映射且参数未变；601088 PARTIAL，`registered_model_inputs=false`；000333 尚无注册假设集。 |
| Materiality | 000333 财务公司影响为 LOW / MODEL_AS_RANGE，但不得解除 MODEL_NOT_APPLICABLE。 |
| Excel | 三家卡均展示研究、估值、假设/重大性、价格桥接、价格吸引力和阻断分类；不生成买卖指令。 |
| Freeze | 无第四家公司、无全市场筛选、无 Web、无模拟扩展、无实盘准入。 |

新增本地回归 `tests/test_three_company_unified_acceptance.py` 会重新校验指针 Hash、三家共享载荷、
证据引用、假设/Materiality 边界及聚合状态。该测试依赖本地 runtime，不进入 Linux Core Gate。

## 600519 贵州茅台

| # | 问题 | 当前真实状态 |
| --- | --- | --- |
| 1 | 公司怎么赚钱 | 高端白酒的品牌、渠道和产品结构，以量价、实际价格与现金归属持续验证；品牌标签不能替代商业证据。 |
| 2 | 核心回报来源 | 盈利持续性、现金分配与资本配置；估值重评不预设。 |
| 3 | 最强经济驱动 | 品牌、渠道与产品结构支撑的长期盈利及每股现金回报，实际优势持续时长仍未经验计量。 |
| 4 | 最强反证 | FY2025 白酒收入同比 -1.08%、销量 +2.13%，收入/吨走弱；2026 上半年子公司投资收益回款仅 1.01 亿元，覆盖全年研究分配能力明显低于季节性稳定水平；日常关联交易上限 92.06 亿元仍需复核。 |
| 5 | Thesis Breaker | 量增价跌或产品结构持续走弱；现金流、必要投入和现金归属不能支持分配能力；关联交易实际发生额/定价/独立审计与披露原则不一致。 |
| 6 | 当前事实 | 2026 中报归母权益、扣非 TTM 利润锚、FY2025 三年现金分配、回购并注销事实、FY2025 量价与母公司/子公司现金流均已 Hash 锁定。 |
| 7 | 估值假设 | 五年 -5%/0%/+5% 增长、75% 派息、五年预测与五年优势衰减、2% 终值增长、有界权益成本；已映射为 READY 统一假设集且未重算参数。 |
| 8 | 主模型 | `quality_compounder -> residual_income_or_equity_value`。 |
| 9 | 为什么适用 | 高质量复利与现金回报画像与剩余收益/权益价值路径注册一致；只产生条件研究结果，不代表正式合理价。 |
| 10 | Bear/Base/Bull | 403.44 / 478.43 / 571.25 元/股，条件研究情景，非目标价。 |
| 11 | Confidence | 低；参数敏感度高、周期性未知，不得升级为研究吸引力。 |
| 12 | PriceBridge | 同日 1252.57 元/股，READY；相对熊/基准情景为 -210.5% / -161.8%。 |
| 13 | PriceAttractiveness | NOT_ASSESSABLE；ResearchGate 仍为“估值未就绪”，低置信度阻断正向价格判断。 |
| 14 | 最大不确定性 | 优势实际持续时长、全年 2026 可分配现金与子公司回款、折现率基础、关联交易与治理证据。 |
| 15 | 下一事件 | 下一份定期报告及重大资本动作；不得以旧时点价格桥接更新为新交易日结论。 |

## 000333 美的集团

| # | 问题 | 当前真实状态 |
| --- | --- | --- |
| 1 | 公司怎么赚钱 | 年报披露家电、商用及工业解决方案等业务；发行人披露不等于竞争优势或财务口径已获独立证明。 |
| 2 | 核心回报来源 | ResearchCase 将候选回报写为经营效率、再投资与每股价值增长；收益驱动尚未形成注册模型。 |
| 3 | 最强经济驱动 | 2025 年营业收入 4,564.52 亿元、经营现金流 533.46 亿元及商用/工业方案高增长；仍是年报事实，需要独立竞争与治理证据。 |
| 4 | 最强反证 | 金融业务、机器人、能源与医疗混列，独立金融业务口径缺失；家电与商用/工业毛利率分别下降。 |
| 5 | Thesis Breaker | 收入增长不能持续覆盖各品类需求；金融业务独立范围、企业价值桥接或当前普通股分母无法取得可审计证据。 |
| 6 | 当前事实 | FY2025 合并现金流、权益、利润、期末 A/H 总股本、会计加权普通股、HKEX 2026-03-30 公告日库存股及财务公司规模观察已 Hash 锁定。 |
| 7 | 估值假设 | 尚未注册；不能从合并权益/利润直接推导普通股价值，也不能用会计 EPS 分母代替当前估值分母。 |
| 8 | 主模型 | `mature_manufacturing -> fcff`，经济路线 SUPPORTED；事实适用性 MODEL_NOT_APPLICABLE。 |
| 9 | 为什么适用 | 成熟制造画像支持 FCFF 路线，但需可审计工业口径剥离、净债务/现金、营运资本和企业价值桥接。 |
| 10 | Bear/Base/Bull | 未生成，三项均为 null。 |
| 11 | Confidence | 低；模型事实准入未通过。 |
| 12 | PriceBridge | PENDING_EXTERNAL_DATA；估值本身未形成，不虚构行情或边际。 |
| 13 | PriceAttractiveness | NOT_ASSESSABLE；没有合法 READY PriceBridge。 |
| 14 | 最大不确定性 | 金融业务独立利润表/资产负债表、企业价值桥接、2025 年末库存股股数及当前估值日普通股分母。 |
| 15 | 下一事件 | 独立金融业务报表或可审计企业价值桥接；经注册的当前普通股分母与完整权益价值假设链。 |

## 601088 中国神华

| # | 问题 | 当前真实状态 |
| --- | --- | --- |
| 1 | 公司怎么赚钱 | 煤炭、发电、铁路、港口、航运和煤化工一体化经营；年报披露事实不能直接替代竞争优势证明。 |
| 2 | 核心回报来源 | 若后续研究成立，来自周期经营利润、一体化协同与现金回报；不能把高点利润永久化。 |
| 3 | 最强经济驱动 | 一体化业务和可分配现金；尚无注册的中周期正常化利润与成本曲线。 |
| 4 | 最强反证 | 2025 年营收/营业利润/归母净利同比下降；煤价、煤量、电量、电价均走弱，火电利用小时下降。 |
| 5 | Thesis Breaker | 中周期煤价与成本不能形成有依据区间，或煤电协同无法稳定穿越周期；资源寿命、债务、矿业权投入或大型资本开支显示压力高于可解释范围。 |
| 6 | 当前事实 | 2025 年报分部分利润、资本开支、储量、销量、价格、成本以及 2014-2025 运营/利润/税负/外部指数材料均已作为时期事实或候选边界 Hash 锁定。 |
| 7 | 估值假设 | 正常化价格、成本、销量、资本开支与资源寿命形成 PARTIAL 候选集；折现率、长期增长率、归母净现金和当前普通股分母仍缺失，`registered_model_inputs=false`。 |
| 8 | 主模型 | `cyclical_cash_return -> cyclical_normalized`，经济路线 SUPPORTED；事实合同尚未满足。 |
| 9 | 为什么适用 | 资源周期与现金回报画像支持周期正常化模型，但需要中周期利润、可复算成本曲线、指数原始档案和股本/净现金口径。 |
| 10 | Bear/Base/Bull | 未生成，三项均为 null。 |
| 11 | Confidence | 低；事实合同未满足且关键假设敏感性高。 |
| 12 | PriceBridge | PENDING_EXTERNAL_DATA；估值未就绪。 |
| 13 | PriceAttractiveness | NOT_ASSESSABLE；没有合法 READY PriceBridge。 |
| 14 | 最大不确定性 | 归母税前利润桥接、可复算成本曲线、价格指数原始档案、当前普通股分母和归母净现金。 |
| 15 | 下一事件 | 子公司逐户利润税费披露、路线成本矩阵、可核验指数原始档案或经注册的正常化假设链。 |

## Freeze Boundary

- 600519 只保留条件研究、同日价格观察和已有研究卡；不重估参数，不启动 P1/P2/P3、R1、模拟或实盘。
- 000333 保留 fail-closed FCFF 路径和 Materiality 结论；不继续从同一批年报/转载页挖掘缺失口径。
- 601088 保留 PARTIAL 正常化假设候选；不继续构造历史煤价或运输成本模型输入。
- 不新增第四家公司，不启动全市场筛选、Web 前端、银行/保险/地产专项估值、复杂 CycleAnalyzer、
  市场情绪系统、真实交易或券商 API。
- 只允许 bug fix、回归修复和安全/数据完整性修复。每日行情、风险显示、备份和必要维护继续。

## Verdict And Handoff

三公司统一验收在本轮通过，但只表示“三家公司已共用同一研究/估值/价格边界并可冻结”，不表示
阶段 B 正式估值完成。600519 是条件研究，000333 与 601088 是 fail-closed 工程节点；三者均
没有正式合理价、仓位、订单或实盘准入。

下一主线按既有顺序转入 20-50 家固定跨行业样本的可复用性验证。只有在对应新披露或经注册的
假设链出现时，才按各公司停止规则重新打开美的或神华；茅台 P1/P2/P3、真实历史与前瞻模拟及
R1 仍排在固定跨行业样本之后。
