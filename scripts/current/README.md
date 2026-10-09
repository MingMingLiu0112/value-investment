# Current CLI Wrappers

The authoritative product/engineering split is
`config/current-cli-entrypoints-v2.json`. The v1 registry remains in place for
compatibility and every v1 path is preserved in one of the v2 layers.

Generic product commands in this directory accept `--symbol` as an argument and
delegate orchestration to `value_investment_agent.application.product`. This
directory holds thin CLI wrappers only.

Run the manual trade-before-research assistant with
`python -X utf8 scripts/current/run_daily_trade_assistant.py --symbol 600519`.
It attempts the existing same-day dual-source close collector, then runs the
registered source-bound research case, v3 advisory decision, offline three-role
review and a runtime-only Excel preview. Read `report.md` and `receipt.json`
under the printed run directory. Use `--no-collect-quote --agent-mode mock` for
an explicit offline product check; the mock never becomes admitted research.
An unregistered symbol, stale model, invalid quote or missing private portfolio
cannot manufacture a buy price, position size or order. `000651` is a second
registered research case with no source-verified product handoff yet, so it
emits a workbench/report but no Excel preview.

`register_prospective_research.py` creates an immutable, runtime-only receipt
for the committed public observation plan. It records research scope and PIT
rules before outcomes are observed; it does not fetch data, value a company,
write the canonical workbook, create a decision signal, or touch private data.

`stamp_prospective_checkpoint.py` creates or verifies a forward-only RFC 3161
timestamp chain for explicitly public research bytes. The signed time proves
only that those bytes existed no later than the TSA time; it cannot repair a
historical timestamp, validate the registered baseline retrospectively, or by
itself admit strict PIT. Creation requires `--public-research-only` and a
locally trusted CA bundle; chains are written under `runtime/`.

```powershell
py -3 scripts/current/stamp_prospective_checkpoint.py create `
  --payload runtime/public-observation.json `
  --output-dir runtime/prospective-timestamp-chains/observation-20260928 `
  --ca-bundle C:/path/to/trusted-ca-bundle.pem `
  --public-research-only

py -3 scripts/current/stamp_prospective_checkpoint.py verify `
  --chain-dir runtime/prospective-timestamp-chains/observation-20260928 `
  --ca-bundle C:/path/to/trusted-ca-bundle.pem
```

The sole current user workbook is the canonical file resolved from
`WORKBOOK_PATH` by `open_current_trial_workbook.py`. Its seven-page workbench
includes the decision process; a runtime preview is never a current user entry.
`build_product_workbench_candidate.py` is a retained historical five-page M7
preview builder, not the current user workbook. It does not change
`config/current-trial-workbook.json`. M4 synthetic onboarding
rehearsal is available as the engineering entry
`rehearse_m4_onboarding.py` and never counts as real private-portfolio
acceptance.

`build_simulated_product_user_trial.py` is an engineering-only learning preview.
It requires `--simulated-user-trial`, writes only under `runtime/`, and cannot
replace the canonical workbook or accept private portfolio data.

For a fully synthetic trial that does not read the pinned production M3/M7
artifacts, supply both `--synthetic-packet` and `--evidence-root`. Both must be
under the project's `runtime/`; the packet must declare `simulation_only: true`
and `action: no_order`. The existing application validates every referenced
evidence file and SHA-256 before rendering. A missing or changed input rejects
the preview. Use a new output filename because previews are immutable.

```powershell
py -3 scripts/current/build_simulated_product_user_trial.py `
  --simulated-user-trial `
  --synthetic-packet runtime/simulated-product-flow-20260930/packet.json `
  --evidence-root runtime/simulated-product-flow-20260930 `
  --output runtime/simulated-product-flow-20260930/cli-product-workbench.xlsx
```

## Read an existing research result without rerunning research

### Publish an already reviewed research-only preview

`publish_product_workbench_to_canonical.py` now accepts
`--reviewed-research-folder runtime/REVIEW_FOLDER` with
`--reviewed-research-proof-sha256 REVIEWED_SHA256` and exactly one of
`--verify-only` / `--publish`. This separate, explicit mode excludes all daily
quote/observation inputs. It never admits a current price or a trading decision.
The daily publication mode still requires its verified quote bundle.

The folder must contain the historical preview, pinned preservation proof,
matching WPS read-only/native-export proof and readability proof. Original
canonical hash, protected sheets and OOXML parts are checked again, not trusted
from the proof's PASS label. Old proofs fail after the canonical source changes.
Verify-only writes nothing. Publish backs up and uses the existing atomic
replacement; actual post-publication WPS and user acceptance remain separate.
This does not yet replace the preview-generation workflow or its research gates.

`run_company_research.py --existing-manifest` reads an existing valuation and
verifies the explicitly pinned manifest, result and original files. Supply the
manifest SHA-256 from the reviewed receipt; do not silently calculate a new pin
after changing the input. This mode cannot be combined with `--package` or
`--schedule-request`. Optional output must be a new path inside the project.

```powershell
py -3 -B scripts/current/run_company_research.py --symbol 600887 `
  --existing-manifest runtime/publication-receipts/600887-existing-valuation-originals-20260930.json `
  --existing-manifest-sha256 032dc2823dcd3e475221e45c8876be1af309b80bcbd8df705b40b33446ebe740
```

The example names a dated, local receipt, not a portable bundled data set. If
that exact receipt or its originals are unavailable or changed, the read fails
closed. Omitting `--output` prints JSON without creating another artifact.
The result is `EXISTING_RESEARCH_ONLY`, `NOT_READY`, `action=no_order`:
it neither publishes Excel nor admits current model validity, a quote,
historical PIT, research approval or portfolio guidance. Original-file
availability is the recorded observation time, not an inferred historical
publication time. Normal research mode retains its existing evidence-stop
rules; this read-only mode is not a way to reopen a stopped evidence search.

The existing-read output includes a shared `PriceBridgeResult` with
`PENDING_EXTERNAL_DATA`, null price/date/margins and a bound model identity.
`model_validity_result.status=UNKNOWN` records the missing admitted event scan;
the product-level `model_validity=NOT_ESTABLISHED` and `suggested_state=NOT_READY`
remain unchanged. The manifest observation is not a quote or event-check date.
This does not fetch a quote, approve research or write the canonical workbook.

The existing-read mode can additionally take `--arithmetic-input PATH` and
`--arithmetic-input-sha256 HASH`. Both are required together. This is explicitly
residual-income arithmetic, not a default model for other industries: the
versioned packet must bind the exact retained valuation, three explicit scenario
inputs, basis date and source hashes. A mismatch rejects output. Success is
`ARITHMETIC_MATCH`, with `original_run_input_descriptor_verified=false`, strict
PIT unproven and no current admission. Reconstructed review inputs must never be
described as the historical original input descriptor or strategy backtest.

If a reconstructed input explicitly binds `primary_numeric_review`, the reader
also checks the two equity-basis fact values, units, report dates and original
file hashes against the arithmetic inputs. The result includes reviewed source
URL/page/excerpt metadata with its actual current observation date. This is
`INPUT_VALUES_BOUND_TO_REVIEWED_FACTS`, not full FinancialFacts admission:
the command does not independently interpret PDF excerpt semantics, prove
historical availability or upgrade research/decision/portfolio gates.
