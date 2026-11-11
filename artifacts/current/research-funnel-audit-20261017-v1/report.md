# W6 Research Funnel Audit

- Task: `W6-FUNNEL-AUDIT-V1`
- Action: `no_order`
- Trade intent: `NO_TRADE`
- Run ID: `m2-20261012T090828Z`
- As of: `2026-10-12`

## Funnel counts

| Layer | Count |
| --- | ---: |
| universe | 5573 |
| market_snapshot | 5573 |
| industry_snapshot | 5573 |
| industry_mapped | 5573 |
| financial_points | 21277 |
| financial_evidence | 873 |
| dividend_records | 3653 |
| dividend_evidence | 3622 |
| leads | 114 |
| queue_entries | 114 |
| queue_selected | 10 |
| queue_deferred | 104 |

## Quote date

- Quote date: `2026-10-12`
- Verification: `UNVERIFIED_PROVIDER_TRADE_DATE`
- Verified quote count: 0
- Unverified quote count: 5573
- Trade date verified: `false`
- Interpretation: Provider trade dates are unverified; quote dates are not claimed as verified trading dates.

## Channels

| Channel | Raw statuses | Effective statuses | Top reason |
| --- | --- | --- | --- |
| quality | {"BUDGET_EXCLUDED":0,"CONFLICT":0,"DATA_GAP":4677,"NOT_EVALUATED":0,"PASS":0,"REJECTED":775,"UNSUPPORTED":121} | {"BUDGET_EXCLUDED":0,"CONFLICT":0,"DATA_GAP":4677,"INSUFFICIENT_EVIDENCE":775,"NOT_EVALUATED":0,"PASS":0,"REJECTED":0,"UNSUPPORTED":121} | 当前快照缺少同一报告期、可验证的财务质量证据 (4677) |
| dividend_cash_return | {"BUDGET_EXCLUDED":367,"CONFLICT":0,"DATA_GAP":0,"NOT_EVALUATED":1951,"PASS":50,"REJECTED":3099,"UNSUPPORTED":106} | {"BUDGET_EXCLUDED":367,"CONFLICT":0,"DATA_GAP":0,"NOT_EVALUATED":1951,"PASS":50,"REJECTED":3099,"UNSUPPORTED":106} | 参考股息率低于 0.025 (2888) |
| value | {"BUDGET_EXCLUDED":350,"CONFLICT":0,"DATA_GAP":1468,"NOT_EVALUATED":0,"PASS":50,"REJECTED":3584,"UNSUPPORTED":121} | {"BUDGET_EXCLUDED":350,"CONFLICT":0,"DATA_GAP":1468,"NOT_EVALUATED":0,"PASS":50,"REJECTED":3584,"UNSUPPORTED":121} | PE、PB 或总市值缺失，无法完成 Value 通道校验 (1468) |
| cyclical | {"BUDGET_EXCLUDED":1534,"CONFLICT":0,"DATA_GAP":692,"NOT_EVALUATED":3063,"PASS":50,"REJECTED":113,"UNSUPPORTED":121} | {"BUDGET_EXCLUDED":1534,"CONFLICT":0,"DATA_GAP":692,"NOT_EVALUATED":3063,"PASS":50,"REJECTED":113,"UNSUPPORTED":121} | 已通过通道规则，但超出单通道展示预算 50；仍保留在覆盖率分母，未静默删除 (1534) |

## Interpretation

775 Quality rows have raw status REJECTED but zero evidence refs; the product-level classification is INSUFFICIENT_EVIDENCE. The raw receipt status remains REJECTED rather than being rewritten.

## Financial source coverage

| Source category | Points | Symbols | Verified points | Accepted points |
| --- | ---: | ---: | ---: | ---: |
| cninfo_statutory_points | 5946 | 687 | 5769 | 5769 |
| cninfo_official_institution_report | 132 | 42 | 15 | 15 |
| independent_structured | 12585 | 716 | 0 | 0 |
| tencent_market | 784 | 784 | 784 | 784 |
| derived_facts | 1769 | 568 | 1692 | 1680 |
| other | 61 | 11 | 0 | 0 |

## GENERAL_FIELDS matrix

| Field | Points | Symbols | Verified | Accepted |
| --- | ---: | ---: | ---: | ---: |
| roe | 705 | 705 | 567 | 567 |
| gross_margin | 693 | 693 | 306 | 306 |
| net_margin | 653 | 653 | 347 | 347 |
| operating_cash_flow_to_net_income | 713 | 713 | 466 | 466 |
| cash | 678 | 678 | 306 | 306 |
| interest_bearing_debt | 695 | 695 | 12 | 0 |
| debt_ratio | 712 | 712 | 427 | 427 |
| revenue_yoy | 635 | 635 | 21 | 21 |
| net_income_yoy | 703 | 703 | 22 | 22 |

- Same-period complete symbols: 0 (point-complete 581, verified-complete 0)
- Capital return / ROIC: `UNAVAILABLE`; ROIC/capital-return points are present but none pass financial_quality._accepted.

## Research queue

- Entries: 114
- Selected: 10
- Deferred: 104
- Industry distribution: `{"all":{"交通运输":7,"传媒":2,"公用事业":6,"农林牧渔":1,"医药生物":8,"商贸零售":3,"基础化工":7,"家用电器":5,"建筑材料":1,"建筑装饰":11,"房地产":3,"有色金属":11,"机械设备":6,"汽车":8,"环保":6,"电力设备":3,"电子":3,"石油石化":2,"社会服务":1,"纺织服饰":9,"轻工制造":5,"钢铁":1,"食品饮料":5},"deferred":{"交通运输":7,"传媒":2,"公用事业":6,"农林牧渔":1,"医药生物":8,"商贸零售":2,"基础化工":7,"家用电器":5,"建筑装饰":11,"房地产":2,"有色金属":9,"机械设备":6,"汽车":7,"环保":3,"电力设备":3,"电子":3,"石油石化":2,"社会服务":1,"纺织服饰":9,"轻工制造":4,"钢铁":1,"食品饮料":5},"selected":{"商贸零售":1,"建筑材料":1,"房地产":1,"有色金属":2,"汽车":1,"环保":3,"轻工制造":1}}`

## Human review

- Status: `HUMAN_REVIEW_PENDING`
- Sample size: 10
- Signature: `None`
- Approval: `None`

| Symbol | Company | Industry | Queue status |
| --- | --- | --- | --- |
| 000151 | 中成股份 | 商贸零售 | SELECTED_FOR_DATA_CHECK |
| 000544 | 中原环保 | 环保 | SELECTED_FOR_DATA_CHECK |
| 000612 | 焦作万方 | 有色金属 | SELECTED_FOR_DATA_CHECK |
| 000656 | 金科股份 | 房地产 | SELECTED_FOR_DATA_CHECK |
| 000672 | 上峰材料 | 建筑材料 | SELECTED_FOR_DATA_CHECK |
| 000685 | 中山公用 | 环保 | SELECTED_FOR_DATA_CHECK |
| 000807 | 云铝股份 | 有色金属 | SELECTED_FOR_DATA_CHECK |
| 000885 | 城发环境 | 环保 | SELECTED_FOR_DATA_CHECK |
| 600210 | 紫江企业 | 轻工制造 | SELECTED_FOR_DATA_CHECK |
| 600741 | 华域汽车 | 汽车 | SELECTED_FOR_DATA_CHECK |

This audit is read-only. It does not approve research, establish model validity, create a price decision, or authorize an order.
