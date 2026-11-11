# TL8-B：600887 真实历史输入回放（2026-08-27 / 09-22 / 10-01）

本轮以现有共享回放入口 `scripts/current/replay_workbench_cutoffs.py` 对 600887
伊利股份执行了一次完整的真实输入回放，并复现了此前的绑定产物。全部输出保持
`action=no_order`；这不是策略验证、不是实盘就绪证明，也不是当前投资建议。

## 实际执行

入口：`scripts/current/replay_workbench_cutoffs.py`（`--decision-input-review`）。

决策截止时点（显式、带时区）：

- 2026-08-27T15:00:00+08:00
- 2026-09-22T15:00:00+08:00
- 2026-10-01T12:00:00+08:00

输入全部按路径 + SHA-256 绑定（见 `tl8-b-600887-historical-replay-receipt-20261013.json`）：

- 保留研究结果 `runtime/shared-existing-workbench-20261001/result.json`
  (`d8f7581b...9f29dd`)；
- 财务重建算术输入 `runtime/primary-equity-basis-20261001/primary-bound-arithmetic-input.json`
  (`da108054...17d80`)；
- 官方披露索引与事件证据扫描（2026-09-23 归档，`f68b7e83...` / `a6a2dffa...`）；
- 归档双源收盘行情包 `runtime/quote-sessions/20260923T005634211464Z/bundle.json`
  (`5e49dc79...19c0`)；
- 合成执行机制场景 `runtime/shared-execution-scenario-20261001/input.json`
  (`521826b7...e3a`，显式标记 `SYNTHETIC_ENGINEERING_FIXTURE`)；
- 已封存原件绑定 `runtime/company-research/m1-event-scans/20260923T050735Z/600887/cninfo-index.json`。

输出：

- `runtime/tl8-b-600887-replay-bound-20261013/result.json`
  SHA-256 `985cf871aa5344e7a1f2f3241ef7158fd0aa6738437d4dd6763b0323c92fdd58`；
- `runtime/tl8-b-600887-replay-bound-20261013/replay.md`
  SHA-256 `e2a53632fc86bbfc82f11bcfc136da118495d3c4b2ac3fa8c5d4ef3bcd3c11b8`；
- 复跑核验 `runtime/tl8-b-600887-replay-bound-20261013-recheck/result.json`，
  除 `reconstructed_financial_inputs.reconstructed_at` 时间戳外与首跑逐项相等。

## 回放结论（真实、非装饰）

1. 2026-08-27 与 2026-09-22 两个时点：保留行情包与保留估值结果都晚于该时点，
   不能回填；当时可用的已复核财务事实为“无”，缺项为 `start_book_equity`、
   `ordinary_shares`。因此 `decision_input_status = NOT_READY`。
2. 2026-10-01 12:00 时点：保留估值与行情已可观察，历史价格 26.77 元、
   `bridge_arithmetic_status = READY`；但前置公告仍需人工材料性复核
   （`pre-model disclosures require human review`），决策输入仍为 `NOT_READY`。
3. 所有时点均：`orders = []`、`fills = []`、`position_guidance = null`，
   `strict_pit_admitted = false`、`historical_execution_validated = false`、
   `performance_claim_allowed = false`。
4. 审计发现一处真实取证漂移：`600887-cninfo-event-index` 的原路径文件在扫描后被
   后续抓取覆盖（期望 `f68b7e83...`，现值 `1b267402...`）。回放在没有绑定封存
   原件时会 fail-closed（`HASH_MISMATCH` / `NOT_READY`）；绑定
   `20260923T050735Z` 的封存副本后 `PASS_RECOVERED_ORIGINAL`。结论：已完成扫描的
   目录内原件不得再写；本轮验证了审计链能够发现并拒绝该漂移。

## 语义边界（B3）

历史重建（`HISTORICAL_RECONSTRUCTION`）与正式当前决策（contemporaneous）在共享
PriceBridge 中已通过新的五级兼容阶梯（`compatibility`）明确区分：报价核验、
研究覆盖、历史重建对比资格、价格比较准入、正式决策资格逐级判定、互不替代，
正式决策资格恒为 False。归档收盘“当时合法”不因今天已过多个交易日而被一律
判为当前过期；反过来，历史重建结果也不得冒充当时真的运行过该策略。

## 执行约束与合成场景（B4）

`execution_engineering_scenario` 用冻结的合成场景证明执行机制（限于 2015-2025
冻结费率研究跨度）：次一交易日有界订单、逐日资金/持仓账、拒单与费用语义可
计算。该场景明确标注 `SYNTHETIC_ENGINEERING_FIXTURE`，价格为合成、
`investment_rule_validated = false`，不得当作真实交易记录或收益统计。

600887 当前没有可核验的当时可观察决策输入（见上），因此本轮回放不产生真实
手续费/滑点/T+1 成交统计；不拿合成场景冒充历史业绩，也不与后续真实价格表现
混算。要做真实执行回放，必须先补齐“当时可观察”的行情与已批准研究输入。

## 与本轮之前的关系

- 与 `runtime/real-historical-decision-input-bound-20261001/result.json` 对比：
  除新增 `execution_engineering_scenario`、`reconstructed_financial_inputs.cutoffs`
  与后来新增的 `historical_decision_input_review.rows[*].fact_evidence_timeline`
  及时间戳外，其余字段逐项相等——同一保留产物可继续复现，无静默改写。
- 状态：`engineering_delivery = DELIVERED`；
  `current_research_admission = NOT_ADMITTED`；
  `final_operational_acceptance = NOT_PASSED`；`action = no_order`。
