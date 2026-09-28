# Shenhua 2014-2025 Operating-Series Classification

**Conclusion:** The local package contains annual operating observations, not a comparable normalized-earnings or owner-cash-flow series. No series is admitted as a cyclical valuation-model input. Report-date availability below is inferred from the annual-report URL date marker and is not an independently authenticated timestamp. This review does not establish strict contemporaneous PIT. `action=no_order`.

## Series Coverage

The seven observed fields are group coal sales (Mt), group average coal price (CNY/t), self-produced coal sales (Mt), self-produced coal average price (CNY/t), self-produced coal unit production cost (CNY/t), electricity sales (TWh), and average electricity selling price (CNY/MWh).

- Group coal sales, group average coal price, self-produced coal sales, self-produced coal unit production cost and electricity sales are present in the 12-year package, but only as period facts.
- Self-produced coal average price is present for 2022-2025 only.
- Group average electricity selling price is present for 10 of 12 years; 2019 and 2020 are excluded around the electricity joint-venture restructuring and are not comparable on the retained evidence.
- Group average coal price and self-produced coal unit cost have different scopes and cannot be subtracted to create a unit margin. These operating fields do not determine attributable earnings, full-cycle cost curve, normalized profit or owner cash flow.

## Annual Source Index and Breaks

| Year | Local annual-report PDF; SHA-256 | Date marker | PIT / scope note |
|---|---|---|---|
| 2014 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1200725016.pdf`; `45dba6cb163a2dc4fd1c3be5d1b4430fd2cf54820185d5acac2a1e68d574c1eb` | 2015-03-21 | 2014 self-produced coal sales comes from the 2016 report comparative table; 2015 report also restates 2014 after common-control acquisition. Keep versions separate. |
| 2015 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1202078941.pdf`; `a8b83a21c7e50ddff4d5e8e90d01f570fb2238d8f0bfcee41eaddff53f4e59c7` | 2016-03-25 | Self-produced coal sales is sourced from the 2016 comparative table; not contemporaneously available in 2015. |
| 2016 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1203174851.pdf`; `564fcaab934004549537add2b76f95f2e5fa9f91d47d628e1a60c5b6fcb5bc5a` | 2017-03-18 | Annual operating fields; same metric label does not prove unchanged consolidation scope. |
| 2017 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1204513630.pdf`; `c3e3fa4e45cafd9a27f075eedc064703a1c4b6bb87c081e9dff93673e37ca3c5` | 2018-03-24 | Self-produced coal sales comes from the 2018 comparative table, not a 2017 contemporaneous observation. |
| 2018 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1205932599.pdf`; `cd42bd43c859be0d1d2212547b721336f875de90cbcc49cfd854226be94d9cc9` | 2019-03-23 | Annual facts; full scope comparability with adjacent periods not established. |
| 2019 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1207418808.pdf`; `dc95b78d30fb92300683e209dcc04fc6aae9f1662c5bd77b9106f1105573f687` | 2020-03-28 | January 2019 electricity joint-venture restructuring breaks electricity scope; self-produced coal sales is from the 2020 comparative table. |
| 2020 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1209465173.pdf`; `13f71fce037a15ec2aeca16a31171c1cf86cab50df5137156016db20db4264e6` | 2021-03-27 | Disclosed electricity price is a retail-sales-company measure, not group average. The 2021 report restates 2020 unit cost from 119.2 to 128.6 CNY/t; preserve both versions. |
| 2021 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1212687181.pdf`; `d5d3e92f6749f052a0daef9a2d000109cc4b4d9e47e8729e0f98d74a8ba82b30` | 2022-03-26 | Self-produced coal average price is not yet present in the series. Keep the 2020 unit-cost restatement distinct from original disclosure. |
| 2022 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1216223000.pdf`; `10eec7dee0b418ea817fd4e9cc955aef8ce269a741928e60c7f313927a836a17` | 2023-03-25 | Self-produced coal average price begins in the retained series. Fields remain separate operational observations. |
| 2023 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1219390021.pdf`; `451aaacb1779c2572807a0f25985d8c18db355c2b40f3eef0a673210c9820bf9` | 2024-03-23 | 2025 report retrospectively restates some 2023 comparatives following common-control acquisition of **Hangjin Energy (杭锦能源)**. |
| 2024 | `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1222870380.pdf`; `4b3a8db26ae2fb07083966fadea0f92535cfbe6d0791c3318c6511113b138e8f` | 2025-03-22 | Package retains original-report values; 2025 report restates some 2024 comparatives (e.g. group coal sales 459.3 vs restated 460.2 Mt). Do not merge versions. |
| 2025 | `runtime/shenhua-2025-official.pdf`; `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc` | 2026-03-30 | HK disclosure-site copy; includes restated 2023/2024 comparative figures but does not remove the earlier scope breaks. Its hash is distinct from the CNINFO copy used in another research card. |

