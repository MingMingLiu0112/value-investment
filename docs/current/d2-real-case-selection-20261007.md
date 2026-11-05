# D2 real-case selection: 600887

Date: 2026-10-07. Scope: evidence-readiness selection, not investment approval.

## Selection

600887 is the first D2 real-company candidate. The repository retains official
financial originals, a conditional residual-income Bear/Base/Bull result, and
the October 1 official repayment and guarantee disclosures. In comparison,
000333 has four active accounting/model-scope Evidence Stops and 601088 lacks a
current-perimeter through-cycle parent-profit bridge. Selection is based on
evidence readiness, not expected return or likelihood of a buy state.

## Verified change and remaining gap

- CNINFO [repayment completion notice](https://static.cninfo.com.cn/finalpage/2026-10-01/1225591152.PDF), archived at
  `runtime/public-event-followup-20261002/1225591152.pdf`, SHA-256
  `f59267675689f0d77cc142d91e910e2e839adfc0282a260483e0858cc82a1ba3`,
  reports completion of SCP010/011 repayment on September 29. This supersedes
  the narrower statement that the repayment outcome was wholly undisclosed.
- CNINFO [guarantee notice](https://static.cninfo.com.cn/finalpage/2026-10-01/1225591147.PDF), archived at
  `runtime/public-event-followup-20261002/1225591147.pdf`, SHA-256
  `62815ec8a6fed035e1ead0d11f73ae8ce8d5f783a2c40a1b090259cbf6f4fe19`,
  introduces a separate guarantee-risk question. A guarantee ceiling is not an
  incurred loss or automatically an added consolidated debt balance.
- Neither original establishes post-repayment unrestricted cash, debt and
  refinancing, nor resolves the ordinary/special dividend classification.
  The two 600887 Evidence Stops remain active. Existing research is
  conditional; current ModelValidity, PriceBridge and Decision Review admission
  have not been established. `action=no_order`.

## Next real-input acceptance

Use the existing Evidence Stop reopen protocol for a bounded official
post-maturity cash/debt and refinancing bridge and dividend classification.
Record publication availability separately from retrieval. Only after those
reviews can the shared ResearchCase -> FinancialFacts -> gate -> valuation ->
ModelValidity -> current quote -> PriceBridge -> PreDecision -> DecisionReview
chain be replayed and projected into the canonical workbook. A legitimate
result remains `NOT_ASSESSABLE` or `WAIT` if the evidence does not admit more.

This selection does not block independent D2 product engineering or require
private portfolio data. No canonical workbook, server, order or portfolio
state was changed by this review.

## October 7 read-only negative decision evidence

The supported existing-result CLI read the pinned nine-original 600887
manifest (`runtime/publication-receipts/600887-existing-valuation-originals-20260930.json`,
SHA-256 `032dc2823dcd3e475221e45c8876be1af309b80bcbd8df705b40b33446ebe740`)
and wrote `runtime/d2-real-negative-20261007/600887-existing-read.json`, SHA-256
`1d1eaaab293007aacec26381962a251087649303fcb243bcbb7e9ed138c5e2e4`.
The retained valuation remains `conditional_research_only`; shared
PreDecisionEligibility returns `NOT_ELIGIBLE` with missing human approval,
event review, current model validity and quote bridge. The existing
InvestmentDecisionReview returns `INSUFFICIENT_RESEARCH`; price attractiveness
is `NOT_ASSESSABLE`; position guidance is null and `action=no_order`.

This is a current fail-closed read of *existing* research, not a fresh
ResearchCase/FinancialFacts admission, complete event scan, current quote, or
canonical product publication. D2 real-company vertical-slice acceptance
remains open. The next product step is to consume this verified negative
review through the ProductWorkbenchReadModel without presenting retained
conditional values as current fair value.
