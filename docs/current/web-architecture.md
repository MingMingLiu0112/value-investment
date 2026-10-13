# WEB-D1 boundary and current baseline

The Web workbench is a local presentation and manual-input surface. It does not
replace the canonical WPS workbook, valuation engine, research gates, decision
restoration, or private portfolio authority. Every output has `action=no_order`.

## Baseline audit (2026-10-12, `3e6c5b4`)

| Capability | Existing code | Current actual data | Web reuse | Gap |
| --- | --- | --- | --- | --- |
| Market-wide discovery | M2 manifest, `marketwide_daily`, value research queue | 5,573 securities; queue is research-only | Hash-bound published product extension | Provider trade date unverified; quality pass count zero |
| Value decision | ResearchCase, DecisionRecommendation v3, replay/restore | 600519 and 600887 are not formal buy candidates | Existing explanation and product read model | G3, event/model/price gates remain incomplete |
| Hotspot observation | Hotspot scan, watch queue, dual-sleeve public summary | Classification date unknown | Published observation only | Not formal entry/exit eligible |
| Logic explanation | `value_decision_explanation.py` and product read model | Bound research for two fixed companies, pending 600741 | Verified read-only projection | No generic approved decision for new companies |
| Manual PLAN/FILL/REVIEW | `application/portfolio/private_portfolio_service.py` journal; hash-chain `dual_sleeve_records.py` | No user-confirmed private fills in the canonical root | Implemented: prepare / confirm / cancel with audit chain | Still manual; no broker import and no automatic reconciliation |
| Cash and holdings | Private portfolio journal + PortfolioSnapshot and risk contracts | Private portfolio `NOT_CONNECTED` until the user confirms a baseline | Implemented: user-confirmed baseline, fills, cash, T+1 sellable | Market value and weights stay `null` while `PRICE_NOT_ADMITTED` |
| Dual-sleeve risk | `dual_sleeve_risk.py` | Public result is blocked private input | Show exact blocked status | No personal budgets or holdings |
| Publication | Canonical Excel pointer, receipt, bound runtime read model | WPS publication verified, final user acceptance not passed | Read bound product state; no workbook mutation | Runtime artifacts local to this machine |

## Data flow

```
Existing research/decision/portfolio application services
  -> hash-bound public product read model -> thin FastAPI read API
  -> React pages

User-confirmed private inputs -> isolated application reconciliation
  -> existing PortfolioSnapshot / dual-sleeve risk contracts
  -> private API only after local authorization and durable audit are verified
```

The current public API may show research observations and blocked states. It must
never derive a candidate action from price, PE, a screening rank, or UI state.
An observed quote is not a PriceBridge. A manually recorded FILL is not a
reconciled PortfolioSnapshot. Missing source artifacts fail closed, without
falling back to fabricated sample content.

## Private portfolio journal

The private ledgers live outside the repository, under
`VALUE_INVESTMENT_PRIVATE_ROOT/<account_scope>/portfolio/journal.jsonl`. When the
variable is unset the default root is `~/value-investment-private`. The strict
guard in `private_portfolio_intake.require_private_data_path` rejects any path
inside a Git worktree, so a journal can never be committed by accident, and every
`/api/v1/portfolio` read fails closed to `NOT_CONNECTED` when no journal exists.

The journal is append-only JSONL. Each record carries `schema_version`,
`sequence`, `previous_record_sha256`, `record_sha256`, `idempotency_key`,
`request_sha256`, `action=no_order`, `changes_holdings`, `body` and `response`.
Writes use canonical JSON, `flush` and `fsync`. The whole read-check-commit
transaction runs inside an OS-owned cross-process lock (`msvcrt.locking` on
Windows, `fcntl.flock` elsewhere), so a competing process cannot pass the same
revision check and the lock is released automatically if a writer crashes.
Reads re-verify both the per-record digest and the chain link, so a mutated byte
or a removed record raises `JournalValidationError` instead of silently
projecting a wrong portfolio.

Record kinds: `BASELINE_CONFIRMED`, `FILL_PREPARED`, `FILL_CONFIRMED`,
`FILL_CANCELLED`, `RECONCILED_CONFIRMED`.

Replay projects confirmed state and confirmed fills only. A prepared draft is
returned as `pending_draft` with its own preview, is never merged into
`positions`, `cash_cny` or `trades`, and must be either confirmed or cancelled.
Confirming a fill requires the `prepared_record_sha256` of the draft, so a draft
cannot be silently swapped for a different trade; `expected_revision` and
`idempotency_key` make retries safe.

