# TL8 工作包 C：601088 中国神华 周期模型路由边界核验（2026-10-13）

本轮对 601088 的**周期估值模型适用边界**执行了一次有界核验：
确认哪一类已注册模型可被该公司的经济画像合法路由，并逐项清点
周期合同要求的模型输入是否已准入。所有输入均来自既有留存证据包，
按 SHA-256 固定后重新校验；本轮**不产生任何估值数字**，不登记研究，
不升级任何门禁，`action=no_order`。

**结论：**

```
decision            = CYCLE_MODEL_ROUTE_VERIFIED_INPUTS_NOT_ADMITTED
valuation_status    = NOT_ESTABLISHED
valuation_run_status= NOT_RUN_ADMITTED_INPUTS_UNAVAILABLE
admitted_inputs     = 0 / 13
new_model_family    = false
research_product    = PENDING_RESEARCH（未变更）
```

## 1. 路由边界（用真实路由器验证）

核验直接调用生产 `ValuationRouter`（只读，不写状态）：

| 请求 | 结果 | 阻塞 |
| --- | --- | --- |
| 周期画像默认路由（`cyclical_cash_return`） | `SUPPORTED`，模型 `cyclical_normalized`，合同 `CyclicalFacts` | - |
| 同一画像请求 `residual_income_or_equity_value`（成熟消费制造业的残余收益模型） | `UNSUPPORTED` | `model_not_authorized_for_profile:residual_income_or_equity_value` |
| 同一画像请求 `fcff`（通用默认） | `UNSUPPORTED` | `model_not_authorized_for_profile:fcff` |

即：**只有已注册的周期正常化模型对该画像合法**；把成熟消费制造业的
残余收益模型套用到周期公司、或把 FCFF 作为通用默认，都会被路由器拒绝。

## 2. 合同级输入缺口（用真实事实合同验证）

以零输入构造 `CyclicalFacts`，合同报告 **13/13 项输入缺失**；
最近一次保留的失效关闭（fail-closed）运行结果（stage-b，
`runtime/valuation-results/601088-cyclical-b3/evidence.json`，
`b03eaa05…e5d1df6`）同样以 13 条 `cyclical_input_missing:*` 阻塞，
状态为 `not_ready`，情景值为 `null`，价格桥为 `PENDING_EXTERNAL_DATA`。
该结果被本轮记录锚定，作为“周期模型无法运行”的既有事实。

### 2.1 逐项缺项清单（13 项）

| 输入 | 候选包状态 | 周期审计判定 | 序列审计判定 |
| --- | --- | --- | --- |
| bear/base/bull 正常化归母税前营业利润 | `cannot_derive_from_retained_disclosure` | `cannot_derive_from_operating_series` | `not_derived_series_must_be_reviewed_as_cycle_envelope` |
| `cash_tax_rate` | `unverified_historical_candidate` | `not_present` | `candidate_upper_bound_only_cash_taxes_paid_includes_all_taxes` |
| `maintenance_capex` | `range_only_no_reviewed_split` | `not_present` | - |
| `normalized_working_capital_change` | `raw_balance_sheet_candidate_not_normalized` | `not_present` | - |
| `discount_rate` | `no_company_specific_reviewed_basis` | `not_present` | - |
| `long_term_growth` | `no_company_specific_reviewed_basis` | `not_present` | - |
| `resource_life_years` | `reserve_over_current_output_range_candidate` | `not_present` | - |
| `net_cash_attributable_to_parent` | `unverified_reported_surface_proxies` | `not_present` | - |
| `ordinary_shares` | `period_end_value_not_current_denominator` | `separate_point_in_time_denominator_approved_but_not_registered` | - |
| `trough_parent_operating_profit` | （候选包装载于序列包） | `not_established_by_descriptive_series` | `descriptive_series_does_not_by_itself_establish_trough` |
| `unit_cost` | `change_only_no_absolute_cost_curve` | `rejected_as_direct_model_input_historical_production_cost_only` | - |

要点：

- 候选包内 **9 组候选推导全部 `model_input = null`**；
- 两个周期审计包（2014-2025 经营周期审计、归母盈利序列）均记录
  `registered_cyclical_facts_operating_inputs = []`；
- 普通股分母仅有 2026-06-30 候选 **21,689,434,304 股**，
  复核要求明确（逐笔发行原件、时点/加权口径选择、库藏股确认），
  未注册为模型输入；
