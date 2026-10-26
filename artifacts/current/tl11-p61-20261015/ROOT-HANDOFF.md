# P6.1 Daily Refresh / B1 Handoff

Scope complete: daily refresh, completed-session dates, B1, bounded collection,
partial results and failure recovery. No commit or push. HEAD remains
35c0c4e6d7519febc66cf44e9e0280688e6fe411. Unrelated concurrent changes are not
part of this package. Frontend, app.py, private accounts, WPS and Goal documents
were not edited by this package. No service was started; HTTP checks used the
existing loopback service on port 8001.

## Actual Windows Runs

PowerShell 7.6.6, 2026-10-15 Asia/Shanghai, before the session closes:
latest completed trading session = **2026-10-14**.

- Initial default SAFE_REFRESH -NoServer: SUCCESS, exit 0, reused verified inputs.
- Explicit SAFE_REFRESH -NoServer -Symbols 600887,000333: PARTIAL, exit 3.
  Actual Tencent/Sina responses at 10:18:21 were intraday_quote for both symbols;
  neither was registered as a formal close. Existing verified observations stayed
  available. Missing 000333 registered close remains PENDING_EXTERNAL_DATA.
- Default SAFE_REFRESH -NoServer recovery: SUCCESS, exit 0, finished
  2026-10-15T02:18:52.3613557+00:00 (10:18:52 China). published=true means the
  same verified local snapshot was repointed; it does NOT mean today's live
  quotes became completed-session closes. No new trade or research admission.

Live acquisition original: runtime/quote-sessions/20261015T021826694238Z/bundle.json,
SHA256 53169790e8f359e8860bc1c085719c865a0c0cb100b0016ca1ae7ecec2e7663f.
Copies of this bundle and report are retained here as live-probe-bundle.json and
live-probe-collection-report.json. Documents include per-request attempt counts;
this real request succeeded without transport retry. Network-denial and bounded
backoff are separately tested, never represented as actual provider outages.

## Exact HTTP / Receipt State

All three GET requests to http://127.0.0.1:8001 returned HTTP 200; raw JSON is
saved as http-daily-update-status.json, http-daily-public-snapshot.json and
http-daily-decisions.json.

- /api/v1/daily-update-status: status=RECORDED; last_run.status=SUCCESS,
  exit_code=0, published=true, notes=[], action=no_order.
- /api/v1/daily-public-snapshot: status=VERIFIED, reason=null.
- /api/v1/daily-decisions: status=RESEARCH_OBSERVATION;
  publication.packet_status=CURRENT; publication.snapshot_status=VERIFIED;
  summary.formal_count=0. Its separate market field is still
  UNKNOWN / UNVERIFIED_PROVIDER_TRADE_DATE, not a failure of the verified
  per-security closes and not a claim of certified current sector-wide data.
- All publication IDs: pub-53fd34a5ae8aefdcaa5e.
- Current runtime receipt: .tmp/daily-workbench-latest-run.json, SHA256
  53c30dbdced97449020195d598d368e7072f8469bc8be30801089221fa9a3b27.
  Its frozen evidence copy is recovery-run-receipt.json. The update-status API
  intentionally exposes its existing allowlisted fields, not raw source paths
  or arbitrary error text. Local receipts also contain price_securities,
  quote_securities and core_integrity_ok.
- Research remains STALE (research cutoff 2026-10-11 versus quote 2026-10-14);
  CURRENT_RESEARCH_ADMISSION=NOT_READY; no automatic human approval.

## Root Owns Final Pointer Archiving

Do not rerun the daily entry during final pointer archiving; successful reuse
updates the pointer's published_at. This package will make no further public
pointer changes. The quote and price registries were not modified by these runs.

At handoff, config/current-daily-public-snapshot.json has SHA256
abd03c30a790d2f9f6823c3f3f182d9e3de7603b41d152e28ec6a7e9291e76e2.
Root should verify its current bytes before final archiving, because independent
integration work may legitimately have advanced it.

