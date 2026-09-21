"""Separate Midea's reconciled TTM profit from unresolved per-share scope."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TTM = ROOT / "runtime/midea-ttm-evidence-20260908.json"
TTM_SHA256 = "59999e4d1c43b54cc0e7cddcd15e9655138f479196795f5040b5b065da078a39"
SHARES = ROOT / "runtime/company-research/midea-2025-share-scope-20260912T054618687004Z/evidence.json"
SHARES_SHA256 = "9d61456fd9048d62835640c908c98fbe634ea3cad70a2be0c268958a64ab736a"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit() -> dict:
    if digest(TTM) != TTM_SHA256 or digest(SHARES) != SHARES_SHA256:
        raise ValueError("Pinned Midea research input changed")
    ttm = json.loads(TTM.read_text(encoding="utf-8"))
    shares = json.loads(SHARES.read_text(encoding="utf-8"))
    if (ttm.get("symbol") != "000333" or ttm.get("period_end") != "2025-09-30"
            or ttm.get("metric") != "parent_attributable_net_income"
            or ttm.get("unit") != "CNY thousand" or ttm.get("research_ttm_profit") != "44721506"
            or ttm.get("q4_2024_reconciled") != "6838123"
            or ttm.get("financial_facts_verified") is not False):
        raise ValueError("TTM evidence scope changed")
    if (shares.get("symbol") != "000333" or shares.get("monthly_period_end") != "2025-09-30"
            or shares.get("share_scope_approved") is not False):
        raise ValueError("Share-scope evidence changed")
    ttm_cny = int(ttm["research_ttm_profit"]) * 1000
    blockers = [
        "weighted_average_ordinary_shares_not_verified",
        "A_H_and_treasury_denominator_scope_not_approved",
        "monthly_share_availability_is_research_bound_only",
        "financial_fact_sources_not_independently_verified",
    ]
    return {
        "symbol": "000333",
        "reporting_basis": "China enterprise accounting standards",
        "as_of_period": "2025-09-30",
        "research_ttm_parent_attributable_net_income_cny": ttm_cny,
        "ttm_profit_status": "reconciled_research_fact_not_independently_financial_verified",
        "eps_cny": None,
        "per_share_value_cny": None,
        "inputs": {
            "ttm_evidence": {"path": str(TTM.relative_to(ROOT)), "sha256": TTM_SHA256},
            "share_scope_evidence": {"path": str(SHARES.relative_to(ROOT)), "sha256": SHARES_SHA256},
        },
        "per_share_blockers": blockers,
        "allowed_research_uses": [
            "Trend and scale analysis of reconciled parent-attributable TTM profit.",
            "Comparison to a later per-share model only after all listed blockers are independently closed.",
        ],
        "prohibited_uses": [
            "Do not divide TTM profit by annual issued shares, month-end shares, or outstanding shares to manufacture EPS.",
            "Do not convert TTM profit directly into a fair value, safety margin, buy signal, position size, or order.",
            "Do not treat issuer-origin TTM and share disclosures as independent sources.",
        ],
        "financial_scope_approved": False,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/company-research" / f"midea-financial-scope-audit-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_audit(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "financial_scope_approved": False}))


if __name__ == "__main__":
    main()
