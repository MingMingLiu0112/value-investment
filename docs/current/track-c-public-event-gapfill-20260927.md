# Track C bounded public event gap fill, 2026-09-27

Scope: CNINFO exact-issuer windows for 2026-09-23 through 2026-09-26, queried at 2026-09-27 04:53 UTC. This is bounded public research, not a complete exchange or issuer-IR review. `action=no_order`.

## Captured windows

| Symbol | Window | Result | Index SHA-256 |
|---|---|---:|---|
| 000333 | 2026-09-23..26 | Complete query, 0 announcements | `3cdaa42730c98f65d45c5bcdee65aaacb3c6a9d1faf22a7f1b7a488dd5e63601` |
| 601088 | 2026-09-23..26 | Complete query, 5 announcements | `0717da2e13c2c17f95015a3c28795cd447cd0a3bf920cb917ca9b1f950175e2a` |

Raw response hashes are retained in the corresponding `runtime/prospective-public-event-20260927/gapfill-*` directories. The query covers CNINFO's exact issuer and those dates only.

## Shenhua document review

CNINFO ID `1225531759` (2026-08-29) and meeting materials `1225546779`
(2026-09-04) state a proposed **gross, pre-tax CNY 0.98 per share** interim
distribution, estimated at CNY 21.256bn using the June 30 share count. CNINFO
ID `1225579981` (2026-09-24) records that shareholders passed the proposal at
the 2026-09-23 meeting; the resolution itself does not repeat the amount.
Using the report's CNY 28.715bn H1 consolidated parent-attributable profit,
the estimate is 74.0%; compared with H1 operating cash flow of CNY 54.664bn,
it is 38.9%. These are context ratios, not distributable-cash, free-cash-flow
coverage or sustainability conclusions. CNINFO date-only markers imply
conservative `available_at` dates of 2026-08-30, 2026-09-05 and 2026-09-25,
all before the registered observation start by calendar date; exact release
times and strict PIT remain unproven. The proposal is **approved, but
implementation and payment are unverified**. Classification remains
`MATERIAL_SUPPORTING_EVIDENCE` for capital-allocation monitoring. Do not infer
yield, recurring capacity or payment completion. The later section below
contains the source hashes and detailed limits.

CNINFO ID `1225579956`, URL `https://static.cninfo.com.cn/finalpage/2026-09-24/1225579956.PDF`, is an announcement that 457,665,903 restricted shares (2.11% of total share capital) will become tradable on 2026-10-08. The source PDF SHA-256 is `f7d78ed7a7270069f112060bd90cd2779b9fa81c774a522f826174f0fdb38cd2`. It also recites prior transaction registration and lock-up facts. Classification: `MATERIAL_RISK_MONITOR` for a dated potential float/supply event; not a new operating fact and not an automatic valuation or sell signal.

The other two records are an intermediary legal opinion and a shareholder-meeting materials item; no additional issuer operating or dividend amount was established in this bounded pass.

## Baseline admission status

The official 2025 annual report CNINFO ID `1225064293` was independently captured with raw response, parsed index, scan evidence, and PDF. Page 8 (physical and printed) reports 2025 summary values in CNY million: revenue `294916`, parent-attributable profit `52849`, and operating cash flow `75059`. Conservative date-only availability is `2026-04-01T00:00:00+08:00`.

These values are **not admitted into a successor baseline snapshot in this pass**. Verification failed closed because the existing Midea/Yili scan evidence artifacts no longer match the immutable hashes in verification-v5. Recomputing those legacy pins would silently bless changed evidence bytes, so no pin was rewritten and no canonical Excel publication was made. Shenhua remains at the last published baseline state until the original evidence artifacts or a separately audited successor chain is available.

All three valuation states remain `VALUATION_NOT_READY`; strict contemporaneous PIT remains unproven; no quote package was duplicated; no order, production, shadow, private portfolio, or WPS write occurred.

## Shenhua original-document verification addendum

