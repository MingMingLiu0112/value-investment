# Strict verification flag deployment

Production previously treated nonempty strings such as `"false"` as approved
cross-source verification flags. The reviewed production/local diff contained
only three changes: require `is True` in quality.automatically_verified,
financial_quality._accepted, and derived_financials._accepted. Quarantine and
all surrounding eligibility checks remain unchanged.

The backtest-readiness inventory script was corrected locally as well. Eight
regression cases reject false, null, strings, integers and empty containers.
This inventory never approves historical backtest readiness.

## Verification and deployment

- Local focused suite: 75 passed.
- Deployment guarded by the market-screen lock, idle filing service check,
  no active application container, and exact baseline/staged SHA-256 checks.
- Backup: `/opt/value-investment-agent/deploy-backups/strict-verification-9d3p2gv9`.
- Actual production modules loaded in a network-disabled 128 MiB container:
  30 assertions passed, including legitimate True and quarantined True cases.
- No business data modified, no service restarted, no image rebuilt.

Deployed SHA-256 values:

| Module | SHA-256 |
| --- | --- |
| quality.py | ed02087289e69891b77233bc833294215de72b0ef902c75dc31c9cfd86e94ef3 |
| financial_quality.py | 6b01ea1b85a61ef1b9259e51f5a56bd4d19731c0b4b968caf645b6f6ebe3c02c |
| derived_financials.py | 022e313019ca1e54943e5dce47eb71d70818ec8342229576bd18be0a730625fb |

This verifies boolean handling, not the truth of financial facts, independent
source provenance, valuation quality, or historical investment performance.
No new workbook publication was performed in this deployment.
