# 中国神华 601088 B3 研究级估值收敛节点评估

日期：2026-09-22。范围：神华 B3 在 P0.5 之后是否已经形成研究级估值收敛。
这不是正式估值、策略、组合、历史回测或交易准入验收。

## Executive Summary

神华 B3 的工程链完整，并继续保持 fail-closed：

- `cyclical_cash_return` 经济画像授权共享 `cyclical_normalized` 主模型；
- 2014--2025 运营、利润、税负、价格和成本运输材料均被保存为时期事实或候选边界；
- 正常化假设包已经形成，但状态为 `PARTIAL`，且 `registered_model_inputs=false`；
- 没有事实被写入 `CyclicalFacts.operating_inputs`，共享模型不执行任何情景算术。

因此本节点结论为：

```text
STAGE_B3_NODE_ASSESSED
ENGINEERING_STATUS = READY
PRODUCTION_VALUATION_STATUS = VALUATION_NOT_READY
CURRENT_DATA_STATUS = PENDING_EXTERNAL_DATA
```

神华不生成 bear/base/bull、正式合理价值、反向估值数值、价格桥接数值、安全边际、仓位或订单，
`formal_fair_value=null`、`trade_approved=false`、`live_eligible=false`。本节点关闭的是
继续无限补证的工程分支，不是把 B3 写成研究级估值完成。

## Authoritative Evidence Baseline

- 2025 年度报告原件：
  `runtime/shenhua-2025-official.pdf`，SHA-256
  `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`。
- 2025 周期范围审计：
  `runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json`，SHA-256
  `4c69cf09f81ae8c0cf7fd5537276a3147d1c25adf3eee80b92c455ee2a3134c0`。
- 2025 周期候选输入：
  `runtime/company-research/shenhua-cyclical-candidate-inputs-20260921/evidence.json`，SHA-256
  `3fc7fd27c13787ff08162e26e9762fbe1912db47766369624a42d41e5eaefe71`。
- 2014--2025 归母利润与现金税候选序列：
  `runtime/company-research/shenhua-2014-2025-attributable-profit-series-20260922/evidence.json`，SHA-256
  `0eb6e930831f19d0e7ab8520dbfd4f67dd2e4afc7183e36233fd4a4ee0191e64`。
- 2014--2025 运营周期序列：
  `runtime/company-research/shenhua-2014-2025-operational-cycle-series-20260922/evidence.json`，SHA-256
  `923cd297a72d39d20968a577475fb19640b2b8f87fe3ca9aefd353cbaa6ce6ad`。
- 2014--2025 运营周期独立审查：
  `runtime/company-research/shenhua-2014-2025-operational-cycle-audit-20260922/evidence.json`，SHA-256
  `7d21b86914e87be98a95dace75356746ee501309f81be273bf6d1453648da015`。
- 2014--2025 外部煤价与 2025 成本运输桥接：
  `runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-20260922/evidence.json`，SHA-256
  `c99cec17a0b671bb6221dbe3e4a81a5f3bfff090e2e1f582872bb2cbc2e3059e`。
- NCEI/BSPI/CCTD 外部指数溯源：
  `runtime/company-research/shenhua-external-index-provenance-20260922/evidence.json`，SHA-256
  `3cf0e8e5df004a6166738194564afd0f421b94c897f14e4261815297bcc4b427`。
- CCTD 公开历史指数端点：
  `runtime/company-research/shenhua-public-index-history-20260922/evidence.json`，SHA-256
  `9a3a5d5e586267e44f668e176eaeb4f73e210f64c442e6d117dbe0de32622fe4`。
- BSPI 与七份年报年度均价对账：
  `runtime/company-research/shenhua-bspi-annual-report-reconciliation-20260922/evidence.json`，SHA-256
  `7b4693eaada98ec0716de32d064ef58d2f25a116075ca88758b4231a55680443`。
- BSPI 点时发布页与转载页：
  `runtime/company-research/shenhua-bspi-point-in-time-publications-20260922/evidence.json`，SHA-256
  `a51b71db3fc928979e5c86de5d97704f6f3877f6e138f203b4d17cf048edaa0e`。
- 2025 内部煤电销售/耗用复核：
  `runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-20260922/evidence.json`，SHA-256
  `8243e55efdff19e8d70389faf3bda510bf0d20c0bb5959525cb1ceae0912f9fb`。
- 2014--2025 分线路到港/到厂全成本审计：
  `runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-20260922/evidence.json`，SHA-256
  `f7d681992eb6a64d3bbc29bace836db2c4d168683a1dd2eddb3ee3908aa2d91b`。
- IFRS 12 子公司税务复核：
  `runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922/evidence.json`，SHA-256
  `ef9f3cca62cf29bfd6ffb5bd89f5585db7ff93887332796ce0d592e2ccf31e1f`。
- 正常化假设候选集：
  `runtime/valuation-assumptions/shenhua-normalized-candidates-20260922/evidence.json`，SHA-256
  `ccd86f507d2728ca0e3258cc895da076ab80366a80b0e4548e482312ab9f951c`。
- 统一周期估值结果：
  `runtime/valuation-results/601088-cyclical-b3/evidence.json`，SHA-256
  `b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6`。

## Unified Acceptance Answers

