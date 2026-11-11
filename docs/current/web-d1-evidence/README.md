# WEB-D1 browser evidence (2026-10-12)

Real browser end-to-end pass over the private portfolio path, plus the public
read pages. Everything below was produced by running the app, not by unit tests.

## Environment

- Repository: `D:\GPTProject\value-investment`, branch `codex/web-d1-investment-workbench`
- Read API: `python -m uvicorn value_investment_agent.presentation.web_api.app:app --port 8001`
  with no `VALUE_INVESTMENT_PRIVATE_ROOT`, so the private portfolio is `NOT_CONNECTED`
- Write API: same app on port 8002 with
  `VALUE_INVESTMENT_PRIVATE_ROOT=C:\Users\we\vi-web-e2e-private` (a scratch directory
  outside every Git worktree, required by `require_private_data_path`)
- Browser: Codex in-app browser against `http://127.0.0.1:8002`
- The scratch private root is synthetic test data only. It is not the user portfolio
  and it is deleted after this pass.

## Flow that was executed

1. `/portfolio` rendered `NOT_CONNECTED` with the manual intake form.
2. Initial holdings submitted: account `E2E 合成测试账户`, as-of `2026-10-10`,
   cash `500000.00`, `600519` SSE 1000 shares, cost `1500000.00`,
   sleeve split CORE 600 / SATELLITE 400.
   -> journal `sequence 1` `BASELINE_CONFIRMED`, `status=BASELINE_CONFIRMED`, `revision 1`.
3. A fill was prepared: `E2E-BROKER-20261012-0001`, BUY, `CORE_VALUE`, `600519` SSE,
   200 @ `1500.00`, fees `5.00`, trade date `2026-10-12`, next sell `2026-10-13`,
   trading unit `100`.
   -> journal `sequence 2` `FILL_PREPARED`, `revision 2`.
   The draft preview showed cash `199995.00` and 1200 shares, while the confirmed
   book still showed `500000.00` and 1000 shares: the draft did not leak.
4. The draft was confirmed with the broker note `E2E：已核对合成券商成交单`.
   -> journal `sequence 3` `FILL_CONFIRMED`, `revision 3`, cash `199995.00`,
   one confirmed trade, position 1200 shares at cost `1800005.00`, per-share
   `1500.004166...`, sleeve CORE 800 / SATELLITE 400.
5. T+1 arithmetic held: CORE sellable was 600 of 800 with `next_sell_session`
   `2026-10-13`; SATELLITE 400 stayed fully sellable.
6. Market value, floating PnL and weight stayed `null` behind
   `PRICE_NOT_ADMITTED`; the page showed the blocker and the reason instead of an
   estimated price.

## Journal integrity

`PrivateJournal.read()` re-verifies both the per-record SHA-256 and the
`previous_record_sha256` link of every line:

```
1 BASELINE_CONFIRMED sha=9f4910548b7a prev=GENESIS     changes_holdings=True
2 FILL_PREPARED      sha=5e8002f9514e prev=9f4910548b7a changes_holdings=False
3 FILL_CONFIRMED     sha=f16441522901 prev=5e8002f9514e changes_holdings=True
VIEW status=CONNECTED revision=3 action=no_order cash=199995.00 trades=1
```

Negative checks on copies of the journal:

```
TAMPER_DETECTED: 私人流水第 2 行内容与摘要不一致
CHAIN_GAP_DETECTED: 私人流水第 2 行哈希链断裂
```

The first mutated a fill quantity without recomputing the digest; the second
removed the middle record. Both were refused instead of being projected.

## Screenshots

| File | Page | SHA-256 |
| --- | --- | --- |
| `01-daily-decisions.png` | `/daily` header, market regime, 5573 scanned, 0 formal, 114 research observations, blockers | `57FBDE500C7B765840CD80AFA57425C4B6EC26409AD88021BF3582A02D2C98CF` |
| `02-daily-sections.png` | `/daily` value research observations with 复核动作 `no_order` | `A59F92C9BF15BC661A1A02A4CA962FE52CC0823C9D20D372AD277002BD7854B8` |
| `03-daily-hotspot.png` | `/daily` value table paging plus the empty hotspot section | `AFCA59EFDEF29E01AEF6CE78E654C58792C3335AE3152CB3A956CE92DCE2E133` |
| `04-decision-detail-600519.png` | `/decisions/600519` status, strategy, date, decision id, supporting evidence | `B117896850476436F9805627111BA7EBBB8AB2D47F719045DC15EBFE426C573F` |
| `05-decision-detail-price-context.png` | `/decisions/600519` price and valuation context with `未提供` fields visible | `3DAA651E53153D0F9D8B02DAA9436A4837CB5924B16CF18BCBE860396361B1E6` |
| `06-decision-history.png` | `/history` with `历史数据状态：NOT_CONNECTED` | `9CB13CC8C99C9E05E5C3E9F91E8993F46049E55C0177528AD9A46E01071FDF88` |
| `07-portfolio-connected-8002.png` | `/portfolio` after the pass: cash `199,995.00`, revision 3, one trade, 1200 shares | `8B8818EE08E08A893448D1B6F8E65CECCB27028F0B7B013A58483DF4D15ED622` |
| `08-portfolio-not-connected-8001.png` | `/portfolio` with no private root configured | `3EC3DDA4C5ECE0BC58CD58F989A5EBB9081EB3DC353720448CD6854164018F97` |

## What this proves

- The private write path works end to end through a real browser: initialize,
  prepare, confirm, with the shared API contract and a durable audit chain.
- A prepared draft cannot change holdings until a separate human confirmation.
- Cash, cost, sleeve split and T+1 sellable quantities are recomputed from the
  journal on every read.
- A corrupted or shortened journal is refused rather than projected.
- Public pages render real published data and never invent a candidate action.

## What this does not prove

- It is not evidence that any security is a good investment, and no BUY, ADD,
  TRIM or SELL recommendation was produced. Every payload stayed `no_order`.
- Market value, floating PnL and position weight remain unavailable until a
  verified quote bridge is admitted; only cost basis is real here.
- The synthetic account is not the user portfolio, and the app has no broker
  import, no order routing and no automatic reconciliation.
- `/api/v1/history` still returns no items, and the hotspot section is empty in
  the current publication.

## Reproducing

```powershell
$env:VALUE_INVESTMENT_PRIVATE_ROOT = "$env:USERPROFILE\vi-web-e2e-private"
python -m uvicorn value_investment_agent.presentation.web_api.app:app --port 8002
```

Unset the variable to get the fail-closed `NOT_CONNECTED` page again. The journal
is the single source of truth for this scratch account; deleting the directory
removes the synthetic portfolio.
