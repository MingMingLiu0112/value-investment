# W7 Hotspot Structure Validation

- Action: no_order
- Trade intent: NO_TRADE
- Selection date: 2026-10-16
- Rule: hotspot-dated-sector-liquidity-ranking-v3
- Source report rule: hotspot-dated-sector-liquidity-ranking-v2
- Rule extension: RETROSPECTIVE_RESEARCH_EXTENSION
- Rule PIT: NOT_PROVEN
- Strategy validation: NOT_PROVEN
- Pool: 10 symbols / 10 industries
- Bound structure assessments: 1
- Unassessed pool members: 9
- Conflict or rejected cases: 7
- Expiry session: 2026-10-19

## Candidate pool

| Rank | Symbol | Industry | Structure status |
| ---: | --- | --- | --- |
| 1 | 600150 | 国防军工 | BOUND_ASSESSED / ACTIVE_ONLY |
| 2 | 000338 | 汽车 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 3 | 600176 | 建筑材料 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 4 | 000560 | 房地产 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 5 | 600667 | 建筑装饰 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 6 | 601857 | 石油石化 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 7 | 002008 | 机械设备 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 8 | 600019 | 钢铁 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 9 | 600127 | 农林牧渔 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |
| 10 | 000333 | 家用电器 | UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE / UNASSESSED |

## Preserved cases

| Role | Symbol | Date | Signal | Structure | Expiry |
| --- | --- | --- | --- | --- | --- |
| CURRENT_PRICE_CONDITION | 600150 | 2026-10-16 | WATCH | ACTIVE_ONLY | 2026-10-19 |
| CURRENT_PRICE_CONDITION | 600391 | 2026-10-16 | WATCH | CONFLICT_OR_REJECTED | 2026-10-19 |
| CURRENT_PRICE_CONDITION | 600967 | 2026-10-16 | WATCH | CONFLICT_OR_REJECTED | 2026-10-19 |
| CURRENT_PRICE_CONDITION | 600316 | 2026-10-16 | WATCH | CONFLICT_OR_REJECTED | 2026-10-19 |
| CURRENT_PRICE_CONDITION | 600893 | 2026-10-16 | WATCH | CONFLICT_OR_REJECTED | 2026-10-19 |
| HISTORICAL_NEGATIVE_CASE | 601318 | 2026-10-15 | TRIGGER_OBSERVED | CONFLICT_OR_REJECTED | 2026-10-16 |
| HISTORICAL_NEGATIVE_CASE | 300059 | 2026-10-15 | WATCH | CONFLICT_OR_REJECTED | 2026-10-16 |
| HISTORICAL_NEGATIVE_CASE | 600030 | 2026-10-15 | TRIGGER_OBSERVED | CONFLICT_OR_REJECTED | 2026-10-16 |

This artifact is research-only. Activity ranking is not a signal, the candidate pool is not an entry list, and no result establishes strategy profitability.
