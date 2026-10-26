# 美的集团（000333）条件性研究草案

> **研究草稿（未批准）**。当前状态为 `RESEARCH_DRAFT_NOT_APPROVED`，`action=no_order`。本研究不能生成正式买入、卖出或仓位建议。

## 结论

美的具备规模化制造、渠道效率、全球化品牌与现金流优势；但2026H1扣非归母净利润同比下降25.31%，本次草案只检验在较低ROE路径下是否存在条件性价值，不用历史高ROE外推。

估值只作为条件性研究结果：Bear / Base / Bull 分别对应不同的 ROE、终端增长和留存假设，不是目标价。已核验收盘价 CNY 84.60（2026-10-16）仅作为报价事实展示，PriceBridge 状态为 `INVALID`，价格准入为 `false`。

## 条件性估值

模型：`residual-income-equity-shared-dated-v2`  
研究截止日：`2026-10-16`  
估值基准：`conditional residual income with an algebraic dividend-path cross-check; not evidence of issuer distributable cash or dividend sustainability`  
置信度：`低`

版本变化：`midea-valuation-applicability-20261013-v5`（INSUFFICIENT_PUBLIC_EVIDENCE）
→ `midea-draft-20261016-v1`（RESEARCH_DRAFT_NOT_APPROVED）。新增事项：
- ordinary_share_denominator_reopened_with_hkex_2026_06_monthly_return
- shared_residual_income_model_executed
- dated_basis_to_valuation_bridge_added
- conditional_bear_base_bull_values_available

| 情景 | 每股权益价值（CNY） | 终端剩余收益贡献比 | 基准至估值日因子 |
|---|---:|---:|---:|
| Bear | 36.0121866604528720800629631840921914063801838080 | 0.04534430046962670813598094236 | 1.02575648851072872078280171866928461148754088061 |
| Base | 45.7417037044192281574936570926129861357849631511 | 0.1567110536503976527408765945 | 1.02575648851072872078280171866928461148754088061 |
| Bull | 58.1686744055803340295467634666441075299523416697 | 0.2672536050867622579183066563 | 1.02575648851072872078280171866928461148754088061 |

## 财务事实

- 2025 年归母净利润：CNY 43945411000
- 2025 年末归母权益：CNY 223221305000
- 2025 年加权 ROE：0.1970
- 2026H1 扣非归母净利润：CNY 19595179000，同比 -0.2531
- 2026H1 归母权益：CNY 212861055000
- 2026-06-30 普通股分母：7464347335 股

## 候选假设

- cost_of_equity: bear=0.09, base=0.09, bull=0.09；No issuer-specific beta estimate is admitted; a common hurdle keeps the draft internally consistent.
- forecast_roe_2026: bear=0.15, base=0.18, bull=0.205；The path allows margin and competitive pressure while preserving a quality-compounder base case.
- forecast_roe_2027: bear=0.14, base=0.17, bull=0.20；The path allows margin and competitive pressure while preserving a quality-compounder base case.
- forecast_roe_2028: bear=0.13, base=0.16, bull=0.195；The path allows margin and competitive pressure while preserving a quality-compounder base case.
- forecast_roe_2029: bear=0.12, base=0.155, bull=0.19；The path allows margin and competitive pressure while preserving a quality-compounder base case.
- forecast_roe_2030: bear=0.11, base=0.15, bull=0.185；The path allows margin and competitive pressure while preserving a quality-compounder base case.
- terminal_roe: bear=0.095, base=0.11, bull=0.13；Terminal ROE remains above or near the equity hurdle by scenario without assuming permanent high excess returns.
- terminal_growth: bear=0.015, base=0.02, bull=0.025；Growth is capped below the 9% equity hurdle in every scenario.
- retention: bear=0.40, base=0.35, bull=0.30；The bear case retains more capital to defend operations; the bull case distributes more of higher earnings.

## 反证与失效条件

反证：

- 2026H1扣非归母净利润195.95亿元，同比下降25.31%。
- 2026H1归母权益2,128.61亿元，ROE 11.33%，较FY2025明显回落。
- 2026年10月14日三项公告仍待逐条材料性复核，模型有效性只能保持UNKNOWN。

失效条件：

