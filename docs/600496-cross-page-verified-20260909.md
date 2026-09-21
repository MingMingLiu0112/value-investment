# 600496 cross-page candidate verified

Date: 2026-09-09. Live production readback, not a backtest result.

The initial database read showed only a pending Sina structured value for
current_portion_long_term_debt and no corresponding official-PDF candidate.
The v33 parser's reviewed candidate was registered with a real savepoint
rollback rehearsal. Existing facts, disclosure metadata and candidates were
compared before/after and remained unchanged during candidate registration.

- Registration task: 6ff15f31-f80e-4abc-8aea-93fa8435e3bd.
- Candidate: d5905499-7043-49cf-9955-55a18969f09d.
- Registration script: scripts/register_cross_page_debt_candidate.py.
- Targeted registration/insertion tests: 10 passed.
- Auto-verification command: auto-verify-filings --limit 500.
- Result: succeeded, records_stored=1.

A subsequent independent production database read confirmed:

- Symbol 600496, period 2025-12-31, value 468249668.22 CNY.
- Candidate status automatically_verified; fact status verified.
- Official source ID: 50b36e98-f705-4676-b0eb-6999f5d60d3b.
- PDF URL: https://static.cninfo.com.cn/finalpage/2026-04-18/1225120796.PDF
- PDF SHA-256: 7063bee136b03667ca138335ce8ac0950406762e64b707f5771483b239d4fa03.
- Amount page 80 and page 81 continuation citation survive in candidate_excerpt.
- Secondary source: AkShare / Sina detailed financial statements.
- Secondary point: 566ab5d4-d02a-4580-b67c-b1ada9f26ce9.
- Secondary URL: https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/600496/displaytype/4.phtml?source=fzb
- automatic_cross_source_verification=true; original-file hash verified at promotion.

The existing annual revenue and net-income growth values remain pending.
Four verified liability components do not establish complete interest-bearing
debt. No trading approval, performance result, or new Excel publication is
claimed in this record. Downstream refresh/export and canonical publication
remain necessary before this new verified status appears in the workbook.

All server commands used the shared market-screen lock and 0.5 CPU / 384 MiB
memory / 512 MiB memory-plus-swap limits. No new original PDF was downloaded,
and no unrelated service was restarted.
