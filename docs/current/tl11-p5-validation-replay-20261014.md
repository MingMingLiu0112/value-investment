# TL11-P5-B frozen v1 event replay

## Protocol registered before outcome calculation

Baseline HEAD: `b8971a318427be3dd0b1111b48a060ce60cd2385`.
The specification is `artifacts/current/tl11-p5-20261014/replay-spec-v1.json`.
Its registration time is the actual local clock, not a historical research time.
Existing v1 calculation and signal code are byte-bound and remain unchanged.

The fixed five cases are 300364, 300413, 300418, 300058 and 002354 from the
current registry. Their common minute window begins 2026-04-13. Development is
2026-04-13 through 2026-06-30; the temporal validation segment is 2026-07-01
through 2026-10-14. Only five preceding completed bars feed each v1 calculation.
Earlier bars may supply warm-up, never outcomes. Outcomes cannot cross the
development/validation boundary. No thresholds, dates or horizons are optimized.

This is a retrospective, fixed-current-candidate case study. Today's selection
does not reconstruct historical sector membership or the investable universe.
Source acquisition occurred on October 14, not at the historical signal times.
Time partitioning does not establish strict PIT, independent strategy OOS,
survivorship safety or stable profitability. Unadjusted corporate actions and
single-provider minute evidence remain explicit limitations.

The primary rule is the existing 60m strict close above prior-five high with
volume at least 1.2 times their mean. Daily and 15m are completed-at-cutoff
descriptors, not extra admission gates. Five subsequent *observed* session closes
are the fixed outcome horizon, not a certified complete exchange calendar.
False-breakout proxy means a subsequent 60m close at/below the frozen trigger
through the next observed session close. Failure means a close below the frozen
invalidation through the fifth observed session close. Missing follow-up is
censored. Overlapping events are counted as events, not independent trades.

Forward close changes and adverse excursion from the signal close are descriptive
price outcomes, not fills, trade returns or trade MAE. True net returns, costs,
slippage, average trade wins/losses and executable stop outcomes remain null when
dated execution evidence is missing. The existing virtual-account engine can
check explicit synthetic execution controls separately; no replacement engine
or hypothetical private capital is created for these real cases.

## Interfaces and scope

`domain.hotspot.event_replay.replay_v1(bars_by_period, spec)` returns event
records, cutoff-only states, fixed-horizon descriptive outcomes and segment
counts. `application.hotspot.event_replay.build_replay(root, spec_path,
expected_sha256, now)` verifies originals using the current-price loader,
computes real dependency availability and returns a report with source hashes.
`application.hotspot.event_replay.write_replay(...)` saves append-only artifacts.

`domain.hotspot.shadow_observation.make_shadow_baseline(case, plan, observed_at)`
records only an actually completed current observation. No previous archived
judgment is invented; no future session row is emitted; elapsed Shadow session
credit is zero. The optional comparison requires a prior archived baseline and
can only evaluate subsequent *already observed* bars.

Root owns `confirmed_price_structure.py` and
`analyze_price_behavior(bars: dict[daily/60m/15m]) -> dict`, rule version
`hotspot-confirmed-structure-v1`. It is not imported, edited or silently mixed
into v1. Existing `price_behavior.py` and `describe_bars` remain unchanged.

All results retain `action=no_order`, formal eligibility false and personal
eligibility unknown. No packet, Web, backend route, Excel, scheduler or private
data is changed.

## Actual frozen v1 results

Run time: 2026-10-14 21:06:18 Asia/Shanghai. Maximum necessary evidence
availability: 2026-10-14 18:05:04.861142+08:00, using all minute sources,
the dual-close bundle completion and referenced source/calendar fetches.
Development has 1,060 completed cutoffs and 65 triggers; temporal validation
has 1,400 cutoffs and 117 triggers. Of the latter, 100 have full five-observed-
session follow-up and 17 are censored. Validation failure proxy is 35/100;
false-breakout proxy is 56/113. These denominators differ by declared horizon.

