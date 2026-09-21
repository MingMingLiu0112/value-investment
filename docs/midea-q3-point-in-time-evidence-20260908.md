# Midea Q3 point-in-time evidence

Research date: 2026-09-08. No production facts or Excel signals promoted.

An initial three-company CNINFO query failed with HTTP 504 during issuer
resolution. A bounded single-company retry succeeded. The complete returned
index for 000333, 2024-01-01 through 2025-12-31, category_sjdbg_szsh, contains
two Chinese reports and the 2024 English report. Index and PDF manifests:
`runtime/historical-filing-index/20260908T124941550748Z`.

## Original documents

- 2025 Q3: https://static.cninfo.com.cn/finalpage/2025-10-30/1224767336.PDF
  SHA-256: 9367216dcb6d6aaf15d3cfe5b7dc375b665eb3c8946d82d0725fefde48913a90
- 2024 Q3: https://static.cninfo.com.cn/finalpage/2024-10-31/1221570980.PDF
  SHA-256: 684d66248c30b0d9f2ab1bdf3f85338ef48b6ede0b6ff0725b405ed82a32c51f

Both PDFs were downloaded and opened by pypdf. The observations below were
read from extracted body text, not independently verified numeric facts.

## Body observations

Amounts are CNY thousand unless explicitly per-share.

| Item | 2024 original | 2025 comparative | Evidence pages |
| --- | ---: | ---: | --- |
| 2024 Jan-Sep parent-attributable net income | 31,699,114 | 31,699,114 | 2024 p2/p9; 2025 p8 |
| 2024 Jan-Sep operating cost, expense magnitude | 233,629,908 | 235,907,649 | 2024 p9; 2025 p8 |
| 2024 Jan-Sep selling expenses, expense magnitude | 31,163,032 | 28,885,291 | 2024 p9; 2025 p8 |

The 2025 report p2 explains Interpretation No. 18 warranty-cost
reclassification: 2,277,741 moved from selling expenses to operating cost.
Both movements reconcile exactly, while the displayed parent-attributable
profit is unchanged. Do not apply this later classification to a 2024 signal.

2025 p2/p8 report Jan-Sep parent-attributable profit of 37,883,383.
2025 p2 reports Jan-Sep basic EPS 4.98 CNY/share and parent equity 220,559,233.
2024 p2 reports Jan-Sep basic EPS 4.58 CNY/share. Different weighted share
denominators mean EPS addition/subtraction is not automatically valid.
The 2025 Q3 report explicitly states it is unaudited (p1).

## Remaining gates

TTM profit still requires the compatible 2024 annual input. Per-share
valuation additionally requires an explicitly defined and verified share
basis, including A/H shares and treasury stock. Announcement dates are not
verified intraday release timestamps. Preserve conservative availability
bounds and do not backdate 2025 disclosures to their report period.

These two reports establish a useful comparative reconciliation, not a
complete history, an approved valuation, or a successful trading backtest.

## Annual input and reproducible reconciliation

The 2024 annual PDF was subsequently read and its archived hash rechecked:
https://static.cninfo.com.cn/finalpage/2025-03-29/1222951181.PDF
SHA-256: b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9.
PDF p9 reports China-GAAP parent profit 38,537,237 CNY thousand. PDF p10
separately reports IFRS profit 38,538,987: do not mix accounting standards.
The same page reports fourth-quarter profit 6,838,123, exactly equal to
38,537,237 minus 31,699,114. Adding 2025 Jan-Sep 37,883,383 produces research
TTM profit 44,721,506 CNY thousand, not a per-share valuation.

`scripts/check_midea_ttm_evidence.py` successfully rechecked all three PDF
hashes, reviewed numeric-token presence on specified pages with pypdf and
PDFium, and the fourth-quarter arithmetic. Its result is
`runtime/midea-ttm-evidence-20260908.json`. This is a reviewed-cell evidence
check, not a general financial parser or independent source confirmation.

2025 Q3 p4 explains increased treasury stock from repurchases. PDF p7 has
treasury stock 10,996,382 and share capital 7,682,862, both monetary amounts
in CNY thousand, not a verified outstanding-share count. A/H ownership is
shown on p4. Share capital cannot simply be used as the EPS/BVPS divisor.
Availability and share-basis gates remain incomplete; no formal signal changed.

## September repurchase-account reconciliation

Additional official index search, 2025-09-15 through 2025-10-15, all categories,
returned five issuer-matched announcements after one bounded retry of a 504
issuer-lookup failure. Retained index:
`runtime/historical-filing-index/20260908T153702487714Z`.
An earlier exact monthly-return search returned zero results; this does not
prove absence of an HKEX monthly return.

- Repurchase progress, published 2025-10-11:
  https://static.cninfo.com.cn/finalpage/2025-10-11/1224706501.PDF
  SHA-256: 9c17caab0fbbdc2d9f328d00704f4c3e4a5a56990da0e8e332f3226bfca08039.
  Pages 1-2 disclose two A-share plans with 20,564,598 and 76,781,146 shares
  repurchased as of 2025-09-30. Their sum is 97,345,744, matching the quarterly
  report page 5 A-share repurchase-account balance. The rounded percentages
  0.2679% and 0.9994% must not be inverted into an exact total-share count.
