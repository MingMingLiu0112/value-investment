# First Value-Research Case: 000333 Midea (W3)

`action=no_order`. This is a real, source-bound research draft, not an
approved valuation and not a buy recommendation.

## Executed research

- Research run: `midea-draft-20261017-v2`.
- Research cutoff: `2026-10-17`.
- Valuation date: `2026-10-16`.
- Execution receipt:
  `artifacts/current/midea-draft-20261017/research-execution-receipt-v2.json`,
  SHA-256 `566470fc37e8598b5a5b2bd39e58cf07ee561ae19f429e584ff964956ea3eb4d`.
- Research result:
  `runtime/company-research/midea-draft-20261017-v2/research-result.json`,
  SHA-256 `81f232242412f4b15b93f67e8d8c43132e26d19715484aa408b9eecb32140539`.
- Public draft:
  `artifacts/current/midea-draft-20261017/public-draft-v2.json`,
  SHA-256 `6ddde5fd690fd862126de50bebd314f091335bb722ed9fe4f580a0412d6ea907`.

## Conditional valuation

The admitted model path is the shared dated residual-income/equity-value
model, not the rejected industrial FCFF route.

| Scenario | Value per share (CNY) |
| --- | ---: |
| Bear | 36.01218666 |
| Base | 45.74170370 |
| Bull | 58.16867441 |

Confidence is **low**. Cost of equity, five annual ROE paths, terminal ROE,
terminal growth and retention are all explicitly bound to the registered
assumption memo. The values are conditional research outputs; they are not a
price band and do not create an order.

## Gate result

| Gate | Result | Reason |
| --- | --- | --- |
| G0 evidence | PASS | Source-bound evidence exists |
| G1 financial | FAIL | Financial/event completion criteria are not all satisfied |
| G2 thesis | PASS | Thesis, return driver, mispricing hypothesis, counter-evidence and breakers exist |
| G3 valuation | FAIL | Draft is not approved and material events remain unreviewed |

## Price bridge

`2026-10-16` dual-provider close is **84.60 CNY** and is
`VERIFIED_CLOSE_NOT_ADMITTED`. ModelValidity is `UNKNOWN`;
PriceBridge is `INVALID`; `price_admitted=false`; margins and position
guidance are null.

Blocking evidence:

- four 2026-10-14/2026-10-17 announcements remain
  `PENDING_HUMAN_REVIEW`;
- CNINFO coverage is explicitly incomplete;
- strict contemporaneous PIT is `NOT_PROVEN`;
- no real G3 approval exists.

## Version delta

The v1 to v2 update migrated the research inputs to the source-bound v2
contract, added physical-page anchors for nine financial facts, bound all nine
scenario assumptions to a hashed memo and added four announcements. Bear/Base/
Bull did not change. The absence of human approval, formal G3 and admitted
price also did not change.

