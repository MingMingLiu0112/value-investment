# TL11-P6.2 business workflow acceptance

Date: 2026-10-15. Baseline: a1bc035e5fea4787703e0c62edabf208fab01329.
Branch: codex/web-d1-investment-workbench. Permanent action=no_order.

## Verified changes

- Authenticated private policy confirmation refreshes the personal decision view immediately and after reload. Public research remains separate. TEST_ONLY 600887 base x 93% produced 9.3699 CNY, explicitly a registered draft arithmetic price without G3 permission. This is not a recommended policy or production approval.
- The external review handoff returns version-bound questions, supporting/counter evidence, unsigned responses and existing signing/import/verification commands. No pinned authorized signer exists (count 0). Download works; real signing was not performed. The policy, G3 and event decisions remain distinct.
- Public candidates have conditional OPEN/ADD/REDUCE/EXIT rules. Daily decline or insufficient upper space moves them to waiting for structure improvement; a local trigger never becomes BUY.
- The existing risk engine accepts explicit hypothetical execution/economic/holding-risk choices in SIMULATED only. UI produced 200 hypothetical shares for 300059; actual quantity remained unavailable. No assumptions are written as actual facts or account approval.
- Per-security quote failure no longer erases other verified account facts. Future account facts retain ledger cash/cost/positions but cannot assert complete current equity.
- TEST_ONLY Windows browser flow: confirmed IPS; external synthetic reconciliation; BUY 100 x 18 + 5 fee (Oct14); SELL 100 x 20 - 5 fee (Oct15). Cash 100000 -> 98195 -> 100190; shares 0 -> 100 -> 0; realized profit 190. History immediately retained both records and their captured research version. No broker connection or real private ledger mutation.
- Isolated positive integration additionally exercises qualified synthetic value research -> OPEN -> confirmed IPS -> existing risk engine -> manual fills -> cold replay -> immutable review history. It does not establish a profitable strategy.
- Retired candidate errors are separate warnings, not current candidate blockers. Price-policy review uses an immutable archived quote-pointer binding, preserving old artifacts and requiring reconfirmation when review bindings change.
- Unbound research is now explicitly reported alongside price gaps. Missing models are not described as merely missing quotes; no valuation was invented.
- Launcher opens /daily#unlock= rather than losing the secret fragment in the root redirect.

## Real data conclusions

Latest observed market session: Oct15. Research remains older and not formally admitted.

| Security | Close | Conditional observation | Structural invalidation | Current restriction |
|---|---:|---:|---:|---|
| 300059 | 18.320 | 18.480 | 17.680 | Insufficient upper space; no entry permission |
| 601318 | 51.780 | 51.600 | 50.850 | Local trigger observed, daily downtrend |
| 600030 | 26.230 | 26.210 | 25.510 | Local trigger observed, daily downtrend |
| 601211 | 16.950 | 17.000 | 16.700 | Daily downtrend, trigger not observed |
| 000712 | 10.610 | 11.020 | 9.740 | Daily downtrend, trigger not observed |

These are existing model observations, not limit orders or guaranteed exit prices. Breakout requires a completed 60m close strictly above the observation price and volume >=1.2 times the preceding five-bar average, plus all independent gates. Stop references do not guarantee execution. ADD/REDUCE/EXIT are holding-dependent reviews, not new personal sell instructions.

600887 has retained conditional scenarios 9.7976/10.0751/10.3007 and Oct15 close 28.10, but normalization, model validity, current event coverage and G3 remain unresolved. These scenarios do not establish an admitted present-price comparison or buy range. 000333/000651/600741 have no admitted valuation in the inspected authoritative current bindings; their formal prices remain null. See real-company-audit.json for the pre-refresh audit and real-public-api-after.json for the later observation; the former is intentionally not rewritten as final evidence.

## Evidence and verification

Evidence directory: artifacts/current/tl11-p62-20261015/.
Screenshots: real-daily-desktop.png, real-hotspot-300059.png, external-review-handoff.png; TEST_ONLY-policy-confirmed.png, TEST_ONLY-scenario-200-shares.png, TEST_ONLY-after-buy.png, TEST_ONLY-after-sell.png, TEST_ONLY-trade-history.png.

Public market manifest is a host inventory, not a portable backup. Raw runtime market files follow the existing no-daily-Git-upload policy. Private journals, unlock tokens and actual account data are not included.

Desktop interaction passed. **Mobile acceptance NOT PASSED:** the documented viewport override was requested at 390x844; actual DOM measured 1280x720 on both the existing and a new tab. viewport-override-ineffective.png is a desktop rendering proving the limitation, not a mobile screenshot. Overrides were reset. Do not replace this missing acceptance with CSS inspection or a cropped desktop screenshot.

Local verification: Core 2743 passed/35 skipped; final packet/startup/future-fact regressions 27 passed/2 skipped; API 157 passed; Web 168 passed and typecheck/format/build passed. Final Core/Web CI results are reported separately after push. Local skipped cases are not represented as passed operational acceptance.

Final public packet: pub-61aceb64acecbe0c4c91; engine v12; packet SHA-256 d1fd8439120e3e59c12e010924890fe4c2803263facf8d6bc75c85c805035f66. Research, policy, account and trading permissions were not upgraded by publication.

## Exact remaining acceptance

1. Run actual responsive desktop/mobile interactions with a functioning viewport controller or a real mobile device. No claim of P6.2 engineering completion until this passes.
2. A real authorized reviewer must independently enroll their scoped public trust root, sign G3/event responses, import them through the supplied handoff commands and verify the resulting qualification. Local login and a personal price policy cannot replace this authority.
3. Actual user must connect and confirm their own IPS/holdings/reconciliation and policy. Test-only cash, policies and fills must never be copied into that account.
4. Current research, financial/model/event evidence and rule validation remain investment-eligibility gates; do not fabricate approvals or interpret conditional arithmetic as an investment edge.

Status: ENGINEERING_WORKFLOW=PARTIAL_MOBILE_ACCEPTANCE_PENDING; VALUE_DECISION_CLOSURE=CONDITIONAL_WORKFLOW_VERIFIED_FORMAL_NOT_READY; HOTSPOT_DECISION_CLOSURE=CONDITIONS_VISIBLE_NO_ELIGIBLE_ENTRY; PRIVATE_RISK_CLOSURE=SCENARIO_AND_LEDGER_VERIFIED_FORMAL_BLOCKED; HUMAN_APPROVAL_WORKFLOW=EXTERNAL_HANDOFF_VERIFIED_SIGNATURE_NOT_EXECUTED; FORMAL_INVESTMENT_ELIGIBILITY=NOT_REACHED; USER_ACCEPTANCE=NOT_PASSED.

No total goal, milestone product acceptance or initial assisted-use completion is asserted.
