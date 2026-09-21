# 000429 financing scope review

Reviewed 2026-09-08 against `runtime/000429-2025-annual.pdf`.
SHA-256: `369370607f3205de735f2f7b1d70311ac8a098fad4395c000f35cbaa62c6c7c1`.
Report period 2025-12-31; amounts in CNY; physical PDF pages.

## Cross-note evidence

- Page 154 financing table includes dividends payable 36,900,482.45. Page 141
  reconciles this to ordinary dividends 36,080,113.26 and other 820,369.19.
  Dividends are not to be promoted as interest-bearing financing debt.
- Page 154 other payables 45,451,750.00 matches the explicitly labeled borrowed
  funds in the page 141 other-payables breakdown. This establishes a financing
  description, not a verified interest rate or fully corroborated debt scope.
- Page 146 long-term payables 2,022,210.11 are described as amounts payable for
  non-operating assets. Do not assume they bear interest or exclude them without
  checking the agreement and accounting policy.
- Page 146 leases: payments 2,752,713.17 less unrecognized financing expense
  22,524.06 equals 2,730,189.11; all is current, leaving an explicitly printed
  noncurrent balance of 0.00. A zero noncurrent balance does not mean zero leases.
- Page 145 bond movement table identifies 20 Yuegaosu MTN001, principal
  750,000,000.00, coupon 3%, maturity 2025-03-17 and repayment 772,500,000.00.
  The closing cell is blank; this review does not promote it as verified zero.
  Separate redemption disclosure and accounting-sign reconciliation remain needed.

Text-layer search found no further occurrence of the borrowed-funds term beyond
page 141; this is not proof there is no related agreement or other disclosure.
Same-PDF cross-note matching is not independent-source verification.

## Classification consequences

Keep the existing generic `requires_note` category for other payables and
long-term payables. The financing description observed for this specific issuer
must not be generalized to every company's similarly named balance-sheet line.
Record date, issuer, label, amount and note evidence separately before approving
any issuer-specific mapping. No complete debt value or quality score was promoted.

## Separate rating-agency corroboration

The CNINFO issuer query for the redemption keyword, 2025-01-01 through
2026-09-08, returned zero announcements. Its response was archived under
`runtime/historical-filing-index/20260908T095301967361Z`; zero results are not
proof that no redemption disclosure exists.

Browser search located the rating agency's original notice:
https://www.lhratings.com/reports/B1044-P11957-2018-1-ZZ2025.pdf
Local file: `runtime/000429-mtn001-rating-termination-2025.pdf`.
SHA-256: `0294c2f8a7802cd8309f1c486ad1995b65364ed55530fc0838e33c1c2f302163`.

The one-page notice, Lianhe [2025] 1610, dated 2025-03-18, explicitly says
20 Yuegaosu MTN001 completed redemption on 2025-03-17 and is no longer
outstanding. It terminates the issuer and this issue's ratings. It cites an
issuer redemption-arrangement announcement dated 2025-02-21 and states that
completion information came from materials provided by the company.

This is a separate publisher corroborating redemption of this specific issue,
not an independently observed settlement record, not proof of no other debt,
and not permission to map every blank bond balance to zero. The cited issuer
arrangement and any settlement-agent confirmation remain additional evidence
targets. Do not treat the terminated AAA rating as a current rating.

## Bond identity and issuer arrangement retrieved

ChinaMoney browser page:
https://www.chinamoney.com.cn/chinese/zqjc/?bondDefinedCode=17818jzegn
The displayed bond code is 102000367, actual issue amount CNY 750 million,
coupon 3%, maturity 2025-03-17. The page explicitly warns that basic information
is updated only through issuance completion; its displayed AAA is therefore
not evidence of a current rating. The related-announcement list directly links
the 2025-02-21 issuer redemption arrangement.

Downloaded original:
https://www.chinamoney.com.cn/dqs/cm-s-notice-query/fileDownLoad.do?contentId=3055788&priority=0&mode=save
Local: `runtime/000429-mtn001-redemption-arrangement.pdf`.
SHA-256: `9b8f936e21bf7b95c14f6fe2def96bb9c155e1e027877798d30ceb0da888831e`.

This four-page file is scanned. Physical pages 1 and 2 were rendered and visually
read, not inferred from empty extracted text. Page 1 confirms bond identity,
principal CNY 750 million, coupon 3%, and payment date 2025-03-17. Page 2 states
principal plus interest payable CNY 772.5 million, matching the annual report's
repayment. Arithmetic: 750,000,000 * (1 + 0.03) = 772,500,000. The named registrar
and custodian is Shanghai Clearing House (Bank Clearing Market Co., Ltd.).

The issuer arrangement is a prospective payment notice, not a settlement receipt.
Actual completion is corroborated by the later rating termination and annual
report, with their source-dependency limitations preserved. Pages 3-4 were not
visually reviewed in this pass. No all-company debt-zero inference is authorized.