| Symbol | Validation triggers | Full five-session paths | Failure proxy | False-breakout proxy | Mean fifth-close change | Worst signal-close excursion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 300364 | 25 | 21 | 6/21 | 9/24 | 3.01% | -12.49% |
| 300413 | 28 | 24 | 7/24 | 15/27 | 4.03% | -23.94% |
| 300418 | 23 | 19 | 7/19 | 13/21 | -1.24% | -20.68% |
| 300058 | 22 | 20 | 9/20 | 13/22 | 1.62% | -17.52% |
| 002354 | 19 | 16 | 6/16 | 6/19 | 1.04% | -27.36% |

Price changes are raw Decimal observations; this table rounds only their
presentation. They exclude execution and corporate-action normalization, are
not total shareholder returns, and do not show strategy profitability.
The substantial false-breakout/failure counts and adverse excursions do not
support upgrading this simple rule to an admitted trading strategy.

All five actual October 14 primary states are WATCH. Five baseline rows record
only the actually completed October 14 session, with original case hash and
actual observation/source-availability times. No previous Shadow judgment,
future session, simulated account or real trade is created. Elapsed credited
Shadow sessions remain zero.

Artifacts:

- `replay-spec-v1.json`: SHA256 `750220bcb8639c8c78f7b337a67f006ae8b076fcdc362e79336e58e2bca252f2`.
- `replay-results-v1.json`: SHA256 `9ea23276ae58d853541915e84adf3e0894fed01e3fa57aee65672c98ead011f0`.
- `replay-shadow-baseline-v1.json`: SHA256 `4b95391af03ee2d8814ed02973ddeed7159e42ea965f93e63f86c11d67b01469`.
- `replay-manifest-v1.json`: SHA256 `084db88666db823d788a928388a99633bbc7916363729dcda8720f363fe33373`.

Original source bytes remain in existing immutable local runtime directories;
the manifest records exact relative paths and hashes. This package does not
claim independently portable recovery without those originals. It does not
duplicate a market-wide snapshot or modify historical originals.

The real run was repeated read-only: all five event/result objects, dependency
availability, implementation hashes and archived output hashes matched.
Scoped v1/current-case/plan/registry tests passed: 39 tests. Execution controls
are synthetic tests using the existing virtual account, explicit costs,
slippage and quantity; they are not actual execution validation of these cases.

## Separate new-rule prefix description

After Root's rule became available, a separate protocol was registered at
2026-10-14 21:08:36+08:00: `replay-structure-spec-v1.json`. It binds
`confirmed_price_structure.py` and its existing registration byte hashes,
and inherits the frozen five cases and chronological partitions.
Original v1 outputs are not rewritten. Neither rule parameters nor thresholds
are changed.

`domain.hotspot.structure_replay.observe_structure_prefixes(bars, spec)` calls
Root's `analyze_price_behavior` on each completed 60m prefix. Daily rows are
included only after 15:00 Shanghai; confirmed swings must already be known.
`application.hotspot.structure_replay.build_structure_observation(...)`
verifies the same real cases and produces separate immutable results.

The comparison measures inherited trigger/protection equality, state transitions,
daily trend descriptions, next-bar confirmations, pullback recovery descriptions
and availability of structural upper space. State-transition frequency is a
descriptive stability measure, not evidence of predictive edge or net returns.
Raw windows with fewer than six completed bars are explicitly unavailable;
adequate raw windows lacking two confirmed highs/lows are separately marked
INSUFFICIENT_CONFIRMED_SWINGS. Missing upper resistance keeps risk/reward null.
This is retrospective prefix analysis, not prospective OOS validation.

Actual new-rule run evaluated 2,460 primary prefixes. Each case has 212
development and 280 validation cutoffs. The first development cutoff has only
four contemporaneously completed 15m bars, so each case has one explicit
MISSING_COMPLETED_BAR_WINDOW row. The remaining 2,455 prefixes have adequate
raw windows; none lacks enough confirmed daily swings in this actual source
history. Synthetic regressions separately exercise sufficient raw data with
insufficient confirmed swings, and missing minute data with no fabricated result.
Current source windows for each case are 492 daily, 1,968 60m and 1,968 15m bars.

