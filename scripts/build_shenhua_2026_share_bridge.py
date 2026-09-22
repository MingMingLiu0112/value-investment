"""Compile the post-2025 ordinary-share bridge for 601088 as unreviewed evidence."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "company-research" / "shenhua-2026-share-bridge-20260921"
ANNUAL = ROOT / "runtime" / "shenhua-2025-official.pdf"

ANNUAL_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
ANNUAL_HASH = "460EA07EE14D3AEB2B7518A25F87B47833EA5473715D911C378C15F7425698FC"

SOURCES = (
    {
        "id": "acquisition_result",
        "filename": "1225014661-acquisition-result.pdf",
        "url": "http://static.cninfo.com.cn/finalpage/2026-03-18/1225014661.PDF",
        "sha256": "21701FBFDD0525423FD57F1C87F337EF55A5FD5C3BD5FF55279AD99890B6F345",
        "document_title": "发行股份及支付现金购买资产并募集配套资金暨关联交易实施情况暨新增股份上市公告书摘要",
        "document_date": "2026-03",
        "retrieval_date": date(2026, 3, 18),
    },
    {
        "id": "placement_result",
        "filename": "1225086590-placement-result.pdf",
        "url": "http://static.cninfo.com.cn/finalpage/2026-04-09/1225086590.PDF",
        "sha256": "46F6041A7B97A3013C7734C7E503FB66D43B7EA1619D9F87DAA8C2F4EA2C8631",
        "document_title": "发行股份及支付现金购买资产并募集配套资金暨关联交易实施情况暨新增股份上市公告书摘要",
        "document_date": "2026-04",
        "retrieval_date": date(2026, 4, 9),
    },
    {
        "id": "interim_summary",
        "filename": "1225531754-2026-interim-report.pdf",
        "url": "http://static.cninfo.com.cn/finalpage/2026-08-29/1225531754.PDF",
        "sha256": "48755B5E67F05A5D22AA94368C5502B010820F0403D3B5565D712144DB55F56D",
        "document_title": "2026 年半年度报告摘要",
        "document_date": "2026-08-29",
        "retrieval_date": date(2026, 8, 29),
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _require_page_text(reader: PdfReader, page_number: int, expected: tuple[str, ...], label: str) -> str:
    text = (reader.pages[page_number - 1].extract_text() or "").replace("\x00", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"{label} page {page_number} does not contain expected evidence {missing!r}")
    return text


def _source_descriptor(source: dict, path: Path) -> dict:
    reader = PdfReader(str(path))
    return {
        "id": source["id"],
        "path": path.relative_to(ROOT).as_posix(),
        "url": source["url"],
        "sha256": source["sha256"],
        "size_bytes": path.stat().st_size,
        "pdf_pages": len(reader.pages),
        "document_title": source["document_title"],
        "document_date": source["document_date"],
        "retrieval_date": source["retrieval_date"].isoformat(),
        "source_boundary": "CNINFO issuer-disclosure mirror retained locally; direct exchange original not yet matched",
    }


def build() -> dict:
    if _sha256(ANNUAL) != ANNUAL_HASH:
        raise ValueError("Shenhua 2025 annual report hash mismatch")

    paths = {source["id"]: OUT / source["filename"] for source in SOURCES}
    for source, path in zip(SOURCES, paths.values()):
        if not path.exists():
            raise ValueError(f"Missing retained source {path.name}")
        if _sha256(path) != source["sha256"]:
            raise ValueError(f"Hash mismatch for {path.name}")

    annual_reader = PdfReader(str(ANNUAL))
    annual_page_130 = _require_page_text(
        annual_reader,
        130,
        ("19,868,519,955", "16,491,037,955", "3,377,482,000", "概无持有库存股份"),
        "2025 annual report",
    )
    _require_page_text(
        annual_reader,
        152,
        ("股本", "19,869", "归属于母公司股东权益合计", "409,107"),
        "2025 annual report",
    )

    acquisition_reader = PdfReader(str(paths["acquisition_result"]))
    _require_page_text(
        acquisition_reader,
        3,
        ("29.40元/股", "1,363,248,446", "21,231,768,401", "2026年 3月 16日"),
        "acquisition result",
    )
    _require_page_text(
        acquisition_reader,
        13,
        ("36个月内", "锁定期自动延长 6个月"),
        "acquisition result",
    )
    _require_page_text(
        acquisition_reader,
        10,
        ("13,359,834.78", "9,351,884.35", "4,007,950.43"),
        "acquisition result",
    )

    placement_reader = PdfReader(str(paths["placement_result"]))
    _require_page_text(
        placement_reader,
        3,
        ("43.70 元/股", "457,665,903", "2026 年 4 月 7 日"),
        "placement result",
    )
    _require_page_text(
        placement_reader,
        22,
        ("19,999,999,961.10", "457,665,903"),
        "placement result",
    )
    _require_page_text(
        placement_reader,
        23,
        ("19,967,492,729.19", "6 个月内不得转让"),
        "placement result",
    )
    placement_page_24 = _require_page_text(
        placement_reader,
        24,
        ("21,689,434,304", "2025 年 4 月 7 日", "2026 年 3 月 30 日"),
        "placement result",
    )

    interim_reader = PdfReader(str(paths["interim_summary"]))
    _require_page_text(
        interim_reader,
        3,
        ("2026年6月30日", "21,689", "19,869", "总股本"),
        "2026 interim summary",
    )

    period_end_total = 19_868_519_955
    acquisition_issue = 1_363_248_446
    placement_issue = 457_665_903
    post_acquisition_total = period_end_total + acquisition_issue
    post_placement_total = post_acquisition_total + placement_issue
    if post_acquisition_total != 21_231_768_401 or post_placement_total != 21_689_434_304:
        raise ValueError("Share-bridge arithmetic does not match official totals")

    placement_date_typo_present = "2025 年 4 月 7 日" in placement_page_24
    if not placement_date_typo_present:
        raise ValueError("Expected placement-registration typo was not found on page 24")

    payload = {
        "symbol": "601088",
        "package_version": "shenhua-2026-ordinary-share-bridge-v1",
        "purpose": (
            "Reconstruct the ordinary-share denominator after the 2026 acquisition and "
            "placement issuances from retained issuer-disclosure PDFs. This package is "
            "compiled evidence only; it does not approve or feed a valuation model input."
        ),
        "status": "share_bridge_compiled_not_reviewed_or_approved",
        "valuation_status": "VALUATION_NOT_READY",
        "annual_report": {
            "path": ANNUAL.relative_to(ROOT).as_posix(),
            "url": ANNUAL_URL,
            "sha256": ANNUAL_HASH,
        },
        "sources": [_source_descriptor(source, path) for source, path in zip(SOURCES, paths.values())],
        "period_end_2025_12_31": {
            "ordinary_shares_total": period_end_total,
            "a_shares": 16_491_037_955,
            "h_shares": 3_377_482_000,
            "treasury_shares": 0,
            "restricted_shares": 0,
            "share_capital_audited_cny_millions": 19_869,
            "no_hk_buyback_sale_or_redemption_in_2025": True,
            "evidence": {
                "path": ANNUAL.relative_to(ROOT).as_posix(),
                "sha256": ANNUAL_HASH,
                "page": 130,
                "quoted_facts": [
                    "Ordinary share total was 19,868,519,955 at 2025-12-31.",
                    "A shares were 16,491,037,955 and H shares were 3,377,482,000.",
                    "The company held no treasury shares at 2025-12-31.",
                ],
            },
        },
        "post_balance_issuances": [
            {
                "id": "acquisition_asset_share_issuance",
                "registration_date": "2026-03-16",
                "issue_price_cny": "29.40",
                "new_shares": acquisition_issue,
                "share_class": "restricted A ordinary shares",
                "restricted_at_registration": True,
                "post_issuance_total": post_acquisition_total,
                "lock_up": (
                    "Seller shares are locked for 36 months from issuance completion, "
                    "with an automatic six-month extension if the price condition is met."
                ),
                "cash_consideration_cny": "93518843500.00",
                "total_consideration_cny": "133598347800.00",
                "share_consideration_cny": "40079504300.00",
                "evidence_pages": [3, 10, 13],
                "source_id": "acquisition_result",
            },
            {
                "id": "placement_supplementary_fund_share_issuance",
                "registration_date": "2026-04-07",
                "issue_price_cny": "43.70",
                "new_shares": placement_issue,
                "share_class": "restricted A ordinary shares",
                "restricted_at_registration": True,
                "post_issuance_total": post_placement_total,
                "gross_proceeds_cny": "19999999961.10",
                "net_proceeds_cny": "19967492729.19",
                "lock_up": "Placed shares are locked for six months from issuance completion.",
                "evidence_pages": [3, 22, 23, 24],
                "source_id": "placement_result",
            },
        ],
        "arithmetic": {
            "period_end_total": period_end_total,
            "acquisition_issue": acquisition_issue,
            "post_acquisition_total": post_acquisition_total,
            "placement_issue": placement_issue,
            "post_placement_total": post_placement_total,
            "verified_against_official_total": True,
        },
        "interim_corroboration_2026_06_30": {
            "ordinary_shares_total": post_placement_total,
            "stated_millions_of_shares": "21,689",
            "period_end_comparative_millions_of_shares": "19,869",
            "statement": (
                "The 2026 interim summary shows 21,689,434,304 total shares at 2026-06-30, "
                "matching the post-placement total and leaving no bridge residue between "
                "the two issue registrations and the interim balance date."
            ),
            "evidence_pages": [3],
            "source_id": "interim_summary",
        },
        "source_typo_caveats": [
            {
                "id": "placement_registration_year_typo",
                "detail": (
                    "Placement page 3 and the document context give a registration date of "
                    "2026-04-07, while page 24 prints 2025-04-07 in the same registration "
                    "sentence. The page also refers to the March 2026 capital verification "
                    "report and the April 2026 listing document. The retained source has "
                    "not been silently corrected; 2026-04-07 is recorded as the supported "
                    "reading with the typo preserved as a review caveat."
                ),
                "page": 24,
            }
        ],
        "ordinary_share_denominator_candidate": {
            "candidate_value": post_placement_total,
            "as_of": "2026-06-30",
            "basis": (
                "Ordinary shares outstanding after both 2026 share registrations and "
                "corroborated by the interim balance sheet; there is no evidence of treasury "
                "shares or a subsequent share-count change through the interim balance date."
            ),
            "review_status": "not_reviewed_or_approved",
            "model_input": None,
            "weighted_average_shares": None,
            "treasury_adjusted_shares": None,
            "review_requirements": [
                "Obtain a direct SSE/HKEX original for each issuance, not only the CNINFO mirror.",
                "Confirm whether the valuation date needs a point-in-time or weighted-average denominator.",
                "Confirm no treasury shares or further capital changes between the valuation date and 2026-06-30.",
            ],
        },
        "model_contract_observations": [
            "CyclicalFacts requires ordinary_shares to be a positive whole number.",
            "The model does not calculate weighted-average or treasury-adjusted shares by itself.",
            "This package leaves model_input null until an independent review chooses and documents the appropriate denominator.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }
    return payload


def main() -> int:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    source_hashes = {
        source["filename"]: source["sha256"]
        for source in SOURCES
    }
    manifest = {
        "script_sha256": _sha256(Path(__file__)),
        "evidence_sha256": _sha256(target),
        "source_sha256": source_hashes,
        "annual_report_sha256": ANNUAL_HASH,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pointer = ROOT / "runtime" / "company-research" / "shenhua-2026-share-bridge-latest.json"
    pointer.write_text(
        json.dumps(
            {
                "path": OUT.relative_to(ROOT).as_posix(),
                "sha256": _sha256(target),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(target),
                "sha256": _sha256(target),
                "status": payload["status"],
                "ordinary_share_denominator_candidate": payload["ordinary_share_denominator_candidate"]["candidate_value"],
                "model_input": payload["ordinary_share_denominator_candidate"]["model_input"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
