# TL7-P1 交付：600887 真实研究更新与 PriceBridge 闭环（2026-10-13）

分支：`codex/web-d1-investment-workbench`；PR #1 保持 **Draft**，未合并 `main`。
本文件只记录本轮实际执行的研究、价格桥接与 Web 集成结果，以及仍然被外部证据或人工门阻塞的部分。

## 状态

```text
ENGINEERING_DELIVERY          = DONE（研究重跑、共享价格桥接执行、Web 展示、跨模块测试）
CURRENT_RESEARCH_ADMISSION    = NOT_ADMITTED
                                （2026-10-12 收盘已双源核验；研究截止日 2026-10-11 尚未覆盖该行情；
                                  formal G3 与模型有效性人工门仍未通过）
FINAL_OPERATIONAL_ACCEPTANCE  = NOT_PASSED（缺真实 IPS/组合、正式人工门与 Windows 用户验收）
```

永久保持 `action = no_order`；研究吸引 ≠ 买入信号；高股息 ≠ 买入信号；安全边际 ≠ 仓位。
三类状态互相独立：工程交付不等于投资准入，也不等于系统可用。

## 1. 工作包 A：实际执行研究重算链

复用现有链，没有新建伊利专用研究系统：

- 入口：`scripts/current/run_daily_trade_assistant.py`
- 研究编排：`value_investment_agent.application.product.daily_trade_assistant`
- 估值模型路由：`build_current_workbench_for_symbol` → `residual_income_or_equity_value`
- 研究包（真实、已登记）：`runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/package.json`
  SHA-256 `3ec6e2c955343ccf287dcbeafc4beff7ac49f114f5ddc85679845e69422a25b5`
  （`package_version = pending-600887-2026-10-11-short-advantage-fc7dba372686`，
  `research_as_of = 2026-10-11`，`report_period = 2026-06-30`，
  `model_version = residual-income-equity-shared-dated-v2`，`profile_id = quality_compounder`）

实际执行的命令：

```powershell
cd D:\GPTProject\value-investment
python -X utf8 -B scripts/current/run_daily_trade_assistant.py `
  --case-registry config/user-daily-trade-assistant-v1.json `
  --case-registry-sha256 bcd27349fb18aa17dd4f17820e642d7d07c8865a1652abe0b1a78e9f4aed2996 `
  --symbol 600887 --no-collect-quote `
  --quote-bundle runtime/quote-sessions/20261012T092313080159Z/bundle.json `
  --agent-mode offline

python -X utf8 -B scripts/current/run_daily_trade_assistant.py `
  --case-registry config/user-daily-trade-assistant-v1.json `
  --case-registry-sha256 bcd27349fb18aa17dd4f17820e642d7d07c8865a1652abe0b1a78e9f4aed2996 `
  --symbol 600887 --no-collect-quote --collect-events `
  --quote-bundle runtime/quote-sessions/20261012T092313080159Z/bundle.json `
  --agent-mode offline
```

两次运行的真实产物（`runtime/` 不入库，本机实测）：

| 运行 | workbench.json | report.md | agent-packet.json | asset-index.json |
| --- | --- | --- | --- | --- |
| `runtime/daily-trade-assistant/20261013T031205828663Z-600887` | `c0ae444d87485dd78d75e6eb18f73509b663615704ee24411d39cc2522269d6f` | `ee2d7ec0b5a920ccfcee45959186eb9429d88cd3a6c679a43ff9beaab11e9eb5` | `2b2a0fcaa95104d1f55cc9581fbc87e8af69e86ae154b477e081c6bea380eb87` | `7557ab31e498079ecd18f9fde2ea35f2094138c7951c105c0460a2c5dd32ccf0` |
| `runtime/daily-trade-assistant/20261013T031330686666Z-600887` | `f96a884975d0536a280d5c85f738494adc6c338ea21691aa338bd1c0ee8957fb` | `eceb735627e44ae6a4dd888486ec2140435874cc82b5e425825f876735bc6f89` | `41221fa200a00207790484652b0687368012fd7d17ddc7c5ae13f5bfd476ec75` | `7557ab31e498079ecd18f9fde2ea35f2094138c7951c105c0460a2c5dd32ccf0` |

