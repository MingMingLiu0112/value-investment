# Independent full-project audit (2026-10-16)

`action=no_order`. This audit was executed independently at the request of the
user (VALUE-INVESTMENT-INDEPENDENT-AUDIT-AND-NEXT-LONG-RUN-GOAL). It does not
inherit P9/P10/P11 completion statements; every claim below was re-derived from
code, git state, live services, artifacts, the database and re-run tests.

Audit baseline: branch `codex/web-d1-investment-workbench`, HEAD
`34019fd52d07b68cff831e8ca6441e7527d65db3` (= origin branch after fetch), origin/main
`3e6c5b4`. Working tree: 7 modified files (4 config pointers, LONG-TERM-GOAL.md,
docs/current-stage-goal.md, docs/current/advisory-sentiment-satellite-goal-v1.md)
and 43 untracked entries (P11 evidence bundle + D2 research docs). No existing
file was modified by this audit; the audit added only new `docs/current/*`
deliverables and local scratch evidence under `.tmp/a9/`.

## 1. Executive summary

**Verdict: this is currently a well-engineered research-and-observation system,
not yet an investment-decision assistant.** It can reliably answer "what should
I look at, and why not buy it yet" for a small set of companies and for a daily
hotspot observation list. It cannot yet answer "what should I buy, at what
price, and how much" for any company, and it never claims to.

What is real (independently reproduced this round):

- A daily, hash-bound, dual-source (Tencent/Sina) close-quote acquisition and a
  content-addressed public packet. The embedded raw provider bytes inside
  `runtime/quote-sessions/20261016T090031652233Z/bundle.json` (bundle SHA-256
  `08a8cb10...` verified) were decoded and re-hashed: all five declared document
  hashes match, including Sina `37b88049...` and Tencent `1241d6d6...`.
- A fail-closed product chain: live publication `pub-5f803ec65b6e52fd7de4`,
  engine `daily-public-packet-engine-v18`, runtime identity `MATCHED`
  (backend HEAD = source HEAD = web build commit `34019fd`), 0 formal admissions.
- Real engineering depth under the hood: valuation model router
  (residual-income / FCFF / cyclical), ResearchGate layers, ValueActionPlan,
  a substantial private portfolio/risk engine with an append-only hashed
  journal, and an independent test suite that passes locally (5,684 passed /
  44 skipped) plus 198 web tests and 21 live browser checks at four viewports.

What is not real yet (the honest gap):

- No company has an authorized valuation. All six registry companies are
  `PENDING_RESEARCH`; only two (600519, 600887) even have conditional scenarios,
  and both are explicitly marked "not a reliable current fair value".
- No buy/add/reduce/exit price, no position size, no authorized G3 review.
- The hotspot list is a sector-strength Top-5 activity cut, not a
  structure-qualified opportunity set; its validation is descriptive replay
  only (no costs, fills, OOS or prospective shadow).
- The verified publication chain lives only on this one machine (gitignored
  `runtime/`), and the committed pointers are older than the working tree.

## 2. Current git / runtime baseline (verified, not quoted)

