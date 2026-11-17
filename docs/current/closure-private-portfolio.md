# Private Portfolio and Risk Wiring (W5)

`action=no_order`. No real holdings, cash, IPS, broker statement or private key
was read or fabricated.

## Engineering E2E

The isolated HTTP E2E uses a temporary `TEST_ONLY` ledger and exercises:

- account initialization and IPS admission;
- confirmed initial cash;
- a BUY draft and confirmation;
- exchange-calendar-aware T+1 sellable quantity;
- a partial SELL;
- fees and realised P/L update;
- restart and state continuity;
- stale/duplicate request rejection and ledger hash conflict checks.

The exchange calendar rejects weekends, known holidays, non-T+1 settlements and
uncovered venue/year inputs. It does not pretend that a simple `date + 1` is a
trading-day rule.

## Real-use boundary

The current public projection is `NOT_CONNECTED` and then
`BLOCKED_PRIVATE_INPUT`. It returns no position size, no target weight and no
trade eligibility.

The user must personally provide, through the controlled local workflow:

- real account cash;
- actual securities, quantities and sellable quantities;
- confirmed cost basis;
- dual-sleeve IPS and risk limits;
- broker reconciliation.

Until then:

```text
PRIVATE_ENGINEERING_E2E=PASS
REAL_PRIVATE_PORTFOLIO=BLOCKED_PRIVATE_INPUT
POSITION_GUIDANCE=null
```
