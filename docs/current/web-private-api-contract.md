# WEB-D1 private portfolio API contract (frozen 2026-10-12)

Local manual-record API only. Never a broker interface. Every response carries
`action=no_order`. Authoritative arithmetic and state live in Python; the Web
frontend only renders what these endpoints return.

## Storage

- Private root resolution order: environment variable
  `VALUE_INVESTMENT_PRIVATE_ROOT`, otherwise `<user home>/value-investment-private`.
- The root must exist, live outside the repository and every Git worktree, and
  must not sit in a synced directory. Validation reuses
  `value_investment_agent.private_portfolio_intake.require_private_data_path`.
- Journal file: `<private_root>/portfolio/journal.jsonl`, append-only JSON lines.
- Missing root directory while writing: HTTP 503 `PRIVATE_ROOT_UNAVAILABLE`.

## Journal record

```json
{
  "schema_version": "private-portfolio-journal-v1",
  "sequence": 1,
  "recorded_at": "2026-10-12T20:00:00+08:00",
  "kind": "BASELINE_CONFIRMED | FILL_PREPARED | FILL_CONFIRMED | FILL_CANCELLED | RECONCILED_CONFIRMED",
  "previous_record_sha256": null,
  "record_sha256": "64 hex over the record without record_sha256",
  "idempotency_key": "client supplied",
  "request_sha256": "64 hex over the canonical request body",
  "action": "no_order",
  "changes_holdings": false,
  "body": { },
  "response": { }
}
```

Replaying the same `idempotency_key` with the same `request_sha256` returns the
stored `response` without appending. Reusing the key with different content is
HTTP 409 `IDEMPOTENCY_CONFLICT`.

## Authorization (revised 2026-10-13, WEB-D3 P0.2)

Every private read and write requires the local operator session. The launcher
creates the only credential; no endpoint hands one out on request:

1. `scripts/current/start_web_workbench.ps1` generates a per-run bootstrap
   secret, exports it to the server process and opens the workbench with
   `#unlock=<secret>` in the URL fragment. The fragment is never sent to the
   server, never logged and never published with research data.
2. The page posts the secret to `POST /api/v1/private/session/unlock` and
   receives a process-scoped token. Without a launcher secret the server can
   never unlock, and `GET /api/v1/private/session` only reports
   `LOCKED`/`AUTHORIZED` - it never returns a token.
2. The token is sent back in the `X-Local-Session` header on every private
   request, including `GET /api/v1/portfolio`.
3. The server also requires: a loopback TCP peer, a `Host` header naming the
   bound loopback interface and port, and - when `Origin`/`Referer` are present
   - an exact same-origin match including scheme and port. Non-browser clients
   (curl) may omit `Origin`, but must still present the token.
4. `POST /api/v1/private/session/logout` invalidates the token immediately;
   restarting the service invalidates it too, and a logged-out client cannot
   mint a new token by calling the session endpoint again. A rejected request
   never reaches the ledger. `GET /api/v1/system/status` reports
   `"portfolio":"LOCKED"` to unauthorized callers instead of revealing whether
   a private ledger exists.

The token lives in server memory only. It is never logged, written to disk,
published with research data, or committed to Git.

## Endpoints (all under /api/v1)

`GET /private/session` -> 200 `{"action":"no_order","status":"LOCKED",
 "header":"x-local-session","unlock_path":"/api/v1/private/session/unlock"}`
when locked, or `{"status":"AUTHORIZED", ...}` when the request already carries
a valid token. A token is never returned here.

`POST /private/session/unlock` `{"bootstrap_token":"..."}` -> 200
`{"action":"no_order","status":"AUTHORIZED","token":"...","ttl_seconds":43200}`.
A wrong or missing secret is 401 `LOCAL_UNLOCK_REJECTED`.

`POST /private/session/logout` -> 200 `{"action":"no_order","status":"SIGNED_OUT"}`

`GET /portfolio` -> 200
```json
{"action":"no_order","status":"NOT_CONNECTED | CONNECTED","as_of":null,
 "cash_cny":null,"realized_pnl_cny":null,"positions":[],"trades":[],
 "policy":null,"pending_draft":null,"reconciliation":null,
 "blockers":["PRIVATE_PORTFOLIO_NOT_CONNECTED"]}
```

`POST /private/portfolio/initialize`
```json
{"idempotency_key":"str","expected_revision":0,"account_scope":"str",
 "as_of":"YYYY-MM-DD","cash_cny":"0.00",
 "holdings":[{"symbol":"600519","exchange":"SSE","quantity":"1000","cost_basis_cny":"1500000.00"}],
 "sleeve_allocations":{"600519":{"CORE_VALUE":"600","HOTSPOT_SATELLITE":"400"}},
 "policy":{"investable_assets_cny":"2000000.00","minimum_cash_cny":"100000.00",
           "max_single_security_pct":"10","max_single_industry_pct":"30"},
 "confirmation_note":"str","confirmed_at":"ISO8601 with offset","policy_as_of":"YYYY-MM-DD"}
```
-> 200 status `BASELINE_CONFIRMED`, `revision`, `record_sha256`, `portfolio`.

