#!/usr/bin/env python3
"""Freeze the scope-matched 600519 parent-equity P1 candidate without admission."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "parent_equity_facts": ("runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T104011Z/evidence.json", "3ba2b4caa8584100fc41c2ec76ad04794a49dde215cc334abe5a879275dba728"),
    "model_feasibility": ("runtime/company-research/600519-consolidated-parent-equity-model-feasibility-20260914T104237Z/evidence.json", "fd701df519ec2bb5734e1faa9306b9914fa16f0aa5ee5fefc1b788d2019ba00f"),
    "discount_range": ("runtime/valuation-research/moutai-consolidated-parent-equity-discount-range-20260914T104355Z/evidence.json", "d53f204548a2a97c83c046572b93e331af3963e53773f0b3f8d4962a819dd154"),
    "conditional_model": ("runtime/company-research/600519-consolidated-parent-equity-residual-income-20260914T104426Z/evidence.json", "284eb3bc348bd6c931e043fed1f06304449d32decdb114761b2a6c6dab358d26"),
    "assumption_review": ("runtime/company-research/600519-consolidated-parent-equity-assumption-review-20260914T104502Z/evidence.json", "be65d9fba01435110f9ec6d402a48966c2a8650041722e4838f50246fd4b033e"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    data, refs = {}, {}
    for name, (relative, expected) in INPUTS.items():
        path = ROOT / relative
        if digest(path) != expected:
            raise ValueError(f"Pinned input changed: {name}")
        data[name] = json.loads(path.read_text(encoding="utf-8"))
        refs[name] = {"path": relative, "sha256": expected}
    facts, feasibility, discount, model, review = (data[key] for key in INPUTS)
    def same_reference(actual: dict | None, expected: dict) -> bool:
        return (isinstance(actual, dict) and actual.get("sha256") == expected["sha256"]
                and Path(actual.get("path", "")) == Path(expected["path"]))

    dependencies = [(feasibility.get("input"), refs["parent_equity_facts"]),
                    (discount.get("inputs", {}).get("scope_assessment"), refs["model_feasibility"]),
                    (model.get("inputs", {}).get("facts"), refs["parent_equity_facts"]),
                    (model.get("inputs", {}).get("discount"), refs["discount_range"]),
                    (review.get("inputs", {}).get("facts"), refs["parent_equity_facts"]),
                    (review.get("inputs", {}).get("model"), refs["conditional_model"])]
    if (facts.get("contract_version") != "moutai-consolidated-parent-equity-inputs-v2"
            or any(not same_reference(actual, expected) for actual, expected in dependencies)):
        raise ValueError("P1 inputs do not share the corrected fact/model dependency chain")
    if (facts.get("valuation_approved") is not False
            or feasibility.get("conclusion") != "candidate_scope_matched_but_not_admitted"
            or discount.get("selection_status") != "bounded_research_range_not_single_selected_rate"
            or model.get("formal_fair_value") is not None
            or model.get("model_version") != "moutai-consolidated-parent-equity-residual-income-v2"
            or len(model.get("results", [])) != 3
            or any(abs(Decimal(row["dividend_crosscheck_difference_cny"])) >= Decimal("0.01")
                   for row in model["results"])
            or review.get("conclusion") != "historical_anchor_consistent_but_forecast_assumptions_not_independently_validated"):
        raise ValueError("Unexpected P1 candidate approval state")
    return {
        "symbol": "600519",
        "contract_version": "moutai-p1-model-contract-v3",
        "supersedes_contract_version": "moutai-p1-model-contract-v2",
        "evidence_revision": "publication-and-share-provenance-correction-v1",
        "inputs": refs,
        "candidate_primary_model": {
            "name": "consolidated_parent_equity_residual_income_or_dividend_capacity",
            "economic_scope": "Listed-company parent-attributable consolidated equity, parent-attributable profit, and issued shares.",
            "scope_match": "Starting equity, profit and denominator describe the same parent-attributable listed equity claim.",
            "conditional_value_status": model["model_scope"],
            "model_version": model["model_version"],
            "conclusion": "not_admitted_for_specified_simulation",
        },
        "legacy_research_path": {
            "name": "industrial_operating_fcff_dcf_with_explicit_equity_bridge",
            "role": "preserved_non_primary_research_path",
            "reason_not_primary": "Its operating/financial scope and enterprise-to-equity bridge remain unresolved; this contract neither repairs nor approves it.",
        },
        "necessary_cross_check": {
            "name": "cash_distribution_anchored_equity_range",
            "role": "research_only_cross_check",
            "conclusion": "research_only_cross_check_not_formal_value",
        },
        "admission_gates": [
            {"id": "parent_equity_scope", "passed": True, "reason": "The annual index establishes April 17 publication and April 18 date-only availability. Parent equity/profit and directly disclosed issued shares match the reported listed-equity scope; the complete active model chain uses the corrected facts."},
            {"id": "model_arithmetic", "passed": True, "reason": "Corrected terminal opening-equity timing reconciles with independent dividend discounting under identical clean-surplus assumptions; economic and actual accounting applicability remain separate."},
            {"id": "cost_of_equity_selection", "passed": False, "reason": "Freeze the dated base/stress selection policy for the intended valuation date. Existing mixed-date research inputs do not yet establish that applicability; a uniquely true rate is not required."},
            {"id": "forward_assumptions", "passed": False, "reason": "Support beginning-equity ROE, payout/capital requirements, fade and actual clean-surplus adjustments with relevant facts and counterevidence. The updated historical-plausibility review uses the corrected model but does not independently validate forward economic assumptions."},
            {"id": "current_share_capital_actions", "passed": False, "reason": "The model uses 2025 reporting-date shares and has no post-report current share/capital-action bridge."},
        ],
        "separate_execution_requirements": {
            "affects_valuation_admission": False,
            "daily_simulation_policy_implemented": False,
            "requirements": "Versioned daily execution with point-in-time prices/status/actions, dated fees, adverse slippage, order limits, prior-session liquidity and account constraints. Ordinary daily simulations do not require historical queue proof.",
            "real_fill_verified": False,
        },
        "specified_simulation_eligible": False,
        "formal_fair_value": None,
        "trade_approved": False,
        "allowed_now": ["research observation with no order", "synthetic mechanics tests", "research-only counterevidence"],
        "next_evidence_path": [
            "Support and freeze forward assumptions, beginning-equity ROE and clean-surplus applicability; do not require proof of future outcomes.",
            "Freeze dated base/stress equity-cost policies separately for current/forward and historical use.",
            "Bridge dividends, repurchases, current ordinary shares and latest financial facts before a current per-share value.",
            "Implement and test the separate conservative daily-execution policy before simulation fills; this is not a valuation dependency.",
        ],
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/company-research" / ("600519-p1-model-contract-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence), "inputs": result["inputs"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/company-research/600519-p1-model-contract-latest.json").write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "specified_simulation_eligible": False, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
