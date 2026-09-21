"""Describe dated 2025 Midea share-scope observations without daily inference."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "runtime/company-research/midea-2025-share-scope-20260912T054618687004Z/evidence.json"
SCOPE_SHA256 = "9d61456fd9048d62835640c908c98fbe634ea3cad70a2be0c268958a64ab736a"
TTM = ROOT / "runtime/midea-ttm-evidence-20260908.json"
TTM_SHA256 = "59999e4d1c43b54cc0e7cddcd15e9655138f479196795f5040b5b065da078a39"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_timeline() -> dict:
    if digest(SCOPE) != SCOPE_SHA256 or digest(TTM) != TTM_SHA256:
        raise ValueError("Pinned share-scope input changed")
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    ttm = json.loads(TTM.read_text(encoding="utf-8"))
    december = ttm.get("separate_december_cancellation", {})
    required = {
        "effective_date_disclosed": "2025-12-19",
        "publication_date": "2025-12-23",
        "cancelled_a_shares": 95000000,
        "issued_a_before": 7041957278,
        "issued_a_after": 6946957278,
        "issued_h_before_and_after": 650848500,
        "issued_total_before": 7692805778,
        "issued_total_after": 7597805778,
        "class_totals_and_cancellation_reconciled": True,
    }
    if any(december.get(key) != value for key, value in required.items()):
        raise ValueError("December cancellation evidence changed")
    september_total = scope["monthly_issued_total_shares"]
    if september_total != 7682861544:
        raise ValueError("September scope evidence changed")
    if december["issued_total_before"] - september_total != 9944234:
        raise ValueError("September-to-December pre-cancellation difference changed")
    if december["issued_total_before"] - december["issued_total_after"] != december["cancelled_a_shares"]:
        raise ValueError("December cancellation arithmetic changed")
    return {
        "symbol": "000333",
        "timeline_version": "midea-2025-capital-observations-v1",
        "events": [
            {
                "observation_period_end": "2025-09-30",
                "available_at_research_bound": scope["monthly_availability_research"]["available_at_candidate"],
                "issued_total_shares": september_total,
                "treasury_total_shares": scope["monthly_treasury_total_shares"],
                "status": "month_end_observation_only",
            },
            {
                "effective_date_disclosed": december["effective_date_disclosed"],
                "available_at_research_bound": "2025-12-24T00:00:00+08:00",
                "publication_date": december["publication_date"],
                "issued_a_before": december["issued_a_before"],
                "issued_a_after": december["issued_a_after"],
                "issued_h_unchanged": december["issued_h_before_and_after"],
                "issued_total_before": december["issued_total_before"],
                "issued_total_after": december["issued_total_after"],
                "cancelled_a_shares": december["cancelled_a_shares"],
                "status": "issuer_announcement_completed_cancellation_with_unverified_intraday_publication",
            },
        ],
        "known_differences": {
            "september_to_december_pre_cancellation_issued_total_delta": 9944234,
            "december_cancelled_a_shares": 95000000,
        },
        "unknown_intervals": [
            "The cause and dates of the 9,944,234-share difference between the September month-end observation and the December pre-cancellation count are not inferred.",
            "No daily treasury-share series is known after 2025-09-30.",
            "The December announcement date is a conservative research availability bound, not verified intraday availability for a 2025-12-19 decision.",
        ],
        "share_scope_approved": False,
        "valuation_approved": False,
        "trade_approved": False,
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/company-research" / f"midea-2025-capital-timeline-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_timeline(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "share_scope_approved": False}))


if __name__ == "__main__":
    main()