## Web routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/daily-decisions` | Published product read model: universe, formal candidates, research observations, hotspot observations, dual-sleeve status and the private inputs it still misses |
| GET | `/api/v1/decisions/{symbol}` | Research explanation, evidence, blockers for one security |
| GET | `/api/v1/decision-history` | Real, hash-verifiable research versions per security plus a mechanical field diff; `PREVIOUS_UNAVAILABLE` when only one version exists |
| GET | `/api/v1/portfolio` | Private portfolio view, or a fail-closed disconnected projection |
| GET | `/api/v1/private/portfolio/risk` | Confirmed private facts plus the dual-sleeve risk engine report, or its exact missing-input gaps |
| GET | `/api/v1/private/session` | Mint the process-scoped local operator token |
| POST | `/api/v1/private/session/logout` | Invalidate the local operator token |
| POST | `/api/v1/private/portfolio/initialize` | Record the user-confirmed opening baseline |
| POST | `/api/v1/private/fills/prepare` | Append a `FILL_PREPARED` draft |
| POST | `/api/v1/private/fills/confirm` | Promote a draft with its `prepared_record_sha256` |
| POST | `/api/v1/private/fills/cancel` | Void a draft without touching holdings |
| POST | `/api/v1/private/portfolio/reconcile` | Append a confirmed reconciliation snapshot |

Every private read and write is authorized by `presentation/web_api/local_auth.py`
before it touches anything: the TCP peer must be loopback, the `Host` header must
name the bound loopback host and port, `Origin`/`Referer` when present must match
that origin exactly (scheme included), and the request must carry the
process-scoped `X-Local-Session` token minted by `GET /api/v1/private/session`.
Non-browser clients may omit `Origin` only when they present the token. Domain
failures map onto `503 PRIVATE_ROOT_UNAVAILABLE`, `409 <JournalConflict.code>` and
`422 VALIDATION_FAILED`; authorization failures answer `401
LOCAL_AUTHORIZATION_REQUIRED`, `403 HOST_REJECTED`, `403 CLIENT_NOT_LOOPBACK` or
`403 ORIGIN_REJECTED` and never reach the ledger. All private routes run on the
same `127.0.0.1`-bound server as the read API.

## Presentation rules

## Private ledger backup and restore (WEB-D2 P0.3)

`scripts/current/backup_private_portfolio.py` is the only supported maintenance
entry point (`create | list | verify | restore`). Bundles live at
`<private_root>/portfolio/backups/<backup_id>/` and may not be created anywhere
outside the private root, so they can never enter Git or a synced folder. Each
bundle carries a byte-verbatim `journal.jsonl` plus a `manifest.json` with
`source_sha256`, `copied_sha256`, `record_count`, `head_record_sha256`,
`source_status` and its own `manifest_sha256`.

`restore` refuses to run without an explicit `--confirm`, refuses any bundle
whose verification is not `VERIFIED`, never truncates or repairs a damaged
record, and takes a `pre-restore-*` safety bundle of the current bytes before it
replaces anything. Snapshot and restore run under the same cross-process journal
lock as an append. A hash chain detects tampering; it cannot stop an attacker who
can rewrite the whole file, which is why the backup must stay on a path the
project itself never publishes.

## Presentation rules

- Money is rendered with two decimals and thousands separators; per-share cost
  keeps up to four decimals so fee dilution stays visible. Raw backend `Decimal`
  strings must never reach the user.
- A field the backend reports as `null` is rendered as unavailable, not dropped.
  The company page must always show `当前价`, `margin_to_base`, `margin_to_bear`
  and `quote_status` even when the quote is not admitted yet.
- `行情未准入` / `PRICE_NOT_ADMITTED` blocks market value, floating PnL and weight.
  The UI shows the blocker and the reason instead of estimating a price.

## Static bundle serving

The API serves `web/dist` at the root. Any request is first resolved against the
built bundle; only unmatched paths fall back to `index.html` for SPA routing. An
unconditional catch-all previously answered `/umi.js` with HTML, which broke the
page with a JavaScript parse error.

## Verification

`tests/web_api/` covers the read contract, the private service and the private
routes, including origin refusal, draft isolation, hash-chain tamper detection,
idempotency and revision conflicts. A real browser end-to-end pass over
initialize -> prepare -> confirm on a scratch private root is recorded in
`docs/current/web-d1-evidence/`.