`POST /private/fills/prepare`
```json
{"idempotency_key":"str","expected_revision":1,
 "fill":{"transaction_id":"str","side":"BUY | SELL","sleeve":"CORE_VALUE | HOTSPOT_SATELLITE",
         "symbol":"600519","exchange":"SSE","quantity":"200","price_cny":"1500.00",
         "fees_cny":"5.00","trade_date":"2026-10-12","next_sell_session":"2026-10-13",
         "trading_unit":"100","corporate_action":false}}
```
-> 200 status `FILL_PREPARED`, `revision`, `record_sha256`, `draft`.

`POST /private/fills/confirm`
```json
{"idempotency_key":"str","expected_revision":2,"prepared_record_sha256":"...",
 "confirmed_at":"ISO8601 with offset","confirmation_note":"str"}
```
-> 200 status `FILL_CONFIRMED`, `revision`, `record_sha256`, `portfolio`.

`POST /private/portfolio/reconcile`
```json
{"idempotency_key":"str","expected_revision":3,"reconciled_at":"ISO8601 with offset",
 "confirmation_note":"str"}
```
-> 200 status `RECONCILED`, `revision`, `record_sha256`, `snapshot`.
An optional `account_evidence:{"id":"str","kind":"broker_statement |
account_statement | custodian_statement"}` records that the reconciliation came
from an external statement. Without it the snapshot scope stays
`INTERNAL_JOURNAL_REPLAY`, which is a journal replay and is never presented as
broker reconciliation.

## Reconciliation projection (WEB-D3 P0.1)

`GET /portfolio` and the risk facts report
`reconciliation:{status,superseded,reason,state_version,snapshot_version,scope,reconciled_at}`.
A stored `RECONCILED_CONFIRMED` snapshot stops standing for the current holdings
as soon as a newer `FILL_CONFIRMED` lands: `status` becomes
`PENDING_RECONCILIATION`, `superseded` is true and `reason` is
`SUPERSEDED_BY_NEWER_FILL`. The risk engine is then driven by a freshly derived
pending snapshot, so the projected quantities, cash and reconciliation version
can never contradict the newest confirmed journal record.

`POST /private/fills/cancel`
```json
{"idempotency_key":"str","expected_revision":2,"prepared_record_sha256":"...",
 "cancelled_at":"ISO8601 with offset","reason":"str"}
```
-> 200 status `FILL_CANCELLED`, `revision`, `record_sha256`,
`cancelled_transaction_id`. The voided draft stays in the journal; nothing is
deleted and no holding changes. A cancelled draft stops blocking the next fill.

## Error contract

| HTTP | status | meaning |
| --- | --- | --- |
| 409 | VERSION_CONFLICT | expected_revision does not match the journal revision |
| 409 | IDEMPOTENCY_CONFLICT | key reused with a different request payload |
| 409 | DUPLICATE_TRANSACTION | transaction id already confirmed |
| 409 | ALREADY_INITIALIZED | initialize called on an existing journal |
| 409 | NO_CONFIRMABLE_DRAFT | confirm without a matching prepared fill |
| 422 | VALIDATION_FAILED | malformed or unsafe user input (detail list included) |
| 403 | ORIGIN_REJECTED | request Origin/Referer is not the local workbench |
| 403 | HOST_REJECTED | Host header is not the bound loopback host and port |
| 403 | CLIENT_NOT_LOOPBACK | the TCP peer is not a loopback address |
| 401 | LOCAL_AUTHORIZATION_REQUIRED | missing, invalid or expired local session token |
| 401 | LOCAL_UNLOCK_REJECTED | wrong or missing launcher bootstrap secret |
| 503 | PRIVATE_ROOT_UNAVAILABLE | private root missing or invalid on this machine |

Business states such as NOT_CONNECTED, PENDING_QUOTE_ADMISSION, and an empty
candidate list are normal 200 responses, never 5xx.

## Portfolio projection

positions are grouped per symbol/exchange; each sleeve keeps its own quantity,
cost and next sellable session. Market value, floating profit and portfolio
weight stay null with a PRICE_NOT_ADMITTED blocker until an admitted quote
bridge exists. Realized profit and cash are computed only from confirmed fills.

## Frontend rules

- The frontend never computes cash, cost, sellable quantity, PnL or weights.
- Forms submit raw user input, then render the Python result.
- Draft fills are visibly DRAFT_UNRECONFIRMED and cannot be shown as holdings.
