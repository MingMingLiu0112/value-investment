# Excel MVP Stage A Acceptance

> Status as of 2026-09-21: **passed for the Excel research-workbench scope**.
> This is not a valuation, simulation, portfolio, or trading-readiness acceptance.
> Each unresolved evidence, financial, valuation and price dependency remains
> visible in the corresponding card and gate output.

Date: 2026-09-21

## Scope and Evidence

This acceptance covers only Stage A in
[value-investment-excel-mvp-goal.md](value-investment-excel-mvp-goal.md): the
uniform research object, gate and original Excel presentation for 600519,
000333 and 601088. It is not a valuation, strategy, simulation, or live-trade
acceptance.

The authoritative generated artifact is
`runtime/excel-mvp-research-cases/evidence.json`, pinned by
`runtime/excel-mvp-research-cases-latest.json`. The pointer SHA-256 was
recomputed on acceptance and matched the evidence file. Each evidence
reference in the three records was also hash-addressable locally.

## Requirement Audit

| Stage A requirement | Evidence | Result |
| --- | --- | --- |
| Three uniform research objects | `ResearchCase`, `ResearchGate`, and three records in the pinned payload | Structural pass |
| Homepage summary | `00_首页Dashboard` displays the three fixed cases with path, data date, research/valuation state, counterevidence, blockers and next event | Structural pass |
| Research gate and blocked valuation state | G0 evidence, G1 financial, G2 business and G3 valuation results are independently saved with blockers. All three cases pass G2; no case is promoted through G3. | Pass |
| Financial summary | Each card contains dated, scoped facts and explicit five-dimension status where available. Midea and Shenhua retain financial gaps rather than filling them with scores or estimates. | Pass with disclosed gaps |
| Business thesis, support, counterevidence, breakers, next event | Every case has at least three evidence-linked supporting facts, three counter-evidence items, three thesis breakers and registered next events. | Pass |
| Traceability | Every current case has named local evidence references with file paths and SHA-256 | Structural pass |
| Original Excel display | Published WPS workbook contains the three MVP cards on `00_公司总览` | Structural pass |
| No valuation/order promotion | Payload has `formal_trade_instructions: false`; all cases are `not_ready`; Excel labels say no price, position, or order | Pass |

## Runtime Verification

- Focused Python tests: `16 passed` in the latest Stage A research, gate,
  valuation-boundary, price-bridge and profile regression run.
- Isolated workbook build: preserved non-derived source-cell fingerprints,
  internal-link serialization and layout checks.
- WPS COM verification: passed against the published WPS cloud workbook. The
  verifier followed the homepage, company overview, pending, research,
  valuation and decision links and retained a formula calculation check.
- Publication: original file was hash-guarded and atomically replaced from
  `runtime/workbook-backups/frontdoor-20260921T091602230674Z/`. Published SHA-256:
  `0EEEAEA8143DB9D6969A0C85F09D99850988E46551799FB4689F75A338CF37AE`.

Later on the same date, the B1 same-date Moutai result was independently published
from `runtime/workbook-backups/frontdoor-20260921T124307037961Z/`, changing the
canonical workbook SHA-256 to
`A9F9BC91AF801F26E45B21CD3CEAA2840B67110F9FCFD2F8034FB5DAD6F298D5`. That later
publication is a Stage B result, not a change to this Stage A acceptance.

A later Shenhua subsidiary-allocation evidence package and its corresponding Stage A
research-card traceability update were published from
`runtime/workbook-backups/frontdoor-20260921T155641364470Z/`. The focused new package and
Stage A research-case tests passed (`9 passed`), and the canonical workbook SHA-256 became
`F96ED4D90701C999BFE0491B0DAFCBE2427992D99CB7075B1E487AF5A81ED0E5`. This also does not
change the Stage A acceptance result or permit valuation or trading promotion.

On 2026-09-22 the IFRS 12 subsidiary-tax review was added to the Shenhua research card and
published from `runtime/workbook-backups/frontdoor-20260921T161640335295Z/`. The focused
research-case and IFRS-review tests passed (`10 passed`), and the canonical workbook SHA-256
became `17036D1F8EBC094DF9287AB25B4BF256F70B6AA9F1DF23DEDD16D3E7A98AFA9B`. This preserves
the Stage A acceptance result and keeps valuation and trading promotion blocked.

## Objective Assessment

Stage A is usable as a research workbench: it makes facts, interpretation,
counterevidence, gaps and blocked valuation visible for all three companies.
It is not usable to decide a purchase, sale, position size or portfolio
allocation. Moutai remains a constrained, no-current-price research model;
Midea lacks approved FCFF and per-share inputs; Shenhua lacks the debt, resource,
cost-curve and normalized-cycle package required for a cyclical valuation.

The next plan follows Stage B's model order: first obtain a date-matched,
reproducible Moutai valuation and price bridge; then finish Midea FCFF scope;
then build Shenhua's cyclical-normalization input contract. No Stage B result
may be promoted to simulation or trading readiness without its own acceptance.
