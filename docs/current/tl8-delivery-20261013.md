# TL8-LONG-RUN 交付记录（2026-10-13）

本轮在 `codex/web-d1-investment-workbench` 分支上完成 TL8 工作包 A、B 与
D/E 的一个真实产品切片，并核查了工作包 C 的当前真实状态。所有输出保持
`action=no_order`；未接自动交易、未代签任何人工资格、未修改正式 Excel、
未改动用户未提交的工作区文件。

## 1. 实际完成了什么

工作包 A（提交 `eb0e9df`，含真实产物）：

- 新增通用研究有效性复核
  `src/value_investment_agent/application/product/research_validity_review.py`
  与薄 CLI `scripts/current/review_research_validity.py`（两个 CLI 清单已登记）；
- 共享 PriceBridge 新增五级比较资格阶梯 `compatibility`：报价核验 /
  研究覆盖 / 历史重建对比资格 / 价格比较准入 / 正式决策资格逐级判定，
  `formal_decision_eligible` 恒为 False，Web 公司页直接展示；
- 真实运行 600887 复核（研究包 `3ec6e2c9…`、事件扫描 `3c1a3ae9…`、
  行情包 `628f52aa…`），产物
  `docs/current/tl8-a-600887-research-validity-review-20261013.json`
  SHA-256 `aa8f8080…ace983c`、`.md` SHA-256 `115302f4…bcada23`；
  结论 `BLOCKED_ON_HUMAN_EVENT_REVIEW`（反事实模型有效性为 VALID，
  但事件窗口仍需人工材料性复核，不放行任何门禁）。

工作包 B（提交 `07cf0d0`，含真实产物）：

- 用共享 `scripts/current/replay_workbench_cutoffs.py` 对 600887 在
  2026-08-27 / 2026-09-22 / 2026-10-01 三个真实截止时点完成回放，
  输入全部路径 + SHA-256 绑定，并附合成执行机制场景（费用、T+1 有界订单、
  拒单语义，显式标记 `SYNTHETIC_ENGINEERING_FIXTURE`）；
- 产物 `runtime/tl8-b-600887-replay-bound-20261013/result.json`
  SHA-256 `985cf871…2fdd58`、`replay.md` SHA-256 `e2a53632…c11b8`；
  复跑（`-recheck/`）除重建时间戳外逐项相等；
- 与此前 `runtime/real-historical-decision-input-bound-20261001/result.json`
  对比：除新增执行场景、`cutoffs`、`fact_evidence_timeline` 与时间戳外逐项相等；
- 发现并封存一处真实取证漂移：扫描目录内 `cninfo-index.json` 被后续抓取覆盖
  （期望 `f68b7e83…`，现值 `1b267402…`）；不绑定封存原件时回放 fail-closed，
  绑定 `20260923T050735Z` 副本后 `PASS_RECOVERED_ORIGINAL`。

工作包 D/E 切片（提交 `5b58881`）：

- 新增 `application/product/daily_research_status.py`：按已登记行情绑定逐家
  执行共享价格桥接，输出“研究截止日是否覆盖核验收盘日 / 是否需要重新研究”，
  单家公司失败相互隔离且不升级任何门禁；
- `/api/v1/daily-decisions` 新增 `research` 段（不可用时 fail-closed 为
  `UNAVAILABLE`），并把“正式复核候选”计数改为从已发布行派生，不再写死 0；
- 新增薄 CLI `scripts/current/build_daily_research_summary.py`：写出不可覆盖的
  `daily-summary.json`；同一输入重复执行返回 `UNCHANGED`（同日不产生分叉记录）；
- `/daily` 页面新增“研究状态与重新研究清单”，逐家显示研究截止日、核验收盘日、
  是否需重新研究、原因与下一步，可点入公司页。

工作包 C 现状核查（真实接口证据，非新估值）：

- 三个已授权公司共用同一合同与同一页面组件；
- 600887 = `RESEARCH_ONLY`（已登记研究 + 条件性估值，价格未准入）；
- 000333 = `PENDING_RESEARCH`（下一份官方财报：现金流、资本配置与股本披露）；
- 601088 = `PENDING_RESEARCH`；估值路由已注册 `cyclical_normalized` +
  `CyclicalFacts`，但 601088 尚无准入的周期输入，因此不套用消费制造业模型，
  周期估值为 `NOT_ESTABLISHED`；
- 000333 的 2026-06-30 普通股股数分母已按第 7 节 NEXT TASK 的有界官方核验
  闭环（2026-10-13 追加，见第 8 节）；仍未以任何测试夹具填充真实财务事实。

## 2. 600887 当前处于什么状态

