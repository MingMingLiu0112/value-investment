# WEB-D3 交付：可信交易状态、单票真实研究决策闭环（2026-10-13）

分支：`codex/web-d1-investment-workbench`；PR #1 保持 **Draft**，未合并 `main`。
本文件只描述本轮实际执行的工程与只读验证结果。

## 状态

```text
ENGINEERING_DELIVERY              = DONE（本轮 §1-§6 工程项，已在分支实现并有测试证据）
CURRENT_RESEARCH_ADMISSION        = 0 家公司通过正式准入（600887/600519 仍为 RESEARCH_ONLY / NO_ACTION）
FINAL_OPERATIONAL_ACCEPTANCE      = NOT_PASSED（缺真实 IPS/组合、真实行情准入与 Windows 用户验收）
```

工程交付不等于投资准入，也不等于系统可用。三类状态互相独立。

## 1. 修改过的实际代码

P0.1 交易状态一致性（`8a04734`）

- `src/value_investment_agent/application/portfolio/private_portfolio_service.py`
- `src/value_investment_agent/application/portfolio/private_risk_projection.py`
- `tests/web_api/test_private_risk_projection.py`、`tests/web_api/test_private_portfolio_api.py`

新增 `snapshot_version` / `snapshot_scope`；对账范围区分 `INTERNAL_JOURNAL_REPLAY`（本系统流水重算）
与 `EXTERNAL_ACCOUNT_STATEMENT`（仅当提交 `account_evidence` 时）。风险引擎只复用版本、现金、数量
三项都一致的快照，否则重新投影并标记 `PENDING_RECONCILIATION`。

P0.2 本地授权边界（`b9d9b34`）

- `src/value_investment_agent/presentation/web_api/local_auth.py`
- `src/value_investment_agent/presentation/web_api/private_routes.py`
- `src/value_investment_agent/presentation/web_api/app.py`
- `scripts/current/start_web_workbench.ps1`、`web/src/services/api.ts`
- `tests/web_api/test_local_auth.py`、`tests/web_api/test_private_write_auth.py`、`web/tests/api-session.test.ts`

服务默认锁定；只有启动脚本生成的每次运行凭证可以解锁（`POST /api/v1/private/session/unlock`）。
`GET /api/v1/private/session` 不再返回任何 token；未授权调用 `/api/v1/system/status` 只看到
`"portfolio":"LOCKED"`。

P1.3 发布异常 fail-closed（`38c269e`）

- `src/value_investment_agent/presentation/web_api/app.py`、`web/src/types/api.ts`、
  `web/src/pages/DailyDecisions/index.tsx`、`tests/web_api/test_read_api.py`

发布链缺失/损坏/hash 不符/条目数与报告不一致时返回 `UNAVAILABLE`，不再给出可被误读的计数。

P1.4 单票真实研究决策闭环（`ead1dc1`、`89b1569`、`417a183`）

- `src/value_investment_agent/presentation/read_models/value_decision_detail.py`
- `src/value_investment_agent/presentation/web_api/app.py`（`GET /api/v1/decisions/{id}` 附加 `research`）
- `web/src/pages/DecisionDetail/index.tsx`、`web/src/utils/researchDetail.ts`
- `tests/web_api/test_value_decision_detail.py`、`web/tests/research-detail.test.ts`

P1.5 历史语义拆分（`d031141`）

- `src/value_investment_agent/presentation/read_models/research_history.py`
- `tests/web_api/test_decision_history.py`

区分“研究提案历史”和“已发布决策历史”；逐条重算声明摘要，报告 `VERIFIED/HASH_MISMATCH/MISSING/
OUTSIDE_ROOT/...`，并把无法解析的提案列入 `skipped_proposals` 而不是静默丢弃。

P1.6 对账投影与界面（`7ec2a61`）

- `web/src/components/DualSleeveRisk.tsx`、`web/src/pages/Portfolio/index.tsx`、
  `web/src/utils/codes.ts`、`web/src/types/api.ts`、`web/tests/reconciliation.test.ts`

契约文档：`docs/current/web-private-api-contract.md`（`f705718`）
CI 修复：`tests/web_api/test_decision_history.py`（`09b116a`，见 §4）

