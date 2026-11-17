# 研究有效性复核：伊利股份（600887）

- 结论状态：`BLOCKED_ON_HUMAN_EVENT_REVIEW`
- 登记研究版本：`pending-600887-2026-10-11-short-advantage-fc7dba372686`（研究截止日 2026-10-11）
- 复核截止日：2026-10-12；来源可用截止：2026-10-13T03:13:31.815290+00:00
- 永久动作边界：`action=no_order`

## 窗口与事实变化
- 事件窗口：2026-10-11 → 2026-10-12（覆盖 COMPLETE，扫描状态 `PENDING_HUMAN_REVIEW`）
- 公告数：0；事实变化：`NONE`
- 假设变化：`NONE`

## 模型有效性
- 当前：`UNKNOWN`（blockers: pending_complete_event_materiality_review; event scan is pending human review; This acquired query window does not replace earlier event/model/G3 reviews.）
- 若人工完成事件窗口复核：`VALID`（反事实，不是批准）

## 价格兼容性阶梯
- 报价双源核验：通过。双源收盘行情已通过核验并归档。
- 研究覆盖报价日：未通过。报价日 2026-10-12 晚于登记研究截止日 2026-10-11；须先完成研究重登记与事件复核。
- 历史重建对比资格：未通过。报价日 2026-10-12 晚于登记研究截止日 2026-10-11；须先完成研究重登记与事件复核。
- 价格比较准入：未通过。报价日 2026-10-12 晚于登记研究截止日 2026-10-11；须先完成研究重登记与事件复核。
- 正式决策资格：未通过。正式投资决策资格需 G3 人工批准与决策门通过；执行层不评估、不预支。

## 待人工审批
- `EVENT_WINDOW_HUMAN_REVIEW`（human）：事件扫描有效期 2026-10-11→2026-10-12 仍为人工待复核；复核完成前，模型有效性不能由 UNKNOWN 变为 VALID。 → 解锁 模型有效性覆盖 2026-10-12（当前 UNKNOWN）
- `RESEARCH_VERSION_RE_REGISTRATION`（engine+operator）：登记研究截止日为 2026-10-11，未覆盖更晚的已核验行情；重登记只能生成待复核版本，不能代签审批。 → 解锁 价格桥接从 QUOTE_VERIFIED_BUT_RESEARCH_STALE 进入可判断状态
- `G3_VALUATION_APPROVAL`（human）：正式估值批准是正式投资决策的前置人工门。 → 解锁 正式决策资格（formal_decision_eligible）
- `PRIVATE_PORTFOLIO_OR_IPS`（user）：仓位建议必须基于真实组合与约束，当前未接入。 → 解锁 position guidance（在此之前保持 null）

## 重开条件
1. 人工完成事件窗口材料性复核（扫描 3c1a3ae9e8d5…，2026-10-11→2026-10-12，公告数 0）。
2. 以覆盖 2026-10-12 的研究版本完成有界重登记（既有引擎 prepare_pending_research_candidate，输出 PENDING_REVIEW，不得代签）。
3. 重登记后重跑价格桥接登记与执行（pin_current_quote_bridge.py / execute_quote_bridge_for_symbol）。
4. 在产生当日已核验收盘后重跑 run_daily_trade_assistant.py，使报价日为当前交易会话。
5. G3 人工批准与决策门通过前保持 action=no_order，不产生买入/加仓建议。

## 证据
- review-package：runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/package.json（3ec6e2c95534…）
- review-event-scan：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/event-scan.json（3c1a3ae9e8d5…）
- daily-index-600887：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/cninfo-index.json（7664b603cc4c…）
- daily-raw-index-manifest-600887：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/raw-index-manifest.json（679f858dbd7b…）
- daily-raw-600887-1：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/raw-index/response-0001.bin（8dddfb3858f9…）
- daily-raw-metadata-600887-1：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/raw-index/response-0001.json（ecd7f38c12bd…）
- daily-raw-600887-2：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/raw-index/response-0002.bin（c2a890bbf3a6…）
- daily-raw-metadata-600887-2：runtime/daily-trade-assistant/20261013T031330686666Z-600887/event-observation/raw-index/response-0002.json（9149ece8442a…）