- 研究版本 `pending-600887-2026-10-11-short-advantage-fc7dba372686`，
  研究截止日 2026-10-11；
- 已核验收盘 2026-10-12，27.96 元（腾讯/新浪双源，归档包 `628f52aa…`）；
- 条件性估值（`residual_income_or_equity_value`，2026-10-11，confidence 低）：
  Bear 9.7976…、Base 10.0751…、Bull ≈10.3007…；
- `model_validity = UNKNOWN`；`margin_to_base / margin_to_bear = null`；
- PriceBridge：`QUOTE_VERIFIED_BUT_RESEARCH_STALE`，`price_admitted = false`；
  阶梯：报价核验通过、研究覆盖未通过、历史重建/比较/正式决策均未通过；
- G3 未批准；正式决策 `NO_ACTION`；仓位建议 `BLOCKED_PRIVATE_INPUT`；
- 还缺：事件窗口人工材料性复核、研究重登记（含模型有效性）、G3 人工批准、
  真实 IPS/组合输入。

## 3. 历史回放是否完成

已按现有共享回放基础设施完成一个真实公司、三个真实截止时点的可复现回放
（见第 1 节工作包 B）。区间：2026-08-27 → 2026-10-01；数据：保留研究结果、
官方披露索引与事件原件（含封存恢复绑定）、归档双源收盘行情、重建财务输入、
合成执行机制场景。

PIT 限制：2026-08-27 与 2026-09-22 两个时点的保留行情与估值均晚于截止时点，
不能回填，`NOT_READY`；2026-10-01 12:00 时点历史价格 26.77 元、
桥接算术 `READY`，但前置公告仍待人工材料性复核。所有时点 `orders=[]`、
`fills=[]`、`position_guidance=null`、`strict_pit_admitted=false`、
`performance_claim_allowed=false`。这是 `HISTORICAL_RECONSTRUCTION`，
不代表当时真的运行过该策略，也不与后续真实价格表现混算。

## 4. 多公司复用进度

| 公司 | 工程支持 | 真实研究 | 当前状态 |
| --- | --- | --- | --- |
| 600887 伊利股份 | 同一合同与页面 | 条件性估值 + 10-12 核验收盘 | RESEARCH_ONLY；价格未准入；需重新研究 |
| 000333 美的集团 | 同一合同与页面 | 2026-06-30 官方股本分母已核验（7,464,347,335 股）；情景输入未注册 | PENDING_RESEARCH；A 级阻塞清零，仍无准入估值 |
| 601088 中国神华 | 同一合同与页面；周期模型已注册 | 周期输入未准入 | PENDING_RESEARCH；周期估值 NOT_ESTABLISHED |

## 5. 用户现在打开 Web 能新增看到什么

- `http://127.0.0.1:8001/daily`：新增“研究状态与重新研究清单”，
  当前显示 600887 需要重新研究（研究截止日 2026-10-11 早于核验收盘日
  2026-10-12），并给出原因与下一步；
- `http://127.0.0.1:8001/decisions/600887`：新增“比较资格阶梯（逐级判定，
  互不替代）”，直接显示报价核验通过但研究覆盖未通过；
- 每日摘要 CLI（可审计运行入口）：

```powershell
python -X utf8 -B scripts/current/build_daily_research_summary.py --output runtime/<new-dir>/daily-summary.json
```

## 6. 测试与提交

- 提交：`eb0e9df`（A）、`07cf0d0`（B）、`5b58881`（D/E），均已推送
  `origin/codex/web-d1-investment-workbench`；
- 定向测试：`tests/test_research_validity_review.py`、
  `tests/test_quote_bridge_execution.py`、`tests/test_daily_research_status.py`、
  `tests/web_api`、`tests/test_product_cli_entrypoints.py`、
  `tests/test_architecture_boundaries.py` 全部通过；
- Core Gates（与 CI 同一文件清单）：批次 1 后 2334 passed / 33 skipped，
  批次 3 后 2340 passed / 33 skipped；
- Web：`npm run typecheck`、`format`、`test`（35 项）、`build` 全部通过；
- 新增测试已登记进 `.github/workflows/core-research-gates.yml`，远端 CI 结果
  已核对：`eb0e9df`（Core Research Gates run 38347596983 / Web Workbench
  38347596986）、`07cf0d0`（38348005271 / 38348005305）、`d84bc10`
  （38348996375 / 38348996427）均为 `success`。

## 7. 下一轮应做什么

NEXT TASK：000333（美的集团）2026-06-30 普通股股数分母的有界官方核验，
并把可核验结果接回共享研究链。

