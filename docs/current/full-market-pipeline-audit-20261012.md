# Full-market to dual-strategy pipeline audit (2026-10-12)

Baseline: `b8fab1d0bd05af887070231c8c4c15a793089ec7` plus the scoped changes in this worktree. This is an engineering audit, not an investment admission.

| Module | Actual code and run | Product consumption | Gap / priority |
| --- | --- | --- | --- |
| Official universe | Live SSE/SZSE/BSE collection: 5,573 securities, including 5,572 A shares and 1 CDR; matched quotes 5,573/5,573. `runtime/m2-live-20261012-product-v1/` | M2 only | Provider trade dates not carried by bulk snapshot; `PARTIAL`, P0 data admission |
| M2 four channels | Live QUALITY 0, DIVIDEND 50, VALUE 50, CYCLICAL 50; 114 unique leads. 873 financial and 3,622 dividend evidence records; 121 unsupported financial profiles. Receipt and raw-input replay match. | Not consumed by current Canonical Excel | New discovery report is hash-bound and `LEAD` only; controlled renderer migration needed, P1 product |
| Candidate ResearchCase | Existing pending candidate preparer consumes a pre-existing issuer package and finite policy choice; it does not convert arbitrary M2 symbols into an official-source ResearchCase. | Only existing registered cases | New-company official filing/facts adapter absent, P0 pipeline |
| Formal valuation/admission | Registered 600519/600887 research, quote, event and decision gates run; no new M2 symbol admitted. | Existing Canonical workbook | Human economic/G3/event approval and independently dated prices remain separate gates, EXTERNAL_GATE |
| Hotspot | Real snapshot scan exists; same-day historical bars now require completed China session. | Current daily product | Multi-day continuity and 60/15-minute source coverage unproved, P2 research |
| Dual-sleeve risk | Synthetic cross-sleeve cap and cash-floor tests pass; no actual private IPS/holdings loaded. | Current daily product | Real position guidance requires user's private input, EXTERNAL_GATE |
| Excel | One Canonical workbook remains at `WORKBOOK_PATH`, existing source hashes preserved. Runtime M2 workbook is a non-current preview only. | Two registered companies plus existing hotspot/risk surface | New M2 leads are not yet visible in Canonical; do not claim integrated, P1 product |

The M2 provider's `fetched_at` is not a verified `provider_trade_at`. The run's nominal `quote_date` is therefore not an admitted price date; `data_health.status=PARTIAL` and the report labels every lead `UNVERIFIED_PROVIDER_TRADE_DATE`. No BUY/ADD or position sizing is derived from these leads. `action=no_order` throughout.

Current path: official lists + bulk quotes + retained financial/dividend points -> M2 receipt -> bound `value-discovery-report.json` -> **stop**. The independent registered-company and hotspot/risk paths continue to the Canonical publisher. The published source binding pins `render_dual_strategy_artifact_pages.mjs` and `daily_product_composition.py`; editing either in place fails the source-hash gate. A versioned, reviewed publication-contract migration is required before adding the discovery board.

Verification: the final complete offline regression passed with `4,886 passed, 42 skipped` using the required project `.tmp` test root. An obsolete D2 display assertion was updated to verify the actual audit-sheet evidence hyperlink, without changing the frozen renderer. The runtime M2 receipt and retained inputs replayed identically. Canonical Excel and production services were not modified in this work package.

Next engineering task: produce one official-source, evidence-bound *pending* ResearchCase for a real M2 company outside 600519/600887, without approving economics or a price. After that, migrate the frozen publication contract in a separate reviewed step to display the lead queue in the one Canonical workbook.
