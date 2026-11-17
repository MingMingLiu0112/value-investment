# P8 C4/D4 Held Continuity

Backend entry: `application.portfolio.held_continuity.review_held_continuity`.
Invoke only from an existing authorized PRIVATE route after daily update or on
private read. Inputs: journal, repository_root, timezone-aware generated_at,
selected_symbols (descriptive only), plan_provider(symbol).

The provider must resolve existing verified value/hotspot engine plans for every
held symbol. For hotspots, `load_held_price_plan(root, symbol, binding, now=...)`
uses the existing case loader and projector directly, bypassing ranking and its
ten-retired-item limit. Keep bindings in the existing private decision/history
context; do not append actual held symbols to public registries. Refresh through
the existing current-case collector when needed. Missing/stale evidence returns
a retained held row with explicit gaps, never a fabricated price or exit signal.

The service reuses confirmed journal replay, existing per-lot T+1 projections,
and review_private_risk_rehearsal (the existing dual-sleeve risk engine). All
engine blockers and facts remain present. Journal revision mismatch requests a
retry rather than mixing account versions. It never writes the journal. Held
rows retain both sleeves and sellable quantities, prioritize exit/invalidation,
flag downtrend, and preserve unknown entry-thesis/announcement reviews. These
unknowns are review requirements, not assertions that no adverse event exists.
Formal eligibility and sell permission remain false; position guidance is null.

Root integration is still required: replace ranking-driven private holding
iteration with this entry and supply the existing verified value-plan resolver
and held hotspot case bindings. Shared daily_public_packet.py, private risk
modules, routes and public payloads were not edited. This bounded backend
delivery does not claim daily/Web integration or product acceptance complete.

Evidence: replay-audit.json distinguishes two verified real public selection
snapshots/five deterministic archived price plans from TEST_ONLY ledger tests.
No actual private account was opened, mutated or exported. No source collection,
approval, trade, production operation or strategy-performance claim occurred.

Validation command (PowerShell 7; TEMP and TMP set to repository .tmp):
`python -m pytest tests/test_held_continuity.py tests/test_private_risk_partial_facts.py tests/test_hotspot_continuity.py tests/test_hotspot_current_refresh.py tests/test_hotspot_price_action_case.py -q --basetemp=.tmp/p8-held-continuity-final`

Result: 34 passed in 3.44s. Includes isolated confirmed-fill T+1 release,
read-only journal bytes, both sleeves, 21 held securities beyond registry caps,
multiple ranking exits, per-symbol unavailable/corrupt/future/foreign/stale
plans, closed-position retirement and future-account sellability suppression.
`git diff --check` passed (unrelated existing files emitted CRLF notices).