- 若未来两年ROE持续低于9%的候选权益门槛，剩余收益假设失效。
- 若利润下降伴随经营现金转换和资产负债表质量同步恶化，当前底部ROE路径仍需下调。
- 若股本注销、回购或分红导致普通股分母与可分配现金桥接发生变化，必须重算每股价值。

## 事件与模型有效性

截至研究截止日的公告状态：`PENDING_HUMAN_REVIEW`，人工复核状态：`PENDING_HUMAN_REVIEW`。

- 2026-10-14 2026年第一次临时股东会决议公告 (`PENDING_HUMAN_REVIEW`)
- 2026-10-14 北京市嘉源律师事务所关于美的集团2026年第一次临时股东会的法律意见书 (`PENDING_HUMAN_REVIEW`)
- 2026-10-14 关于回购注销部分限制性股票减资暨通知债权人的公告 (`PENDING_HUMAN_REVIEW`)

模型有效性：`UNKNOWN`。  
PriceBridge：`INVALID`，价格准入：`false`。  
阻塞原因：模型有效性尚未建立，不能把收盘价与条件性估值进行正式比较。

## 重开与后续证据

- 人工逐条完成2026-10-14三项公告的材料性复核。
- 补充下一期定期报告，重新核验利润、现金转换和ROE路径。
- 任何股本注销、回购或分红变化均触发普通股分母重算。

## 限制

- 9%权益门槛、ROE路径、终端增长和留存率均为候选研究假设，未经人工批准。
- 正式 G3 估值门未通过；不得据此生成买卖信号。
- 报价仅为已核验收盘事实，PriceBridge 未准入。
- 未接入真实个人组合、现金和 IPS，不得生成仓位建议。

## 证据与哈希

- 美的集团 2025 年年度报告（`midea_fy2025_annual`）：https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF  
  SHA-256 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`
- 美的集团 2026 年半年度报告（`midea_2026h1`）：https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF  
  SHA-256 `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`
- 美的集团 H 股 2026 年 6 月月度证券变动报告表（`midea_202606_hkex_monthly_return`）：https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0707/2026070700419_c.pdf  
  SHA-256 `fab9be2f0349dcda9880b178e45e4dd65474b98635bf454adeeb19ed7bc3ecfd`
- 2026年第一次临时股东会决议公告（`cninfo_1225603532`）：https://static.cninfo.com.cn/finalpage/2026-10-14/1225603532.PDF  
  SHA-256 `6732a5255485d7cdd81d0b73af961fac639c3f344420b84c1a69ac135be7a0bd`
- 北京市嘉源律师事务所关于美的集团2026年第一次临时股东会的法律意见书（`cninfo_1225603533`）：https://static.cninfo.com.cn/finalpage/2026-10-14/1225603533.PDF  
  SHA-256 `e0aebb190712c15e82b29297c1e27d843564ea51cfe36f587eb0955bbe63985c`
- 关于回购注销部分限制性股票减资暨通知债权人的公告（`cninfo_1225603534`）：https://static.cninfo.com.cn/finalpage/2026-10-14/1225603534.PDF  
  SHA-256 `b38a3d71faa803d485d3400410a1dab61699653fc8635e6b2d435df86f04d733`
- 2026-10-16 双源收盘行情封包（本地证据）（`midea_quote_20261016`）：`runtime/quote-sessions/20261016T090031652233Z/bundle.json`  
  SHA-256 `08a8cb10dbb7785870645f8b2e1ab7d4a5f3f6cf8bf4295da5b5baa8ccbd927e`
- 巨潮资讯 2026-10-14 公告检索结果（`midea_event_scan_20261016`）：https://www.cninfo.com.cn/new/hisAnnouncement/query  
  SHA-256 `a3d2e0b0de6013f739ba0fb508a754fd40f164a13e0c7da01f85c75d401e7d84`

## 运行链

`research package -> shared residual-income model -> ValuationResult -> ModelValidity -> PriceBridge -> Web research draft`

本次研究通过一次性 Evidence Stop 重开后，由于第一次运行暴露了 PriceBridge 模型版本绑定错误，已保留中断包与恢复凭据，并在修复后显式恢复同一准入；没有第二次消费同一 Evidence Stop，也没有伪造审批。