- Goal：用官方披露（巨潮/公司 IR）核对 2026-06-30 普通股股数及其口径，
  有证据则生成新的 FinancialFacts 事实并走既有估值路由；无证据则封存
  具体查询窗口、来源与缺项，保留 `NOT_READY`。
- Files likely affected：`scripts/collect_m1_event_scan.py` 相邻的官方证据工具、
  `application/product/` 下共享事实验证入口、`runtime/`（新目录）、
  `docs/current/`（核验记录）。
- Forbidden changes：不得用测试夹具/推算填充真实股本；不得降低价格桥接或
  研究门标准；不得修改正式 Excel；不得代签任何人工批准。
- Acceptance：一条可从“Excel/页面数值 → 数据库/产物 → 官方公告 URL/Hash”
  追溯的分母事实（或明确的、可复现的封存缺项记录），且 000333 状态更新
  只依据该证据。

## 三项独立状态

```text
ENGINEERING_DELIVERY = DELIVERED
CURRENT_RESEARCH_ADMISSION = NOT_ADMITTED
FINAL_OPERATIONAL_ACCEPTANCE = NOT_PASSED
action = no_order
```

## 8. 追加：工作包 C 首项闭环（2026-10-13）

按第 7 节 NEXT TASK 执行了 000333 2026-06-30 普通股分母的有界官方核验，
结果为正：发行人港交所月报表直接枚举该日股本，A 级阻塞清零。

- 新增有界 HKEX 采集工具
  `scripts/cases/capture_hkex_issuer_disclosure_window.py`（身份固定、
  行数上限、窗口校验、原件哈希、目录不可覆盖），含
  `tests/test_hkex_issuer_window_capture.py`（4 例，已入 CI 清单）；
- 两个真实窗口：2026-07-01~08-07（35 条，含 6 月与 7 月月报表）、
  2026-09-30~10-13（6 条，含 9 月月报表与三份回购/过户公告）；
  CNINFO 同步窗口 2026-09-30~10-13（5 条）；
- **2026-06-30 分母 = 7,464,347,335 股**（已发行不含库存：A 6,813,498,835 +
  H 650,848,500；库存 A 149,091,572 = 注销用途 68,679,031 + 激励用途
  80,412,541），与 H1 报告已发行总数 7,613,438,907 完全对账；
- 9 月滚动闭环：23,212,340 回购 − 15,772,385 持股计划过户 =
  +7,439,955 = 月报表库存变动，验证“库存股 = 回购专用账户”口径；
- 共享链接入：`midea-valuation-applicability-v5`
  （`runtime/company-research/midea-valuation-applicability-20261013-v5/evidence.json`
  SHA-256 `b69e2fc9…f5ee5f541`）`A_BLOCKING_UNKNOWN = 0`，
  决定 `AUTHORIZED_DENOMINATOR_VERIFIED_PENDING_B_SCENARIO_INPUTS`；
  6 项 B 类情景输入与 FCFF 三项证据停止不变，无 `ValuationResult` 输出；
- 记录与回执：`docs/current/tl8-c-000333-share-denominator-recheck-20261013.md`、
  `docs/current/tl8-c-000333-share-denominator-recheck-receipt-20261013.json`；
  `track-b-midea-share-denominator-review-20260928.md` 追加同日闭环章节；
- 未做：未注册任何情景输入、未运行估值模型、未修改正式 Excel、
  未回填 2026-09-29 计数到 6-30、未升级任何门禁。

提交与验证：`f9344d9`（已推送 `origin/codex/web-d1-investment-workbench`）；
定向测试 `tests/test_midea_valuation_applicability.py`、
`tests/test_midea_unified_valuation_provenance.py`、
`tests/test_hkex_issuer_window_capture.py`、`tests/test_architecture_boundaries.py`、
`tests/test_product_cli_entrypoints.py` 全部通过；Core Gates（与 CI 同一文件清单）
2344 passed / 33 skipped；远端 CI 已核对：`f9344d9`（Core Research Gates
run 38357165840 / Web Workbench 38357166097）均为 `success`。

## 9. 追加：工作包 C 第二项，601088 周期模型路由边界（2026-10-13）

按工作包 C3 核验了中国神华的周期估值模型边界，只读复用生产路由器与
共享合同，不新增模型家族、不运行估值算术：

- 路由验证：`cyclical_cash_return` 画像 → `cyclical_normalized`
  （`SUPPORTED`，合同 `CyclicalFacts`）；同一画像请求
  `residual_income_or_equity_value` 与 `fcff` 均被拒绝
  （`model_not_authorized_for_profile:*`），成熟消费制造业模型
  在代码层不可能被无条件套用到周期画像；