| Item | Observed |
| --- | --- |
| Branch / HEAD | `codex/web-d1-investment-workbench` / `34019fd` |
| Remote sync | `origin/codex/web-d1-investment-workbench` = `34019fd` (fetch via proxy succeeded) |
| origin/main | `3e6c5b4` (a different line; PR #1 open, still Draft) |
| Working tree | 7 modified + 43 untracked; source dirs clean (`runtime_identity` `source_worktree_dirty=false`) |
| CI at HEAD | Core Research Gates run 38881849174 success; Web Workbench run 38881849179 success |
| Live service | `python -m uvicorn ...app:app` on 127.0.0.1:8001 (READ_ONLY), started 19:06 CST by this audit |
| Runtime identity | `MATCHED`; publication `pub-5f803ec65b6e52fd7de4`; web build commit `34019fd`, built 2026-10-16 09:36Z |
| P9 read-only preflight | 38 checks PASS (`scripts/current/audit_p9_readonly.ps1`) |
| Full local test suite | **5,684 passed, 44 skipped** in 15m43s at this HEAD (independent run) |
| Web test suite | **198 passed / 34 files** (independent run) |
| Live browser | **21 checks, 0 failures** at 1280x900 / 1440x900 / 390x844 / 430x844 (independent run) |
| Database | PostgreSQL 16.15 on the Aliyun host via Tailscale, read-only user; 14 tables; `data_points` 188,297 rows (refreshed 2026-10-16 10:30 UTC) |
| Canonical Excel | `C:\Users\we\WPSDrive\...\A股价值投资_Agent前端智能跟踪模板.xlsx`, SHA-256 `aeaa3c7f...` = registered pointer; mtime 2026-10-12 19:33; snapshot as-of 2026-10-01 |

Committed-versus-worktree divergence (material):

- `config/current-daily-public-snapshot.json`: committed = `pub-6167d094c68f6d8105c1`;
  worktree (live) = `pub-5f803ec65b6e52fd7de4` (2026-10-16). Both packet files exist
  on disk; nothing is lost, but a fresh clone points at the older publication.
- `config/current-trial-workbook.json`: worktree registers the new canonical
  workbook SHA `aeaa3c7f...` (matches the real file); the committed form
  references an older SHA (`dd8aa81f...`).

## 3. Real module architecture and status

Independently reconstructed from imports, registrations and live routes:

- ACTIVE (on the live product path): `application/product/daily_public_packet.py`
  (engine v18) -> `application/product/public_snapshot.py` (pointer verification +
  atomic publish) -> `presentation/web_api/app.py` (~30 GET routes) -> `web/src`
  (7 pages). Quote acquisition: `scripts/current/collect_quote_sessions.py` +
  `pin_current_quote_bridge.py`. Hotspot: `domain/hotspot/daily_selection.py`,
  `current_price.py`, `price_action_plan.py`, `opportunity_quality.py`,
  `confirmed_price_structure.py`.
- ACTIVE (private path, never yet exercised with real data):
  `application/portfolio/private_portfolio_service.py` (+ `private_routes.py`,
  15 POST routes: initialize, policy prepare/confirm, fills prepare/confirm/cancel,
  reconcile, costs, held-continuity refresh, risk preview).
- ACTIVE (human-policy path): `application/decision/value_policy_interaction.py`
  exposed at `/api/v1/value-policy-review/{symbol}/preview|confirm`; the local
  operator is resolved as `PolicyPrincipal("local-account-owner")` in
  `app.py:709-713`.
- PARTIALLY_CONNECTED: valuation router (`valuation_router.py` still imports flat
  modules `research_profile` / `valuation_models`); ResearchGate
  (`domain/research/research_gate.py` real, flat shim `research_gate.py` forwards);
  Excel publication chain (frozen snapshot; not fed by the new daily chain).
- LEGACY / engineering-only: the M5 event family (`m5_event_state_store.py`,
  `m5_event_run.py` 1,397 lines) - never imported by the web/public path;
  `workbook_simple_overview.py` (1,371 lines) and `investment_decision.py`
  (1,363 lines) still hold real implementations at the package root.
- DUPLICATED (benign, by design): two publication chains (trial-workbook chain for
  Excel/private/policy surfaces; daily-public-packet chain for the public Web)
  share the same `research_version`.
- Second, older decision pipeline (see section 9) still runs on this machine and
  on the server, outside the live Web path.

Flat-module consolidation is roughly 10% done: 18 root modules are shims, **177
root modules still carry implementation**, of 197 root `.py` files.

## 4. Market data and publication integrity

- The 2026-10-16 session was acquired post-close (17:00:31 CST) from Tencent and
  Sina, together with two SSE monthly calendar documents and one CNINFO
  announcement; all five raw payloads are embedded in the bundle and re-hash to
  their declared SHA-256. Bundle date: `2026-10-16`; six symbols matched
  (600887 28.20, 600519 1329.00, 000333 84.60, 000651 39.49, 600741 15.59,
  601088 50.98 in the acceptance record; the raw payloads are the archive).
- Publication identity is content-addressed and idempotent: my READ_ONLY run
  re-published the same `publication_id` and same packet SHA with a new
  `published_at` only.
- Date separation is honored everywhere in the UI: natural date 2026-10-16,
  latest completed session 2026-10-16, quote date 2026-10-16, research as-of
  2026-10-11, model validity `UNKNOWN`, decision published 2026-10-12, Excel
  snapshot 2026-10-01.
- Correct distinction observed: `REAL_B1_OBSERVED=PASS` (today's session) does
  not imply formal price admission; `PRICE_NOT_ADMITTED` remains for all six.
- Gap: historical minute data for the hotspot arm is single-provider (Sina) and
  "acquired now for past bars"; the replay itself declares
  `HISTORICAL_CLASSIFICATION_PIT_NOT_PROVEN`.

## 5. Value research: the six companies (beyond "a ResearchCase exists")

All six are `PENDING_RESEARCH` in `config/current-company-research-registry.json`
(reviewed 2026-10-16). Layer key: (a) code implemented, (b) research executed on
real evidence, (c) production-validated (authorized valuation + price policy +
eligibility).

| Symbol | Real evidence ingested | Model chosen / why | Honest state |
| --- | --- | --- | --- |
| 600519 Moutai | FY2025 + H1 2026 annual/interim PDFs, share count 1,250,081,601, deducted TTM 81,367,067,677.44 | quality_compounder -> residual income (brand economics, verifiable parent equity) | conditional 437.66 / 587.88 / 812.27; explicitly NOT a reliable fair value; 29 blockers |
| 600887 Yili | 2025 annual + H1 2026 + dividend plan + two Oct announcements (hash-bound) | quality_compounder -> residual income (short advantage, 1+3y decay) | conditional 9.80 / 10.08 / 10.30; `CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED` still holds; 30 blockers |
| 000333 Midea | 2026-06-30 equity-change report, 2026-09-29 HKEX share count (7,464,347,335 ex-treasury), buyback progress | industrial FCFF -> **ruled `MODEL_NOT_APPLICABLE`** (finance subsidiary / consolidation scope), RI authorized | valuation not ready; 6 class-B scenario inputs unregistered |
| 000651 Gree | H1 2026, M1 dossier, FCFF inputs (EBIT 28.84bn, net debt 71.74bn, non-op 238.30bn, 5.601bn shares) | mature_manufacturing FCFF | scope not closed (finance company, restricted cash); 2026-09-23 record `REJECTED_NEEDS_REWORK` |
| 600741 Huayu | FY2025 + H1 2026 + M1 dossier + M2 pending intake | mature_manufacturing FCFF | `COMPLETED_WITH_BLOCKERS`, `decision_admitted=false` |
| 601088 Shenhua | 2025 official PDF, parent profit bridge, net cash bridge, share bridge, IFRS tax review | cyclical cash return -> normalized | route SUPPORTED, **0 of 13 required inputs admitted**; fail-closed |

Only (a) and (b) hold for every company; (c) holds for none.

## 6. Research funnel and its real bottleneck

Layer counts (M2 live receipt 2026-10-12 + packet re-check 2026-10-16):

- Universe 5,573; quotes matched 5,573; **financial evidence only 873 (15.7%)**;
  dividend evidence 3,622; industry mapping 5,573.
- Screening passes: cyclical 50, dividend 50, value 50, **quality 0**
  (4,677 dropped for data gaps). Distinct leads: **114**.
- Queue: 114, all `research_state=DATA_CHECK`; 10 selected for data check;
  104 budget-deferred.
- Deep research executed on real evidence: 600519 + 600887 (daily batch),
  600741 (M2 intake).
- Model admissions 0; formal admissions 0.

Root cause is the thin evidence base, not the model code: no company can reach
`quality` because official financial evidence is admitted for 15.7% of the
market, and the 114 surviving leads are then capacity-limited. The gate chain
itself (G0 evidence -> G1 scope -> G2 thesis -> G3 typed human receipt ->
model validity -> price bridge -> registered price policy -> private IPS) is
correctly fail-closed; today nothing can traverse it end-to-end.

## 7. Economic-model audit (what the numbers really are)

- Residual income: anchored on deducted TTM as a starting proxy; 1+3y
  full-capital ROE decay (600887) or 10+5y (600519); terminal ROE = cost of
  equity, g = 0; no DPS floor and no distributable-cash proof. The TTM/spread
  ratio (~17.96% for Yili) is a proxy, not a verified average-equity ROE.
- FCFF: WACC hard-coded at 8.5% for 000651/600741; reinvestment = capex - D&A +
  dWC with no maintenance/growth split; tax only when EBIT>0; scenario output
  carries `evidence_authenticated=false / assumptions_validated=false`.
- Cyclical: 13 required inputs, monotone-ordered scenarios, finite-annuity
  factor; `distributable_cash = profit*(1-cash_tax) - maintenance_capex -
  normalized_WC`; no parent distributable bridge; 0/13 admitted (correctly
  fail-closed).
- Scope hygiene: no arithmetic double-counting found in code, but the evidence
  layer mixes consolidation and parent scopes: 600519 consolidated CFO includes
  a finance company's absorption of member deposits (H1 70.69bn); 600887
  consolidated CFO 9.759bn vs parent 35.552bn cannot be added, and 48.141bn of
  bill discounting is a real external obligation; 000651/600741 FCFF inputs are
  consolidated. These are labelled risks, not yet resolved inputs.
- **P0 integrity finding**: `scripts/build_m1_post_review_receipts.py` (self-declared
  `ONE_OFF_REVIEW_RECEIPT_GENERATOR`) contains a hard-coded `APPROVAL_SPECS` map
  and emits records named `*-g3-human-approval-*` with
  `reviewer_type="human_research_lead"`, identical `reviewed_at`
  (2026-09-23T05:30:00+00:00), no reviewer identity, all with
  `price_assessment_eligible=false`. They live only in an untracked runtime
  bundle, are not consumed by `src/` or `config/`, and the current chain records
  `RESEARCH_REVIEW_NOT_G3_APPROVAL`. No active bypass exists, but a record that
  looks like a G3 human approval and is machine-generated is a forgery-shaped
  artifact that must be retired or renamed before any real G3 flow ships.

## 8. Hotspot / price-action arm

- Selection: `daily_selection.py` sorts by (industry relative strength, turnover,
  symbol) and slices `ordered[:limit]` with `structure_tier="UNASSESSED"`;
  structure is assessed only afterwards. Today: 5,226 classified, 5,216 dated,
  5,021 ranked, 10 quote failures, 31 industries, and **5 of 5 candidates from
  one industry (defense)**. Top-5 is therefore applied too early; a
  structure-qualified stock outside the day's sector-strength cut is never
  assessed.
- Price action: entry = completed close above prior-five high with volume >= 1.2x
  prior-five mean; invalidation = close below prior-five low; confirmation =
  next completed 60m bar holds; risk/reward = structural distance, explicitly not
  expected return. Live cases are post-close, completed-bar and calendar-bound
  (correct PIT for the current session); intraday structure is single-provider.
- Validation classification: **code replay + descriptive event statistics only**
  (dev 212 cutoffs / 15 triggers / failure-proxy 0.267; validation 280 / 25 /
  0.286). `net_return_distribution`, verified fills, and shadow sessions are
  null/0; `performance_claim_allowed=false`.
- Held continuity: positions are tracked independently of Top-5
  (`ACTUAL_HELD_SECURITY_NOT_RANKING`), invalidation is re-checked, T+1/sellable
  is modeled per lot. Two gaps: `next_sell_session` is user-supplied with no
  exchange-calendar validation, and held-risk "announcement review" is a static
  placeholder with no wired feed.

## 9. Second pipelines that still run (dual-source risk)

This is a real, currently-active duplication that earlier acceptance rounds did
not consolidate:

- Windows scheduled tasks (enabled, ran today): `ValueInvestmentAgent-DailyUpdate`
  (17:05, exit 0), `ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh` (14:45,
  exit 0), `ValueInvestmentAgent-MoutaiB1ExcelPublish` (17:30, **exit 1 =
  fail-closed "not_published"**); `MoutaiPostclosePolicyStage` disabled. These
  drive the legacy 600519 stage-B valuation and its Excel publication attempt.
- Server-side DB pipeline (Docker/systemd on the Aliyun host, writing the same
  PostgreSQL): today `collect-filings`, `enrich-financials`, `refresh-valuations`
  etc. ran ~37 times since 2026-10-15 and refreshed `valuation_results` (888 rows:
  765 awaiting valuation, 76 missing, 37 abnormal, 10 model-valuation pending
  review; **0 rows with `target_weight>0`**). It emits no buy signal today, but it
  is a second, independent state producer with its own vocabulary.

Neither is on the live Web path, and neither currently contradicts `no_order`.
Their continued existence is what makes "two decision sources" a genuine audit
finding rather than a theoretical one.

## 10. Private portfolio, risk and the first real-use path

- Implementation is substantial and fails closed: append-only hashed journal with
  file locking outside the repo (`C:\Users\we\value-investment-private\portfolio`),
  prepare/confirm/cancel fills, partial sells, cash/cost/realized/unrealized
  equity projection, dual-sleeve budgets, per-trade risk, cash floor, lot size,
  costs, slippage, gap stress, liquidity, limit up/down, cross-pool same-symbol
  and industry caps.
- Actual state: the private root contains only `journal.jsonl.lock`; no account,
  IPS or fills exist. `REAL_PRIVATE_PORTFOLIO = BLOCKED_PRIVATE_INPUT` is
  accurate. `GET /api/v1/portfolio` returns 401 while locked; the service never
  fabricates cash or positions.
- The T+1 helper accepts any strictly-later date (a Saturday would pass code
  validation; the UI only warns), and held-risk announcements are a placeholder.

## 11. Agent capability (honest assessment)

- A bounded three-role orchestration exists (`application/research/agent_review/`:
  fundamental / counter-evidence / event) with snapshots, source-context
  verification and no admission authority, plus a provider-neutral Chat
  Completions adapter and a mock provider.
- Only **mock** runs exist (`runtime/agent-research-pilot-20261009/*mock-llm*`,
  scopes `MOCK_LLM_RESEARCH_NOT_ADMITTED`); no live LLM credentials are
  configured in `.env` and no live run artifact exists.
- Deterministic Python remains the only producer of numbers, as required. The
  agent layer is therefore "rehearsed", not "operational".

## 12. Web product acceptance (performed live this round)

Pages: `/daily`, `/decisions/:id`, `/portfolio`, `/history`, `/system`,
`/historical-price/:symbol/:day`. 21 checks at 4 viewports: 0 failures, no
horizontal overflow, no stale-as-current display, version identity consistent.
A user today sees: research date and quote date on the first line; "0 formal
admissions"; two value names with conditional ranges and the sentence "not yet
admitted, scenarios are not buy prices"; five hotspot names all `WATCH`, four of
them explicitly "does not meet current entry conditions"; a locked private page
with a one-time unlock link; and a system page that maps internal codes to
readable text with raw codes hidden in a collapsible section.

Product-level divergences worth stating plainly:

- The **Excel** interface the user originally asked for is frozen at the
  2026-10-01 snapshot (published 2026-10-12), while the Web is live through
  2026-10-16. Two user-facing surfaces now disagree by ~15 days.
- `runtime-identity`'s dirty check covers source dirs only, so it reports
  `MATCHED` while config pointers are uncommitted (observed).

## 13. Persistence, backup and recovery

- `runtime/` is gitignored (`.gitignore:25`) and contains **0 tracked files**;
  every verified publication, receipt, quote bundle and incremental-validity
  artifact lives there. A fresh clone of this repo cannot verify any pointer.
- `artifacts/current/tl11-p61-20261015/*` (16 files) and ~24 D2 research docs are
  untracked; the tracked P8 bundle is committed.
- Single points of failure: (1) this machine's `runtime/`; (2) the WPS-cloud
  canonical workbook; (3) the private journal directory (empty, but outside
  version control by design).
- Backup tooling exists (encrypted `.viabackup` from 2026-10-01 under
  `backups/server-backup/`, AES-256-GCM config, server-side restore drill
  script), but no restore rehearsal of `runtime/` + canonical Excel was
  performed or evidenced in this audit.

## 14. Maintenance cost and security posture

- Scale: 461 `src` .py files (197 at package root), 737 `scripts/` entries
  (563 at scripts root), 682 test files, 784 directories under `runtime/`
  (including dozens of `.pytest-*` basetemps), and 16 timestamped copies of
  systemd units under `deploy/server/`.
- Security: local loopback-only host binding, per-run bootstrap secret + session
  token, private data outside the repo, keys by env-var name only, CI read-only
  permissions, `.env` untracked. Noted: `docker-compose.yml` ships
  `POSTGRES_PASSWORD: change-me` (only relevant if that compose DB is used).

## 15. Corrections to earlier completion claims

1. "Latest evidence" a reader would pick up (`artifacts/current/tl11-p61-*`) was
   produced with engine v9 and is superseded by the tracked P8 bundle and the
   live v18 pointer. It is not currently wrong, but it reads as current.
2. The 2026-09-23 `*-g3-human-approval-*` records are machine-generated; they
   are not G3 approvals and must not be counted as human review.
3. "Canonical Excel updated" is only true as a 2026-10-01 snapshot; the live
   daily data has not reached the Excel since.
4. The committed config pointers do not match the working tree; "the repo says
   X" and "the machine runs X" are different statements until committed.
5. Earlier claims of "reading time / model validity" progress remain accurate,
   but `research_as_of` is still 2026-10-11 while quotes are 2026-10-16; the
   incremental-validity path is `PENDING_HUMAN_REVIEW`, not complete.

## 16. Three top-level conclusions

1. **Engineering foundation**: solid and unusually disciplined for a solo
   project (fail-closed, hash-bound, version-identified, test-dense). Status:
   PASS-with-debt. Its biggest engineering risk is not correctness but
   single-machine data custody and the un-consolidated legacy pipelines.
2. **Real assisted-use readiness**: NOT_READY. The user can observe and
   prioritize, and can already enter private data, but no workflow produces an
   actionable, authorized decision.
3. **Investment-decision quality**: NOT_PROVEN for both arms. No valuation is
   authorized; no strategy edge is validated. The largest single shortfall is
   the value arm's economic evidence base (normalized earnings, invested-capital
   returns, parent distributable cash, issuer-specific cost of equity, advantage
   period), which gates everything downstream.

The maturity matrix with all 20 required dimensions and evidence is in
`docs/current/independent-capability-matrix.json`; the prioritized engineering
gaps are in `docs/current/independent-prioritized-backlog.md`; the next-stage
execution prompt is `docs/current/next-long-run-goal-prompt.md`; the plain-language
user status is `docs/current/project-status-for-user.md`.

## 17. Not verified / NOT_RUN in this audit

- No live LLM provider run (no credentials configured).
- No real private account data (none exists); the private flow was verified as
  fail-closed, not end-to-end with real numbers.
- No restore drill executed for `runtime/`, PostgreSQL or the canonical Excel.
- No exchange-calendar validation test of private T+1 sellability.
- No inspection of the Aliyun host itself (only its database and its DB pipeline
  effects); the PTA project was not touched.
- Historical minute-level PIT/OOS for the hotspot arm cannot be verified with the
  single provider available today.

`action=no_order`.