重算得到的条件性估值（两次运行一致，且与已发布决策解释一致）：

```text
bear = 9.79764118439777680597278298395676515182872214703
base = 10.0751373530680129477021471870066470782479712991
bull = 10.3006925009950307944059171660835859543186976072
confidence = 低；status = conditional_research_only；recommendation_type = NO_ACTION
current_price = null；margin_of_safety = {to_bear: null, to_base: null}；entry_zone = null
```

官方事件窗口（真实 cninfo 有界查询并归档）：

```text
scan_from = 2026-10-11；scan_to = 2026-10-12
announcement_count = 0；pagination_complete = true
collection_status = OFFICIAL_QUERY_ARCHIVED
materiality_approved = false；model_revalidated = false；research_date_advanced = false
```

因此本轮**没有新增官方披露**，也就没有通过改日期或复制旧结果来"刷新"研究：
研究数值未变，变的是研究链被真实重跑、事件窗口被真实封存、价格桥接被执行并进入 Web。

## 2. 工作包 B：PriceBridge 实际执行结果（结果 B：保留 NOT_ADMITTED）

本轮新增共享入口 `value_investment_agent.application.product.quote_bridge`，
命令行与 Web 读模型调用的是**同一个** `admit_quote_for_research` 规则，
同一个归档行情不可能在一个界面被"准入"、在另一个界面被判定"过期"。

真实执行（本机实测）：

```text
status            = QUOTE_VERIFIED_BUT_RESEARCH_STALE
reason            = 行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性
quote_date        = 2026-10-12        display_price = 27.96
collected_at      = 2026-10-12T09:23:13.080145+00:00
display_scope     = LAST_COMPLETED_CLOSE_DISPLAY_ONLY   is_historical_close = true
latest_completed_session = 2026-10-12
research_day      = 2026-10-11        price_admitted = false
bundle_sha256     = 628f52aa203a5ddc43a860d35772645f2903b163deea592264f00f79a9774f4f
pointer           = config/current-quote-bridge.json
                    sha256 414551e2579f3826fdf6fb18ad34afab7b10c50a17d2676d24f8b6942ffb751e
双源              = tencent https://qt.gtimg.cn/q=sh600887（4787985d…e900db）
                    sina    https://hq.sinajs.cn/list=sh600887（702da032…35268b）
```

已核对的准入要素：两路来源均为 `quote_provider_document` 且带日期；报价与最近已完成交易日
（2026-10-12，SSE 官方日历）一致；股本/分红口径沿用登记研究包，不额外折算；未发现 PIT 越界
（抓取时间 2026-10-12 ≤ 判定时间）；模型有效性仍为 `UNKNOWN`，G3 人工门未通过。

阻塞字段与来源：

| 阻塞 | 字段 | 来源 | 重开条件 |
| --- | --- | --- | --- |
| 行情晚于研究截止日 | `research_as_of = 2026-10-11` < `quote_date = 2026-10-12` | 研究包 `point_in_time.research_as_of`；归档行情包 | 完成一次覆盖 2026-10-12 的有界研究重登记（含事件窗口复核），再重跑本链 |
| 模型有效性未确立 | `model_validity.status = UNKNOWN` | 已发布决策解释 | 补齐模型有效性复核并留痕 |
| 正式人工门未通过 | `G3_估值门`、`decision_gate = BLOCKED` | 已发布决策解释 | 走既有正式人工审批流程，不得由代理代签 |

登记与执行命令（可复现）：

```powershell
python -X utf8 -B scripts/current/pin_current_quote_bridge.py `
  --symbol 600887 `
  --quote-bundle runtime/quote-sessions/20261012T092313080159Z/bundle.json `
  --research-package runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/package.json
