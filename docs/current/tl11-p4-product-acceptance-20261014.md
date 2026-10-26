# TL11-P4 bounded product delivery - 2026-10-14

Baseline: `3464314e35974b7db80cdf0fd2e8823490b096f5` on `codex/web-d1-investment-workbench`.

`ENGINEERING_DELIVERY=VALIDATED_BOUNDED_DAILY_AND_ISOLATED_PORTFOLIO_LOOP`

`CURRENT_RESEARCH_ADMISSION=0_FORMAL_CANDIDATES`

`FINAL_OPERATIONAL_ACCEPTANCE=NOT_PASSED`

`action=no_order`. This receipt does not complete the long-term Goal. Gate 4's fully admitted valuation-to-action-price chain remains incomplete; its typed contract and truthful absent-policy projection are implemented, not substituted for real research approval.

## Actual daily output

The dated Sina classification/Tencent quote capture covers 5,225 supported classified securities, 5,214 dated quotes and 5,019 valid ranked securities; 11 quotes are missing. This is not a certified complete exchange universe. Rule `hotspot-dated-sector-liquidity-ranking-v1` deterministically orders valid dated observations by industry equal-weight relative change, turnover and symbol. ST/delisting labels, incomplete data and unsupported classifications are excluded. Persistence, fund flows, catalyst and market admission remain UNKNOWN. Neither coverage strength nor a positive industry ranking certifies a bull market.

| Symbol | Company | 2026-10-14 close | 60m observation trigger | Structure invalidation | State |
| --- | --- | ---: | ---: | ---: | --- |
| 300364 | 中文在线 | 26.580 | 27.880 | 24.700 | WATCH |
| 300413 | 芒果超媒 | 25.640 | 27.120 | 22.500 | WATCH |
| 300418 | 昆仑万维 | 42.100 | 43.420 | 40.310 | WATCH |
| 300058 | 蓝色光标 | 12.850 | 13.320 | 12.660 | WATCH |
| 002354 | 天娱数科 | 7.650 | 8.030 | 7.390 | WATCH |

All five are next-session observations, not BUY recommendations. Rule `hotspot-prior-five-completed-bars-v1` requires a completed 60m close above the preceding five highs and volume at least 1.2 times their mean. Invalidation is a completed close below the preceding five lows, requiring exit review, not an automatic stop order. 15m and aggregated daily structures are separate evidence; minute structure remains single-source. Conditions expire at the next session, 2026-10-15, and must be refreshed. Previous rejected candidates are retained and collapsed.

Sina supplies classification and completed minute bars; Tencent supplies dated universe quotes; Tencent/Sina independently verify the relevant daily closes against the registered exchange calendar. Original files are retained. The first capture's report-level `available_at` precedes completion of the quote batches; row and source timestamps remain authoritative. Future captures use the maximum source availability; the original report was not rewritten.

600887 has a genuine residual-equity research scenario: bear 9.7976411844, base 10.0751373531, bull 10.3006925010, research through 2026-10-11, verified 2026-10-14 close 28.13. These scenarios are not action prices. Applicable registered investment price policy is absent; entry/add/reduce/exit prices remain null. G3, current research/event and model eligibility remain incomplete. 000333 and 601088 receive no invented valuation. `ValueActionPlan` accepts verified registered policy inputs; no implicit discount or fixed-PE replacement is introduced.

Research intent, security qualification and personal qualification are separate. Public output never supplies private sizing. OPEN/ADD/REDUCE/EXIT policy entrances are tested; the real current observations are WATCH. Frozen value plans are revalidated at read time. Changed current registry, altered originals or rejected current prices remove current conditions and chart levels while immutable history remains intact.

## Portfolio and actual verification

The existing authenticated private journal supports cash-only initialization, partial IPS drafts, prepare/confirm, revision conflicts and idempotent fill confirmation. Confirmed IPS maps to the same shared/sleeve budgets and reserve. Drafts cannot activate personal guidance. Actual price, quantities and fees must be entered; strategy reference prices do not fill the actual price field.

