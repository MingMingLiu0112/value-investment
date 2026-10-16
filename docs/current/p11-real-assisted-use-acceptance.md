# TL11-P11 first real assisted-use acceptance (2026-10-16)

## Verdict

`action=no_order`. **PUBLIC_OBSERVATION_READY**, but
**LIMITED_REAL_ASSISTED_USE_READY=NOT_READY** for personal investment actions.
The public daily research/market workflow can be used to observe and prioritize
further work. No current value entry/add/reduce/exit price, approved G3,
confirmed personal risk capacity, or validated hotspot strategy is available.
No artificial BUY was produced. The code verification baseline is
`a48d4f713dda5f760b37d774c72b7555d85581e3`; a later documentation-only
commit does not change this code. Actual live version must always be checked
again at `/system`.

## P11-01: running version and product

At the start, the Windows service on 127.0.0.1:8001 was the project's
`D:\APP\Python313\python.exe -m uvicorn ...app:app`, PID 32336, started at
09:10 CST. It read the new publication pointer dynamically, but returned
`{"detail":"Not Found"}` for the new runtime-identity route: its loaded Python
code was old. This is a real server lifecycle mismatch, not merely browser
cache. The owned-process identity check in `start_web_workbench.ps1` was used
for a controlled restart; no unrelated process was stopped. The new public
`/api/v1/runtime-identity` reports backend loaded Git HEAD, on-disk source
hash, relevant source worktree cleanliness, server Web build, current HEAD,
verified publication and distinct dates.
The Web build embeds its own identity; postbuild fails if that identity is not
actually in the served JavaScript. Chrome confirmed `/system` says the page,
backend and source match at the code baseline, including after refresh.

## P11-02: real B1 acquisition

`SAFE_REFRESH -NoServer` ran after the 2026-10-16 close and exited 0 at
17:01:07 CST. The exchange calendars identify 2026-10-16 as the most recent
completed session. Tencent and Sina were fetched at 17:00:31 CST; their
original SHA-256 values are respectively
`1241d6d61cc9f1bed0f3b6716deca879c8339e24d1e81e96b67d347677a97ce6`
and `37b88049feb84f58666b08e32d2e3042837b6766ba6ed31c10572098efd1a31e`.
The archived bundle is
`runtime/quote-sessions/20261016T090031652233Z/bundle.json`, SHA-256
`08a8cb10dbb7785870645f8b2e1ab7d4a5f3f6cf8bf4295da5b5baa8ccbd927e`.
Per-symbol raw replay and `require_current_b1=True` passed for 600887 28.20,
600519 1329.00, 000333 84.60, 000651 39.49, 600741 15.59 and 601088
50.98. `REAL_B1_CLOSE_ACQUISITION=PASS` for this session only. The collection
bundle's `collected_not_verified` archive status is not itself admission; the
separate per-symbol replay/registration and published source checks are the
verification. No failure retry was required. Future sessions need fresh
evidence and cannot reuse this verdict.

The new verified public packet is `pub-5f803ec65b6e52fd7de4`, file SHA-256
`1ed978a5b2fe8baf9f7db801b46c97ca97fa3b03575ac4115c3eef57aa8a93b4`.
HTTP `/api/v1/daily-public-packet` returns this ID and 2026-10-16 dates. Its
research cutoff remains 2026-10-11, formal admissions remain 0, and 600887 /
600519 model validity remains `UNKNOWN` pending event review. The older P10
`b1_price_state=BLOCKED_EXTERNAL` describes the *formal price bridge*, not
today's source-acquisition timing. These are deliberately separate.

## Task outcomes

| Task | Engineering / real-world result |
| --- | --- |
| P11-01 running version | PASS on code baseline; runtime API and Chrome page agree. Recheck after every code/deployment change. |
| P11-02 B1 close | PASS for six 2026-10-16 source observations and publication; formal price comparison still blocked by research/model/human gates. |
| P11-03 first economic case | Explicit `CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED` for 600887. Existing primary facts and arithmetic are not a justified fair value. See `p11-yili-economic-audit.md`. No new G3 or ResearchCase admission. |
| P11-04 value actions | Existing four-action policy engine and fail-closed tests retained. No authorized prices or complete formal action chain; not promoted from old scenarios. |
| P11-05 hotspot quality | Active rank and structural quality remain separate; stale ex-Top5 qualified label now downgrades to `ACTIVE_ONLY`. Five 2026-10-16 real observations are WATCH, 0 formal entries. Strategy edge not proven. |
| P11-06 personal portfolio | 43 TEST_ONLY continuity/portfolio/risk tests passed. Actual personal cash, IPS, holdings and fills are absent; private UI remains locked without local authorization. |
| P11-07 daily product | Actual Chrome checked `/daily`, 600887 detail, `/portfolio`, `/history`, `/system` at 1280x900, 1440x900, 390x844, 430x844, then clicked daily to 600887 and refreshed `/system`: 22 checks, 0 final failures, no post-load horizontal overflow. Private unlocked usability remains unaccepted. |
| P11-08 independent validation | No strict OOS/net-return/forward Shadow claim. Retained replay is engineering/chronology evidence only. |
| P11-09 canonical Excel | Read-only live file hash equals registered SHA-256 `aeaa3c7fec2b46d34c0651b0384dec49fb3ca16747dc41fcf675bbd022be82f1`; its formal snapshot remains 2026-10-01. Not overwritten or duplicated; Web is newer. No real backup-restore success inferred from isolated PostgreSQL CI. |

## Verification and user use

P9 source/publication preflight: 38 checks passed after the refresh. P10
acceptance `-RunTests`: 237 focused Python tests and Web build passed; its
overall result remains `NOT_PROVEN`, not investment approval. P11 version and
hotspot targeted tests: 17 passed. Independent TEST_ONLY portfolio path: 43
passed. Full Web suite: 198 passed; formatting, typecheck and build passed.
The earlier P10 full local Core result (5678 passed, 44 skipped) applies to
the previous code baseline; exact P11 CI must be reported separately. Browser
receipt and screenshots are local ignored evidence under `.tmp/p11/`, not a
second user workbook or formal trade artifact.

Today the user can open the local Web workbench to inspect today's dated
research/price observations, why each case is still under review, hotspot
structure and official-source links. The user can use the private local flow
to *enter and personally reconcile* cash, IPS and holdings when ready. The
system cannot yet tell the user an authorized buy/add/reduce/exit price or
personal position size. See `p11-unresolved-external-gates.md` for the exact
independent remaining gates.
