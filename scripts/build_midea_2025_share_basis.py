"""Pin Midea's disclosed 2025 accounting share basis without creating a valuation denominator.

The annual report gives both the year-end A/H issued-share totals and the
weighted ordinary-share denominators used for reported EPS. Those are different
questions. This package preserves that distinction and refuses to promote the
accounting EPS denominator into a current per-share valuation input.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
SOURCE_SHA256 = "16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6"
SOURCE_URL = "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF"

OUT = ROOT / "runtime/company-research/midea-2025-share-basis-20260922"
POINTER = ROOT / "runtime/company-research/midea-2025-share-basis-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_text(reader: PdfReader, page: int) -> str:
    return " ".join((reader.pages[page - 1].extract_text() or "").replace("\x00", " ").split())


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = normalized_text(reader, page)
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def source_ref(ref_id: str, page: int, unit: str, description: str) -> dict:
    return {
        "id": ref_id,
        "path": str(SOURCE.relative_to(ROOT)),
        "url": SOURCE_URL,
        "sha256": SOURCE_SHA256,
        "page": page,
        "unit": unit,
        "description": description,
    }


def build_payload() -> dict:
    if digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("Midea 2025 official annual report changed")

    reader = PdfReader(str(SOURCE))
    page_text(reader, 4, ("公司2025 年度利润分配方案", "每10 股派发现金43 元（含税）"))
    page_text(reader, 143, ("7,597,145,346", "6,946,296,846", "650,848,500", "2026 年3 月 30 日批准报出"))
    page_text(reader, 219, ("7,655,956", "7,597,145", "50,101", "108,912", "650,849"))
    page_text(reader, 220, ("8,151,117", "11,606,405", "9,183,734", "5,728,446"))
    page_text(reader, 223, ("6,983,922,480", "6,896,648,327", "650,848,500", "2,821,000"))
    page_text(reader, 231, ("7,559,265", "7,608,132", "48,867", "43,829,974", "5.80", "5.76"))

    payload = {
        "symbol": "000333",
        "package_version": "midea-2025-annual-share-basis-v1",
        "as_of_period": "2025-12-31",
        "report_approved_on": "2026-03-30",
        "research_available_at": "2026-04-01T00:00:00+08:00",
        "purpose": (
            "Establish the disclosed FY2025 accounting EPS share scope and the year-end "
            "A/H issued-share totals. This is not a valuation share denominator."
        ),
        "status": "accounting_share_facts_disclosed_not_valuation_denominator",
        "facts": {
            "year_end_2025": {
                "issued_total_shares": 7597145346,
                "issued_a_shares": 6946296846,
                "issued_h_shares": 650848500,
                "a_plus_h_reconciles_to_total": True,
                "p143_total_and_p219_movement_agree": True,
                "rounding_note": (
                    "Page 219 reports the movement table in thousands of shares and rounds "
                    "the H-share class to 650,849 thousand. The exact page-143 class total is "
                    "650,848,500 shares; both are retained, and no H-share amount is inferred."
                ),
            },
            "fy2025_accounting_eps": {
                "parent_ordinary_net_profit_cny_thousand": 43829974,
                "weighted_average_ordinary_shares_thousand": 7559265,
                "share_payment_ordinary_shares_added_thousand": 48867,
                "diluted_weighted_average_ordinary_shares_thousand": 7608132,
                "basic_eps_cny": "5.80",
                "diluted_eps_cny": "5.76",
                "denominator_is_fy2025_time_weighted_scope": True,
            },
            "treasury_stock_2025": {
                "year_end_carrying_value_cny_thousand": 8151117,
                "increase_cny_thousand": 11606405,
                "decrease_cny_thousand": 9183734,
                "year_end_share_count": None,
                "reason_share_count_not_observed": (
                    "Page 220 discloses treasury-stock carrying values and movements only; "
                    "it does not disclose the corresponding year-end number of treasury shares."
                ),
            },
            "dividend_scope_bases": [
                {
                    "meeting_date": "2025-05-30",
                    "cash_per_share_cny": "3.50",
                    "a_shares_excluding_repurchased": 6983922480,
                    "h_shares": 650848500,
                },
                {
                    "meeting_date": "2025-09-24",
                    "cash_per_share_cny": "0.50",
                    "a_shares_excluding_repurchased": 6896648327,
                    "h_shares": 650848500,
                },
            ],
        },
        "derived_scope": {
            "fy2025_weighted_denominator_can_verify_reported_eps": True,
            "fy2025_weighted_denominator_is_current_valuation_share_basis": False,
            "year_end_issued_total_is_weighted_denominator": False,
            "year_end_treasury_share_count_is_observable": False,
            "day_by_day_weight_inputs_are_disclosed": False,
        },
        "registered_valuation_inputs": {
            "ordinary_shares": None,
            "reason": (
                "The accounting denominator is retained as evidence but not registered "
                "because it is not date-matched to a future valuation date."
            ),
        },
        "allowed_uses": [
            "Cross-check the reported FY2025 basic and diluted EPS denominators against the annual report.",
            "Display the disclosed 7,559,265 / 7,608,132 thousand weighted-share range as an accounting scope.",
            "Display the exact 2025-12-31 issued A/H totals as a point-in-time share-capital fact.",
        ],
        "blocked_uses": [
            "Do not divide a future-period equity value by the FY2025 weighted denominator.",
            "Do not treat the 2025-12-31 issued total as the FY2025 weighted EPS denominator.",
            "Do not convert the treasury-stock carrying amount into a treasury share count.",
            "Do not infer a current A/H tradable float or an execution share quantity.",
        ],
        "blockers": [
            "year_end_treasury_share_count_not_disclosed",
            "fy2025_weighted_denominator_is_not_a_current_valuation_denominator",
            "future_valuation_share_scope_not_yet_date_matched",
            "financial_business_carve_out_and_fcff_enterprise_bridge_still_not_ready",
        ],
        "evidence_refs": [
            source_ref("midea_2025_page_143_issued_share_totals", 143, "shares",
                       "Company overview disclosing the 2025-12-31 issued A/H share totals"),
            source_ref("midea_2025_page_219_share_movement", 219, "thousand shares",
                       "Share capital note disclosing FY2025 movements and closing class totals"),
            source_ref("midea_2025_page_220_treasury_stock", 220, "CNY thousands",
                       "Treasury-stock carrying-value movements; no year-end share count"),
            source_ref("midea_2025_page_223_dividend_bases", 223, "shares and CNY",
                       "Dividend distribution A/H share bases and restrictive-share cancellation"),
            source_ref("midea_2025_page_231_eps", 231, "CNY thousands, thousand shares and CNY/share",
                       "Reported FY2025 basic and diluted EPS denominators"),
        ],
        "share_basis_approved": False,
        "valuation_approved": False,
        "trade_approved": False,
    }
    return payload


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
        "share_basis_approved": False,
        "registered_ordinary_shares": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