The five CNINFO items returned for 601088 in the bounded 2026-09-23..26 window
now have locally retained original PDFs. The four previously missing files
are under
`runtime/prospective-public-event-20260927/shenhua-gapfill-originals-20260927T130000Z/`;
the issuer's unlock announcement `1225579956` was already archived at
`runtime/prospective-public-event-20260927/shenhua-major-transaction-1225579956.pdf`.
The four gapfill files were fetched with the project's existing CNINFO
disclosure downloader. The formal downloader retrieval receipt was not
persisted, so this addendum does **not** claim an independently attested
download timestamp. The verification receipt records the later local
byte/hash/content check and labels its process clock accordingly:
`runtime/prospective-public-event-20260927/shenhua-gapfill-source-verification-20260927.json`.
The original index was retrieved at `2026-09-27T12:53:25.361914+08:00`; that is
the index-query time, not the PDF download time. Its raw response SHA-256 is
`151ec87ef637f5e53bff690b958b244710acd1dc04b83f5f8b7497bf1a8d9849` and its
parsed index SHA-256 is
`0717da2e13c2c17f95015a3c28795cd447cd0a3bf920cb917ca9b1f950175e2a`.
All five rows carry CNINFO's date-level `announcementTime` marker for
2026-09-24. Applying the project's conservative next-day availability rule
gives `available_at=2026-09-25T00:00:00+08:00`, before the 2026-09-27 08:45
observation start. This is post-start local retrieval/review of pre-existing
public material, not a newly disclosed post-registration event and not strict
contemporaneous PIT evidence.

| CNINFO ID | Document-level finding | Source PDF SHA-256 |
| --- | --- | --- |
| `1225579981` | The 2026 third extraordinary shareholders' meeting resolution records passage of the 2026 interim profit-distribution proposal. This resolution does not establish per-share amount, payment date/completion, cash coverage, or sustainability. | `a30578712ce65e62c379ad4ca271693aa9819f45d15f8cf21850bfdc19dc8940` |
| `1225579978` | Counsel's legal opinion supports meeting procedure and voting validity; it is not independent evidence for the economics or amount of the distribution. | `f5c193122f1d66e881b4974a38715c1171f5ba90350e2527f6a00fc9882a2689` |
| `1225579977` | Board resolution concerns membership/chair assignments for board committees; no operating or distribution amount was established. | `4d3797622573ea6ae3ff407c4459f99df4dc74efea529995e028015c26f9419e` |
| `1225579959` | Independent financial adviser review concerns release of 457,665,903 shares that were issued earlier as restricted shares in the transaction. It reports total share capital of 21,689,434,304; the unlock changes tradable status, not total shares. Treat as dated float/supply monitoring, not a new issuance at unlock, operating evidence, or an automatic sell signal. | `a120d97bcd8686cf327e9510953bdb5558ab69508760d561678f2d80937c937e` |
| `1225579956` | Issuer's original unlock announcement, already separately archived and hashed in this memo above: 457,665,903 shares (2.11%) scheduled to become tradable on 2026-10-08. | `f7d78ed7a7270069f112060bd90cd2779b9fa81c774a522f826174f0fdb38cd2` |

The meeting resolution is `MATERIAL_SUPPORTING_EVIDENCE` for capital-allocation
monitoring only. Dividend amount, payment timing, cash coverage, sustainability,
and valuation impact remain `INSUFFICIENT_EVIDENCE`; the unlock remains
`MATERIAL_RISK_MONITOR` for potential float/supply. Do not infer a yield or
change model inputs. This local document review does not advance the registered
601088 event watermark: earlier continuous coverage is still missing, so its
formal status remains `INCOMPLETE`. All three valuation states remain
`VALUATION_NOT_READY`, strict PIT remains unproven, and `action=no_order`.

## Midea issuer-window gap fill and document review

