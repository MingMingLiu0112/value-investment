# Private aggregate release

No actual connection is configured. Default update remains NOT_CONNECTED.

Private input, full risk report, and local config must remain outside Git and sync
directories. Existing private-path validation and IPS/portfolio validation apply.
Do not copy a private report into runtime or supply it as an extension.

The local config is user-maintained JSON with exactly these fields:
schema_version (dual-sleeve-local-release-v1), action (no_order), private_root,
input_path, input_sha256, approved_summary_sha256 (initially null).
Paths are absolute. Input is the existing dual-sleeve-risk-input-v1 JSON.
No real policy defaults, identities, signatures, or input files are created.

Preview with review_dual_sleeve_risk.py --summary-preview --private-risk-config
PATH --private-risk-config-sha256 SHA. Preview writes nothing and displays only
the allowlisted aggregate and its canonical SHA. After inspecting every field,
the user may copy that SHA into approved_summary_sha256 in the private config.
This is local disclosure consent, not investment approval or a signed G3 review.

Normal run_update_and_publish.py accepts the same two private config parameters.
Recalculate the config file SHA after changing consent. Update revalidates the
pinned private input; a missing or changed summary approval fails before exporting.
Only the authorized summary is written to fresh runtime output for the existing
dual_sleeve_report role. Private paths, raw source hashes, holdings, securities,
policy details, sizing, returns, and free-text blockers never enter that summary.
Authorized fields are total assets/cash/reserve and each sleeve's budget, equity,
used/available funds, cash, risk budget, committed/available risk. Unknown stays null.
REVIEW_REQUIRED remains visible, with a generic private-review blocker.

Reuse is explicit through the local config path and hash; no automatic search or
implicit loading. Updated input requires a new exact input pin, preview, and user
consent. No personal input or consent was supplied during implementation.

Tests use isolated synthetic IO stubs for the release seam and separately check
the real private input pin gate. They do not constitute real user authorization.

## Change inventory and freeze

Production files owned by this change: application/product/dual_sleeve_public_summary.py,
scripts/current/review_dual_sleeve_risk.py, scripts/current/run_update_and_publish.py.
The two scripts were already registered product CLIs; inventory metadata is refreshed,
with no new CLI category or count. The application module is not a script entrypoint.
Test registration: tests/test_dual_sleeve_public_summary.py in offline-core.
Other agents' additions registered in the same CI pass: test_hotspot_report_readability.py,
test_dual_strategy_authored_company_contract.py, test_pending_candidate_midnight_pit.py.
Their production module application/hotspot/report_text.py is not a script entrypoint.
Production sources frozen after the focused 54-pass release/risk/P0/composer run.
