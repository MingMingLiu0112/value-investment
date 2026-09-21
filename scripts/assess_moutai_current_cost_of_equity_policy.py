#!/usr/bin/env python3
"""Assess the dated cost-of-equity selection policy for current 600519 research."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"
SERIALIZATION_TOLERANCE = Decimal("1e-24")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_json(reference: dict) -> tuple[dict, dict]:
    path = (ROOT / reference["path"]).resolve()
    if path.is_dir():
        path = path / "evidence.json"
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned evidence changed")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.relative_to(ROOT)), "sha256": reference["sha256"],
    }


def build() -> dict:
    pointer = json.loads(MODEL_POINTER.read_text(encoding="utf-8"))
    model, model_ref = pinned_json(pointer)
    policy, policy_ref = pinned_json(model["policy"])
    discount_ref = policy["sources"]["discount"]
    discount, discount_ref = pinned_json(discount_ref)
    valuation_at = datetime.fromisoformat(model["valuation_at"])
    registered_at = datetime.fromisoformat(policy["registered_at"])
    if (model.get("symbol") != "600519" or policy.get("symbol") != "600519"
            or policy.get("use_scope") != "Current-date forward paper research; not a historical policy or live-account approval."
            or not registered_at < valuation_at
            or policy.get("event_coverage_date") != valuation_at.date().isoformat()
            or discount.get("selection_status") != "bounded_research_range_not_single_selected_rate"):
        raise ValueError("Unexpected policy date or scope")
    ranges = {name: Decimal(value) for name, value in discount["range"].items()}
    if not Decimal("0") < ranges["lower"] < ranges["central"] < ranges["upper"]:
        raise ValueError("Cost-of-equity range is unordered")
    expected_cases = {"bear": "upper", "base": "central", "bull": "lower"}
    if {name: row.get("discount_case") for name, row in policy["scenarios"].items()} != expected_cases:
        raise ValueError("Scenario policy does not map bear/base/bull to the registered range")
    model_cases = {row["scenario"]: Decimal(row["cost_of_equity_cny_nominal"]) for row in model["results"]}
    differences = {name: abs(model_cases[name] - ranges[case]) for name, case in expected_cases.items()}
    if any(value > SERIALIZATION_TOLERANCE for value in differences.values()):
        raise ValueError("Current model does not consume the registered cost policy")
    higher = next(row for row in model["sensitivity"] if row["case"] == "base_higher_equity_cost")
    if Decimal(higher["cost_of_equity_cny_nominal"]) != ranges["central"] + Decimal("0.02"):
        raise ValueError("Higher-cost sensitivity differs from registered policy")
    return {
        "symbol": "600519",
        "assessment_version": "moutai-current-cost-of-equity-policy-v1",
        "as_of": valuation_at.date().isoformat(),
        "assessment_scope": "dated base/stress selection policy for current conditional research only",
        "passed": True,
        "selection": {
            "formula": discount["formula"],
            "lower": str(ranges["lower"]), "central": str(ranges["central"]), "upper": str(ranges["upper"]),
            "scenario_mapping": expected_cases,
            "additional_base_stress": "+200bp",
            "model_serialization_max_difference": str(max(differences.values())),
            "model_serialization_tolerance": str(SERIALIZATION_TOLERANCE),
        },
        "evidence": {"current_model": model_ref, "policy": policy_ref, "discount_range": discount_ref},
        "limitations": [
            "The selected range is an auditable research policy, not a uniquely true or forward-observed cost of equity.",
            "The sovereign-yield, premium and historical slope inputs have the date and measurement limitations recorded in the pinned discount range.",
            "This selection does not validate forward earnings, payout, terminal growth, franchise duration or a fair value.",
            "A later valuation date requires a refreshed policy and evidence review.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/company-research" / (
        "600519-current-cost-of-equity-policy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-current-cost-of-equity-policy-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": True, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
