#!/usr/bin/env python3
"""Freeze the current dated 600519 P1 research-model contract without approval."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTERS = {
    "current_model": ("runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json", "evidence.json"),
    "capital_bridge": ("runtime/company-research/600519-current-capital-bridge-latest.json", "evidence.json"),
    "cost_policy": ("runtime/company-research/600519-current-cost-of-equity-policy-latest.json", "evidence.json"),
    "forward_assumptions": ("runtime/company-research/600519-current-forward-assumptions-latest.json", "evidence.json"),
}
DAILY_POLICY_POINTER = ROOT / "runtime/strategy-validation/moutai-daily-simulation-policy-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pointer(pointer_relative: str, filename: str) -> tuple[dict, dict]:
    pointer = json.loads((ROOT / pointer_relative).read_text(encoding="utf-8"))
    path = (ROOT / pointer["path"] / filename).resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != pointer["sha256"]:
        raise ValueError("Pinned evidence changed: " + pointer_relative)
    return json.loads(path.read_text(encoding="utf-8")), {"path": str(path.relative_to(ROOT)), "sha256": pointer["sha256"]}


def load_daily_simulation_policy() -> tuple[dict, dict] | None:
    """Read the separately dated policy only when its pointer and hash still match."""
    from value_investment_agent.daily_simulation_policy import IMPLEMENTED_STATUS, validate_policy

    if not DAILY_POLICY_POINTER.exists():
        return None
    pointer = json.loads(DAILY_POLICY_POINTER.read_text(encoding="utf-8"))
    path = (ROOT / pointer["path"] / "evidence.json").resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != pointer["sha256"]:
        raise ValueError("Pinned daily simulation policy changed")
    policy = validate_policy(json.loads(path.read_text(encoding="utf-8")))
    if policy["implementation_status"] != IMPLEMENTED_STATUS:
        raise ValueError("Daily simulation policy is not implemented for paper execution")
    return policy, {"path": str(path.relative_to(ROOT)), "sha256": pointer["sha256"]}


def build() -> dict:
    data, refs = {}, {}
    for name, (pointer, filename) in POINTERS.items():
        data[name], refs[name] = load_pointer(pointer, filename)
    model, capital, cost, assumptions = (data[name] for name in POINTERS)
    as_of = model.get("valuation_at", "").split("T")[0]
    if (model.get("symbol") != "600519" or model.get("valuation_approved") is not False
            or model.get("formal_fair_value") is not None or len(model.get("results", [])) != 3
            or capital.get("as_of") != as_of or capital.get("passed") is not True
            or cost.get("as_of") != as_of or cost.get("passed") is not True
            or assumptions.get("as_of") != as_of or assumptions.get("passed") is not True):
        raise ValueError("Current P1 dependency scope is incomplete")
    daily_policy = load_daily_simulation_policy()
    policy_implemented = daily_policy is not None and daily_policy[0].get("observed_session") == as_of
    return {
        "symbol": "600519", "contract_version": "moutai-p1-model-contract-v4", "as_of": as_of, "inputs": refs,
        "candidate_primary_model": {"name": "consolidated_parent_equity_residual_income_or_dividend_capacity", "model_version": model["model_version"], "research_date_only": bool(model["model_policy"].get("research_date_only")), "conclusion": "admitted_for_bounded_current_paper_research"},
        "admission_gates": [
            {"id": "parent_equity_scope", "passed": True, "reason": "Parent equity, profit and issued shares use the same listed-equity claim."},
            {"id": "model_arithmetic", "passed": all(value is True for value in model["checks"].values()), "reason": "Residual-income and dividend paths reconcile under identical registered assumptions."},
            {"id": "cost_of_equity_selection", "passed": True, "reason": "Dated base/stress policy is separately hash-bound; it is a bounded research policy."},
            {"id": "forward_assumptions", "passed": True, "reason": "Dated assumptions and counterevidence are separately hash-bound; they remain assumptions, not forecasts."},
            {"id": "current_share_capital_actions", "passed": True, "reason": "Complete official index reaches the research date with no new capital event and a dated denominator bridge."},
        ],
        "specified_simulation_eligible": False, "formal_fair_value": None, "valuation_approved": False,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "separate_execution_requirements": {
            "affects_valuation_admission": False,
            "daily_simulation_policy_implemented": policy_implemented,
            "daily_simulation_policy": daily_policy[1] if daily_policy else None,
            "requirements": "A separate dated execution contract must cover prices, status, corporate actions, fees, slippage, liquidity and account constraints before simulation fills.",
            "real_fill_verified": False,
        },
        "scope": "Current-date bounded paper research only. It is not information available at the prior market close and cannot create a safety-margin signal, paper order, simulation admission, or trading instruction.",
        "next_evidence_path": [
            "Maintain a new point-in-time capital-event bridge for every later research or market-session date.",
            "Refresh the separately dated daily execution policy and execution contract for every later session before any simulation fill.",
            "Do not convert research-date values into market-session safety margins without a date-consistent quote and model bridge.",
        ],
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/company-research" / ("600519-p1-model-contract-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_hash = digest(evidence)
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": evidence_hash}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/company-research/600519-p1-model-contract-latest.json").write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": evidence_hash}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "specified_simulation_eligible": False, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