An exact-issuer CNINFO query was run for 000333 over 2026-08-29 through
2026-09-27. The archived index is
`runtime/prospective-public-event-20260927/gapfill-000333-20260927T114140840633Z/index.json`
(SHA-256 `6c04cd73eeb3e3d79e9589b80398b96eafa34d36f7f49d317300a630e5ea1dab`).
The single raw page is SHA-256
`eb834a595b21868d75453f8afe2eafd5b502e73572d721af716e03a86d448198`, HTTP
200, 8 returned records, and `hasMore=false`. Scope is CNINFO's exact issuer
and bounded dates only; this does not establish continuous earlier coverage,
issuer-IR/exchange-site coverage, or correction coverage, and does not advance
the registered 000333 watermark (`INCOMPLETE`).

Three PDFs were downloaded through the repository's CNINFO disclosure adapter
to `runtime/prospective-public-event-20260927/midea-gapfill-originals-20260927T114140Z/`.
Their bytes were checked as PDFs and rendered for visual review because text
extraction produced garbled embedded-font mappings. The index retrieval time
is `2026-09-27T11:41:41.050337Z`; a durable downloader receipt was not
persisted, so no independently attested PDF-fetch timestamp is claimed.

| CNINFO ID | Available date (conservative date-level rule) | Finding and bounded classification | PDF SHA-256 |
| --- | --- | --- | --- |
| `1225544342` | 2026-09-04 | Reports 99,797,967 A shares (1.31% of total share capital) repurchased through 2026-08-31 for CNY 8,019,722,850 excluding fees; disclosed highest and lowest prices were CNY 87.71 and CNY 73.66. The notice says the 2026 program's use was changed from equity/employee plans to cancellation and reduction of registered capital, approved by the 2025 annual shareholders' meeting on 2026-06-05. `MATERIAL_RISK_MONITOR`: verify final buyback completion, cancellation and resulting share-count treatment. The progress notice does not prove cancellation completed; no current valuation input is changed. | `24900692f953f24bff8464e27e3383e91b2a272984e38bff21ca628b3d7cc50b` |
| `1225544482` | 2026-09-04 | The 2026 A-share employee plan received 15,772,385 shares by non-trading transfer (0.21% of total share capital). The notice traces these shares to a separate 2025 buyback and states a 2026-09-03 to 2028-09-02 lock-up. The company describes share-based compensation accounting during the service/vesting period but this notice does not quantify the expense. `MATERIAL_RISK_MONITOR` for compensation-expense and plan monitoring. This is not the 2026 cancellation program and not evidence of a new issuance; treatment in the ordinary-share denominator is not inferred. | `d93bfd07da79f6b5e11b1c7bbdb151a4fe021690a2a307c0fc3c1047b4716365` |
| `1225557650` | 2026-09-12 | The notice schedules a 2026-09-15 investor reception / interim-report briefing; that notice alone is `NOT_MATERIAL` to model inputs. It does not contain substantive answers; the meeting record/Q&A remains `INSUFFICIENT_EVIDENCE` until obtained and reviewed. | `f2711300f4011fd3c3602ad834e02e3b496fc4ff13386902e2ac3ce49d7b8e96` |

The indexed 2026-08-29 interim distribution proposal (`1225531406`) remains
only a proposal in the reviewed materials: CNY 5 per 10 shares and aggregate
cash distribution of CNY 3,724,298,992, subject to the stated shareholder
approval process. The bounded result contains no subsequent resolution or
implementation notice through 2026-09-27; approval, payment, cash coverage,
and sustainability are therefore not established here. The 2026H1 related-
party balances schedule (`1225531405`, physical pages 1-5, SHA-256
`a7c61ed6737c28071b28582c1db0faa40512e2c45521bb0df561e9e705a94344`) is
denominated in CNY 10,000. Its related-party table totals CNY 34.521bn opening
balance, CNY 4.472bn period debit, CNY 4.694bn period credit, and CNY 35.271bn
ending balance. The largest line is CNY 24.980bn due from Foshan Shunde Midea
Home Appliance Industry Co., identified as a subsidiary; the entity and
consolidation scope must be reconciled before treating this as an external
consolidated receivable. A separate related-bank line shows CNY 6.294bn opening
and CNY 2.644bn ending in non-current assets, described as financial products
with a term exceeding one year. The dedicated non-operating fund-occupation table reports none in its
listed controlling-shareholder/related-party categories. These schedules have
different scopes and must not be collapsed into a single conclusion. They are
not evidence by themselves of misappropriation, impairment, or cash-flow
stress; reconcile counterparties, eliminations, terms, impairment and
consolidated cash-flow treatment against the audited annual report and notes.
This line-level follow-up remains supplemental and is not admitted to the
versioned baseline snapshot or valuation inputs.