| Symbol | October 14 daily trend | Validation next-bar confirmations | Pullback recovery observations | Available structural ratios | V1 state changes | Daily-trend changes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 300364 | DOWNTREND | 23 | 6 | 242/280 | 93/279 | 11/279 |
| 300413 | RANGE | 23 | 3 | 209/280 | 104/279 | 7/279 |
| 300418 | DOWNTREND | 17 | 2 | 238/280 | 80/279 | 11/279 |
| 300058 | DOWNTREND | 17 | 2 | 251/280 | 89/279 | 9/279 |
| 002354 | DOWNTREND | 16 | 2 | 265/280 | 95/279 | 6/279 |

All complete prefixes retain identical v1 trigger, invalidation and raw breakout
conditions (zero mismatches). New-rule validation has 96 next-bar confirmation
observations and 15 recovery observations. They are observation timestamps,
not a trade count or a survival fraction of the 117 v1 signals: confirmation is
observed on a different completed bar and recovery can repeat. Daily trend
changes less often than the 60m v1 state, but the two describe different horizons;
this does not prove better stability, better entry timing or predictive edge.
Structural ratio availability does not certify risk/reward after costs or execution.
Four actual latest downtrends give unfavorable background, not personal sell
permission; the remaining RANGE is not approved entry permission either.

New output `replay-structure-results-v1.json` SHA256:
`97e2d27d54c15ddbf32896057cd64629766caf966708a5eb8d6f642a58796e84`.
New manifest `replay-structure-manifest-v1.json` SHA256:
`1c4e270a58e909b6b51fee1909892c3155338d745ca6e06728da2cbf912aceb5`.
Both rule registrations, original cases and implementation files are bound;
all bound source-code hashes were checked again after the run.

## Final handoff and Web consumer contract

Root can call the read-only application interface:

```python
from value_investment_agent.application.hotspot.replay_read_model import load_replay_summary

summary = load_replay_summary(
    root=root,
    manifest_sha256="084db88666db823d788a928388a99633bbc7916363729dcda8720f363fe33373",
    structure_manifest_sha256="1c4e270a58e909b6b51fee1909892c3155338d745ca6e06728da2cbf912aceb5",
)
```

Return schema is `hotspot-replay-web-summary-v1`. Root owns any HTTP route;
none is added here. Top-level fields are status, reference_scope, computed_at,
data_available_at, partitions, manifest hashes, items and limitations. Per-symbol
items expose case_sha256, v1_rule_version, v1_segments,
archived_v1_observation, structure_rule_version, structure_segments and
archived_structure_observation. Passing no structure manifest returns explicit
null new-rule fields. Externally pinned manifest hashes and bound result bytes
are checked; unrelated input chains and changed reports are rejected.

The Web must keep `reference_scope=FROZEN_REPLAY_NOT_CURRENT_JUDGMENT` visible
in its presentation and distinguish raw price-path proxies from executions.
Do not feed these historical rows into current admission or personal quantity
calculations. Source numeric strings retain full precision; a UI can round
display to two decimals without rewriting evidence. Formal and prospective
OOS eligibility remain false; personal eligibility remains null.

The actual consumed payload is also saved in `replay-web-summary-v1.json`,
SHA256 `06f78a3921b394cb6c4d2ff7bc3591ef81adec5c863f2b5be0bd22c9f8fd2775`.
`replay-verification-v1.json` records actual window checks, inherited counts,
code/source hashes and the 51-passed scoped test run. New baseline rows remain
October 14 only, with zero elapsed Shadow session credit.

Owned source additions:

- `domain/hotspot/event_replay.py`
- `domain/hotspot/shadow_observation.py`
- `domain/hotspot/structure_replay.py`
- `application/hotspot/event_replay.py`
- `application/hotspot/structure_replay.py`
- `application/hotspot/replay_read_model.py`

Tests: `test_hotspot_event_replay.py`, `test_hotspot_structure_replay.py`,
`test_hotspot_replay_read_model.py`. Final selection also includes Root's
`test_hotspot_price_behavior.py` and the existing current-case/plan/registry
tests. Result: 51 passed. All pytest/trust-registry temporary data remained
inside repository `.tmp` by setting Python's process-local `tempfile.tempdir`
before `pytest.main`, without weakening the trust-registry guard.

No existing hotspot module, Root structure rule, packet, Web, backend route,
Excel, private data, current pointer or scheduler is edited. No commit.