## 2. 一只公司从研究输出到 Web 详情的可复现命令

前置：本地存在已发布研究物（`runtime/` 不入库，纯 checkout 无此文件）。

```powershell
cd D:\GPTProject\value-investment
$env:PYTHONPATH="$PWD\src"
python -X utf8 -B -c @"
from pathlib import Path
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
body = TestClient(create_app(root=Path(r'D:\GPTProject\value-investment'))).get('/api/v1/decisions/600887').json()
print(body['status'], body['decision']['research']['research_binding'])
"@
```

浏览器路径：`scripts/current/start_web_workbench.ps1` 打印一次性解锁链接，打开后进入
`/daily` → 点击“伊利股份” → `/decisions/600887`。

## 3. 可读产物示例（真实数据，2026-10-13 实测）

```json
{"action": "no_order", "status": "RESEARCH_ONLY",
 "decision": {"symbol": "600887", "name": "伊利股份",
  "research": {
   "research_binding": {"status": "VERIFIED",
    "path": "runtime/daily-trade-assistant/20261012-productization-canonical-publish-v5/600887-value-decision-explanation.json",
    "sha256": "54ecf79bd1e1f752d32dd9d7032224f8aa2ee3d557265b84600475ad99454049"},
   "decision_cutoff": "2026-10-11",
   "valuation_model": "residual_income_or_equity_value",
   "valuation": {"bear": "9.79764118...", "base": "10.07513735...", "bull": "10.30069250...",
    "confidence": "低", "status": "conditional_research_only"},
   "price": {"current_price": null, "quote_admission_status": "PENDING_EXTERNAL_DATA",
    "margin_to_base": null, "attractiveness_status": "NOT_ASSESSABLE"},
   "gates": [{"financial_facts": "PASS"}, {"business_quality": "PASS"},
    {"model_applicability": "BLOCKED"}, {"valuation": "CONDITIONAL"},
    {"price_bridge": "BLOCKED"}, {"research_gate": "BLOCKED"},
    {"portfolio_gate": "BLOCKED"}, {"decision_gate": "BLOCKED"}],
   "suggested_state": {"value": "NO_ACTION"},
   "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "position_guidance": null}}}
```

页面按阅读顺序展示 10 个区块：研究结论与数据日期 → 支撑逻辑与关键反证 → 估值区间与适用模型 →
价格与估值的关系 → 当前缺失的证据与门禁 → 为什么状态允许或不允许变化 → 影响结论失效的事件 →
官方证据与历史版本入口。价格区在无准入行情时显示“暂不可评估 + 原因 + 需要补充”，不会产出
安全边际、仓位或订单。

## 4. 测试证据

成功场景（本机实测）

- `tests/web_api` → 124 passed（`python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/bt-webapi tests/web_api`）。
- Core Research Gates（220 个测试文件，CI 同一清单）→ 2325 passed, 40 skipped in 124.59s。
- 前端：`typecheck` 通过、`format` 通过、`npm test` 31 passed / 8 files、`npm run build` 成功。
- 真实发布物只读验证：`GET /api/v1/decisions/600887` → `RESEARCH_ONLY`，绑定摘要重算一致。
- 运行中的工作台：`GET /api/v1/system/status` → `"portfolio":"LOCKED"`；解锁后 `GET /api/v1/portfolio`
  → `NOT_CONNECTED` + `PRIVATE_PORTFOLIO_NOT_CONNECTED`（未接入真实组合，未编造持仓）。

阻塞场景（反例，均实测）

- 启动凭证错误 → 401 `LOCAL_UNLOCK_REJECTED`；未解锁读取私人接口 → `LOCAL_AUTHORIZATION_REQUIRED`。
- 发布链缺失/损坏/hash 不符/计数不一致 → `UNAVAILABLE` + `gate_code`（`tests/web_api/test_read_api.py`）。
- 新增确认成交后，旧对账快照不再被复用 → `PENDING_RECONCILIATION`（`test_private_risk_projection.py`）。
- 提案文件不可解析 → 进入 `skipped_proposals`，不进入历史，也不冒充有效版本。
- 干净 checkout（无 `runtime/`）→ 真实发布物相关测试 **skip 而不是 fail 或假装通过**；
  本地有发布物时同一测试实际运行（`122 passed, 2 skipped` ↔ `124 passed`）。

