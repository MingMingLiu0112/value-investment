# Current CLI Wrappers

The authoritative product/engineering split is
`config/current-cli-entrypoints-v2.json`. The v1 registry remains in place for
compatibility and every v1 path is preserved in one of the v2 layers.

Generic product commands in this directory accept `--symbol` as an argument and
delegate orchestration to `value_investment_agent.application.product`. This
directory holds thin CLI wrappers only.

The current product candidate builder is
`build_product_workbench_candidate.py`; it renders the five-page M7 UX candidate
without changing `config/current-trial-workbook.json`. M4 synthetic onboarding
rehearsal is available as the engineering entry
`rehearse_m4_onboarding.py` and never counts as real private-portfolio
acceptance.
