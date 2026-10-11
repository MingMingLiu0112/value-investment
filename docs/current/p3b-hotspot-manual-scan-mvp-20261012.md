# P3-B manual hotspot research MVP

Implemented independently under domain/hotspot, application/hotspot and infrastructure/hotspot. Shared renderer/read-model/registry/CI are unchanged; Root integrates the bound JSON as product_extensions role hotspot_report. No commit, paid provider, production service, broker order or new valuation engine.

## Runnable contract

CLI: scripts/current/scan_market_hotspots.py. Use explicit PowerShell 7, UTF-8, PYTHONPATH=src. All temporary files stay under repo/.tmp; tests also set process-local TMP/TEMP there to satisfy the existing isolated trust-registry fixture.

Default: `python -B scripts/current/scan_market_hotspots.py --output-dir runtime/<fresh-dir>`.

Replay: add `--offline-bundle runtime/p3b-hotspot-manual-20261011-v1/dated-input/offline-bundle.json --offline-bundle-sha256 <actual SHA-256>`. A missing/wrong bundle hash rejects; a reused output directory rejects. Optional --cutoff is timezone-aware and offline-only; network collection does not accept an injected clock. Application entry: run_manual_scan(root=Path, output=Path, offline_bundle=None, offline_sha256=None, cutoff=None).

Stdout is `{report_path: <repo-relative report.json>, sha256: <exact file hash>, action: no_order}`. Report schema hotspot-observation-report-v1 includes observation_list, themes, sources with path/hash/URL/available_at, dated_quote_observations, price_behavior.periods, deterministic_explanation, gates, collection, semantic_content and semantic_content_sha256. Semantic content excludes generated_at/observed_at, collector fetched_at, config hash and per-run paths; preserves actual prices, quote dates/times, sector/issuer content and content hashes. Actual replay comparison passed.

Root may put the output at extensions/hotspot/report.json beneath its fresh runtime run. It should catch source-integrity/config errors as an explicit UNKNOWN/error supplement, rather than aborting company research publication. Network request failures alone use the explicit, hash-reverified old cache fallback; report.collection contains each failure and cache availability. Missing or hash-corrupt fallback is not silently accepted. Existing signal contracts are not weakened to accommodate absent assets.

## Actual public data

Default network scan successfully reused existing M2 Tencent board/Sina industry public collectors: 5,573 rows each, 31 industry groups. Acquisition: Tencent 2026-10-12 00:00:49 China time; Sina 00:01:11. These are acquisition timestamps, not trading dates. Sector results (for example retained snapshot equal-weight changes for media 5.527%, communications 3.404%) are descriptive coverage means, not an official industry index, current-day theme admission or money-flow fact. Classification effective date, catalyst, persistence and survivorship remain UNKNOWN.

The first report honestly had confirmed_market_date=null. It and its Mock explanation remain frozen historical engineering evidence. The successor removes MockLLMProvider from real reports and uses deterministic counter-evidence text; no paid Agent call, inferred catalyst or language-model signal is produced.

Without redownloading the same market snapshots, collected a bounded 13-security dated quote bundle using existing collect_session_bundle and parse_quote. Tencent and Sina agree within the inherited 0.01 tolerance for all 13 names and explicitly report 2026-10-09. This includes 000651 38.83. The successor's confirmed_market_date=2026-10-09 has explicit scope DATED_QUOTE_SUBSET_ONLY_NOT_INDUSTRY_SNAPSHOT. It does not assign this date to the 31 industry aggregates or their raw changepercent/turnover. Provider date agreement is observation evidence, not a latest-session PriceBridge or trade admission; calendars in the raw bundle do not automatically pass a gate.

Historical 000651 unadjusted daily behavior reuses the retained crosscheck manifest and existing Tencent bar parser: 640 supplied bars, 2024-01-31 to 2026-09-22, final close 38.18. Descriptive final five-bar change -0.3133%, prior five-bar support 37.83/resistance 38.79, no close breakout, volume ratio 1.0514. The 640-row supplied window is bounded history, not a complete historical database. Corporate actions and volume units are unverified; volume confirmation remains UNKNOWN. This historical price behavior is separately dated from 10/9 quotes. Daily observations are not synthesized into 60m/15m; both absent periods remain UNKNOWN.

## Gates and tests

All value/risk, issuer/financial/liquidity/event, PIT, walk-forward/OOS, cost-validation, Shadow and production gates remain NOT_PROVEN/passed=false. entry_review_eligible=false, action=no_order. HOT_WATCH/NO_SIGNAL only label descriptive snapshot observations; no ENTRY_REVIEW_CANDIDATE, live swing plan or investment approval. No private portfolio, ST/limit/suspension fact is invented.

43 focused tests passed: dedicated hotspot tests plus unchanged D5 synthetic contracts and bounded virtual execution tests. Dedicated tests exercise exact source hash, future availability, containment, bundle hash, config admission override denial, network failure fallback, semantic equality across run times, same-directory refusal, real timestamp parser date conflict and no Mock in real reports. Reused VirtualAccount replay tests enforce next-session/T+1, limit-up/down rejection, suspension/unknown rejection, 10bps adverse slippage, explicit synthetic costs and idempotence. A synthetic 100-share 100.00 opening fills at 100.10 with 5.10 fee; same-day sellable shares=0, following-day=100. These are mechanics tests, not real trades, observed costs, profitable strategy, OOS or Shadow validation. No new trading parameters have been approved.

## Fixed artifacts

- Current successor JSON: runtime/p3b-hotspot-manual-20261011-v1/dated-successor/report.json; SHA b0a297998490f61b21c0fcff38f7a4b58466f464983008dd3805d1178eb4f847.
- Original network JSON (preserved): network/report.json; SHA f4e068773f3916f87b389ec8ddafe7269babbb1c09d9dd223d335af58a5eb45d.
- Exact successor offline replay: dated-replay/report.json; SHA 72cb424f15b6507e09ca18a482f792e53e3e518370c35bdd80e5f1a1cfecef84.
- Public market snapshot bytes: Tencent SHA f59fe2116350be27d63116dc30b54d8e18a10c852fd3172b00d6a62437a0525a; Sina SHA 5462a7bcaa3b8c714eddb96d008312b1487c296dcc519c0220ec6ee85f806337.
- Test receipt: focused-dated-tests.xml. Final source/code inventory: handoff-verification-v2.json, with exact file hashes and semantic comparison.

Usable now: manual source-bound market observations, explicitly dated quote subset, one real historical price-behavior example, readable reports and deterministic counter-evidence, lawful replay and denied entry. Not proven: a trading-date-bound whole-market hotspot ranking, intraday setup, official catalyst, future profitability, OOS, Shadow or real trade eligibility.