测试能证明什么：工程契约、失败关闭、状态语义、真实发布物的可追溯绑定。
测试不能证明什么：估值正确、策略有效、投资准入或可交易——这些需要独立证据与人工批准。

## 5. 新增接口与契约兼容

- `POST /api/v1/private/session/unlock`：新增。旧客户端调用 `GET /api/v1/private/session` 仍返回 200，
  但不再收到 token；改为先解锁。这是有意的破坏性收紧，已更新 `docs/current/web-private-api-contract.md`。
- `GET /api/v1/private/session`：`token` 字段移除；新增 `unlock_path`。
- `GET /api/v1/portfolio`：新增 `reconciliation`，可能为 `null`；`status` 取值不变。
- `GET /api/v1/system/status`：未授权时 `portfolio` 固定为 `LOCKED`，不再暴露是否存在私人台账。
- `GET /api/v1/decisions/{id}`：新增 `decision.research`；缺失时保持旧结构，前端回退旧渲染。
- `GET /api/v1/decision-history`：新增 `research_proposal_history`、`published_decision_history`、
  `historical_reconstruction`、`skipped_proposals`；原字段保留，`evidence` 项新增 `status`。
- `GET /api/v1/daily-decisions`：失败时可返回 `status=UNAVAILABLE`、`summary.universe_count=null`
  且 `watch_count=null`；正常路径字段不变。

## 6. PR #1 与剩余 blocker

PR #1（`[Draft] WEB-D1 本地双策略研究与人工持仓工作台`）保持 Draft，等待审查，不合并。
CI：Core Research Gates 通过；Web Workbench 因“干净 checkout 缺少 runtime 发布物”一度失败，
已用显式 skip 修正（`09b116a`）。修正后 GitHub Actions 全部通过：
`Core Research Gates` run 349（PR）与 `Web Workbench` run 12（push）、run 13（PR）均为
completed successfully。

必须先说明、且不得由本系统代签的缺口：

- 600887：双源行情已核实但 `price_admitted=false` → `QUOTE_VERIFIED_BUT_RESEARCH_STALE`
  （登记的研究截止 2026-09-22 早于 2026-10-12 报价）；G3 与模型有效性批准仍为 false。
- 000333 美的：需要 2026-06-30 普通股股数分母才能准入财务事实；当前只有测试夹具，没有真实研究案例。
- 601088 中国神华：周期研究未开始，前置条件未满足。
- 私人仓位：缺少真实 IPS/组合/现金/风险约束，风险投影始终停在 `BLOCKED_PRIVATE_INPUT`。
- 本地解锁只约束自动化与浏览器来源，不能阻止同一用户的恶意本地进程；`https://localhost` 源仍被接受。

## 7. 下一阶段最小可执行工作包

`NEXT: TL7-P1 让 600887 的研究截止日与已核实报价重新对齐（不调参、不代签）`

- 目标：把“行情已核实但研究过期”这一具体冲突变成一次有界重算请求，产出新的待人工复核材料。
- 影响文件：`src/value_investment_agent/presentation/read_models/value_decision_detail.py`、
  `presentation/web_api/app.py`、`tests/web_api/test_value_decision_detail.py`，必要时在
  `runtime/` 生成新的重算产物（不改写旧产物）。
- 禁止：修改估值公式、门槛、G3 批准状态；伪造行情或规则版本；把 `NO_ACTION` 改成买入。
- 验收：Web 详情显示“报价已核实、研究需重算”的明确原因与所需证据；`action=no_order` 不变；
  其余公司不受影响；新增反例测试。

永久边界：`action=no_order`；不接券商、不自动下单；`Research Attractive != Buy Signal`；
`High Dividend Yield != Buy Signal`；`Margin of Safety != Position Size`；
`Current Price != Intrinsic Value`；`Backtest != Shadow`。
