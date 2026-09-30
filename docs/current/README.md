# Current Documentation

This directory is the current documentation entry. It points to authoritative
files without duplicating their content. Historical stage notes live under
`docs/archive/` and are read-only context, never a task queue.

## Current Entries

| Need | Authoritative entry |
| --- | --- |
| Current goal | `docs/current-stage-goal.md` |
| Current execution status | `docs/execution-status.md` |
| Latest verified public close | 2026-09-29 dual-source close bundle for 000333 / 600887 / 601088 (runtime-only, SHA-256 `c7e14a9626db695c489a485fa7134bbba4568238b67a85cc3805c8cd4ba10395`); product verification passed in memory, Canonical Excel not updated |
| Current execution-correction review and three-company blocker burn-down | `docs/current/track-b-execution-correction-20260929.md` (current A/B/C/D counts, remaining A blockers, evidence stops, Yili bounded candidate dispositions and R1 findings) |
| Yili shared-model result binding | `docs/current/600887-shared-valuation-result-20260929.json` (input/result/source-package and artifact hashes; replay uses only 600887 CNINFO source refs) |
| Yili prospective case follow-up | `docs/current/600887-prospective-case-followup-20260930.json` (new shared-application run bound to the registered case and frozen v13 receipt/snapshot; baseline unchanged, strict PIT not proven, no admitted price bridge) |
| Yili conditional valuation result and full sensitivity grid | `docs/current/600887-valuation-readiness-review-20260929.json` (research-only; `price_bridge=null`, Decision Review is NOT_ASSESSABLE because quote-date ModelValidity is not established; Canonical Excel remains unchanged) |
| Root workbook governance audit | `docs/execution-status.md` (2026-09-28 update: 29 referenced root workbooks; no safe relocation proof) |
| Current R0 audit state | `docs/execution-status.md` (open R0 nodes; non-blocking to public research) |
| Midea and Yili baseline cards | `docs/current/track-b-midea-yili-baseline-cards-20260927.md` |
| Shenhua cyclical baseline card | `docs/current/track-b-shenhua-cyclical-baseline-20260927.md` |
| Shenhua 2026H1 acquisition, segment and capex supplement | `docs/current/track-b-shenhua-h1-acquisition-segment-capex-supplement-20260929.md` (keeps H1 and restructuring reports separately identified; this material does not provide a full post-acquisition through-cycle attributable-profit bridge; current case is `INSUFFICIENT_PUBLIC_EVIDENCE / D1 EVIDENCE_STOP`) |
| Shenhua operating and capital-allocation review | `docs/current/track-b-shenhua-operations-and-capital-allocation-20260927.md` |
| Midea 2026H1 source admission | `docs/current/track-b-midea-2026h1-admission-20260927.md` |
| Midea cash-scope correction and FY2026H1 liquidity facts | `docs/current/track-b-midea-cash-scope-correction-20260929.md` (v2 remains historical; current v3 separates monetary funds from cash equivalents; net debt remains unknown) |
| Midea CapEx / fixed-assets review and page corrigendum | `docs/current/track-b-midea-capex-fixed-assets-review-20260928.md` (source-cited memo; its prior machine receipt binds different bytes, see the 2026-09-29 audit); `docs/current/track-b-midea-capex-fixed-assets-review-corrigendum-20260928.md` |
| Midea share-denominator and model-scope review | `docs/current/track-b-midea-share-denominator-review-20260928.md` (2026-09-29 A/H denominator verified but not backdated; shared residual-income is explicitly profile-authorized; 2026-06-30 denominator is now a scoped `D1 / EVIDENCE_STOP`, so no 6/30 per-share valuation; see the current blocker burn-down above) |
| Midea CapEx memo receipt-binding audit | `docs/current/track-b-midea-capex-receipt-binding-audit-20260929.md` (current memo SHA differs from the memo SHA recorded in its prior receipt) |
| Midea 2026 extraordinary shareholder meeting notice | `docs/current/track-c-midea-egm-notice-20260928.md` |
| Current bounded public-event scans / gap fills / watermarks | `config/prospective-public-event-watermarks-v9.json` (v8 remains the latest formal continuous watermark; v9 adds 2026-09-29 bounded snapshots without advancing it); `docs/current/track-c-prospective-watermark-continuity-corrigendum-20260928.md`; Yili financing-note redemption and July issuance/maturity schedule: `docs/current/track-c-yili-short-term-financing-redemption-20260929.md` |
| Prior Midea meeting-notice review | `docs/current/track-c-midea-egm-notice-20260928.md` (re-observed after conservative availability in watermark v9; no new event) |
| Prospective event continuity as of 2026-09-28 | `docs/current/track-c-prospective-watermark-continuity-corrigendum-20260928.md` (bounded date chains, latest CNINFO snapshots, missing intervals and clock limitations) |
| Shenhua annual-series restatement corrigendum | `docs/current/track-b-shenhua-operating-series-corrigendum-20260928.md` (page corrections, checked restatement bridge and remaining ResearchCase blockers) |
| Yili liquidity bridge follow-up | `docs/current/track-b-yili-liquidity-bridge-review-20260928.md` |
| Yili 2026H1 cash-quality analysis | `docs/current/track-b-yili-h1-cash-quality-review-20260928.md` |
| Yili dividend/cash-coverage review | `docs/current/track-b-yili-dividend-cash-coverage-review-20260928.md` (FY2021-2025 partial payout and CFO coverage; FY2025 proposal and 2025-2027 return plan approved; ordinary/special classification and sustainability remain unknown) |
| Midea historical public-event projection builder | `scripts/cases/build_midea_public_event_projection.py` (read-only, hash-pinned; pre-registration materials only; not a PIT-ledger writer) |
| M4 private input | `docs/m4-private-input-package.md` |
| External gate handoff | `docs/current/external-gate-handoff.md` (2026-09-26 historical snapshot; not authorization) |
| M6 authorization | `docs/m6-production-authorization-package-20260924.md` |
| M6 start criteria | `config/m6-start-criteria-matrix-v1.json` and `docs/current/m6-start-criteria-matrix.md` |
| M7 trial | `config/current-trial-workbook.json` and `docs/m7-readonly-user-trial.md` |
| M7 product UX candidate builder | `scripts/current/build_product_workbench_candidate.py` |
| M4 synthetic onboarding rehearsal | `scripts/current/rehearse_m4_onboarding.py` |
| Historical validation status | `docs/historical-validation-current-status.md` |
| Architecture status | `docs/architecture/repository-architecture.md` |
| Permanent boundaries | `AGENTS.md` |
| Long-term envelope | `LONG-TERM-GOAL.md` |
| Product purpose | `docs/north-star.md` |
| Methodology | `docs/research-methodology.md` |
| Evidence policy | `docs/data-and-evidence-policy.md` |
| Current CLI split | `config/current-cli-entrypoints-v2.json` |
| CLI v1 compatibility | `config/current-cli-entrypoints-v1.json` |

`docs/execution-status.md` is factual history, not a backlog. Historical stage
acceptance files are read-only context and do not create new work.
