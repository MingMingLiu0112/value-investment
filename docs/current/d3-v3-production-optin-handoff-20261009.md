# D3 v3 Recommendation Production Opt-In Handoff (2026-10-09)

## Interruption Audit

Goal `VALUE-INVESTMENT-ADVISORY-AND-SENTIMENT-SATELLITE`. Baseline HEAD
`cc8680038efa38599339015ea75bf15addc47874` (`Fix product UX audit page column
scope`), equal to `origin/main` after `git fetch origin`. The tree remains very
dirty with inherited untracked D2/D3 work; nothing was reset, checked out,
bulk-staged or overwritten. This turn added no commit and no push. Canonical
workbook and current-trial pointer were not touched. No server, database,
scheduler, notification or production change.

## Work Package

`WIRE-D3-V3-PRODUCTION-OPT-IN`: make the v3 advisory recommendation reachable
from the real production entry point as an explicit opt-in, without changing the
default contract and without weakening any gate.

## Contract Fixes Found by Real Execution

1. `src/value_investment_agent/application/decision/restore_decision_recommendation.py`
   - v3 `NO_ACTION` no longer demands `model_validity` / `event_materiality`
     dependencies that the builder never emitted. Replay now requires exactly the
     bound dependency set. Regression:
     `test_v3_no_action_replays_without_optional_model_event_or_quote`.
2. `src/value_investment_agent/application/product/workbench.py`
   - accepts `recommendation_schema_version`; default remains v2;
   - rejects schedule/market/review/schema overrides in existing-manifest mode;
   - re-verifies the emitted v3 payload by replay through
     `ReadOnlyArtifactBundleRepository` before projecting a workbench.
3. `scripts/current/build_current_workbench.py`
   - exposes `--recommendation-schema-version`.
4. `src/value_investment_agent/application/product/decision_surface.py`
   - a workbench generated after the research date is legal; only
     `decision_as_of > generated_at` is rejected. Staleness stays ModelValidity's
     job. Regression: `test_current_workbench_allows_generation_after_research_date`.
5. `src/value_investment_agent/presentation/read_models/existing_research_report.py`
   - action-specific human-review sentences for BUY / ADD / HOLD / TRIM / SELL /
     NO_ACTION instead of one shared sentence.

## Real 600519 Data-Bound Replay

Command executed through the supported entry point:

```powershell
python -X utf8 scripts/current/build_current_workbench.py `
  --symbol 600519 `
  --package runtime/d2-model-bound-followup-20261008/package-v8-financial-scope-bound.json `
  --recommendation-schema-version advisory-decision-recommendation-v3 `
  --schedule-request runtime/d3-v3-production-optin-20261009/schedule-request.json `
  --output runtime/d3-v3-production-optin-20261009/600519-scoped-workbench-v3-final.json `
  --report runtime/d3-v3-production-optin-20261009/600519-scoped-workbench-v3-final.md
```

Observed result:

```text
schema                  = advisory-decision-recommendation-v3
recommendation_type     = NO_ACTION
confidence              = 低
current_price           = (not admitted)
valuation bear/base/bull= 404.82 / 479.88 / 572.74 CNY
model_validity.status   = UNKNOWN
price_bridge_status     = INVALID
price_attractiveness    = NOT_ASSESSABLE
portfolio_input_status  = BLOCKED_PRIVATE_INPUT
position_guidance       = null
decision_as_of          = 2026-10-08
research_status         = COMPLETED_WITH_BLOCKERS
action                  = no_order
```

Artifact SHA-256:

```text
600519-scoped-workbench-v3-final.json 70d969b77df752cb5c3f9e72b9ee0debf87ae360b10e6fc68eb59869d667dfe9
600519-scoped-workbench-v3-final.md   c6d4cff0edd7a7031f734db842e46eef261fb00f751b3da6ac2bb8f6f5107f68
```

An earlier attempt without the registered schedule request was refused as
`BLOCKED_NO_REGISTERED_SCOPE`; the stale `600519-workbench-v3.json`,
`600519-workbench-v3.md` and `600519-scoped-workbench-v3.json`/`.md` files are
retained as failure evidence and are not the accepted result.

## Verification

- Fresh targeted rerun this turn: `62 passed` covering v3 replay, decision
  surface, workbench decision projection and product CLI entrypoints.
- Full offline regression recorded for this slice: `4199 passed, 41 skipped` in
  728.15s.
- `git diff --check`: only benign LF/CRLF notices.

## Standing Blockers (unchanged, not worked around)

- Event materiality for the official originals remains pending human review.
- ModelValidity is `UNKNOWN`; no current quote admitted.
- Primary/neutral valuation is not approved; G3 remains false.
- No real IPS/portfolio/cash/risk constraints, so position sizing stays
  `BLOCKED_PRIVATE_INPUT` with `position_guidance = null`.
- D2 still IN_PROGRESS; `INITIAL_ASSISTED_USE` not reached.

## CI Outcome (updated 2026-10-09)

The first push of this slice (`4be8891`) failed GitHub Core Research Gates
because the commit was published without the working-tree dependency closure:
`research_artifacts.py`, `research_artifact_codecs.py`,
`research_application.py`, `source_bound_inputs.py` and related modules were
still uncommitted, so a clean checkout raised
`ImportError: cannot import name 'ARTIFACT_DECISION_RECOMMENDATION'` and
aborted 13 test modules during collection. The failure was reproduced from a
clean clone rather than inferred.

Repair commits: `6908d16` (source/script closure plus architecture inventory)
and `6f0a667` (24 accompanying test modules, including four suites updated for
the human-approval price-assessment flag). Independent clean-checkout
verification of the CI offline list: `1581 passed, 49 skipped` in 92.42s.
GitHub run `37898312249` for `6f0a6671b755d8a7de690d0cf430992db93cbdb6`
completed SUCCESS. No investment logic, threshold, valuation or gate changed.
## Next

Product-level D3 work is now the gap: emit a non-canonical product read model /
Excel preview from this real v3 workbench JSON to close the real
JSON -> presentation E2E, then continue the D2 evidence blockers above rather
than relaxing any of them. `action = no_order` at every layer.