Final HTTP E2E used actual public evidence and a distinctly synthetic isolated account. Cash 10,000 became 7,337 after a 100-share fill at 26.58 plus 5 fees; verified market value 2,658, total equity 9,995 and floating PnL -5. Draft creation did not change holdings. Confirmation retry was idempotent; reconciliation and original judgment-version association passed. The real private root was never resolved or written.

Missing verified economic security attributes remain `security_attributes.missing`; a supplied arbitrary path/hash does not certify industry/factor research. The UI displays verified cash, costs, market values and equity independently of incomplete risk qualification. Drawdown is unknown without a verified equity history; full personal guidance is unavailable until all required inputs pass.

Windows local Web was actually inspected on desktop 1280x900 and mobile 410x840: daily candidates, real hotspot detail and three chart periods, value scenario, locked real portfolio, isolated confirmed IPS/positions/fills and history. Temporary viewport and QA server were cleaned up. The user daily tab remains open. Screenshots and the sanitized receipt are in `artifacts/current/tl11-p4-20261014/`; portfolio/history screenshots are explicitly synthetic, not a user account or user signoff.

Validation: Core workflow selection 2,424 passed / 33 skipped; Web API 142 passed; frontend 105 tests passed; typecheck, Prettier and production build passed. Independent review found and fixed stale chart levels and registry/packet membership disagreement. Actual UI caught and fixed a suppressed total-equity display.

## Bound evidence

- Current packet: `pub-5c7d42d7243fc011cb0a`, engine/identity v8.
- Packet SHA256: `b427203761c97b6e118c0e924255e6fcd47a0984f7658db2a184f86d5e45b488`.
- Selection SHA256: `989aa97241824b61cd3bf3283b4705e846a4d9de78ad4651c5d12bcb00235b8b`.
- Final isolated HTTP receipt SHA256: `df809f99c01415f74b74630dbcde916490f314656bb4a2cbdf393595cff1d0a6`.
- Valuation input SHA256: `876bfdf7829c1e8225e3338bd090dd102965ebce8049edc2628bae90c0264b68`.

The transitive inherited evidence audit found four references to one changed historical 600887 `cninfo-index.json`, 102 absolute-path references, seven unbound files and one directory reference. The changed index is a historical audit branch, not a direct current valuation input; it does not grant formal qualification. Frozen historical bytes/hashes were not rewritten. The current packet and direct dated selection/case evidence verify, but this is not proof that the entire inherited repository is independently portable or every historical evidence chain is intact. Bounded byte-identical public copies are archived under `artifacts/current/tl11-p4-20261014/public-evidence/`, with original-to-archive paths and SHA256 in `manifest.json`. Local runtime originals remain untouched and untracked. An auditor can restore those original relative paths from the manifest after checking every hash; this bundle is not a full inherited deployment backup. No private journals or 371 MB inherited asset migration are included.

Initial remote Core failed because the new authenticated-route tests lacked the Web dependency extra and runtime evidence was tracked contrary to the repository boundary. CI now installs `[dev,web]`; public evidence copies use the approved artifact location. The failing tests were retained unchanged.

## Daily use and remaining gates

Run the existing unique entry:

```powershell
& 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File 'D:\GPTProject\value-investment\scripts\current\run_daily_workbench.ps1' -Mode SAFE_REFRESH -Open
```

Read Today, open detailed conditions and evidence, then inspect Portfolio with locally authenticated access. Enter real IPS and holdings yourself; record actual fills only after deciding and trading yourself. History preserves the original research version. The canonical WPS Excel, server and PTA are unchanged.

Remaining: legitimate investment-price policy and G3/model/event approval; current evidence and formal hotspot validation (independent minute evidence, PIT/OOS/cost/shadow); real user-confirmed IPS/portfolio and verified security attributes; inherited historical integrity/portability; user final acceptance. No approvals, future trading sessions or actual user usage are fabricated.
