# M2 Official List Session-Date V2 Handoff

Base: `248ee135aae5c98a47fbb50f8747f291f7f054a7`.
Branch: `codex/m2-official-calendar-20261024` in cp1 only.
Original `codex/source-bound-simulated-journey-20261024` remains at c489eb64.
No vv1/LIVE, private account, Excel, server, scheduler, paid API or public push.
Permanent `action=no_order`; this is acquisition engineering, not investment admission.

## Implemented Contract

`application.discovery.official_universe_collection.collect_official_m2_input(directory, root)`
returns `(official_payload, EvidenceReference)` using the new infrastructure adapter.
The existing registered M2 CLI calls this through its original thin `_collect_official` hook.
No new CLI, screening engine, financial threshold, valuation or decision gate.

New data parser: `official-security-lists-v2-session-date`.
New date policy: `official-list-session-calendar-2026-v1`.
Timing envelope: `official-list-timing-v2`.

- Calendar-supported weekend/holiday acquisition accepts BSE's exact latest completed
  session date, not the computer's civil date. Saturday Oct24 + raw xxjsrq Oct23 is valid.
- Actual response fetched_at and collection started/available_at remain actual acquisition
  clocks. Raw xxjsrq/as_of remains Oct23. effective_session is a separate field.
- A covered trading day before 15:05 is rejected, even when the prior session exists;
  this prevents mixing undated current SSE/SZSE lists with a previous BSE day. The
  15:05 conservative buffer follows existing quote collection practice, not a new
  exchange holiday-notice rule or guarantee of provider publication completeness.
- Future/stale/non-session/mixed BSE dates, missing/repeated/inconsistent pages,
  changed totals, duplicate securities, future listing dates, too-small coverage,
  naive/future/out-of-span source times, cross-day collection and uncovered years reject.
- Counts retain existing minimums: SZSE2000, SSE2000, BSE200. No coverage reduction.
- Only BSE supplies the per-row effective date used here. SSE/SZSE effective dates
  are not fabricated; the metadata explicitly states their responses are undated.
- `quote_date_verified=False` and `strict_contemporaneous_pit=False`. A calendar-aligned
  official list does not verify provider quote timestamps, historical PIT or BUY eligibility.
- No automatic fixed fallback copying. Collection errors propagate; existing dated
  research-retention display is separate from fresh acquisition success.

`screening_quote_date(payload, generated_at, retained_quote_date=None)` orchestrates
the session label outside scripts. Fresh v2 M2 gets quote_date=Friday while receipt
generated_at/as_of and official fetched_at stay Saturday. Cross-day receipt generation
rejects. V2 historical replay checks its original acquisition/session, never today's clock.
V1 replay keeps its original retained quote_date; financial screening stays
`m2-evidence-screen-v3` because no screening rule changed.

## Official Calendar Evidence

Independently checked each issuer's 2026 notice, including BSE 2025/58:
- BSE publisher: https://www.bse.cn/important_news/200027428.html
- Original BSE notice PDF archived by CNInfo:
  https://dataclouds.cninfo.com.cn/sjother2/regulatory/2025/20251222/55875a9937374da4ae2d4999dfda2722.pdf
- SSE: https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml
- SZSE: https://www.szse.cn/disclosure/notice/general/t20251222_618087.html

Original bytes and actual UTC acquisition times are retained in
`docs/evidence/official-list-calendar-2026/{BSE,SSE,SZSE}.raw` and `acquisition.json`.
The application checks the three pinned notice body SHA-256s before live collection.
BSE official website/direct mirror returned403; those error bodies were NOT admitted.
The BSE closure dates came from its own original PDF, not an SSE venue alias.
Only these limited free official notice requests were performed; no market refresh.
The new notice acquisition timestamps do not prove contemporaneous historical retrieval.

## Validation

Focused command, PowerShell7, UTF-8, `PYTHONPATH=src;tests`, TEMP/TMP/TMPDIR=cp1/.tmp:
```text
python -m pytest tests/test_official_universe.py tests/test_exchange_calendar.py
 tests/test_m2_cli_versioned_integration.py tests/test_architecture_boundaries.py
 tests/test_architecture_migration_agent_runtime.py
 -q -p no:cacheprovider --basetemp=.tmp/cal5
```
Result: **91 passed**, no skips; one retained SZSE workbook style warning.
OFFICIAL_LIST_REPLAY_ROOT explicitly pointed to dual1 public originals, read only.
No full Core, CI/push, production scheduling or actual market collection was run.

The real-source test binds official-universe.json SHA
f500d22bd3ad16f3a139950608b4f0e21cd391f7682b62ed395a56b5011dc98b in the explicit
Oct23 sealed M2 run; checks all21 raw hashes and reparses all18 BSE pages.
The rebuilt5577 rows exactly equal original records (SSE2318/SZSE2906/BSE353), and
original fetched_at remains unchanged. Earliest retained response time is only a
replay lower bound; the original request-start timestamp was not archived in v1.
This historical reparse was NOT registered as a newly acquired Saturday list.
Saturday collection timing was separately tested using explicit synthetic clocks
and mocked official transport with complete production-minimum-sized records.

All9 architecture-frozen paths pass exact SHA-256. Legacy v1 official collector and
execution calendar retain their initial physical worktree hashes; those plus legacy
M2 engine/evidence-v3 code have no Git-content diff from base. A preliminary
Git-blob/physical-byte comparison hit normal LF-vs-CRLF checkout representation;
the final checks used initial worktree hashes and exact frozen hashes, never waived them.
The new modules are in Domain / Infrastructure / Application, not business code in scripts.
The narrowly scoped .gitattributes rule preserves downloaded .raw bytes across
Windows checkout; whitespace in those original responses is not reformatted.

## Minimal Real Trial (Main Only)

After review/integration, run from the selected project root. This collects only
official lists into a NEW runtime directory; no quotes, financial scan, publication,
registration or existing source overwrite. Do not run during an incomplete session.
```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
@'
from pathlib import Path
from uuid import uuid4
import json
from value_investment_agent.application.discovery.official_universe_collection import collect_official_m2_input
root = Path.cwd()
out = root / 'runtime/official-list-v2-trial' / uuid4().hex
payload, ref = collect_official_m2_input(out, root)
print(json.dumps(dict(binding=ref.as_policy(), parser_version=payload['parser_version'],
    effective_session=payload['effective_session'], fetched_at=payload['fetched_at'],
    available_at=payload['available_at'], counts=payload['exchange_counts'],
    timing=payload['collection_timing']), ensure_ascii=False, indent=2))
'@ | & D:/APP/Python313/python.exe -
```
Expected on this Saturday: effective_session Oct23; acquisition times Oct24;
all sources/hash/page checks pass; no quote/PIT/admission authority.
Then main can run the existing M2 CLI in a separate fresh output directory using
its existing --no-wps --no-workbook contract. Actual full refresh, independent
review, integration and publication remain main-owned acceptance.
