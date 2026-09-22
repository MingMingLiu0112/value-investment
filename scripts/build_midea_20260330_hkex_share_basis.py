"""Pin Midea's 2026-03-30 HKEX share-basis disclosure without registering a valuation denominator.

The 2025 annual report discloses the year-end treasury-stock carrying value
but not its share count. The HKEX full-year results announcement dated
2026-03-30 discloses the A-share treasury count as of that announcement date.
That count is a point-in-time fact, not the FY2025 year-end count and not a
current valuation-date denominator.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-hkex-20260330-annual-results.pdf"
SOURCE_SHA256 = "c79bef69e4e0629f46987159698bca4a6a5cbfad0fdea596242580b42a813b2a"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033001929_c.pdf"
ANNUAL_REPORT = ROOT / "runtime" / "midea-2025-official.pdf"
ANNUAL_REPORT_SHA256 = "16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6"

OUT = ROOT / "runtime/company-research/midea-20260330-hkex-share-basis-20260922"
POINTER = ROOT / "runtime/company-research/midea-20260330-hkex-share-basis-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def page_text(page_number: int) -> str:
    pdf = pdfium.PdfDocument(str(SOURCE))
    page = pdf[page_number - 1]
    textpage = page.get_textpage()
    value = textpage.get_text_bounded() or ""
    page.close()
    pdf.close()
    return value


def require_page(page_number: int, expected: tuple[str, ...]) -> str:
    text = page_text(page_number)
    normalized = compact(text)
    missing = [value for value in expected if compact(value) not in normalized]
    if missing:
        raise ValueError(f"Page {page_number} does not contain expected evidence {missing!r}")
    return text


def source_ref(ref_id: str, pages: list[int], description: str) -> dict:
    return {
        "id": ref_id,
        "path": str(SOURCE.relative_to(ROOT)),
        "url": SOURCE_URL,
        "sha256": SOURCE_SHA256,
        "pages": pages,
        "created_at": "2026-03-30T18:49:11+08:00",
        "description": description,
    }


def build_payload() -> dict:
    if digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("Midea HKEX 2026-03-30 results announcement changed")
    if digest(ANNUAL_REPORT) != ANNUAL_REPORT_SHA256:
        raise ValueError("Midea 2025 annual report changed")

    require_page(1, ("截至2025年12月31日止年度之全年業績公告",))
    require_page(15, (
        "7,603,276,186",
        "80,412,541",
        "7,522,863,645",
        "每10股人民幣38元",
        "28,586,881,851",
    ))
    require_page(94, (
        "80,412,541",
        "每10股派發人民幣38元",
        "本公司庫存股份將無權獲付有關股息分配",
        "截至本公告日期",
    ))

    return {
        "symbol": "000333",
        "package_version": "midea-20260330-hkex-share-basis-v1",
        "announcement_date": "2026-03-30",
        "announcement_timezone": "+08:00",
        "document_created_at": "2026-03-30T18:49:11+08:00",
        "review_date": "2026-09-22",
        "purpose": (
            "Pin the HKEX full-year results announcement's 2026-03-30 share-count and "
            "final-dividend base disclosures. This is an announcement-date point-in-time "
            "fact, not a year-end 2025 share count and not a current valuation denominator."
        ),
        "status": "announcement_date_share_basis_disclosed_not_registered",
        "facts": {
            "document": {
                "type": "HKEX full-year results announcement",
                "company": "Midea Group Co., Ltd. / 美的集团股份有限公司",
                "stock_code": "00300",
                "period_end": "2025-12-31",
            },
            "page_15_final_dividend_basis": {
                "total_share_capital_at_approval_date": 7603276186,
                "repurchased_a_shares_excluded": 80412541,
                "shares_entitled_to_final_dividend": 7522863645,
                "final_dividend_cny_per_10_shares": "38.00",
                "final_dividend_total_cny": "28,586,881,851",
                "basis_is_announcement_approval_date": True,
            },
            "page_94_treasury_share_count": {
                "as_of": "announcement_date_2026-03-30",
                "a_share_treasury_share_count": 80412541,
                "treasury_shares_entitled_to_dividend": False,
                "as_of_is_year_end_2025": False,
                "as_of_is_current_valuation_date": False,
            },
            "year_end_2025_reference": {
                "issued_total_shares": 7597145346,
                "treasury_share_count": None,
                "reason": (
                    "The 2025 annual report page 220 gives the treasury-stock carrying "
                    "value but not a year-end treasury share count."
                ),
            },
        },
        "derived_scope": {
            "announcement_date_treasury_share_count_observable": True,
            "announcement_date_distributable_share_base_observable": True,
            "year_end_2025_treasury_share_count_observable": False,
            "announcement_date_scope_is_current_2026_09_22_valuation_scope": False,
            "total_share_capital_delta_from_year_end": 6130840,
            "delta_cause_inferred": False,
        },
        "share_basis_registered_for_current_valuation": False,
        "allowed_uses": [
            "Display the 2026-03-30 announcement-date A-share treasury count as a point-in-time fact.",
            "Display the final-dividend base of 7,522,863,645 shares as of the announcement date.",
            "Use the announcement-date share scope only for a valuation date that is date-matched to 2026-03-30 and after every other input is independently registered.",
        ],
        "blocked_uses": [
            "Do not treat the 2026-03-30 treasury count as the FY2025 year-end treasury count.",
            "Do not use the announcement-date count as the 2026-09-22 current valuation denominator.",
            "Do not infer the cause of the 6,130,840-share increase from year end.",
            "Do not use the dividend base alone to unlock FCFF or an equity-value model.",
        ],
        "blockers": [
            "announcement_date_share_scope_is_not_current_valuation_scope",
            "year_end_2025_treasury_share_count_still_not_disclosed",
            "financial_business_carve_out_and_fcff_enterprise_bridge_still_not_ready",
            "formal_valuation_not_approved",
        ],
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "evidence_refs": [
            source_ref("midea_hkex_20260330_page_1", [1], "Full-year results announcement cover and financial summary"),
            source_ref("midea_hkex_20260330_page_15", [15], "Proposed final dividend and announcement-date share base"),
            source_ref("midea_hkex_20260330_page_94", [94], "Announcement-date A-share treasury count and dividend entitlement"),
            {
                "id": "midea_2025_annual_report_share_scope",
                "path": str(ANNUAL_REPORT.relative_to(ROOT)),
                "url": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF",
                "sha256": ANNUAL_REPORT_SHA256,
                "pages": [143, 219, 220],
                "description": "FY2025 annual-report year-end share totals and treasury-stock carrying values",
            },
        ],
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> None:
    payload = build_payload()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_digest = digest(target)
    manifest = {
        "script_sha256": digest(Path(__file__).resolve()),
        "evidence_sha256": evidence_digest,
        "source_sha256": SOURCE_SHA256,
        "annual_report_sha256": ANNUAL_REPORT_SHA256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    POINTER.write_text(
        json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": evidence_digest},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": evidence_digest,
        "status": payload["status"],
        "share_basis_registered_for_current_valuation": False,
        "registered_valuation_model": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
