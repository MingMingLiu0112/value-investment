# VALUE_LOOP findings, 2026-10-19

Scope: focused G3 implementation, no commit or publication. Baseline HEAD:
`b98f49e3f84bac8a0e044adfff89c3341e2422d7`, branch
`codex/web-d1-investment-workbench`. This is evidence, not a task ledger.

## Actual source and consumer findings

Read the current draft pointer, bound v4 draft and consumed-v3-dated package in
`artifacts/current/web-first-acceptance/s2/midea-consumed-v3-dated/`.
Rebuilt the actual descriptor through the production draft loader after the fix:
`SOURCE_AND_MODEL_INPUTS_MATCH`, input SHA-256
`574a7a1b649d27ac330860e63b20b587f4aec9da984be4f8a57b884f657cb5c6`.
The existing `source_bound_inputs.py` already validates the two required capital
inputs, direct bindings, units, periods, source scope and deterministic conversion.
It needed no change for this bounded fix.

Inspected retained official PDF text directly, not just the draft narrative:

- Half-year report `runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf`,
  physical page 7, SHA-256
  `576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8`:
  revenue 260,042,490 thousand CNY; parent profit 26,446,037 thousand;
  adjusted parent profit 19,595,179 thousand, down 25.31%; parent equity
  212,861,055 thousand. Weighted H1 ROE 11.33% versus 11.29% in prior H1.
  The report explains FX losses versus derivative gains in different recurring/
  nonrecurring classifications. This does not establish a tax/parent-attributable
  normalization adjustment or prove operating profit declined by 25.31%.
- HKEX June monthly return
  `runtime/company-research/midea-denominator-recheck-20261013/hkex-window-20260701-20260807/originals/12235688-2026070700419_c.pdf`,
  physical page 2, SHA-256
  `fab9be2f0349dcda9880b178e45e4dd65474b98635bf454adeeb19ed7bc3ecfd`:
  A shares excluding treasury 6,813,498,835 plus H shares 650,848,500 equals
  7,464,347,335. Treasury A shares 149,091,572 are excluded. Parent equity
  converts exactly to 212,861,055,000 CNY. These are capital facts, not approval.

Closed two consumer gaps: financial facts were present but not rendered by
`ResearchDraftPanel.tsx`; bound-draft verification recomputed per-share value
but accepted altered terminal contribution, timing factor and dividend
cross-check diagnostics. Supplied diagnostics now must equal shared-model
sensitivities and be finite. Optional absence stays backward compatible.
Financial facts now display scope/unit labels and preserve null as missing.
No model, valuation assumption or threshold changed.

## Decisive admission evidence

Actual loader still returns `RESEARCH_DRAFT_NOT_APPROVED`, model validity
`UNKNOWN`, G1/G3 false, PriceBridge `INVALID`, price_admitted false,
economic_approval false and action `no_order`.
Four announcements remain pending materiality review: 1225608903,
1225603532, 1225603533 and 1225603534. Coverage remains `INCOMPLETE` and
`STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN` remains explicit. The current formal
value-policy review manifest contains 600887 only, not an approved 000333 plan.
The company registry still reports economic input/review gaps. Its route
authorization does not approve the newer conditional draft.

ROE persistence, distribution/retention and cost of equity remain unapproved
economic assumptions. Consolidated CFO is not parent distributable cash.
No new economic evidence was sufficient to grant real admission.

## Verification

- Python source contracts, bound drafts and existing P7 signed workflow:
  187 passed. Includes TEST_ONLY positive signed publication/plan/risk/manual
  workflow, revoked/tampered signatures and missing explicit price permission.
- Research-draft API regression: 6 passed.
- Web research panel: 8 passed; TypeScript check exited 0.
- Actual current 000333 loader successfully reverified retained source hashes,
  capital derivations, assumptions, model outputs and new diagnostics.
- Scoped formatting applied; git diff whitespace check passed.
- Initial test attempts failed during trust-registry setup because TEMP/TMP did
  not match repository basetemp. Successful run set both to repository `.tmp`.
- Browser interaction, live server restart and full Core/Web suite: NOT_RUN.
  No claim of full VALUE_LOOP engineering acceptance or live investment readiness.

Only implementation files changed: `application/product/research_draft.py`,
`tests/test_bound_research_draft.py`, `ResearchDraftPanel.tsx` and its Web test,
plus this permitted findings document. Concurrent unrelated edits were preserved.
No config/runtime publication pointers, ledger, Excel, shared API/types,
portfolio, hotspot or agent_review files were edited by this work.