For the self-produced coal sales values sourced from later comparative tables, the field-level source is: 2014 and 2015 values, 2016 annual report `601088-1203174851.pdf`, physical p. 19, SHA-256 `564fcaab934004549537add2b76f95f2e5fa9f91d47d628e1a60c5b6fcb5bc5a`; 2017 value, 2018 annual report `601088-1205932599.pdf`, physical p. 19, SHA-256 `cd42bd43c859be0d1d2212547b721336f875de90cbcc49cfd854226be94d9cc9`; 2019 value, 2020 annual report `601088-1209465173.pdf`, physical p. 15, SHA-256 `13f71fce037a15ec2aeca16a31171c1cf86cab50df5137156016db20db4264e6`. These later tables establish when the respective comparative values became available; they do not backdate them to the year measured.

## Model Consequence and Next Work

## Verified Restatement Version Facts

The following field-level facts are versioned observations. They are not
normalized model inputs and do not backdate later comparative disclosures:

| Field | Original version | Later restated/comparative version | Evidence and availability boundary |
|---|---|---|---|
| 2023 group coal sales volume | 450.0 Mt in the 2023 annual report, physical p. 18 | 454.6 Mt in the 2025 annual report comparative, physical p. 22 (printed p. 21) | 2023 report `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1219390021.pdf`, SHA `451aaacb1779c2572807a0f25985d8c18db355c2b40f3eef0a673210c9820bf9`; 2025 report SHA `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`. Date markers: 2024-03-23 and 2026-03-30 respectively; markers are not independently authenticated timestamps. |
| 2020 self-produced coal unit cost | 119.2 CNY/t in the 2020 annual report, physical p. 25 | 128.6 CNY/t in the 2021 annual report's restated 2020 comparative | 2020 report SHA `13f71fce037a15ec2aeca16a31171c1cf86cab50df5137156016db20db4264e6`; 2021 report SHA `d5d3e92f6749f052a0daef9a2d000109cc4b4d9e47e8729e0f98d74a8ba82b30`; later value available no earlier than 2022-03-26 report date |
| 2024 group coal sales volume | 459.3 Mt in the original 2024 annual-report series | 460.2 Mt in the 2025 annual report restated comparative | 2024 report SHA `4b3a8db26ae2fb07083966fadea0f92535cfbe6d0791c3318c6511113b138e8f`; 2025 report SHA `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`, physical p. 30; restated value available no earlier than 2026-03-30 |
| 2024 average coal selling price | 564 CNY/t in the 2024 annual report, physical p. 26 | 563 CNY/t in the 2025 restated comparative, physical p. 31 (printed p. 30) | 2024 report `runtime/historical-filing-index/20260908T041326996681Z/pdfs/601088-1222870380.pdf`, SHA `4b3a8db26ae2fb07083966fadea0f92535cfbe6d0791c3318c6511113b138e8f`; 2025 report SHA `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`. Date markers: 2025-03-22 and 2026-03-30 respectively; markers are not independently authenticated timestamps. |
| 2024 generation, electricity sales and selling price | Original annual-report presentation | 2025 annual report marks the 2024 comparative electricity fields as restated | 2025 report SHA `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`, physical pp. 34-35; available no earlier than 2026-03-30 |
| 2023/2024 comparative scope | Earlier reported scope | 2025 report identifies retrospective adjustments following the common-control acquisition of Hangjin Energy (杭锦能源) | 2025 report SHA `460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc`, physical pp. 30-35; exact field-by-field bridge remains incomplete |

The later comparative-table sources for self-produced coal sales are explicitly
2016 annual report physical p. 19 for 2014/2015, SHA
`564fcaab934004549537add2b76f95f2e5fa9f91d47d628e1a60c5b6fcb5bc5a`; 2018
annual report physical p. 19 for 2017, SHA
`cd42bd43c859be0d1d2212547b721336f875de90cbcc49cfd854226be94d9cc9`; and 2020
annual report physical p. 15 for 2019, SHA
`13f71fce037a15ec2aeca16a31171c1cf86cab50df5137156016db20db4264e6`.
Their measured years do not become contemporaneously available until those
later report dates.

These additional rows close only a narrow version-recording gap. The aggregate
differences are not attributed to Hangjin Energy and do not establish its
standalone contribution, segment earnings, cost structure or cash flow. The
2023 average coal price and detailed pre/post-acquisition operating bridges
remain unavailable in the reviewed materials; all operating observations
remain excluded from normalized earnings and valuation inputs.

1. Keep original and restated values as versioned observations; use the actual comparative-report publication date for later-disclosed historical values.
2. The remaining safe R1 work is a field-level bridge of restated years and reconciliation of operating observations to segment and consolidated statements, including the electricity restructuring and internal transactions. Do not recrawl the same series.
3. Until those bridges are independently reviewed, retain `CYCLICAL_MODEL_NOT_READY` and do not derive normalized earnings, fair value, price attractiveness or a trade conclusion.
