"""Build an auditable point-in-time timeline for Moutai's 2025 share event.

The completion announcement made the cancellation effective date an expectation.
The later annual report confirms the year-end share movement, but is deliberately
kept as ex-post confirmation rather than being used in a 2025 decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_moutai_ttm_comparability import ROOT, sha, texts
from value_investment_agent.historical_asof import publication_date_upper_bound
from build_moutai_consolidated_equity_inputs import annual_report_metadata


COMPLETION = ROOT / "runtime/company-research/600519-cancellation-2025-20260909T094442562176Z/original.pdf"
COMPLETION_SHA256 = "9ad8dda3c43bbc19bf9926394ddf4a030543455910f7ef1b1bb736bd4385215b"
ANNUAL = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf"
ANNUAL_SHA256 = "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"


def _all_pages_include(path: Path, page: int, phrases: tuple[str, ...]) -> None:
    decoded = texts(path, page)
    if not decoded or any(phrase not in text for text in decoded for phrase in phrases):
        raise ValueError(f"Verified source text mismatch: {path.name} page {page}")


def build_timeline() -> dict:
    if sha(COMPLETION) != COMPLETION_SHA256 or sha(ANNUAL) != ANNUAL_SHA256:
        raise ValueError("A pinned original changed")

    _all_pages_include(
        COMPLETION,
        2,
        ("2025年8月29日", "3,927,585股", "5,999,985,966.95元", "公司回购股份实施完成"),
    )
    _all_pages_include(COMPLETION, 3, ("预计公司将于2025年9月1日",))
    _all_pages_include(
        ANNUAL,
        47,
        ("1,256,197,800", "-3,927,585", "1,252,270,215", "2025年8月30日"),
    )
    _all_pages_include(
        ANNUAL,
        68,
        ("-3,927,585.00", "120,112,601.53", "-6,000,465,970.56"),
    )

    completion_available = publication_date_upper_bound("2025-08-30").isoformat()
    annual_metadata = annual_report_metadata()
    annual_available = annual_metadata["available_at"]
    events = [
        {
            "event": "first_program_completion_and_expected_cancellation",
            "known_at": completion_available,
            "effective_date_claimed": "2025-09-01",
            "status": "contemporaneous_expected_effective_date",
            "shares": 3927585,
            "cash_excluding_fees_cny": "5999985966.95",
            "issued_shares_before": 1256197800,
            "issued_shares_after_if_effective": 1252270215,
            "source": {
                "source_id": "cninfo:1224625694",
                "source_path": str(COMPLETION.relative_to(ROOT)),
                "source_sha256": COMPLETION_SHA256,
                "physical_pages": [2, 3],
            },
            "usable_for_2025_point_in_time_share_basis": True,
            "limitations": [
                "The announcement uses an expected cancellation date, not a separately archived same-day registry confirmation.",
                "It does not establish an intraday effective time or daily treasury-share balance.",
            ],
        },
        {
            "event": "first_program_cancellation_year_end_confirmation",
            "known_at": annual_available,
            "effective_period": "2025 annual reporting period",
            "status": "ex_post_audited_confirmation",
            "shares": 3927585,
            "issued_shares_before": 1256197800,
            "issued_shares_after": 1252270215,
            "treasury_stock_closing_carrying_value_cny": "120112601.53",
            "repurchase_equity_cash_effect_cny": "-6000465970.56",
            "source": {
                **annual_metadata,
                "source_path": str(ANNUAL.relative_to(ROOT)),
                "source_sha256": ANNUAL_SHA256,
                "physical_pages": [47, 68],
            },
            "usable_for_2025_point_in_time_share_basis": False,
            "limitations": [
                "This report became public after the 2025 decision window and must not repair historical decisions retrospectively.",
                "The closing treasury-stock carrying value includes the separately active second repurchase program, so it is not the carrying cost of the cancelled first program.",
            ],
        },
    ]
    return {
        "symbol": "600519",
        "contract_version": "moutai-2025-share-timeline-v2",
        "scope": "issued-share and treasury-stock evidence only; not a daily fill reconstruction or a valuation approval",
        "events": events,
        "reconciliations": {
            "share_delta": 1256197800 - 1252270215,
            "matches_first_program_completion_shares": True,
            "annual_confirmation_is_ex_post_for_2025": True,
            "second_program_not_backfilled_into_2025": True,
        },
        "unresolved_intervals": [
            "No separately archived same-day registry confirmation has been tied to the 2025-09-01 expected effective date.",
            "No daily treasury-share carrying balance or daily repurchase fills are inferred from cumulative disclosures.",
        ],
        "valuation_approved": False,
        "trade_approved": False,
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-2025-share-timeline-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_timeline(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps({"script_sha256": sha(Path(__file__)), "evidence_sha256": sha(evidence)}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "events": 2, "valuation_approved": False}))


if __name__ == "__main__":
    main()
