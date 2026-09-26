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

The current product candidate builder is
`build_product_workbench_candidate.py`; it renders the five-page M7 UX candidate
without changing `config/current-trial-workbook.json`. M4 synthetic onboarding
rehearsal is available as the engineering entry
`rehearse_m4_onboarding.py` and never counts as real private-portfolio
acceptance.

`build_simulated_product_user_trial.py` is an engineering-only learning preview.
It requires `--simulated-user-trial`, writes only under `runtime/`, and cannot
replace the canonical workbook or accept private portfolio data.