1. Archive the final pointer as a NEW file under this P61 artifact directory,
   for example root-final-public-snapshot-pointer.json. Never overwrite the
   existing pointer-before/after evidence files or frozen packet/receipt.
2. Its current packet_path is
   runtime/daily-public-packet/daily-public-packet-pub-53fd34a5ae8aefdcaa5e.json,
   SHA256 8891179146e63f80ef5b210486c29231834a392ee40367233aa0af4ebf8c6f8a.
   content_sha256 is
   81a923b5ed7bad7da881c7b5b20d92d945a2c2fda91abd8dc69095b7093ee46f.
3. Its current receipt_path is
   runtime/daily-public-packet/receipts/daily-public-packet-pub-53fd34a5ae8aefdcaa5e.receipt.json,
   SHA256 b4a7eaca6fd55173f5440c8257e0b880d116159650d57d71972c23cdcb420663.
4. If Root also archives the packet and repoints packet_path to a new artifact
   JSON, copy bytes exactly and keep packet_sha256/content_sha256/publication_id
   unchanged. Keep the original runtime receipt bytes intact; any path-relocation
   receipt must be NEW and explicitly record old/new paths and unchanged hashes.
   Do not rewrite a frozen receipt to make it appear originally published at the
   new path. Recheck the three API versions after the final pointer operation.

Registered input pointers, unchanged by this package:
config/current-quote-bridge.json SHA256
78186d164be785791f3c663cbf8618cbec219a40e06537e4d87b19693cd986d6;
config/current-price-conditions.json SHA256
19355933210b67430b7e023634403db7634f0144985adde708f067656d5badaa.

## Fixes And Acceptance

| Issue | Class | Fix / evidence | State |
|---|---|---|---|
| Quote and K-line transport had no backoff | ENGINEERING_FIXABLE | Three attempts, 1s/2s; only timeout, connection reset and transient HTTP; TLS, invalid originals, SHA/date conflicts not retried | PASS |
| Industry adapter could hang inside AkShare or retry parser faults | ENGINEERING_FIXABLE | Same Sina node protocol, explicit request timeouts, bounded pages/universe, raw source responses retained | PASS tests; live re-ranking not required while valid candidates are reused |
| Quote reuse depended on five price structures | ENGINEERING_FIXABLE | Independent per-symbol quote verification | PASS |
| Local failure blocked all verified securities; PARTIAL unreachable | ENGINEERING_FIXABLE | Reverify surviving inputs, publish PARTIAL only with usable verified input and intact core | PASS actual Windows entry |
| Core identity/integrity damage could be obscured by local successes | ENGINEERING_FIXABLE | Pre-build failures latch blocked; final integrity check required | PASS isolated identity/unavailable tests |
| Historical quote downloaded next day could claim formal B1 | ENGINEERING_FIXABLE | Same-session post-close acquisition for both sources; historical bytes never overwritten | PASS synthetic and real archived regression |
| Unrelated request failure invalidated every symbol's B1 bundle | ENGINEERING_FIXABLE | Reverify only each security's explicit referenced documents | PASS |
| Early exceptions could leave a previous SUCCESS or unfinished receipt | ENGINEERING_FIXABLE | Initial BLOCKED receipt and terminal failure trap | PASS entry tests |
| Current 10/15 live quotes are intraday; 000333 has no registered formal close | EVIDENCE_INSUFFICIENT | Retain 10/14 validated data; do not promote current raw quotes | Correct refusal |

Validation logs: tests-final.log = **122 passed**; tests-handoff.log =
**105 passed**, including final entry changes, network-denial recovery, B1,
historical bridge, daily assistant, observation and classification regression.
These overlap and must not be summed as unique tests. The earlier 49-pass/1-fail
log is retained: the old test wrongly expected next-morning historical evidence
to satisfy same-day B1; its price/source assertions remain and formal status is
now tested as unverified. Existing tests were not deleted.

Remaining: Root's final build/browser/full integration checks and final pointer
archive. No remaining known engineering blocker in this owned refresh package.
No claim of whole-product MVP readiness, strategy validation or final user signoff.