```

登记只记录"哪一份行情"与"哪一版研究"配对，不构成任何批准；准入判定每次读取时重新计算。

## 3. 工作包 C：研究结果进入 Web（`/decisions/600887`）

`GET /api/v1/decisions/600887` 新增 `decision.research.price_bridge_execution`
（只读投影，不重算估值、不产生仓位），页面新增"价格桥接执行（已登记收盘行情）"区块。实测响应摘要：

```json
{"status": "RESEARCH_ONLY", "action": "no_order",
 "research": {"decision_cutoff": "2026-10-11",
  "research_version": "pending-600887-2026-10-11-short-advantage-fc7dba372686",
  "valuation": {"bear": "9.79764118…", "base": "10.07513735…", "bull": "10.30069250…",
                "confidence": "低", "status": "conditional_research_only"},
  "price": {"current_price": null, "quote_admission_status": "PENDING_EXTERNAL_DATA",
            "margin_to_base": null, "margin_to_bear": null,
            "attractiveness_status": "NOT_ASSESSABLE"},
  "price_bridge_execution": {"status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
    "quote_date": "2026-10-12", "display_price": "27.96",
    "price_admitted": false, "comparison_eligible": false,
    "research_day": "2026-10-11",
    "reason": "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性",
    "next_step": "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
    "sources": [{"provider": "tencent", "...": "..."}, {"provider": "sina", "...": "..."}]},
  "position_guidance": null, "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
  "gates": [["financial_facts", "PASS"], ["business_quality", "PASS"],
            ["model_applicability", "BLOCKED"], ["valuation", "CONDITIONAL"],
            ["price_bridge", "BLOCKED"], ["research_gate", "BLOCKED"],
            ["portfolio_gate", "BLOCKED"], ["decision_gate", "BLOCKED"]]}}
```

复现命令（只读，不需要解锁）：

```powershell
cd D:\GPTProject\value-investment
$env:PYTHONPATH="$PWD\src"
python -X utf8 -B -c @"
from pathlib import Path
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
body = TestClient(create_app(root=Path(r'D:\GPTProject\value-investment'))).get('/api/v1/decisions/600887').json()
print(body['status'], body['decision']['research']['price_bridge_execution']['status'])
"@
# -> RESEARCH_ONLY QUOTE_VERIFIED_BUT_RESEARCH_STALE
```

页面把状态码翻成中文并直接给出"是否具备比较资格 + 原因 + 重开条件 + 双源链接与 SHA-256"；
`comparison_eligible` 只有在**共享准入通过**且**已发布桥接为 READY** 时才为真，两者不一致时保持否定。

## 4. 工作包 D：产物、代码与测试

本轮新增/修改的产物：

- 版本化研究执行记录：`runtime/tl7-p1-600887-20261013/research-update.json`
  （SHA-256 `f93afb829397132918078f27f07a976af33f8c8f3f4392620b382c4b59a2a8f6`，入库副本见 `docs/current/tl7-p1-600887-research-update-20261013.json`）
- 价格桥接执行结果：`runtime/tl7-p1-600887-20261013/price-bridge-execution.json`
  （SHA-256 `cff49a5644c88d6f77bd34dd6bad3961b287bb8c81d595ee7539fa90ea666bf2`，入库副本见 `docs/current/tl7-p1-600887-price-bridge-execution-20261013.json`）
- 行情登记：`config/current-quote-bridge.json`（SHA-256 `414551e2579f3826fdf6fb18ad34afab7b10c50a17d2676d24f8b6942ffb751e`）
- 新旧研究差异：见 `docs/current/tl7-p1-600887-research-update-20261013.json#version_diff`
  （发布指针登记日 2026-09-22 → 本次研究截止日 2026-10-11；窗口内无新披露，估值数值复现一致）

代码变更：

