# Independent prioritized backlog (2026-10-16)

`action=no_order`. Derived from `docs/current/independent-full-project-audit.md`
at HEAD `34019fd`. Each item states the real business problem, root cause,
dependencies, whether it needs the user or new data, and how it will be accepted.
Effort scale: S (<=1 session), M (1-3 sessions), L (multi-session workstream).

## P0 - required before any real assisted decision

### P0-1 First authorized valuation for one company (recommend 000333 Midea)
- Business problem: after weeks of work, no company has a valuation a human can
  stand behind, so no price policy, no action, no usable advice can exist.
- Root cause: the economic inputs (normalized earnings, invested-capital return,
  parent distributable cash, issuer-specific cost of equity, advantage period)
  are unapproved or missing; only the model code exists.
- Why Midea first: industrial FCFF is already ruled `MODEL_NOT_APPLICABLE` with
  an audited reason, the shared RI route is authorized, the ex-treasury share
  count (7,464,347,335 at 2026-06-30) is verified, and six class-B scenario
  inputs are already enumerated. Yili is evidence-rich but blocked by the same
  legal-entity/cash bridges repeatedly; Shenhua needs 13 inputs from zero;
  Moutai is the RI reference case.
- Work: bind each required input to a primary document (annual/interim report,
  announcement) with page + hash; compute the input values with deterministic
  code; run the authorized RI model; publish a draft valuation package marked
  NOT YET APPROVED; prepare the review pack (facts, assumptions, sensitivities,
  counter-evidence, exact versions).
- Depends on: nothing (Shenhua/600519 continue in parallel as second cases).
- Needs user: no. Needs new data: yes (already-published filings; no paid feed).
- Acceptance: a hash-bound draft package whose inputs each cite a real primary
  document, with `evidence_authenticated=true` earned by evidence (not by
  assertion), reproducible by a single command, and a human-review pack ready.
- Effort: L.

### P0-2 Real human-review workflow (G3 + event materiality + price policy)
- Business problem: the only thing between "draft valuation" and "usable advice"
  is a human decision, and there is no product surface to make it, while the
  repository contains machine-generated records that look like G3 approvals.
- Root cause: review gates exist as CLI scripts and typed receipts; the Web has
  only the value-policy preview/confirm; `build_m1_post_review_receipts.py`
  fabricated `*-g3-human-approval-*` records with hard-coded specs.
- Work: (1) retire/rename the synthetic records and add a verifier that rejects
  script-generated approvals; (2) expose G3 review (model, facts, assumptions,
  versions, counter-evidence) and event-materiality review in the unlocked local
  Web flow, writing an append-only receipt bound to reviewer identity, exact
  artifact hashes and decision scope; (3) test the negative paths (expired
  session, wrong version, missing scope) and the happy path.
- Depends on: nothing (can be built before P0-1 finishes).
- Needs user: yes, for the actual signature; no for building the flow.
- Acceptance: a user can open the local app, review one draft valuation, and
  sign/decline with a receipt that another process can verify; synthetic
  receipts can never satisfy the gate.
- Effort: L.

### P0-3 One decision pipeline: retire or fence the legacy systems
- Business problem: three enabled Windows tasks (Moutai B1 daily update, preclose
  refresh, B1 Excel publish) and a server-side DB pipeline still write their own
  decision-shaped state; one task failed today (exit 1) and nobody acts on it.
- Root cause: the M-era pipelines were never formally retired after the new
  daily public packet became the product path.
- Work: decide per pipeline (retire / archive-only / fold into the new chain),
  disable the tasks with a recorded decision, mark the legacy 600519 pointer and
  DB tables as historical in one registry, and add a guard that fails if a second
  writer publishes decision state.
- Depends on: nothing.
- Needs user: no (a one-line confirmation that the old Moutai automation is no
  longer wanted is sufficient; it currently only produces non-admitted artifacts).
- Acceptance: exactly one scheduled/daily writer exists; the legacy surfaces are
  explicitly labelled in `docs/current/`; a verifier enumerates decision-state
  writers and fails if more than one is active.
- Effort: M.

### P0-4 Data custody and a proven restore
- Business problem: every verification this system performs today rests on
  gitignored `runtime/` on one PC plus a cloud-synced Excel; a disk loss ends the
  verified chain, and a fresh clone points at an older publication.
- Root cause: runtime artifacts were deliberately kept out of Git and no
  off-machine bundle + restore drill was ever defined for them.
- Work: define the recovery set (`runtime/` snapshot, PostgreSQL dump, canonical
  Excel), produce an encrypted off-machine copy, run one restore drill into an
  isolated location, extend `runtime-identity`'s dirty check to `config/`, and
  commit or export the live pointers.
