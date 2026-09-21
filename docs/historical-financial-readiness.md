# 历史财务输入检查

## Current Recheck (2026-09-08, v25)

The older coverage notes below are historical, not the current inventory.
`runtime/historical-candidates-v25-recheck-20260908` contains 33 hash-checked
original annual reports, 455 candidate rows, covering 2014-2024 for each issuer.
All 33 reports have annual EPS candidates. ROE appears in 31 reports: Midea 2016
and Moutai 2018 remain missing. The main extraction packets still contain no
BVPS or EPS_TTM; separate Shenhua BVPS research has not been merged or approved.

Midea 2015 now produces EPS 2.99 CNY/share and weighted ROE 29.06% at physical
page 10, with the explicit annual column header retained from page 9. It does
not substitute the nearby latest-capital diluted figure 2.98.

`runtime/historical-v25-decoder-{000333,600519,601088}-20260908.json` records
11/11 candidate-page decoding matches for each issuer, including adjacent
header pages when needed. This compares the same parser on two decoders of the
same original, not independent source verification or a completeness check.
pypdf emitted invalid-object-pointer warnings for some Shenhua originals; the
result covers only the inspected candidate pages, not whole-PDF integrity.

Next source gaps: inspect the two missing ROE rows, reconcile historical BVPS
and ordinary-share scope, establish point-in-time availability and quarterly
TTM inputs, then freeze/reconstruct historical valuations. No performance
backtest or production data promotion was performed in this recheck.

### v26 Targeted ROE Follow-up

Read actual source pages for the remaining two ROE gaps. Midea 2016 physical
page 9 discloses weighted ROE 26.88%, continuing the year columns on page 8.
Moutai 2018 physical page 6 discloses weighted ROE 34.46%, with the annual
header on page 5; nearby adjusted ROE 34.84% is not the required metric.

Local v26 accepts a ROE-first continuation and the observed deducted-EPS-first
continuation; the latter is permitted to emit ROE only, never adjusted EPS as
ordinary EPS. Dashed page numbers are recognized. Actual source-page reruns
extracted the two expected values with their preceding header page references.
Full regression: 670 passed, 18 existing Backtrader warnings. The complete
33-report packets and dual-decoder comparison still need a new v26 run; the v25
results above are retained, not overwritten. No server deployment performed.

### v26 Complete Rerun

`runtime/historical-candidates-v26-20260908` now contains all 33 reports, with
457 candidates. All 33 have annual EPS and weighted-ROE candidates. Comparing
field/value/unit/page multisets against v25 found exactly two additions:
Midea 2016 ROE 26.88 at p9 and Moutai 2018 ROE 34.46 at p6. No other candidate
value changes or removals occurred.

`runtime/historical-v26-decoder-{000333,600519,601088}-20260908.json` records
11/11 candidate-page agreement for each issuer, including both new ROE rows.
The same pypdf object-pointer warnings remain for some Shenhua PDFs. Agreement
is still same-source decoding evidence, not independent verification, proof
of complete financial inputs, or a strategy backtest. No production promotion.

### BVPS Coverage Follow-up

`runtime/historical-bvps-coverage-000333-20260908.json` and
`runtime/historical-bvps-coverage-600519-20260908.json` scanned the first 30 pages
of each issuer's 11 original reports with both decoders. Neither issuer matched
the existing narrow explicit-BVPS table formats. This does not prove absence
of disclosure and does not invalidate the archived net-asset data.

Moutai 2018 original `600519-1205958206.pdf`, physical page 5, states attributable
ending net assets CNY 112,838,564,332.05 and ending share count 1,256,197,800.
Their Decimal quotient is 89.82547520147702853802163959 CNY/share, a derived
research candidate, not an issuer-disclosed BVPS quote. Page 38 explicitly marks
the preferred-share section not applicable. Consolidated balance sheet p53
also shows share capital 1,256,197,800.00; share capital in CNY alone is not
substituted for share count. Other equity instrument lines are blank, not an
explicit zero. Complete ordinary-equity scope and historical availability remain
unapproved; no time series or production BVPS was created from this ratio.

### Repeatable Summary-Derived BVPS Candidates

The explicit `--method summary-derived` research mode now uses same-page
year-end columns, CNY-unit disclosure, attributable net assets and the literal
ending-total-shares label. It rejects missing, fractional or zero share counts,
other equity labels, different unit scales and cross-section/page joins.
Inputs, Decimal formula, source page and unapproved equity-scope status persist.

Actual output `runtime/moutai-summary-bvps-20260908.json`: six of eleven annual
reports (2015-2020) produced candidates; all six matched two PDF decoders and
their title reporting periods. 2014 and 2021-2024 remain unmatched by this
narrow layout, not proven absent. Thirty-two focused BVPS tests passed.
Ordinary-equity adjustments, stock-count basis, availability and revisions
remain to be approved separately before any backtest. Production unchanged.

### Remaining Moutai Share-Denominator Evidence

Full-report inspection located the five unmatched cases:

- 2014 p20: ordinary RMB shares and total shares end at 1,141,998,000,
  following a 103,818,000 share bonus issue. The nearby BVPS 41.05 / 37.32
  explicitly relates to 2013 before/after that issue, not 2014 ending BVPS.
- 2021 p43, 2022 p46, 2023 p50, 2024 p49: issuer states no changes in total
  shares or capital structure during the report period. This alone is not an
  absolute share count. Their summary label is share capital, not ending shares.
