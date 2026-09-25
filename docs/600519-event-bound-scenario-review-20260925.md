# 600519 Event-Bound Scenario Review Package

Status: `PROPOSED_FOR_HUMAN_REVIEW` (2026-09-25). This is research preparation, not an approved AssumptionPackage, a new ValuationResult, a price target, or trading advice. Both ACTUAL material events remain `STILL_NOT_READY`; `model_executed=false`, `new_valuation_result=null`, `action=no_order`.

## 1. Evidence and point-in-time basis

| Evidence | Identity and timing | SHA-256 / current use |
| --- | --- | --- |
| July price announcement | CNINFO `1225431263`, [original PDF](https://static.cninfo.com.cn/finalpage/2026-07-18/1225431263.PDF); published/effective 2026-07-18; conservatively available from 2026-07-19 because intraday release time is unverified | PDF `24e51c43dfc6da7d3a19c67b88081715a3a3b4a26c2d83ec51a557e3e5692873`; event `m5-1f43cb646a5884b860d3cd98cdd5ff32` |
| H1 report | CNINFO `1225475868`, [original PDF](https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF); period ended 2026-06-30, published 2026-08-15, conservative `available_at=2026-08-16T00:00:00+08:00` | PDF `0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6`; event `m5-29224038bc5cd91d56cdb050ad05a998` |
| Five verified H1 facts | `runtime/m5-verified-facts-actual-20260925.json` in the isolated M5 worktree; original PDF/page/line/column-bound, verified 2026-09-25 09:09 +08:00 | Artifact file SHA `3481dd1773ec74fd705de1eaca47c7862e94562b5137f30a96912d75379a9fdb`; this ignored runtime file is not committed to Git |
| Parent equity and shares | [Issuer equity basis](../runtime/company-research/600519-consolidated-parent-equity-inputs-20260920T140639Z/evidence.json), report date 2026-06-30, assessment available 2026-09-14 18:55:50 +08:00 | File SHA `efc4dc37d81e9d4bf54930a5c2bf7cd50305b7b7ce808531ef4bc4138f80891b`; no claim of a current registry certificate |
| Materiality decisions | [Nine-decision review](../runtime/m5-600519-disclosure-queue-20260924/delegated-review-application-20260925/reviews.json), reviewed 2026-09-25 07:22 +08:00; two `MATERIAL_REQUIRES_RECALCULATION` | File SHA `46356cf809f73a66c2c0ea21257f297f20cd1d92e6578258303da2c8b60b9966`; decision IDs `cninfo-600519-1225431263-20260924.1` and `cninfo-600519-1225475868-20260924.1` |
| ACTUAL receipt and graph | Receipt `m5-run-56f1d3a52fb26e69a04cbc735f8d451a`, valid offline run 2026-09-25 08:10 +08:00; graph at `runtime/m5-actual-facts-graph-20260925.json` in isolated worktree | Receipt state SHA `8315eeb043b77adddb0a4c3a3772e404539a80731d092dbb0b8aca1423fd63ea`; graph policy SHA `5254ad4e202e6af6e9258e0ed41bf149a393f81e508b4ee4b442052eede86c13`, graph file SHA `9e14506c939b7359b86332515a89cc5d2e6c4e9c820b02986c1ad3531df9fa88` |
| Existing pending input | `runtime/m5-pending-research-input-complete-sources-20260925.json` in isolated worktree; research as of 2026-09-25; cites both PDFs, facts, equity basis and receipt | Input SHA `4e4bae0e877e599f5d54b17c4fcec0909752005f87b2adeebaaff320697105fd`; scenario inputs null, `valuation_inputs` node absent |

The H1 report cannot measure the July price action's *realized* outcome: its accounting period ended before the action. Receipt creation also precedes fact verification; the later research package may use both only at its later research time. Neither timing is backdated into a June decision.

### Verified accounting observations

All amounts below are CNY, current-period first column, consolidated scope unless noted. Source is the H1 PDF above; page numbers are physical PDF pages. Comparatives in the source line are not independently promoted as verified facts here.

| Fact | H1 2026 value | PDF page | Research implication, not a forecast |
| --- | ---: | ---: | --- |
| Operating revenue | 90,703,260,964.48 | 30 | Revenue basis; no July realization |
| Operating cost | 9,473,762,565.88 | 30 | Derived current gross margin 89.555%; channel-level margins unknown |
| Net profit, consolidated | 46,033,330,566.78 | 31 | Not parent profit or distributable cash |
| Cash received from sales | 98,421,697,395.39 | 33 | 108.510% of revenue; **not** operating cash flow or cash conversion after working capital |
| Monetary funds, period end | 53,518,798,979.08 | 25 | Balance-sheet stock, not free cash |

The separate issuer equity basis reports parent equity CNY `251253594419.50` and issued shares `1250081601` as of the H1 report. Shares are supported by physical page 22 and the equity rollforward by pages 28/37. The archived basis itself says `valuation_approved=false` and `as_of_registry_verified=false`; it is a model origin candidate, not a current capital certificate.

## 2. Archived conditional assumptions versus the ACTUAL events

Comparator: the [2026-09-24 conditional forward-assumption research](../runtime/company-research/600519-current-forward-assumptions-20260924T090504Z/evidence.json), SHA `57929708314a9255d02453aefb4053575ff8b1918d4506ee197ac777e2041f63`, and [conditional residual-income policy](../runtime/company-research/600519-consolidated-parent-equity-residual-income-current-20260924T090504Z/evidence.json), SHA `ad8bbeec2058cea818002e23c57dfee4a7b6b18143b93242d3630b60648e370f`. These were prepared *after* the disclosures but are not the completed ACTUAL descriptor. `passed=true` applies only to conditional research; `valuation_approved=false`, `simulation_eligible=false`, `trade_approved=false`. Their numbers are comparison anchors, not inherited approvals.

| Archived conditional assumption | New verified event evidence | Challenge and direction | Magnitude known? | Judgment needed? |
| --- | --- | --- | --- | --- |
| Earnings-growth stresses -5% / 0% / +5%, no extra company-wide price uplift | July affected-SKU prices rose CNY 100; H1 revenue/profit/cost are now PDF-verified | Price may help exposed sales, but volume/mix and company exposure can offset; H1 predates price | No | Yes: price-volume-to-ROE bridge |
| 75% payout (25% retention), stress payouts 50%/85% | H1 cash received from sales and monetary funds verified; parent equity/share bridge separately pinned | Cash receipts do not establish distributable cash; working capital, remittances and capital needs remain open | No | Yes: sustainable payout/retention |
| Five explicit years plus five-year fade | New H1 and July events require renewed durability assessment | Franchise duration could shorten or extend; neither follows from one price notice | No | Yes: forecast horizon and ROE fade |
| Terminal growth 2%, terminal ROE converges to cost of equity | No event-specific long-run reinvestment/ROE evidence | Terminal assumptions dominate long-run value; July one-off change is not recurring growth | No | Yes: terminal policy and sensitivity |
| Archived CNY nominal cost-of-equity cases about 5.81% / 6.76% / 7.70% | No refreshed, synchronized discount-input package for this event-bound date | Required return may have changed independently of business facts | No | Yes: date-aligned discount range |

## 3. July price transmission and falsification

The notice changes the 2026 53%vol 500ml SKU's platform retail display price `1539 -> 1639` (+6.498%) and sales-contract price `1269 -> 1369` (+7.880%), effective July 18. These are different transaction layers and **must not be added for the same bottle**. The [archived price/channel review](../runtime/company-research/600519-current-share-price-review-20260909T135607541717Z/evidence.json), SHA `b4d38f775005c34b3367e85dfb279748b70f2596732c68e6822a2482414d4e16`, records that target-SKU units and future channel weights are unknown; historical platform *all-product* share cannot be used as target-SKU exposure.

| Link | Machine-prepared observation | Missing test before model input |
| --- | --- | --- |
| Price | +6.498% retail; +7.880% contract | Recognized net price after VAT, channel terms and timing |
| Volume / demand elasticity | A volume drop beyond 6.10% or 7.30%, respectively, erases the exposed-channel revenue gain at unchanged mix; at -10% volume the isolated exposed revenue change is about -4.15% / -2.91% | Post-July target-SKU shipments, sell-through and demand elasticity |
| Channel mix | Retail and upstream contract weights must be disjoint | Target-SKU mix, distributor/platform substitution and double-count prevention |
| Company revenue | H1 90.703bn CNY was before July | Exposed recognized-sales weight; no company-wide +6.5%/+7.9% extrapolation |
| Gross / operating margin | H1 consolidated gross margin 89.555% | Post-July product costs, selling expense, mix and operating leverage |
| Cash conversion / working capital | H1 sales cash receipts exceed H1 revenue, but CFO was not among the five verified facts | Receivables, advances, inventory, taxes and actual CFO versus profit |
| ROE path | Parent equity is pinned at H1; no post-July ROE is observed | Forecast net income attributable to parent, retention and opening-equity bridge |

Strong contrary cases to retain: price-driven volume loss, channel inventory/wholesale-price stress, consumption weakness, H1 trend not extrapolating, one SKU repricing failing to sustain franchise ROE, cash/profit divergence, and terminal-value sensitivity. No single price increase establishes profit growth or intrinsic value.

## 4. Bear / base / bull leaves for the shared residual-income model

The existing shared model consumes, **for each scenario**, `cost_of_equity`, every `forecast_roes[i]`, `terminal_roe`, `terminal_growth`, and `retention`; it also consumes starting parent equity and ordinary shares. No leaf below is approved or registerable as `valuation_inputs`. Old conditional figures are review anchors, not automatic values. A five-year explicit period is a *review question*, not a frozen horizon; if approved with another horizon, enumerate every year in the completed package.

| Model leaf | Bear proposal | Base proposal | Bull proposal | Evidence / rationale | Sensitivity, counter-evidence, confidence |
| --- | --- | --- | --- | --- | --- |
| `cost_of_equity` | `UNKNOWN / NEEDS_RESEARCH` (old upper 7.70%) | `UNKNOWN / NEEDS_RESEARCH` (old central 6.76%) | `UNKNOWN / NEEDS_RESEARCH` (old lower 5.81%) | Archived discount policy in conditional model SHA `ad8bbeec...e370f`; needs synchronized event-date sovereign yield, beta and ERP inputs | +200bp stress in old policy; rates/beta asynchronous. **Low** |
| `forecast_roes[0..4]` | Five values `UNKNOWN`; test volume loss and slower margin | Five values `UNKNOWN`; test price-volume balance without automatic uplift | Five values `UNKNOWN`; test realized demand resilience | H1 PDF SHA `0e10aa26...6a4f6`, July PDF SHA `24e51c43...92873`, equity basis SHA `efc4dc37...e91b`; earnings-growth -5/0/+5 is **not** an ROE path | Vary exposure, volume, mix, margin, cash and retention; H1 predates price. **Low** |
| `terminal_roe` | `UNKNOWN`; test convergence toward reviewed cost of equity | `UNKNOWN`; test same | `UNKNOWN`; test whether excess return persists only with evidence | Archived conditional policy assumed no permanent excess return, not an event approval | Recalculate at cost and lower ROE; franchise fade may be faster. **Low** |
| `terminal_growth` | `UNKNOWN`; 0% stress reference | `UNKNOWN`; old 2% reference | `UNKNOWN`; old 2% is **not** a higher bull permission | Archived conditional policy SHA `ad8bbeec...e370f`; no perpetual growth evidence from July action | Test 0%/2%; require growth below cost of equity and terminal ROE. **Low** |
| `retention` (1 - payout) | `UNKNOWN`; old 50% stress reference | `UNKNOWN`; old 25% reference | `UNKNOWN`; old 15% stress reference | Archived forward policy SHA `57929708...1f63`, H1 cash/profit evidence and equity bridge | Test payout 50%/75%/85%, working-capital needs and remittance constraints. **Low** |

Starting book equity `251253594419.50` CNY and shares `1250081601` have a pinned issuer basis, but the completed descriptor must recheck its source bytes, as-of date and capital events. They are not scenario guesses. No Bear/Base/Bull value or valuation band is calculated from this incomplete table.

### Reverse valuation

Not run. This package has no independently checked, date-matched 600519 market close and quote-source SHA for the research timestamp, and the event-bound scenario/discount basis is incomplete. A later reverse run may solve for implied long-run ROE/growth only after those inputs are pinned; `Reverse Valuation != Buy Signal`.

## 5. Human Research Review Required

1. **A: Base path.** Is a stabilization case defensible after the H1 evidence and July SKU price change? Decide the explicit forecast horizon and each year's ROE only after reviewing actual target-SKU volume, channel mix and post-July realized margin. Old 0% earnings-growth stress is not a proposed ROE value.
2. **B: Bear path.** Decide whether the archived -5% earnings stress is severe enough; examine -10% affected-SKU volume, channel inventory/price pressure, weaker margins and cash divergence. Specify every ROE year or request more evidence.
3. **C: Bull path.** Require evidence of demand resilience and realized net-price/margin improvement before adopting any +5% earnings stress or higher ROE path. One-off list-price movement is insufficient.
4. **D: Terminal.** Decide forecast length, fade, terminal ROE and growth; explicitly test no permanent excess return and 0%/2% growth. Reject perpetuity assumptions unsupported by business evidence.
5. **E: Required return and distribution.** Refresh dated CNY cost-of-equity inputs and review the historical 5.81%-7.70% range; decide retention/payout with cash-flow, working-capital and capital-allocation evidence. Archived 25% retention is unapproved.
6. **F: Admission.** Record `APPROVE / REJECT / NEED_MORE_EVIDENCE` for a complete event-bound input set covering **both** material events, every scenario leaf and counterevidence. Approval must carry reviewer identity/time, individual evidence SHA, economic rationale and sensitivity; it cannot be inferred from this package or the conditional policy's `passed=true`.

If F is approved, attach a new completed descriptor while preserving every pending source/PDF/receipt binding, create a versioned AssumptionPackage, register `valuation_inputs`, and run the existing ResearchApplication/ValuationRouter. A new immutable ValuationResult first remains `MODEL_STALE` and `event_validity_status=UNRECONCILED`. Only a **separate** event-refresh reconciliation covering both materiality decisions, PDFs, facts, assumption package and new persisted `ModelValidity=VALID` may project `RECALCULATED`; decision review remains human and `action=no_order` throughout.
