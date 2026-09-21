#!/usr/bin/env python3
"""Freeze the bounded paper-simulation scope for the current 600519 model."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    pointer = json.loads(MODEL_POINTER.read_text(encoding="utf-8"))
    evidence = (ROOT / pointer["path"] / "evidence.json").resolve()
    if not evidence.is_relative_to(ROOT.resolve()) or digest(evidence) != pointer["sha256"]:
        raise ValueError("Pinned current model changed")
    model = json.loads(evidence.read_text(encoding="utf-8"))
    results = model.get("results") or []
    values = [Decimal(row["conditional_value_per_current_disclosed_share_cny"]) for row in results]
    sensitivity = {row["case"]: Decimal(row["conditional_value_per_current_disclosed_share_cny"])
                   for row in model.get("sensitivity") or []}
    policy = model.get("model_policy") or {}
    if (model.get("symbol") != "600519" or model.get("review_status") != "current_model_and_sensitivity_ready_for_scope_review"
            or [row.get("scenario") for row in results] != ["bear", "base", "bull"]
            or not all(model.get("checks", {}).values()) or not values[0] < values[1] < values[2]
            or sensitivity.get("base_higher_equity_cost", values[1]) >= values[1]):
        raise ValueError("Current model does not satisfy bounded-review checks")
    source_refs = [model["policy"], *model["inputs"].values()]
    for ref in source_refs:
        path = (ROOT / ref["path"]).resolve()
        if not path.is_relative_to(ROOT.resolve()) or digest(path) != ref["sha256"]:
            raise ValueError("Bounded-review source changed")
    return {
        "symbol": "600519", "review_version": "moutai-current-equity-scope-review-v1",
        "current_model": {"path": str(evidence.relative_to(ROOT)), "sha256": pointer["sha256"]},
        "facts_and_arithmetic_passed": True,
        "assumptions": {"income_paths": policy["scenarios"], "payout_ratio": policy["payout_ratio"],
                        "forecast_years": policy["forecast_years"], "fade_years": policy["fade_years"],
                        "terminal_roe_policy": policy["terminal_roe_policy"]},
        "counterevidence": ["FY2025 and H1 2026 parent profit declined; the model does not assume recovery in base.",
                              "75% payout is a research assumption, not issuer guidance.",
                              "Peer cash-flow and sales-expense evidence rejects automatic industry recovery."],
        "decision": "admitted_for_bounded_same_date_paper_research_only",
        "constraints": ["Quote session date must equal the model valuation date and capital-event coverage date.",
                        "A refreshed policy, facts and review are required for every later quote date.",
                        "Only a segregated virtual account may consume this model; next-session execution evidence remains separate.",
                        "This is not a formal fair value, price target, historical strategy result, live-trading approval or investment recommendation."],
        "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False,
        "trade_approved": False, "live_eligible": False,
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/company-research" / ("600519-current-equity-scope-review-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/company-research/600519-current-equity-scope-review-latest.json").write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "decision": result["decision"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