- Depends on: nothing.
- Needs user: no (may need the user's chosen storage for the encrypted copy).
- Acceptance: a restore receipt proving the restored chain re-verifies today's
  publication id + packet SHA; the repo's committed pointers match the machine.
- Effort: M.

### P0-5 First real private onboarding (gate, user action)
- Business problem: without real cash/holdings/IPS, no position size, no risk
  budget, and no personalized advice can ever be correct - and fabricating them
  is forbidden.
- Root cause: the private flow was built and tested in TEST_ONLY mode but never
  unlocked with real facts.
- Work: the user unlocks the local app once, enters confirmed cash/positions/
  costs/sellable shares and the investment policy, reconciles against the broker;
  engineering fixes whatever blocks that (calendar validation for T+1, clearer
  wording, print/screenshot receipt).
- Depends on: P0-2 for a smooth review path, but can start immediately.
- Needs user: yes (real numbers only once). Needs new data: no.
- Acceptance: journal holds confirmed facts; projected equity equals the broker
  statement within the declared tolerance; risk preview runs on one candidate.
- Effort: S for the user + S/M engineering.

## P1 - required for a genuinely useful daily product

### P1-1 Widen the admitted research evidence base
- Problem: quality screening passes 0 of 5,573 because financial evidence exists
  for only 873 names.
- Work: instrument the funnel per channel with explicit gap reasons; add the
  missing official-financial acquisition/parsing where legally sourceable;
  re-measure. Keep deep research capacity-limited.
- Acceptance: a published per-channel gap report and a non-zero quality pass set
  whose members survive manual spot checks. Needs new data: yes (public filings).

### P1-2 Hotspot selection v2 (structure-first, cross-industry)
- Problem: Top-5 is a sector-strength/turnover cut taken before structure
  assessment; on the audit day all five came from one industry.
- Work: build the candidate pool first (e.g. industry-balanced), assess structure
  for the pool, and only then rank/present. Keep the day's regime block but make
  it either a real gate or explicitly cosmetic.
- Acceptance: a published day where selected names span >= 2 industries and each
  carries a computed structure tier with evidence; frozen-rule replay shows the
  change does not simply increase signal count.

### P1-3 Hotspot validation machinery and prospective shadow
- Problem: validation is descriptive statistics only; no costs, fills, or
  forward evidence.
- Work: costed execution model (commission, stamp tax, slippage, limit-up/down,
  suspension, T+1), PIT-reconstructed universe/classification, frozen rule
  version, and a shadow recorder that appends one dated observation per real
  trading session.
- Acceptance: `net_return_distribution` populated by the costed model; shadow
  counter increases only on real sessions; performance claims remain blocked
  until pre-registered thresholds are met.

### P1-4 Second intraday source (or licensed minute data)
- Problem: 60m/15m structure is single-provider; historical bars are acquired
  retroactively.
- Acceptance: dual-source intraday candles with a documented conflict rule; or a
  licensed feed with SLA; existing completed-bar contract preserved.

### P1-5 Held-risk completion
- Problem: T+1 sell dates accept any later date; held announcement review is a
  static placeholder.
- Acceptance: exchange-calendar validation rejects non-session sell dates;
  held review consumes the real disclosure feed; tests cover Saturday/holiday.

### P1-6 Excel and Web surface alignment
- Problem: the canonical Excel is frozen at the 2026-10-01 snapshot while the Web
  is live to 2026-10-16; two user surfaces disagree.
- Work: either resume publishing from the daily chain under the existing standing
  authorization, or declare the Excel a frozen quarterly snapshot with a visible
  version stamp and a pointer to the live Web.
- Acceptance: one documented policy + a user-visible version stamp; no silent
  divergence.

### P1-7 Daily scheduling consolidation + morning digest
- Problem: the new daily chain has no scheduler; the ones that exist belong to
  the legacy pipeline; a failed run can go unnoticed (today's exit 1).
- Acceptance: one scheduler runs the daily chain post-close; the morning product
  shows last run status and any failure reason; failures notify locally.

## P2 - valuable, not blocking

- P2-1 Opt-in live LLM agent pilot on one company (source-bound excerpts,
  counter-evidence only, no admission authority), with cost/limits recorded.
- P2-2 Architecture consolidation batch 2: thin `scripts/` (563 root scripts),
  migrate the 177 flat modules behind verified contracts, delete duplicated
  dated systemd copies and `render_dual_strategy_artifact_pages{,_v2,_v3}`, clean
  `runtime/.pytest-*` basetemps, and set a repo debt budget that CI enforces.
- P2-3 Web UX: expose the review/onboarding journey, reduce remaining code
  vocabulary, keep the system page secondary.
- P2-4 Historical replay page: make dated decisions and their evidence
  navigable per session; label replay as chronology, never performance.

## P3 - hygiene / documentation

- P3-1 Keep `docs/current/` curated; move superseded P-series evidence to
  `docs/archive/` with a pointer, so "latest evidence" is unambiguous.
- P3-2 Commit or archive the current untracked research docs (D2 series) so the
  repo matches the machine.
- P3-3 `docker-compose.yml` default password note: replace with an explicit
  placeholder that fails closed if unchanged.

## Dependency order

```
P0-3 (single pipeline) --\
P0-4 (custody/restore) ---+--> P0-1 (first valuation) --> P0-2 (human review) --> first authorized price policy
P0-5 (private onboarding) /                                                                     |
P1-1 evidence base ------------------> more companies                                              v
P1-2/P1-3/P1-4 hotspot ----> prospective shadow (natural time) --> strategy claims      REAL_ASSISTED_USE
P1-5/P1-6/P1-7 daily product -----------------------------------------------------------> daily usable product
```

## What only the user can provide

1. Real private facts (cash, holdings, costs, sellable shares) and the personal
   IPS - once, through the local unlocked flow (P0-5).
2. The actual G3 / materiality signature on the first approved valuation (P0-2)
   - the system may prepare the pack and must never self-sign.
3. A decision that the legacy Moutai automation should be retired (P0-3).
4. Storage location(s) for the encrypted recovery copy (P0-4).
5. Final acceptance that the product is useful in daily practice.

`action=no_order`.
