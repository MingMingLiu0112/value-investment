# P6.1 actual acceptance evidence

`action=no_order`. Public observations are dated 2026-10-14; captured on
2026-10-15 morning. All account screenshots and amounts marked TEST_ONLY use
an isolated synthetic journal, not a user account or real trade.

- `daily-public-packet.json`: byte-identical retained public packet.
- `daily-public-packet.receipt.json`: unchanged original publication receipt;
  its runtime packet path describes the original location, not this archive.
- `final-run-receipt.json`: actual final Windows SAFE_REFRESH launch.
- `isolated-browser-verification.json`: browser-driven account replay,
  duplicate confirmation and API boundary checks; private journals are excluded.
- `daily-*`, `hotspot-chart-*`: real browser viewport screenshots.
- `portfolio-*`, `history-*`, `policy-*`: synthetic account browser screenshots.
- `core-final.log`, `api-final.log`, `web-final.log`, `web-checks-final.log`:
  actual local final verification, with warnings/skips retained.
- `network-failure-e2e-final.json`, `live-probe-collection-report.json`,
  `live-probe-run-receipt.json`, `recovery-run-receipt.json`: failed live
  intraday attempt, bounded failure and recovery evidence.

Raw third-party probe responses, logs containing local authorization links,
cloud-account absolute paths, and private journals remain outside this commit.
The public packet and original receipt retain their hashes. Current pointer
relocation changes only the lookup paths, not original receipt bytes or dates.

Final-head GitHub Core/Web workflow URLs are reported in the task's final
delivery once the actual runs have completed. This evidence does not sign G3,
production permission or final user acceptance, or complete the long-term Goal.