- `src/value_investment_agent/application/product/quote_bridge.py`（新增共享准入与登记执行）
- `src/value_investment_agent/application/product/daily_trade_assistant.py`（改为调用共享规则）
- `src/value_investment_agent/presentation/read_models/value_decision_detail.py`（新增 `price_bridge_execution` 投影）
- `src/value_investment_agent/presentation/web_api/app.py`（只读路由接入共享执行）
- `scripts/current/pin_current_quote_bridge.py`（登记用薄 CLI，已登记进两处 CLI 清单）
- `web/src/pages/DecisionDetail/index.tsx`、`web/src/utils/researchDetail.ts`、`web/src/types/api.ts`
- 测试：`tests/test_quote_bridge_execution.py`、`tests/web_api/test_value_decision_detail.py`、
  `tests/test_daily_trade_assistant.py`、`web/tests/research-detail.test.ts`

测试证据（本机实测，真实数据与合成数据严格区分）：

- `tests/test_quote_bridge_execution.py` → 6 passed（其中 1 条读取本机真实归档行情，
  纯 checkout 自动跳过；其余用 monkeypatch 的合成行情验证 fail-closed 与准入分支）
- `tests/web_api` → 127 passed（含 4 条新增跨模块用例：真实执行进入页面、无登记时不编造、
  只有"准入通过 + 已发布 READY"才允许比较）
- `tests/test_daily_trade_assistant.py` → 27 passed（共享规则抽取后行为不变）
- Core Research Gates（220 个测试文件，CI 同一清单）→ 2325 passed, 40 skipped
- 前端 `npm run typecheck` / `npm run format` / `npm test`（34 passed）/ `npm run build` 全部通过

测试能证明：准入规则在 CLI 与 Web 之间一致、fail-closed、页面不会凭空出现价格/边际/仓位。
测试不能证明：价值投资策略有效、估值正确、或本公司已可交易。

## 5. §8 五问五答

1. **600887 是否实际重新执行了研究模型？** 是。入口 `scripts/current/run_daily_trade_assistant.py`，
   输入为研究包 `pending-600887-2026-10-11-short-advantage-fc7dba372686`
   （`3ec6e2c9…22a25b5`），输出为两个运行目录的 `workbench.json`（`c0ae444d…`、`f96a8849…`）等，
   详见上表与 `runtime/tl7-p1-600887-20261013/research-update.json`。
2. **2026-10-12 已核实行情是否桥接到有效研究版本？** 否。实际结果为
   `QUOTE_VERIFIED_BUT_RESEARCH_STALE`：行情 2026-10-12 晚于研究截止日 2026-10-11，
   `price_admitted=false`。已完成的独立工程工作：共享准入模块、登记 CLI、Web 投影、跨模块测试。
3. **本轮产生了什么新的投资研究成果？** 研究链真实重跑并复现同一条件性估值；官方事件窗口
   2026-10-11→2026-10-12 的真实 cninfo 查询为零公告并已归档；因此结论是"无新增证据、研究日期不推进"，
   而不是产生新的估值数字。
4. **Web 是否能够读取这次新的结果？** 能。`GET /api/v1/decisions/600887` 实测返回
   `price_bridge_execution`，页面显示已核验收盘价 27.96（2026-10-12）、桥接状态、比较资格与否、
   原因、重开条件与双源链接；命令见 §3。
5. **本轮产生了哪些实际代码和产物变化？** 见 §4 的代码清单与哈希表；分支
   `codex/web-d1-investment-workbench`，提交见本轮 commit。

## 6. 未解决与下一步

- 研究准入仍为 `NOT_ADMITTED`：需要一次覆盖 2026-10-12 的有界研究重登记（先复核事件窗口），
  之后重跑本链；在此之前不得出现价格比较、边际或仓位。
- `model_validity = UNKNOWN`、`G3_估值门` 与 `decision_gate` 仍需正式人工流程，代理不得代签。
- 真实私人 IPS/组合仍未接入（`BLOCKED_PRIVATE_INPUT`），"买多少"在录入前始终为 `null`。