| 问题 | 当前真实状态 |
| --- | --- |
| 1. 公司怎么赚钱 | 煤炭、发电、铁路、港口、航运和煤化工的一体化经营；年报披露事实，不能直接替代竞争优势证明。 |
| 2. 核心回报来源 | 周期经营利润、一体化协同和现金回报；尚不能形成注册的中周期利润输入。 |
| 3. 最强经济驱动 | 煤价、单位成本、资源寿命和煤电路径；现有材料均为时期事实或候选边界。 |
| 4. 最强反证 | 子公司归母归属、价格指标断点、内部煤电口径和路线级成本无法对账。 |
| 5. Thesis Breaker | 现有 Thesis Breakers 保留；本次没有新增，也不因证据数量增加而放宽。 |
| 6. 当前事实 | 2025 年报分部分利润、资本开支、储量、销量、价格和成本已 Hash 锁定。 |
| 7. 估值假设 | 正常化假设集为 PARTIAL；折现率、长期增长率、归母净现金和当前普通股分母仍缺失。 |
| 8. 主模型 | `cyclical_cash_return -> cyclical_normalized`，路线为 SUPPORTED。 |
| 9. 为什么适用 | 资源周期和现金回报画像支持周期正常化模型，但事实合同尚未满足。 |
| 10. Bear/Base/Bull | 未生成，三项均为 null。 |
| 11. Confidence | 低；事实合同未满足，且关键假设敏感性高。 |
| 12. PriceBridge | PENDING_EXTERNAL_DATA，估值本身也未就绪。 |
| 13. PriceAttractiveness | NOT_ASSESSABLE，没有合法 READY PriceBridge。 |
| 14. 最大不确定性 | 归母税前利润桥接、可复算成本曲线、价格指数原始档案和当前普通股分母。 |
| 15. 下一复评事件 | 子公司逐户利润税费披露、路线成本矩阵、可核验的指数原始档案，或经注册的正常化假设链。 |

## Why The Node Is Fail-Closed

- 子公司逐户税前利润、所得税和少数股东分配未披露。HKEX IFRS Note 44 只列示内部抵销前的
  Revenue、Expenses 和 Profit and total comprehensive income，没有逐户 profit before tax 或
  income tax expense；因此不能用母公司法人利润或统一所有权比例重构归母税前营业利润。
- 普通股分母 `21,689,434,304` 仅被批准为 `2026-06-30` 时点候选，尚未与估值日期及其余输入
  一并注册，不能单独进入模型。
- 归母净现金、受限现金、财务公司存款、少数股东现金和关联往来未分配。
- 2014--2025 运营、利润和现金税序列只批准为时期事实或候选边界；2019/2020 电价不可比，
  部分销量来自后续年报对比表，统一所有权 pro forma 不是披露的法定报表行。
- 外部价格存在指标切换和披露缺口：环渤海指数到 NCEI 不可直接拼接，2018 无点值，
  2019 只有区间；BSPI 2018/2019/2020 仍缺运营方原文，2020 只有明确转载和 CEI 登录受限列表，
  不得插值或升级。NCEI/BSPI/CCTD/CECI 历史原始数据受会员权限限制。
- 2025 内部煤电销售 73.2 百万吨与发电耗用 77.7 百万吨是两套口径，年报未给桥接。
- 171.6 元/吨只是生产口径单位成本，不是路线加权到港/到厂全成本；年报未披露路线分配矩阵。
- 维护与增长资本开支未拆分，资源寿命仅能从储量/产量形成静态候选，不是经评审的矿井服务年限。
- 折现率、长期增长率、低谷利润和绝对单位成本等假设尚未注册。

共享模型因此保持 `not_ready`，统一估值结果没有写入任何 `operating_inputs`，也没有产生
价格桥接数值、仓位、订单或实盘准入变化。

## Layer Classification

- FACT：子公司逐户税务归属、归母净现金、路线级成本和运营方原始指数档案未披露。
- ASSUMPTION：折现率、长期增长率、中周期利润、成本曲线和资源寿命尚未注册。
- MATERIALITY：现有差异不足以解除模型事实合同，未知或不可对账项目继续 fail-closed。
- MODEL：经济路线 SUPPORTED，事实准入 MODEL_NOT_READY。
- PRICE：估值未就绪，价格桥接为 PENDING_EXTERNAL_DATA，价格吸引力不可评估。
- EXECUTION：无仓位、订单、模拟成交或实盘准入变化。

## Stop Rule

继续挖掘已有年报和转载页不能改变当前 model applicability、assumption range、materiality、
confidence、valuation output 或 thesis。因此按 P0.5 第 49-50 节停止神华证据考古。

只有在出现以下任一项可观测证据时才重新打开：

- 子公司逐户税前利润、所得税和少数股东分配，或可审计的归母税前营业利润桥接；
- 能匹配估值日期的当前普通股分母，以及归母净现金和受限现金分配；
- 独立成本曲线或路线分配矩阵；
- 2018/2019/2020 BSPI 和 2023 后 NCEI 的运营方原始发布档案及修订政策；
- 有明确经济依据和来源的正常化假设链，并先通过共享假设与证据合同。

## Handoff

神华保持研究卡可见的 fail-closed 状态。下一工程主线是三公司统一验收与冻结：

- 复核 600519、000333、601088 的 ResearchCase、ResearchGate、ValuationResult、
  ModelValidity、PriceBridgeResult 和 Excel 展示是否共享同一合同；
- 冻结当前三家公司范围，不新增第四家公司，不启动全市场筛选、Web 前端或交易扩展；
- 不得把 B1 条件研究、B2 或 B3 fail-closed 节点写成正式估值完成。

本节点完成后，正式合理价值、反向估值、模拟、R1、模拟组合和 R2 实盘准入继续单独验收。
