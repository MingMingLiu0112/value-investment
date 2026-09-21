# Excel MVP Stage A Acceptance

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
| Three uniform research objects | `ResearchCase`, `ResearchGate`, and three records in the pinned payload | Passed |
| Homepage summary | `00_首页Dashboard` displays the three fixed cases with path, data date, research/valuation state, counterevidence, blockers and next event | Passed |
| Research gate and blocked valuation state | All three records have G0-G3 results, blockers, and `估值未就绪` | Passed |
| Financial summary | 600519 has H1 2026 financial anchors; 000333 has explicitly restricted TTM scope; 601088 explicitly states current financial evidence is not admitted | Passed, with disclosed limits |
| Business thesis, support, counterevidence, breakers, next event | Every record includes all five structured sections with evidence kinds | Passed |
| Traceability | Every case has named evidence references with file paths and SHA-256 | Passed |
| Original Excel display | Published WPS workbook contains the three MVP cards on `00_公司总览` | Passed |
| No valuation/order promotion | Payload has `formal_trade_instructions: false`; all cases are `not_ready`; Excel labels say no price, position, or order | Passed |

## Runtime Verification

- Focused Python tests: `18 passed` after the Stage A artifact tests were added.
- Isolated workbook build: preserved non-derived source-cell fingerprints,
  internal-link serialization and layout checks.
- WPS COM verification: passed against the published WPS cloud workbook. The
  verifier followed the homepage, company overview, pending, research,
  valuation and decision links and retained a formula calculation check.
- Publication: original file was hash-guarded, backed up under
  `runtime/workbook-backups/published-20260921-excel-mvp/`, then atomically
  replaced. Published SHA-256:
  `E83C482A330FE80005183965271EA8C3E63C1EDC8B66532876666324FF66F0EE`.

## Objective Assessment

Stage A is usable as a research triage surface: it makes the difference between
evidence, interpretation, gap and blocked valuation visible for three
companies. It is not yet usable to decide a purchase, sale, position size or
portfolio allocation. In particular, the Moutai work remains a constrained
research model rather than an approved fair value; Midea lacks approved
per-share inputs; and Shenhua lacks a current fundamental evidence package.

The next plan remains appropriate: Stage B starts with Moutai, completing a
specific applicable valuation contract, dated inputs, scenario analysis,
assumption sensitivity and reverse-valuation result before moving to Midea.
It must not use the existing Stage A cards as a substitute for those checks.
