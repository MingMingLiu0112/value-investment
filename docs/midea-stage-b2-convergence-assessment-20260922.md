# 美的集团 000333 B2 研究级估值收敛节点评估

日期：2026-09-22。范围：美的 B2 在 P0.5 之后是否已经形成研究级估值收敛。
这不是估值、策略、组合或交易准入验收。

## Executive Summary

美的 B2 的工程链已完整，且继续保持 fail-closed：

- mature_manufacturing 指向 fcff 的经济路线为 SUPPORTED；
- 留存的 FY2025 年报没有独立披露金融业务利润表、资产负债表、税费、债务、现金和营运资本，
  因此工业 FCFF 口径仍为 MODEL_NOT_APPLICABLE，合并企业价值桥接仍为 VALUATION_NOT_READY；
- 合并归母普通股权益、归母利润和期末 A/H 股本已披露，但 residual_income_or_equity_value
  尚未获得 mature_manufacturing Profile 授权，且预测 ROE、权益成本、派息/留存、当前普通股
  分母和干净盈余滚动对账均未注册；
- 财务公司规模只构成 OBSERVATION_NOT_MODEL_INPUT，不解除工业 FCFF 阻断。

因此本节点结论为：

STAGE_B2_NODE_ASSESSED
ENGINEERING_STATUS = READY
PRODUCTION_VALUATION_STATUS = VALUATION_NOT_READY
CURRENT_DATA_STATUS = PENDING_EXTERNAL_DATA

美的不生成 bear/base/bull、正式合理价值、价格桥接数值、安全边际、仓位或订单，
formal_fair_value=null、valuation_approved=false、trade_approved=false、
live_eligible=false。本节点关闭的是 继续无限补证的工程分支，不是把 B2 写成研究级估值完成。

## Evidence Baseline

- EBIT scope：runtime/company-research/midea-ebit-scope-20260921/evidence.json，
  SHA-256 e9527b6c824be83366eaef9f7ffb95288c3befbfc1ac1f8811c56441c5248566。
- FY2025 share basis：runtime/company-research/midea-2025-share-basis-20260922/evidence.json，
  SHA-256 f31dfaddf00a42d227107932a3eecdc8b1de9b44860f383c9157b321046c2113。
- Consolidated equity scope：
  runtime/company-research/midea-consolidated-equity-scope-20260922/evidence.json，
  SHA-256 190f7cb5fbe07a47b81a59ae7f04d02ba9f514bb3a8327272cc62a682150c360。
- 2014-2024 equity-return candidate series：
  runtime/company-research/midea-2014-2024-equity-return-candidate-20260922/evidence.json，
  SHA-256 6726e821972d0490753a6cc718f6f54515ccbfbb53341f081900af208eab7ea1。
- Finance-company size observation：
  runtime/company-research/midea-finance-co-2025-size-observation-20260922/evidence.json，
  SHA-256 2b3069bc617167dce2ee60730da52cf3da29483e6515adc428a58bd905fb1714。
- HKEX 2026-03-30 announcement-date share basis：
  runtime/company-research/midea-20260330-hkex-share-basis-20260922/evidence.json，
  SHA-256 ddbccf84f57b40755f9b0146ae0dc288362864ffecd31affbd58bdb8a4de77f8。
- Valuation applicability：
  runtime/company-research/midea-valuation-applicability-20260922/evidence.json，
  SHA-256 70f23d6eedc799194e69b70da282593664efaf931b4cc821a97e9951237a4cf9。
- Unified FCFF result：
  runtime/valuation-results/000333-fcff-stage-b/evidence.json，
  SHA-256 5ad0052e676ffacb4141d8c01b11799026550f0bc7a3d39d6a52916dd2523255。

## Unified Acceptance Answers

| 问题 | 当前真实状态 |
| --- | --- |
| 1. 公司怎么赚钱 | 年报披露家电、商用及工业解决方案等业务；发行人披露，不等同于竞争优势或质量已获独立证明。 |
| 2. 核心回报来源 | ResearchCase 有商业论点候选；收益驱动尚未形成注册模型。 |
| 3. 最强经济驱动 | ResearchCase 有支持证据；其中年报经营事实为发行人披露，仍需独立竞争和治理证据。 |
| 4. 最强反证 | 金融业务与机器人、能源、医疗等混列，独立金融业务口径缺失。 |
| 5. Thesis Breaker | 现有 Thesis Breakers 保留；本次未新增。 |
| 6. 当前事实 | FY2025 合并现金流、权益、利润、A/H 期末股本、公告日库存股等已 Hash 锁定。 |
| 7. 估值假设 | 尚未注册，不能用合并权益或利润直接推导普通股价值。 |
| 8. 主模型 | 经济路线选择 fcff；事实适用性仍未通过。 |
| 9. 为什么适用 | 制造业成熟经营画像支持 FCFF 路线，但需要工业口径剥离和权益桥接。 |
| 10. Bear/Base/Bull | 未生成，三项均为 null。 |
| 11. Confidence | 低；模型未通过事实准入。 |
| 12. PriceBridge | PENDING_EXTERNAL_DATA，估值本身也未就绪。 |
| 13. PriceAttractiveness | NOT_ASSESSABLE，没有合法 READY PriceBridge。 |
| 14. 最大不确定性 | 金融业务独立范围、企业价值桥接、当前估值日普通股分母。 |
| 15. 下一复评事件 | 独立金融业务报表/可审计企业价值桥接，或经注册的当前普通股分母与完整权益价值假设链。 |

## Layer Classification

- FACT：金融业务独立范围未披露；2025 年末库存股股数未披露；当前估值日普通股分母未注册。
- ASSUMPTION：预测 ROE、权益成本、派息/留存政策、终值参数均未注册。
- MATERIALITY：财务公司规模观察为 LOW-size 上下文，但明确不是模型输入。
- MODEL：FCFF 经济路线支持，事实口径不适用；权益价值路线尚未获 Profile 授权。
- PRICE：估值未就绪，价格桥接为 PENDING_EXTERNAL_DATA，价格吸引力不可评估。
- EXECUTION：无仓位、订单、模拟成交或实盘准入变化。

## Stop Rule

继续挖掘年报附注不能改变当前 model applicability、assumption range、materiality、
confidence、valuation output 或 thesis。因此按 P0.5 第 49-50 节停止美的证据考古。
只有在出现以下任一项可观测披露时才重新打开：

- 独立金融业务利润表与资产负债表，或可审计的合并企业价值桥接；
- 2025-12-31 年末库存股股数及能匹配未来估值日的普通股分母；
- 有明确经济依据和来源的权益价值假设链，并先通过共享假设与证据合同。

## Handoff

美的保持研究卡可见的 fail-closed 状态，下一工程主线转向中国神华正常化估值收敛。
神华同样先做大节点收敛评估，不把 B3 工程边界已存在当作研究级估值已完成。
后续披露触发时，美的可从对应证据包恢复，不必重新做 EBIT/股本/权益历史考古。
