#!/usr/bin/env python3
"""Bind a dated quote observation to the existing conditional Moutai values.

The result is a research observation only.  An unverified trading calendar or
an unapproved conditional valuation can never create an order from this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P1_MODEL_POINTER = ROOT / "runtime/company-research/600519-p1-model-contract-latest.json"
FINANCE_COST_SENSITIVITY_POINTER = ROOT / "runtime/company-research/600519-finance-cost-sensitivity-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_primary_model() -> tuple[dict, dict]:
    pointer = json.loads(P1_MODEL_POINTER.read_text(encoding="utf-8"))
    contract_path = (ROOT / pointer["path"] / "evidence.json").resolve()
    if not contract_path.is_relative_to(ROOT.resolve()) or digest(contract_path) != pointer["sha256"]:
        raise ValueError("Pinned P1 contract changed")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_version = contract.get("contract_version")
    if contract_version in {"moutai-p1-model-contract-v3", "moutai-p1-model-contract-v4"}:
        reference_name = "current_model"
        value_field = "conditional_value_per_current_disclosed_share_cny"
    else:
        reference_name = "conditional_model"
        value_field = "conditional_value_per_2025_issued_share_cny"
    reference = contract.get("inputs", {}).get(reference_name)
    if not isinstance(reference, dict):
        raise ValueError(f"P1 contract lacks {reference_name!r} input")
    path = (ROOT / reference["path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned primary model changed")
    model = json.loads(path.read_text(encoding="utf-8"))
    if (contract.get("symbol") != "600519" or model.get("symbol") != "600519"
            or contract.get("specified_simulation_eligible") is not False
            or model.get("valuation_approved") is not False):
        raise ValueError("Primary model is outside this unapproved research-observation path")
    return model, {
        "p1": {"path": str(contract_path.relative_to(ROOT)), "sha256": pointer["sha256"]},
        "model": {"path": str(path.relative_to(ROOT)), "sha256": reference["sha256"]},
        "contract_version": contract_version,
        "value_field": value_field,
        "observation_code_sha256": digest(Path(__file__)),
    }


def load_finance_cost_sensitivity() -> dict:
    reference = json.loads(FINANCE_COST_SENSITIVITY_POINTER.read_text(encoding="utf-8"))
    path = (ROOT / reference["path"] / "evidence.json").resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != reference["sha256"]:
        raise ValueError("Pinned finance-cost sensitivity changed")
    sensitivity = json.loads(path.read_text(encoding="utf-8"))
    if (sensitivity.get("symbol") != "600519" or sensitivity.get("robust_no_entry_under_this_sensitivity") is not True
            or len(sensitivity.get("results") or []) != 1296
            or any(sensitivity.get(key) is not False for key in ("scope_approved", "valuation_approved",
                                                                 "simulation_eligible", "trade_approved", "live_eligible"))):
        raise ValueError("Unexpected finance-cost sensitivity scope")
    results = sensitivity["results"]
    highest = max(results, key=lambda row: Decimal(row["adjusted_conditional_value_per_share_cny"]))
    if any(Decimal(row["safety_margin"]) >= Decimal("0.30") for row in results):
        raise ValueError("Finance-cost sensitivity conflicts with its no-entry conclusion")
    return {"path": str(path.relative_to(ROOT)), "sha256": reference["sha256"],
            "robust_no_entry_under_this_sensitivity": True,
            "registered_case_count": len(results),
            "highest_conditional_value_per_share_cny": highest["adjusted_conditional_value_per_share_cny"],
            "highest_value_scenario": highest["scenario"],
            "highest_value_discount_rate": highest["discount_rate"]}


def build(quote_report: Path) -> dict:
    valuation, dependencies = load_primary_model()
    report = json.loads(quote_report.read_text(encoding="utf-8"))
    rows = [row for row in report.get("observations", []) if row.get("symbol") == "600519"]
    if len(rows) != 1 or rows[0].get("observed_price") is None:
        raise ValueError("Quote report requires exactly one observed 600519 price")
    quote = rows[0]
    quote_check = quote.get("result") or {}
    provider_times = quote_check.get("provider_times")
    if (not isinstance(provider_times, dict) or set(provider_times) != {"tencent", "sina"}
            or any(not isinstance(value, str) or not value for value in provider_times.values())):
        raise ValueError("Quote report requires both provider trade timestamps")
    price = Decimal(quote["observed_price"])
    if not price.is_finite() or price <= 0 or valuation.get("valuation_approved") is not False:
        raise ValueError("Unexpected quote or valuation approval scope")
    observed_at = max(provider_times.values())
    observed_date = datetime.fromisoformat(observed_at).date()
    model_date = datetime.fromisoformat(valuation["valuation_at"]).date()
    same_date_required = dependencies["contract_version"] == "moutai-p1-model-contract-v4"
    date_compatible = not same_date_required or observed_date == model_date
    scenarios = []
    if date_compatible:
        for row in valuation["results"]:
            value = Decimal(row[dependencies["value_field"]])
            if not value.is_finite() or value <= 0:
                raise ValueError("Conditional value must be positive")
            margin = (value - price) / value
            scenarios.append({"scenario": row["scenario"], "conditional_value_per_share_cny": str(value),
                              "observed_price_cny": str(price), "safety_margin": str(margin),
                              "meets_30pct_entry_experiment": margin >= Decimal("0.30")})
        if [row["scenario"] for row in scenarios] != ["bear", "base", "bull"]:
            raise ValueError("Unexpected primary-model scenarios")
    quote_verified = quote_check.get("passed") is True
    reason_codes = ["valuation_not_approved"]
    if not date_compatible:
        reason_codes.append("current_model_not_same_date_as_quote_session")
    elif dependencies["contract_version"] != "moutai-p1-model-contract-v4":
        reason_codes.append("reporting_date_value_not_current_bridged_value")
    if scenarios and all(price > Decimal(row["conditional_value_per_share_cny"]) for row in scenarios):
        reason_codes.append("price_above_all_conditional_values")
    if scenarios and not any(row["meets_30pct_entry_experiment"] for row in scenarios):
        reason_codes.append("no_30pct_entry_in_primary_research_scenarios")
    if not quote_verified:
        reason_codes.append("quote_session_not_verified")
    quote_interpretation = ("The dated two-source close is session-verified. " if quote_verified
                            else "The dated quote does not yet have a verified trading-session check. ")
    return {
        "symbol": "600519", "as_of": observed_at,
        "research_generated_at": datetime.now(timezone.utc).isoformat(),
        "observation_version": "moutai-primary-conditional-observation-v2",
        "dependencies": dependencies,
        "model_version": valuation["model_version"],
        "model_scope": valuation["model_scope"],
        "conditional_valuation_path": dependencies["model"]["path"],
        "conditional_valuation_sha256": dependencies["model"]["sha256"],
        "quote_report_path": str(quote_report.relative_to(ROOT)), "quote_report_sha256": digest(quote_report),
        "quote_session_status": quote_check.get("status"), "quote_session_verified": quote_verified,
        "provider_trade_times": provider_times,
        "scenarios": scenarios,
        "research_state": "watch", "action": "no_order",
        "reason_codes": reason_codes,
        "formal_fair_value": None, "valuation_approved": False,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "interpretation": (
            quote_interpretation
            + ("The current P1 model is only usable with a same-date quote session; this older quote is retained as an observation without a value comparison. "
               if not date_compatible else
               "Scenario differences use the P1-bound primary model on its registered scope. ")
            + "A scenario crossing a price threshold cannot admit an order while the model and current capital bridge remain unapproved."),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    quote_report = args.quote_report.resolve()
    if not quote_report.is_relative_to(ROOT.resolve()):
        raise ValueError("Quote report must remain under the project root")
    result = build(quote_report)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/company-research" / f"600519-current-conditional-observation-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-current-conditional-observation-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
