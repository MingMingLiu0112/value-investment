# Remove duplicate cash display observations at collection

The detailed-statement adapter emitted exact CNY cash with scope metadata and
then emitted the same current-report cash again as CNY 100M with less metadata.
The second pending record could shadow the original-PDF verified observation.

Local parser version is now akshare-financial-v5-sina-statements-single-cash.
Only omit the display duplicate when a non-bank exact record already matches
symbol, period, numeric cash amount, CNY unit and the complete raw payload.
Bank-specific cash semantics are unchanged. If no exact record exists, the
previous fallback is retained. Annual and current-period records stay separate.

Full suite before adding the last dedicated period fixture: 1066 passed with
18 existing Backtrader warnings. Added period fixture passed independently;
it proves the current half-year and prior annual cash rows both survive, in
CNY with consolidated scope, without a third display-only observation.
The initial fixture had an empty cash-flow table and correctly returned no
records under the adapter's existing contract; corrected the fixture rather
than changing that unrelated behavior.

Not deployed. Before rollout, compare the actual production adapter and stage
only this change. Existing pending deduplication already reuses identical
source/value/unit/metadata observations; a genuinely changed source snapshot
must still trigger revalidation. This collection change reduces duplicates,
not a blanket guarantee of permanent verified status. No database or workbook
was modified in this change.

## Production installation confirmed

Follow-up 2026-09-09: retrieved live adapters.py and inspected its diff against
local. Only the cash duplicate guard and parser version differed. Installed
with scripts/install_single_cash_adapter.py under the shared project lock.
Old SHA-256: 9555cfc316d8128680cae3bf9becbce6532f7289a9eadd7697ef6f11b94bc956.
New SHA-256: d66b69693ed1091b6b8a9a6f5cc2e59e6138d202da33a73fcdbb2bff99f28503.

Actual installed module passed the two-period synthetic cash fixture in a
network-disabled container limited to 0.5 CPU, 384 MiB memory and 512 MiB
memory-plus-swap. It confirmed two exact CNY scoped rows and no display-only
duplicate. No network collection or database write occurred. Original and
receipt remain in deploy-staging/cash-units-20260909/adapter-original and
adapter-receipt.json. No service restart was performed.

This supersedes the earlier not-deployed status. It does not demonstrate a
fresh real-provider collection after deployment, nor publish the nine repaired
cash facts to Excel. Those are separate remaining checks.
