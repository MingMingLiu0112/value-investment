# Current CLI Wrappers

The authoritative product/engineering split is
`config/current-cli-entrypoints-v2.json`. The v1 registry remains in place for
compatibility and every v1 path is preserved in one of the v2 layers.

Generic product commands in this directory accept `--symbol` as an argument and
delegate orchestration to `value_investment_agent.application.product`. This
directory holds thin CLI wrappers only.

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

The current product candidate builder is
`build_product_workbench_candidate.py`; it renders the five-page M7 UX candidate
without changing `config/current-trial-workbook.json`. M4 synthetic onboarding
rehearsal is available as the engineering entry
`rehearse_m4_onboarding.py` and never counts as real private-portfolio
acceptance.

`build_simulated_product_user_trial.py` is an engineering-only learning preview.
It requires `--simulated-user-trial`, writes only under `runtime/`, and cannot
replace the canonical workbook or accept private portfolio data.
