"""Join Midea's annual total-share and A/H monthly-share evidence conservatively."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANNUAL = ROOT / "runtime/company-research/midea-annual-share-timeline-20260912T054403745196Z/evidence.json"
ANNUAL_SHA256 = "f5687f0798cdd5898cc166d9a7831adb77e8ed68e619c9effe57c737d5815229"
MONTHLY = ROOT / "runtime/midea-monthly-share-reconciliation-20260908.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reconciliation() -> dict:
    if digest(ANNUAL) != ANNUAL_SHA256:
        raise ValueError("Annual share-timeline evidence changed")
    annual = json.loads(ANNUAL.read_text(encoding="utf-8"))
    monthly = json.loads(MONTHLY.read_text(encoding="utf-8"))
    if (annual.get("symbol") != "000333" or len(annual.get("rows", [])) != 11
            or annual.get("share_timeline_approved") is not False):
        raise ValueError("Annual share-timeline scope changed")
    if (monthly.get("symbol") != "000333" or monthly.get("period") != "2025-09-30"
            or monthly.get("issued_total") != 7682861544 or monthly.get("treasury_total") != 98588844
            or monthly.get("issued_excluding_treasury_total") != 7584272700
            or monthly.get("two_decoders_agree") is not True
            or monthly.get("availability_research", {}).get("availability_bound_verified") is not False):
        raise ValueError("Monthly A/H share scope changed")
    annual_end = annual["rows"][-1]["closing_reported_total_shares"]
    monthly_total = monthly["issued_total"]
    if annual_end != 7655955883 or monthly_total - annual_end != 26905661:
        raise ValueError("Unexpected annual-to-monthly issued-share change")
    share_classes = monthly["share_classes"]
    if (share_classes["A"]["issued_total"] + share_classes["H"]["issued_total"] != monthly_total
            or share_classes["A"]["treasury"] + share_classes["H"]["treasury"] != monthly["treasury_total"]):
        raise ValueError("A/H monthly subtotals do not reconcile")
    return {
        "symbol": "000333",
        "annual_period_end": "2024-12-31",
        "annual_reported_total_shares": annual_end,
        "monthly_period_end": "2025-09-30",
        "monthly_issued_total_shares": monthly_total,
        "monthly_treasury_total_shares": monthly["treasury_total"],
        "monthly_issued_excluding_treasury_total_shares": monthly["issued_excluding_treasury_total"],
        "annual_to_monthly_issued_total_delta": monthly_total - annual_end,
        "monthly_availability_research": monthly["availability_research"],
        "a_h_subtotals": monthly["share_classes"],
        "source_bindings": {
            "annual_share_timeline": {"path": str(ANNUAL.relative_to(ROOT)), "sha256": ANNUAL_SHA256},
            "monthly_share_reconciliation": {"path": str(MONTHLY.relative_to(ROOT)), "sha256": digest(MONTHLY)},
        },
        "conclusion": "The two dated total-share observations reconcile internally but do not establish the cause, effective date, or daily path of the 26,905,661-share increase.",
        "blocked_uses": [
            "Do not forward-fill the September A/H treasury balance to earlier or later dates.",
            "Do not use the month-end total as a period-weighted EPS denominator.",
            "Do not infer a daily issuance, repurchase, cancellation, or tradable float from the annual-to-monthly difference.",
            "Do not use this research-availability bound as a verified intraday publication time.",
        ],
        "share_scope_approved": False,
        "valuation_approved": False,
        "trade_approved": False,
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/company-research" / f"midea-2025-share-scope-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_reconciliation(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "share_scope_approved": False}))


if __name__ == "__main__":
    main()