- 输入缺口：合同 13 项必需输入 **0 项准入**；候选包 9 组推导全部
  `model_input = null`；两个周期审计包 `registered inputs = []`；
  既有 stage-b 失效关闭结果以 13 条 `cyclical_input_missing:*`
  阻塞并保持 `PENDING_EXTERNAL_DATA`；
- 决定：`CYCLE_MODEL_ROUTE_VERIFIED_INPUTS_NOT_ADMITTED`，
  `valuation_status = NOT_ESTABLISHED`；封存证据停止项
  `601088-acquisition-adjusted-through-cycle-profit` 不变，
  并给出 6 条重开条件（跨周期利润情景、资本开支拆分、折现率/增长、
  归母净现金、复核分母、资源寿命与成本曲线）；
- 产物：`runtime/company-research/shenhua-valuation-applicability-20261013-v1/evidence.json`
  （SHA-256 `148e56a3…3c6ac59`）+ latest 指针；入口
  `scripts/research_cases/shenhua/build_shenhua_valuation_applicability.py`；
- 记录与回执：`docs/current/tl8-c-601088-cycle-model-boundary-20261013.md`、
  `docs/current/tl8-c-601088-cycle-model-boundary-receipt-20261013.json`；
- 未做：未登记研究版本、未修改 Web/Excel、未产出情景值或仓位、
  未升级任何门禁；产品状态维持 `PENDING_RESEARCH`，`action=no_order`。

验证：`tests/test_shenhua_valuation_applicability.py`（4 项，本机 runtime
固定件）与 `tests/test_architecture_boundaries.py`（30 项）共 34 项通过；
脚本已按仓库根增长守卫放置于 `scripts/research_cases/shenhua/`，
清单 `docs/architecture/script-inventory-v1.json` 同步登记。

## 10. 追加：WEB-D4 工作包 F，`/daily` 双策略资金池与仓位护栏（2026-10-13）

把已发布的双策略风险复核接进每日工作台，只复述正式绑定，不新建第二套风险系统：

- 新增只读投影
  `src/value_investment_agent/presentation/read_models/dual_sleeve_surface.py`：
  校验 `dual-sleeve-risk-review-v1` 与 `action=no_order`，逐字复述
  `position_guidance` / `trade_eligible` / `acceptance_authority`，并给出
  `portfolio_connected`、`position_guidance_available` 与 `next_user_input`
  （`PRIVATE_PORTFOLIO_INPUT_REQUIRED` / `PRIVATE_INPUT_INCOMPLETE`）；
- `/api/v1/daily-decisions` 新增 `dual_sleeve` 段：
  - 当前发布物已绑定真实报告
    `runtime/daily-trade-assistant/fm3-v3-publish-20261012-v2/dual-sleeve-risk.json`
    （SHA-256 `7d8f49bc…4fb2e9`），实测返回 `NOT_CONNECTED`、
    `blockers=["portfolio.private_input_missing"]`、`position_guidance=null`、
    `trade_eligible=false`、`acceptance_authority=NONE`；
  - 旧发布物没有该绑定时，改走共享 `run_dual_sleeve_review`
    生成真实的未接入结果（`portfolio=None`），不伪造任何私人组合或仓位；
  - 报告被篡改（`action != no_order` 等）时该段单独 fail-closed 为
    `UNAVAILABLE / DUAL_SLEEVE_SURFACE_INVALID`，不拖垮研究页其余部分；
  - 发布链整体损坏时该段为 `UNAVAILABLE / DUAL_SLEEVE_STATUS_UNAVAILABLE`；
- `/daily` 新增“双策略资金池与仓位护栏”：双策略状态、私人组合是否接入、
  仓位建议是否生成、交易资格、决策权限、复核时间与来源路径；未生成仓位建议时
  直接说明原因（“尚未接入真实私人组合，系统不会给出任何买多少/卖多少的
  仓位数字”）和下一步需要本人提供的输入（IPS、持仓、现金与风险约束）；
- 保持不变：`action=no_order`、`trade_eligible=false`、
  `acceptance_authority=NONE`，不生成个性化仓位建议、不读取私人存储、
  不修改私有 API 合同与既有代理逻辑。

验证：`tests/web_api/test_read_api.py` 17 项通过（含 4 项新跨模块用例：
正式绑定逐字复述 / 无绑定回落到共享未接入路径 / 篡改报告单段关闭 /
发布链损坏时该段仍存在且不编造数字）；`tests/web_api` 全量 134 项通过；
Web `typecheck`、`format`、`test`（41 项，含 6 项新用例）、`build` 通过，
`web/dist` 已重建并由本机 `127.0.0.1:8001` 工作台加载。
