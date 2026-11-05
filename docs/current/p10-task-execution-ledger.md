# TL11-P10 execution ledger

Baseline: `0b120753ef98309ed11968d409f85f164d908e27` on
`codex/web-d1-investment-workbench`, 2026-10-16. P9 readonly preflight: 38 checks,
PASS_ENGINEERING_PRECHECK. The existing working tree contains unrelated edits;
they are not part of this ledger. All product outputs remain `action=no_order`.

| Task | Status | Implementation and files | Verification | Remaining condition |
| --- | --- | --- | --- | --- |
| P10-00 baseline | ENGINEERING_PASS | This ledger; P9 baseline and actual HEAD checked | `audit_p9_readonly.ps1`: 38 checks pass | Recheck after integration |
| P10-01 B1 quote window | IN_PROGRESS | Shared acquisition verdict in `quote_sessions.py`, collector report, conversion gate, daily CLI; `test_quote_b1_acquisition.py` | 30 focused quote/bridge tests pass; preclose, mixed-day and next-day inputs reject | Actual same-session post-close acquisition not yet observed; no production schedule authorized |
| P10-02 600887/600519 economics | ENGINEERING_PASS | Reused P8 immutable original/replay audit; no new model or input was asserted | `audit_p8_retained_research.py --check-only`: 64 Yili original rows, 31 calculations, two incremental announcements, 600519 six direct rows; existing `judgments.json` explicitly finds Yili current reliable fair value not established | Normalized profit, cash/financing perimeter, advantage duration and issuer equity cost still lack decisive approval; no formal fair value |
| P10-03 value policy/review | NOT_PROVEN | Existing price policy and signed review services retained; no synthetic signature imported into current publication | 69 focused signed-review, materiality, replay and policy tests pass | Current Yili/Moutai economic and B1 gates remain unsatisfied; real G3/materiality requires authorized human |
| P10-04 hotspot quality | ENGINEERING_PASS | Added domain quality tier, v1 replay-compatible activity v2 metadata, price-plan projection and Web fail-closed consumption | 19 focused tests pass; 601318, 300059, 600030 stay non-entry; `action=no_order` | Current frozen packet predates new quality field; new same-day packet and PIT/OOS edge validation not yet proven |
| P10-05 private onboarding | ENGINEERING_PASS | Existing PrivateJournal/Web setup retained; new isolated account continuity tests | TEST_ONLY init, IPS, cash, T+1, partial sale, restart and dual-sleeve same-symbol tests pass | Actual account and IPS remain BLOCKED_PRIVATE_INPUT; no real-account acceptance |
| P10-06 held continuity | ENGINEERING_PASS | New temporary-ledger tests cover non-Top5 sixth holding and same symbol in two sleeves | Position survives next-day partial sale and restart; unqualified price yields no guidance | Real held-position tracking remains BLOCKED_PRIVATE_INPUT; no natural multi-day user drill |
| P10-07 Web daily workflow | IN_PROGRESS | Backend tier wired to existing A-E cards; old publication retains fallback | 30 actual Chrome pages/interactions at 1280/1440/390/430; no horizontal overflow, public API 200, daily-to-Yili navigation works | Current server still shows frozen 10-15 publication; real user onboarding and latest tier publication not accepted |
| P10-08 PIT/OOS and shadow | NOT_STARTED | Existing replays are engineering evidence only | No strategy edge proven | Historical availability, costs and natural-time observations |
| P10-09 unified acceptance | IN_PROGRESS | `accept_p10_assisted_use.ps1` default read-only, guarded `.tmp/p10` output; optional tests/build | P9 38 source checks; P10 `-RunTests`: 234 targeted tests and Web build pass; out-of-scope output path rejected; full Web 198 pass | Full Core rerun and CI pending; default receipt deliberately says NOT_PROVEN |
| P10-10 three E2E paths | IN_PROGRESS | 600887/600519 original replay; 601318/300059 negative structures; TEST_ONLY cross-day private ledger | Individual links verified, browser 30 pages/interactions | No full same-day B1, approved value plan or real private acceptance; cannot call full E2E PASS |

Status vocabulary: NOT_STARTED, IN_PROGRESS, ENGINEERING_PASS, BLOCKED_DATA,
BLOCKED_HUMAN, BLOCKED_PRIVATE_INPUT, NOT_PROVEN, FAILED. A component may be
engineering-valid while real-data or personal acceptance remains unproven.
