#!/usr/bin/env python3
"""Freeze the first-company P1 model choice without promoting research to value."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED = {
    "integrated_equity": (
        "runtime/company-research/600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json",
        "67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc",
    ),
    "discount_basis": (
        "runtime/valuation-research/moutai-discount-basis-20260909T120002401955Z/evidence.json",
        "6dea599866140d28b7058d60b7c9a0d235aaed1def4df902011fc46e854de709",
    ),
    "market_beta": (
        "runtime/valuation-research/moutai-market-beta-20260912T161052067136Z/evidence.json",
        "edb4592aa6a5d81f5f8c5e9c8c48578950d0b59f65b79f9db6f3b173546c7a3c",
    ),
}
POINTERS = {
    "operating_finance_scope": ("runtime/company-research/600519-operating-finance-scope-audit-latest.json", "evidence.json"),
    "cash_anchor_range": ("runtime/strategy-validation/moutai-historical-cash-anchor-equity-range-latest.json", "summary.json"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pointer(pointer_relative: str, output_name: str) -> tuple[dict, dict]:
    pointer_path = ROOT / pointer_relative
    reference = json.loads(pointer_path.read_text(encoding="utf-8"))
    directory = (ROOT / reference["path"]).resolve()
    path = directory / output_name
    expected = reference.get("sha256") or reference.get(f"{output_name.removesuffix('.json').replace('-', '_')}_sha256")
    if not directory.is_relative_to(ROOT.resolve()) or not expected or digest(path) != expected:
        raise ValueError(f"Pinned pointer changed: {pointer_relative}")
    return json.loads(path.read_text(encoding="utf-8")), {"path": str(path.relative_to(ROOT)), "sha256": expected}


def build() -> dict:
    data, refs = {}, {}
    for name, (relative, expected) in FIXED.items():
        path = ROOT / relative
        if digest(path) != expected:
            raise ValueError(f"Pinned input changed: {name}")
        data[name] = json.loads(path.read_text(encoding="utf-8"))
        refs[name] = {"path": relative, "sha256": expected}
    for name, (pointer, output_name) in POINTERS.items():
        data[name], refs[name] = load_pointer(pointer, output_name)
    scope = data["operating_finance_scope"]
    cash = data["cash_anchor_range"]
    beta = data["market_beta"]
    if (scope.get("approved") is not False or cash.get("valuation_approved") is not False
            or cash.get("simulation_eligible") is not False or beta.get("company_wacc_approved") is not False):
        raise ValueError("Unexpected approval in P1 input")
    sensitivity = scope["shared_cost_sensitivity"]
    if sensitivity["crossing_30pct_entry_cases"] != 72 or sensitivity["total_cases"] != 648:
        raise ValueError("Unexpected scope materiality coverage")
    return {
        "symbol": "600519",
        "contract_version": "moutai-p1-model-contract-v1",
        "inputs": refs,
        "candidate_primary_model": {
            "name": "industrial_operating_fcff_dcf_with_explicit_equity_bridge",
            "economic_scope": "Candidate industrial operating cash flows plus an explicit bridge for retained assets and minority claims.",
            "facts": [
                "The integrated conditional equity grid is reproducible from pinned issuer-derived research inputs.",
                "Explicit finance interest, commission and finance-expense rows are excluded from the operating-profit proxy.",
            ],
            "assumptions": [
                "The 6/8/10 percent grid is an experiment, not an approved industrial WACC.",
                "Cash, tax, minority and retained-book treatments remain stated research approximations.",
            ],
            "gap_impact": "Shared operating/finance boundaries are material: 72/648 cost-removal sensitivity cases cross the frozen 30 percent entry experiment.",
            "conclusion": "not_admitted_for_specified_simulation",
        },
        "necessary_cross_check": {
            "name": "cash_distribution_anchored_equity_range",
            "economic_scope": "Whole-company per-share research range using only implemented annual-cycle cash distributions available by each decision date.",
            "facts": ["Implemented cash entitlements and then-available annual per-share profit are point-in-time bound."],
            "assumptions": ["Past cash-to-EPS ratios persist.", "Required-return and terminal-growth scenarios are research assumptions."],
            "gap_impact": "It avoids an internal industrial/finance allocation but cannot validate its own payout, return or growth forecast.",
            "conclusion": "research_only_cross_check_not_formal_value",
        },
        "discount_rate_evidence": {
            "observed_market_beta_role": "descriptive listed-equity co-movement only; it includes cash, leverage and financial-subsidiary exposure.",
            "company_operating_wacc": None,
            "conclusion": "No matched CNY operating discount-rate method is admitted.",
        },
        "specified_simulation_eligible": False,
        "formal_fair_value": None,
        "trade_approved": False,
        "allowed_now": [
            "current research observation with no order",
            "synthetic state, sizing and virtual-account mechanics tests",
            "research-only historical counterevidence",
        ],
        "next_evidence_path": [
            "Freeze a bounded, auditable treatment for industrial/finance shared scope and rerun the primary model.",
            "Calibrate a matched CNY operating discount-rate method after scope is frozen.",
            "Reassess whether the primary model, rather than the cross-check, can drive the specified simulation.",
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


if __name__ == "__main__":
    main()
