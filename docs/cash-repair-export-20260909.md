# Cash repair downstream refresh

Export: 2026-09-08T23:15:40.333435+00:00.
SHA-256: d940fc095dba9d3aa0438211921bb85c5f3460006a2effe5cac64719d89fc935.
Quality and valuation refresh both succeeded for 738 companies.

The downloaded export independently confirms cash is verified and accepted
by the quality calculation for all nine repaired issuers: 000425, 001233,
001386, 002011, 002043, 002444, 002727, 300815, 301376. Cash gaps fell from
349 to 340. Other major gaps did not change in this comparison.

Audit: runtime/decision-gaps-after-cash-repair-20260909.json.
All-data-gates-passed is still zero; 642 ordinary-company models lack
acceptable complete interest-bearing debt. All 738 fail fair-value evidence
and quality gates. This export is neither a fresh all-market screen nor a
historical performance validation. Keep trading suggestions blocked.

Canonical workbook publication succeeded at 2026-09-09 07:18:05+08:00.
Reopened actual WPS file: 26 sheets, all 738 reminders still say historical
backtest incomplete. Metric-evidence column 4 holds the field code (column 3
is its Chinese label); querying the correct column confirms all nine annual
cash rows present with cross-verified status. A first inspection used the
label column and returned no matches, corrected without modifying workbook.
Pre-publication validation confirmed manual/history preservation and 738
main company rows. The cash repair is now reflected in the original workbook.