At the time of the original gap-fill review, no baseline snapshot, valuation,
dividend state, model input, PriceBridge, or canonical workbook changed. The
following later R1 review and product publication supersede only that
publication-status sentence; they do not change the pre-registration timing,
baseline, valuation, or event-watermark limitations recorded above.

## R1 materiality and product disposition — 2026-09-27

The retained CNINFO index and original PDFs were independently reviewed for
event classification and valuation dependency. All three documents were
public before the 2026-09-27 prospective observation start; they remain
retrospective historical material, not new prospective observations.

| CNINFO ID | R1 disposition | Dependency conclusion | Reopen trigger |
|---|---|---|---|
| `1225531406` | `MATERIAL_SUPPORTING_EVIDENCE`: the issuer proposed CNY 5 per 10 shares (aggregate CNY 3,724,298,992). | Supports capital-allocation monitoring only. Shareholder approval, implementation, payment, cash coverage and sustainability are not established; do not book a completed dividend or change valuation inputs. | Shareholder resolution and implementation notice, with share basis and payment date. |
| `1225544342` | `MATERIAL_RISK_MONITOR`: 99,797,967 shares (1.31%) bought through 2026-08-31 for CNY 8,019,722,850 excluding fees; highest price CNY 87.71 and lowest CNY 73.66. | The stated use was changed to cancellation/reduction of registered capital and approved, but this progress notice does not prove cancellation or the resulting share count. Do not alter current shares or per-share inputs. | Cancellation completion and updated registered share-capital evidence. |
| `1225544482` | `MATERIAL_RISK_MONITOR`: 15,772,385 existing shares (0.21%) were transferred from a separate 2025 buyback account to the 2026 employee plan, locked through 2028-09-02. | Not a new issuance and not the separate 2026 cancellation program. The notice describes share-based-payment accounting but does not quantify expense; do not change diluted shares or earnings inputs. | A later report or settlement disclosure covering expense recognition and share rights. |

These dispositions are evidence review outcomes, not permission to recalculate
or trade. The product now shows explicit supporting-evidence/risk-monitor
labels and monitor triggers instead of a generic pending-human-review label.
The valuation, prospective baseline, registered observation ledger and formal
000333 event watermark are unchanged. The source URLs remain in the versioned
projection report; the Excel audit sheet still shows local original paths and
SHA-256 but has no direct source-URL column. The canonical workbook publication
and WPS read-only verification are recorded in `docs/execution-status.md`.
`action=no_order`.

## 2026-09-28 watermarks v4 and R1 follow-up

### 美的中期分红方案支持性证据：CNINFO 1225531407

R1 原件复核确认 `1225531407` 是现有 2026 年中期分红事件的独立支持性证据，而非新事件或重复件。2026-08-29 董事会决议原件为 <https://static.cninfo.com.cn/finalpage/2026-08-29/1225531407.PDF>，本地留存于 `runtime/prospective-public-event-20260927/midea-baseline-originals-20260927T112500Z/1225531407.pdf`，SHA-256 `669fcc91ff5c791d7d71d860a2153324d81c8fb59af01e0d47574a818d0e0feb`。PDF 物理页 1-3 记载 10 票同意、0 票反对、0 票弃权通过方案并提交股东会；第 2 页重述每 10 股派现 5 元（含税）、按扣除回购专户股份后的 7,448,597,984 股测算总额 3,724,298,992 元。其第 3 页只是授权后续召开股东会，不是股东会表决结果。

