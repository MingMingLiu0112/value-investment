"""Freeze Midea annual reported total-share facts without inventing daily float.

The sources are double-decoder annual-report disclosure neighborhoods.  Each
row is an explicitly reported year-end total and is deliberately kept separate
from an outstanding-share, treasury-share, or daily execution denominator.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.historical_asof import publication_date_upper_bound


INVENTORY = ROOT / "runtime/company-research/midea-annual-share-disclosure-inventory-20260912T001114Z/inventory.json"
INVENTORY_SHA256 = "6cdcbba9b24735d53460810c17b37351014a3925983da47933f000fd17f820c4"
# Report-year, source page, beginning total shares, ending total shares.
ROWS = (
    (2014, 60, 1686323389, 4215808472),
    (2015, 56, 4215808472, 4266839449),
    (2016, 55, 4266839449, 6458766808),
    (2017, 61, 6458766808, 6561053319),
    (2018, 73, 6561053319, 6663030506),
    (2019, 87, 6663030506, 6971899574),
    (2020, 103, 6971899574, 7029975999),
    (2021, 129, 7029975999, 6986563844),
    (2022, 160, 6986563844, 6997273076),
    (2023, 141, 6997273076, 7025769025),
    (2024, 136, 7025769025, 7655955883),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_timeline() -> dict:
    if digest(INVENTORY) != INVENTORY_SHA256:
        raise ValueError("Annual share inventory changed")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    reports = {row["report_year"]: row for row in inventory["reports"]}
    if sorted(reports) != list(range(2014, 2025)):
        raise ValueError("Unexpected annual report coverage")
    timeline = []
    for year, page, opening, closing in ROWS:
        report = reports[year]
        original = (ROOT / report["path"]).resolve()
        if not original.is_relative_to(ROOT.resolve()) or digest(original) != report["sha256"]:
            raise ValueError(f"Annual report original changed: {year}")
        shared = {(entry["page"], entry["term"]) for entry in report["shared_page_term_candidates"]}
        if (page, "股份总数") not in shared:
            raise ValueError(f"Double-decoder share-total page is absent: {year}")
        excerpts = [entry["excerpt"] for entry in report["pdfium_candidates"]
                    if entry["page"] == page and entry["term"] == "股份总数"]
        compact = "".join(excerpts).replace(",", "")
        if str(closing) not in compact:
            raise ValueError(f"Reported closing share count is absent: {year}")
        timeline.append({
            "report_year": year,
            "report_period_end": f"{year}-12-31",
            "available_at": publication_date_upper_bound(report["publication_date"]).isoformat(),
            "prior_annual_closing_total_shares": opening,
            "closing_reported_total_shares": closing,
            "change_implied_by_adjacent_annual_closings": closing - opening,
            "source": {
                "source_id": f"cninfo:{report['announcement_id']}",
                "source_url": report["url"],
                "source_path": report["path"],
                "source_sha256": report["sha256"],
                "physical_page": page,
                "double_decoder_candidate": True,
            },
            "scope": "reported year-end total shares in the listed-company annual report",
            "prohibited_uses": [
                "Not a daily outstanding-share series.",
                "Not proof that treasury shares equal zero or are excluded.",
                "Not an A-share-only denominator after the H-share listing.",
                "Not an execution float, liquidity measure, or trade authorization.",
            ],
        })
    for previous, current in zip(timeline, timeline[1:]):
        if previous["closing_reported_total_shares"] != current["prior_annual_closing_total_shares"]:
            raise ValueError("Annual reported share rollforward is discontinuous")
    return {
        "symbol": "000333",
        "timeline_version": "midea-annual-reported-total-shares-v1",
        "rows": timeline,
        "reconciliations": {
            "annual_opening_to_prior_closing_continuous": True,
            "all_changes_equal_closing_minus_opening": True,
            "reports": len(timeline),
        },
        "interpretation": "Annual report facts support report-period per-total-share research checks only. They do not close the point-in-time treasury/A-H/daily denominator gap.",
        "share_timeline_approved": False,
        "valuation_approved": False,
        "trade_approved": False,
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/company-research" / f"midea-annual-share-timeline-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_timeline(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "inventory_sha256": INVENTORY_SHA256,
        "evidence_sha256": digest(evidence),
    }, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "reports": len(ROWS), "share_timeline_approved": False}))


if __name__ == "__main__":
    main()
