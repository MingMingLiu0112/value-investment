# Midea Ordinary-Share Denominator Review — 2026-09-28

**Disposition:** `PARTIALLY_VERIFIED / CURRENT_OUTSTANDING_DENOMINATOR_NOT_ADMITTED`

**Effect:** narrows a documented research gap only. No valuation, baseline, price assessment, decision state, or workbook value is changed. `action=no_order`.

This is a later research reconciliation of filings published before the declared prospective cutoff. The registration and baseline timestamps are not independently attested; this note does not establish strict contemporaneous PIT and must not be backdated into the frozen baseline.

## Source Evidence

| Filing | Official source and retained bytes | Physical pages used |
| --- | --- | --- |
| FY2025 audited annual report, CNINFO `1225065145` | [Official PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF); `runtime/midea-2025-official.pdf`; SHA-256 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6` | 231 (EPS); 258 (post-balance-sheet dividend proposal) |
| 2026 H1 interim report, CNINFO `1225531404` | [Official PDF](https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF); `runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf`; SHA-256 `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8` | 87-88 (share movement and buyback); 169 (share capital and treasury-stock carrying value); 175-176 (EPS) |

The retained PDF hashes were recomputed and matched the existing research records. Page references are physical PDF pages; the annual report's printed page numbers are one lower on the cited pages.

## Reconciled Facts

- FY2025 basic EPS used a weighted-average ordinary-share denominator of **7,559,265,000**; diluted EPS used **7,608,132,000** (annual report physical p. 231). These are FY2025 period averages, not a point-in-time share count.
- In its 2026-03-30 dividend proposal, the annual report stated total shares of **7,603,276,186** as of the financial-statement approval date and excluded **80,412,541** repurchased shares, giving **7,522,863,645** dividend-eligible shares. Arithmetic reconciles exactly. This is a proposal-date basis, not a 2025-12-31 or 2026-06-30 outstanding-share count (annual report physical p. 258).
- At 2026-06-30, the H1 report gave **7,613,438,907 issued shares**: 6,962,590,407 A shares and 650,848,500 H shares. It separately disclosed **68,679,031 A shares** cumulatively repurchased under the then-current program, whose use had been changed to cancellation (physical pp. 87-88).
- The H1 report's basic EPS denominator was **7,470,497,000** weighted-average shares and its diluted denominator was **7,540,304,000** (physical pp. 175-176). These are H1 averages, not the 2026-06-30 point-in-time denominator.
- H1 note (41) reports treasury stock in **RMB thousands of carrying amount**: closing balance 15,117,924, including 5,476,600 for repurchased shares not yet cancelled and 9,641,324 for share-payment plans. It does not state the corresponding total number of shares held for the share-payment plans. The separately disclosed 68,679,031 buyback shares therefore do not resolve the total treasury-share quantity.

## Decision and Reopen Condition

Do not substitute gross issued shares, an EPS weighted average, or the FY2025 dividend-eligible base for the current point-in-time ordinary-share denominator in a per-share valuation. The exact 2026-06-30 number of treasury shares across cancellation and share-payment-plan holdings is not established by the cited notes. The point-in-time denominator remains `UNKNOWN / NOT_ADMITTED`; diluted EPS averages must also not be mistaken for a current diluted share count.

Reopen only when an official filing or issuer/exchange disclosure supplies a date-bound count of all shares held in treasury (or an equally precise current outstanding-share count) and the share classes/bases reconcile. Even after that gap closes, Midea's FCFF model remains not ready: maintenance versus growth CapEx, operating/financing scope separation, and the enterprise-value-to-listed-equity bridge remain independent blockers.

## 2026-09-29 Observation — H1 Interim-Dividend Share Base

The 2026H1 report, CNINFO `1225531404` (physical p. 60; SHA-256
`576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`), states
that its proposed 2026 interim cash dividend used **7,448,597,984 shares** as
the allocation base: 7,628,798,092 total shares less 180,200,108 shares in
the repurchase account as of the report-disclosure date. At CNY 0.50 per
share, the proposal totals CNY 3,724,298,992; the report states this is 14.06%
of 2026H1 parent-attributable profit. The report's date-level CNINFO marker is
2026-08-29; use conservative availability 2026-08-30T00:00:00+08:00.

This is a source-stated share base for that interim-dividend proposal, not
proof that the proposal was paid, the eventual record-date base, or the exact
ordinary-share denominator on 2026-09-29. Later share issuance, cancellation,
or repurchase-account changes are not resolved here. The valuation denominator
therefore remains `UNKNOWN / NOT_ADMITTED`; this late review does not alter
the frozen baseline, strict-PIT status, model applicability, valuation, or
`action=no_order`.
