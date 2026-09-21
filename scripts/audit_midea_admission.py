"""Create the single visible no-trade admission state for Midea research."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINANCE = ROOT / "runtime/company-research/midea-financial-scope-audit-20260912T054916602476Z/evidence.json"
FINANCE_SHA256 = "88422b693a24410a87a6fcb186a9abb967e18284b83a908846fd92ccab25c0a4"
CAPITAL = ROOT / "runtime/company-research/midea-2025-capital-timeline-20260912T055432312180Z/evidence.json"
CAPITAL_SHA256 = "0707a57140673c00ff060b0866dad9bfc142cd197f933d2919ee9785e3ba350e"
EXECUTION = ROOT / "runtime/strategy-validation/midea-real-execution-contract-20260912T000053Z/summary.json"
EXECUTION_SHA256 = "6da9c7285e042b48b62f5dc76644b857f0e7ea0b4d78d04678d86bf1eb606afa"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit() -> dict:
    if digest(FINANCE) != FINANCE_SHA256 or digest(CAPITAL) != CAPITAL_SHA256:
        raise ValueError("Midea financial or capital evidence changed")
    finance = json.loads(FINANCE.read_text(encoding="utf-8"))
    capital = json.loads(CAPITAL.read_text(encoding="utf-8"))
    if digest(EXECUTION) != EXECUTION_SHA256:
        raise ValueError("Midea execution-contract summary changed")
    execution = json.loads(EXECUTION.read_text(encoding="utf-8"))
    if (finance.get("symbol") != "000333" or finance.get("research_ttm_parent_attributable_net_income_cny") != 44721506000
            or finance.get("eps_cny") is not None or finance.get("financial_scope_approved") is not False):
        raise ValueError("Midea financial-scope audit changed")
    if (capital.get("symbol") != "000333" or capital.get("share_scope_approved") is not False
            or capital["events"][1].get("cancelled_a_shares") != 95000000):
        raise ValueError("Midea capital timeline changed")
    if (execution.get("symbol") != "000333" or execution.get("sessions") != 2621
            or execution.get("full_day_suspensions") != 5 or execution.get("partial_session_days_blocked") != 1
            or execution.get("valuation_approved") is not False):
        raise ValueError("Midea execution scope changed")
    gates = [
        {"id": "financial_scope", "passed": False, "reason": "TTM profit is reconciled but weighted ordinary shares and source independence are unresolved."},
        {"id": "per_share_scope", "passed": False, "reason": "Annual, monthly and December share observations do not form an approved weighted/daily A-H treasury denominator."},
        {"id": "execution_input", "passed": True, "reason": "2,621 archived daily bars and five full-day suspension constraints are available; one partial-session bar remains blocked."},
        {"id": "formal_valuation", "passed": False, "reason": "No admitted fair value, safety margin or order-bearing model exists."},
    ]
    return {
        "symbol": "000333", "research_state": "watch", "action": "no_order",
        "gates": gates, "blocking_gate_ids": [row["id"] for row in gates if not row["passed"]],
        "facts": {"research_ttm_parent_attributable_net_income_cny": 44721506000,
                  "execution_sessions": 2621, "full_day_suspensions": 5,
                  "partial_session_days_blocked": 1},
        "evidence": {"financial_scope": str(FINANCE.relative_to(ROOT)),
                     "capital_timeline": str(CAPITAL.relative_to(ROOT)),
                     "execution_contract": str(EXECUTION.relative_to(ROOT))},
        "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False,
        "trade_approved": False, "live_eligible": False,
        "interpretation": "Research tracking is allowed. Per-share valuation, simulated orders and live orders remain blocked; this is not an investment recommendation.",
    }


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime/company-research" / f"midea-admission-audit-{stamp}"
    output.mkdir(exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build_audit(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, indent=2), encoding="utf-8")
    (ROOT / "runtime/company-research/midea-admission-audit-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output": str(output), "research_state": "watch", "trade_approved": False}))


if __name__ == "__main__":
    main()