- The corresponding share-capital notes are on physical pages 97, 98, 106,
  106. They show 1,256,197,800.00 opening and closing, but 2024 p106 explicitly
  declares CNY rather than shares. Do not silently equate amount and share count.
- 2024 p2: total shares 1,256,197,800 as of 2025-03-31, treasury-account shares
  1,082,700 and dividend-entitled shares 1,255,115,100. These are dated after
  the 2024 balance-sheet date; dividend-entitled shares cannot be used as the
  historical year-end BVPS denominator without the appropriate reconciliation.

No constant-share forward fill or latest-distribution denominator was used.
Next: obtain explicit dated ordinary-share count/par-value and treasury-share
evidence, then link same-period equity and denominator with both source pages.

### Explicit Dated Share Counts

A new research-only extractor recognizes the exact prose pattern "as of
YYYY-12-31, company total shares [number] shares/ten-thousand shares". It does
not convert share-capital CNY into shares or read dividend-entitled balances.
Five focused tests cover the date, currency and entitlement exclusions.

Actual original-report scans now identify 1,256,197,800 shares explicitly as of
2022-12-31 (2022 report p2), 2023-12-31 (2023 report p2), and 2024-12-31
(2024 report p74). Values and dates come from each report separately, not from
forward fill. 2014 and 2021 did not match this exact pattern. These denominator
candidates are not yet dual-decoder compared or joined to approved ordinary
equity; no new production BVPS values were created.

### Dated Shares Dual-Decoder Result

`runtime/moutai-dated-shares-dual-20260908.json` records all eleven reports,
1,275 pages scanned, using a 160-page per-report ceiling. Three candidate
reports (2022, 2023, 2024) matched PDFium and pypdf on value, period, unit and
page, and their periods matched the respective report titles. The output
retains the exact dated prose, report manifest, archive hash and pages scanned.
Other years remain unmatched by this narrow pattern; they were not filled with
the recurring share count. This validates decoding, not independent source
confirmation, treasury-share scope or a completed historical BVPS input series.

## 神华BVPS与重述的后续实证

2026-09-08第三轮BVPS研究输出：`runtime/shenhua-historical-bvps-v3.json`。
扫描各报告前30页，2017至2023七个年度的候选分别为15.16、16.48、17.69、
18.13、18.97、19.82、20.57元/股；七项PDFium与pypdf一致，归属口径未批准。
2014至2016和2024仍是当前规则未命中，不代表未披露。

实际读取2024年报 `601088-1222870380.pdf` 第8页：当前BVPS为21.48元，
日期表头中只有2022比较年度有一组“重述后／重述前”，区别于此前两组布局，
本轮未放宽解析器。该页还明确说明自2023年起执行《企业会计准则解释第16号》，
对2022年财务数据重述，并指向2023-04-29的会计政策变更公告。
2022比较列的基本EPS为重述后3.505、重述前3.504；加权ROE为18.08%、18.07%。
这是禁止用后出年报比较列覆盖原始历史输入的具体案例；政策变更公告尚未读取，
不能仅据本页断定所有指标的重述生效时间和影响范围。

2026-09-08。检查本地v22候选包：33份年报、438条候选，三家公司各11份，
对应2014至2024报告年度。候选存在不等于原文、口径及历史可用时点已验证。

## 关键阻碍

- 三家公司所有11个年度均无 `bvps` 和 `eps_ttm` 候选。
- 年度EPS候选缺失：美的2015；茅台2014；神华2019至2024。
- 不能把年度EPS直接填成全年每日TTM，也不能把最新净资产复制到历史。
- BVPS须使用归属于普通股股东的权益及相匹配的期末股数，不能用含少数股东
  权益的总权益；EPS加权股数与期末股数不等价。
- 年报公布后到下一次报告之间，必须按当时可得报告重建输入，记录修订和送转
  股影响；目前年度报告归档不能替代完整季报可用时间序列。

## 已读原文的解析漏项

茅台2014年年报，第5页，2014年列：基本EPS为13.44元/股，加权平均ROE为
31.96%。不得误用同页扣非EPS13.59或扣非ROE32.32%。

原件：https://static.cninfo.com.cn/finalpage/2015-04-21/1200877315.PDF

本地：`runtime/historical-filing-index/20260908T041326996681Z/pdfs/600519-1200877315.pdf`

归档Hash：`89145ef5bd12256c4c75c122b1c8d59846a912434f1abd0570f678bdb1a20f24`。

同页说明2013、2012年的每股收益按2013年度利润分配后股数重算。因此后出报告
的比较列不能无条件当作历史当时已知的原始披露。该记录只确认所读年报内容，
未批准历史交易输入，没有写入生产数据库或Excel。

## v24双解码检查

神华11份、茅台11份、美的10份的既有EPS/ROE候选在PDFium与pypdf中匹配。
检查只覆盖候选所在页，不是全报告独立抽取，也没有确认应有指标全部齐全。
美的2015年候选为空，不能当成“两种解码都证明未披露”，脚本已增加
`no_candidates_not_compared` 状态以区别真正数值不一致。

该年报原件 `000333-1202084987.pdf` 第10页实际披露基本EPS2.99元/股、
加权平均ROE29.06%；另列按披露前最新股本计算的全面摊薄EPS2.98元/股。
缺项来自表格跨页，上述数值未被现有候选提取器捕获。修复时需要从上一页
延续已确认年度列，且在本页季度表前结束；不得误取最新股本EPS替代基本EPS。
原件归档Hash：`595c0bc14c311d723b3da2b4291cfd0c1bb784fe77bed62427d269ec2f94969f`。