既有方案公告 `1225531406` 的原件 SHA-256 为 `89337c66647fc1758eadc1f7c7d5a7308cf54b62ab1c92781d9dcf12c3b3b5b9`，同样明确尚待股东会审议。两份原件共同支持董事会审议及提案金额，不证明股东会已经批准、方案已实施或现金支付已完成。2026-10-13 股东会通知也只是议程，不可代替会后决议。事件仍为“待股东会批准/实施”；不改变 FinancialFacts、估值、决策状态或正式事件水位。待会议决议及实施公告后再分别核实批准结果、股数基准和支付安排。

The append-only successor `config/prospective-public-event-watermarks-v4.json`
preserves v3 and records seven retained exact-issuer CNINFO query windows for
601088. Independent byte review and focused regression tests verified the
index/raw-response hashes, requested issuer/date boundaries, returned and
total counts, page numbers, and `hasMore=false` termination. The windows form a
no-date-gap chain from 2026-03-31 through the 2026-09-27 19:22:35 +08:00
retrieval point; the 2026-08-25..31 window overlaps the preceding window and
does not create a gap. This is not coverage of issuer IR, exchange channels,
later corrections, or events after that retrieval point. The recovered
documents were public before the prospective observation start and do not
prove strict contemporaneous PIT.

The 2026-09-01..22 exact-issuer index returned four records whose original
PDFs were fetched and locally retained under
`runtime/prospective-public-event-20260927/shenhua-indexed-originals-20260927T154222Z/`.
The retained retrieval receipt binds the source index and original bytes:

| CNINFO ID | Title / bounded disposition | PDF SHA-256 |
| --- | --- | --- |
| `1225546779` | 2026 third extraordinary shareholders' meeting materials. The interim proposal is pre-tax CNY 0.98/share, about CNY 21.256bn total; capital-allocation support only. | `93c49e799e4e2767f78c74c10b36484fa746f6b8aa945e6f1fb7293150275311` |
| `1225565223` | August 2026 main operating data. Issuer-reported; comparison period restated and includes assets consolidated from April. Monitor only; not audited financial facts. | `9d458791200e6b47096859d58d825e5b9c1e619c82c90bf6cf05479eba9b0685` |
| `1225567741` | Registered office address change; nonmaterial to current investment research. | `8377a5db4aef315a9220ee3a17ec3ac99d378561e5e07d4e0556a8938ad02ef4` |
| `1225546775` | Notice convening the extraordinary shareholders' meeting; procedural/audit-only. | `86514cc6996d65e8f410742b280d8532a164726f96d36390f73e253574896d86` |

The later resolution `1225579981` (PDF SHA-256
`a30578712ce65e62c379ad4ca271693aa9819f45d15f8cf21850bfdc19dc8940`)
confirms passage of the interim distribution proposal on 2026-09-23. The
proposal amount is about 74.0% of 2026H1 PRC-GAAP parent-attributable profit;
this is a contextual ratio only. A-share implementation, record/ex/payment
dates, cash coverage and sustainability are not established. Do not treat it
as completed payment, dividend yield, valuation input, or buy/sell signal.

The independent event disposition and product projection are recorded in
`runtime/prospective-public-event-20260927/shenhua-event-projection-v2.json`
(SHA-256
`1c88dd83902b766ac0c208f2b837fa157b91d40189a91a4ddb79bd33cf82a971`). The
same canonical workbook now displays those two bounded monitor cards and
evidence links; publication and WPS read-only receipts are listed in
`docs/execution-status.md`. This projection does not change valuation or
advance strict PIT. `action=no_order`.