- 归母净现金只有候选区间（30,275 ~ 81,701 百万元人民币，表面口径），
  未完成受限资金与少数股东分配复核。

**因此：周期模型本身合规可路由，但没有任何必需输入获批，周期估值
保持 `NOT_ESTABLISHED`，不运行任何情景算术。**

## 3. 证据来源（原件与留存包，全部 SHA-256 固定）

| 来源包 | 路径 | SHA-256 |
| --- | --- | --- |
| 2025 年报周期口径审计 | `runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json` | `4c69cf09…a3134c0` |
| 周期模型候选输入汇编（9 组候选） | `runtime/company-research/shenhua-cyclical-candidate-inputs-20260921/evidence.json` | `3fc7fd27…5eaefe71` |
| 归母税前营业利润桥（候选） | `runtime/company-research/shenhua-2025-parent-operating-profit-bridge-20260921/evidence.json` | `e8f177f2…045504b6c` |
| 归母净现金桥（候选区间） | `runtime/company-research/shenhua-2025-attributable-net-cash-bridge-20260921/evidence.json` | `ce5a021c…f876905a31` |
| 2026 发行后普通股分母桥（候选） | `runtime/company-research/shenhua-2026-share-bridge-20260921/evidence.json` | `1d39ca52…940d6b0e0` |
| IFRS 子公司税务复核 | `runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922/evidence.json` | `ef9f3cca…2e2ccf31e1f` |
| 2014-2025 归母盈利候选序列 | `runtime/company-research/shenhua-2014-2025-attributable-profit-series-20260922/evidence.json` | `0eb6e930…4ee0191e64` |
| 2014-2025 经营周期审计 | `runtime/company-research/shenhua-2014-2025-operational-cycle-audit-20260922/evidence.json` | `7d21b869…53648da015` |
| 交易所披露 2025 年度报告原件 | `runtime/shenhua-2025-official.pdf` | `460ea07e…7425698fc` |
| 失效关闭结果（stage-b 锚点） | `runtime/valuation-results/601088-cyclical-b3/evidence.json` | `b03eaa05…8ee9886e5d1df6` |

## 4. 封存与重开条件

已登记证据停止项（维持不变）：

```
stop_id : 601088-acquisition-adjusted-through-cycle-profit
blocker : current_perimeter_parent_earnings_bridge_incomplete
```

重开条件（全部满足方可重跑周期估值）：

1. 一份经复核的跨周期归母税前营业利润情景区间与低谷利润点；
2. 维持性/增长性资本开支的官方项目级拆分；
3. 公司特有的折现率与长期增长率复核依据；
4. 归母口径净现金分配复核（受限资金、财务公司存款、少数股东）；
5. 经复核的普通股分母（时点/加权口径明确选择）；
6. 经复核的资源寿命年数与绝对单位成本曲线。

**边界：** 本轮不新增估值模型家族（无需用户授权的新模型族），
不代签任何人工批准，不登记研究版本，不修改正式 Excel，
不产生订单、仓位或价格比较资格。产品状态维持 `PENDING_RESEARCH`。

## 5. 产物、复现命令与测试

```text
产物（本机 runtime，未提交）：runtime/company-research/shenhua-valuation-applicability-20261013-v1/evidence.json
SHA-256：148e56a382dc850dd244d9b46176b69a10aaa993df75781769096d97c3c6ac59
指针：runtime/company-research/shenhua-valuation-applicability-latest.json
入口：scripts/research_cases/shenhua/build_shenhua_valuation_applicability.py（薄构建器，只读共享合同与路由器）
```

复现：

```powershell
python -X utf8 -B scripts/research_cases/shenhua/build_shenhua_valuation_applicability.py
python -X utf8 -B -m pytest -q tests/test_shenhua_valuation_applicability.py
```

测试：新增 `tests/test_shenhua_valuation_applicability.py`（4 项，
路由/负例守卫/合同缺口/失效关闭锚点与非交易边界）；与
`tests/test_architecture_boundaries.py` 共 34 项通过。

```text
ENGINEERING_DELIVERY          = 本轮交付（脚本+产物+测试+文档）
CURRENT_RESEARCH_ADMISSION    = NOT_ADMITTED（周期输入未准入，未运行）
FINAL_OPERATIONAL_ACCEPTANCE  = NOT_PASSED
action                        = no_order
```