- Planned restricted-share cancellation, published 2025-09-25:
  https://static.cninfo.com.cn/finalpage/2025-09-25/1224679428.PDF
  SHA-256: 554724cfc92ee58257efc9cb595db5ff064d07642344f7cdd46dff21cf512713.
  Pages 1-2 propose cancellation of 553,811 shares and explicitly promise a
  later completion announcement. This is not evidence of completed cancellation
  at September 30; no share-count reduction is applied from this document.

The reproducible checker now validates all five PDF hashes, two-decoder token
presence for the reviewed cells and the repurchase-plan arithmetic. Output
records unknown issued/outstanding ordinary-share counts as null and keeps
financial_facts_verified=false and backtest_ready=false.

The two notices and quarterly report originate from the same issuer, so this
is inter-document reconciliation, not independent financial-source approval.
The October notice's publication must not be backdated to September 30 when
forming historical signals. Exact A/H issued share counts, treasury scope,
actual cancellation dates and point-in-time availability remain unresolved.

## Distinct December cancellation event

The issuer-matched 2025-09-25 through 2025-12-31 cancellation search returned
two notices, retained in `runtime/historical-filing-index/20260908T154030826694Z`.
The completion notice is NOT the same event as the proposed 553,811 restricted
shares described above.

Original: https://static.cninfo.com.cn/finalpage/2025-12-23/1224890769.PDF
SHA-256: 8cb3d5bcfca9415e9e5ac940c925094f665bfc19b6dcf40f302d5688fcf625d2.

PDF page 2 states that 95,000,000 repurchased A shares were cancelled at CSDC
Shenzhen on December 19, 2025. The announcement is dated December 23, 2025.
Preserve the difference between effective and publicly available dates.

| Share class | Before this cancellation | After this cancellation |
| --- | ---: | ---: |
| A | 7,041,957,278 | 6,946,957,278 |
| H | 650,848,500 | 650,848,500 |
| Total | 7,692,805,778 | 7,597,805,778 |

The checker verifies the original hash, two-decoder reviewed-cell presence,
class totals and 95,000,000 share reduction. This is another issuer-origin
reconciliation, not independent-source approval. The 553,811-share proposal's
completion remains unproven. December pre-event totals must not be backfilled
into September; intervening exercise/issuance/cancellation events have not
been reconciled. Issuer cancellation of its own repurchased shares must not
reduce an ordinary investor's portfolio share balance in the backtest.

No EPS, approved valuation, performance result or trading signal was produced.

## September month-end share counts located

The issuer's official information-disclosure page embeds the Euroland H-share
announcement service:
https://www.midea.com.cn/en/Investors/information_disclosure

Its bounded October 1-15, 2025 query returned eight announcements, including
the monthly return submitted October 3 for the month ended September 30.
The complete query response and vendor-hosted attachment were archived at
`runtime/midea-monthly-shares/20260908T155205603488Z`.
Monthly PDF SHA-256:
`11bd651623c597214119f3df719caaf0622f1728ce48909e294735af0c88b85d`.

| Class | Issued excluding treasury | Treasury | Total issued |
| --- | ---: | ---: | ---: |
| A | 6,934,667,300 | 97,345,744 | 7,032,013,044 |
| H | 649,605,400 | 1,243,100 | 650,848,500 |
| Total | 7,584,272,700 | 98,588,844 | 7,682,861,544 |

Page 1 supplies issuer, period, submitted date and registered share capital.
Page 2 explicitly labels issued shares excluding treasury, treasury shares
and total issued shares. A-share treasury agrees with the quarterly report
and the previously reviewed A-share repurchase figures; H-share treasury is
additional and must not be omitted. Page 3 discloses September option exercises
issuing 7,273,372 new A shares. Page 7 discloses 17,361,485 treasury A shares
transferred for the 2025 ownership scheme and 36,125,230 A shares repurchased.
These movements explain why total repurchases and current treasury balances
cannot generally be substituted for each other.

`scripts/check_midea_monthly_shares.py` verifies the original hash and parses
the explicit page-2 class rows using PDFium and pypdf. Both decoders agree;
all class sums and combined totals reconcile. Six tests reject wrong period,
code, including/excluding wording, arithmetic failure and duplicate rows.
Result: `runtime/midea-monthly-share-reconciliation-20260908.json`.

These supersede the earlier absence of explicit September share-count
candidates, but do not approve the per-share valuation basis. The direct HKEX
copy is not yet matched; the source is accurately labeled issuer-embedded IR
vendor copy, not an independent financial source. Ordinary equity adjustments,
A/H economic rights, availability and subsequent share movements remain
separate gates. Period-end issued-excluding-treasury shares are not weighted
average shares for accounting EPS. No September 30 signal may use an October
3 submission before its verified/conservatively bounded availability.
