# 601800 verified evidence refresh

Date: 2026-09-09 (Asia/Shanghai). This records a live database readback and
downstream refresh, not strategy approval or complete-debt certification.

## Live evidence

- Symbol: 601800; annual period: 2025-12-31.
- Field: current_portion_long_term_debt; value: 109529611559 CNY.
- Live status: verified; candidate status: automatically_verified.
- Candidate ID: 775cc4f9-2083-479f-99a1-b294333ff38e.
- Source ID: 226fa331-eab4-4ac6-b3e6-32d255345023.
- Official URL: https://static.cninfo.com.cn/finalpage/2026-03-31/1225062556.PDF
- Official SHA-256: ed8bc43c43dadf2ddda5dac32bc2e7f037bbb5dcccb7d2ea91972c4014b13254.
- Main-statement PDF page: 172. Stored excerpt explicitly identifies visual
  review rather than text extraction and preserves image/review hashes.
- Secondary point ID: a4f29033-4714-4e69-9b01-1571821fe154.
- Secondary source: AkShare / Sina detailed financial statements.
- Secondary URL: https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/601800/displaytype/4.phtml?source=fzb
- Live metadata: automatic_cross_source_verification=true.

The historical review JSON is unchanged. Its pending status describes its
creation time; the database readback above is the subsequent verified state.
Other old pending candidates remain pending. No records were retired here.

## Refresh and boundary

Both refresh-financial-quality and refresh-valuations returned succeeded for
738 companies. Export generation: 2026-09-08T22:04:24.100077+00:00.
Export SHA-256: 0e3b43e38586aee4833a89f608a448d40e7581128c591bafd3a346305332e39b.
The downloaded payload independently contains this verified annual field.

Decision audit: runtime/decision-gaps-20260909-0604.json. All-data-gates-passed
count remains zero. All 642 ordinary-company models still lack acceptable
complete interest-bearing debt; one liability component is not that total.
All 738 companies still fail fair-value evidence and financial-quality gates.
No historical performance result or buy/sell approval was generated.

Official coverage in this payload is dated 2026-09-07: 5558 matched security
entries, including the documented domestic-depositary-receipt scope. This is
not a fresh 2026-09-09 all-market scan. Candidate boards: main 655, STAR 21,
ChiNext 56, Beijing 6.

Server preflight showed 1990 MiB available on root (95% used). No additional
PDF downloads were started. Existing shared lock and 0.5 CPU / 384 MiB memory /
512 MiB memory-plus-swap limits were used. PTA and other services were not
restarted or reconfigured. Workbook publication must be confirmed separately
from export success using the sync receipt and actual canonical workbook.

## Canonical publication confirmed

Sync exited successfully; runtime/excel-sync-status.json records published at
2026-09-09T06:07:08.2327696+08:00 with the export hash above. The canonical WPS
workbook was independently reopened after publication: 26 sheets, 738 watchlist
companies, and symbol 601800 with numeric value 109529611559 in column 6 of
the metric-evidence sheet. The pre-publication validator confirmed preservation
of manual records and history. Research retains 744 companies including history.
Verified exported points: 4801; annual input cells: 4078; specialized values: 196.
