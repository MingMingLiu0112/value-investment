#!/usr/bin/env python3
"""Build a scope-matched CNY cost-of-equity research range for the parent-equity path."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEASIBILITY = ROOT / "runtime/company-research/600519-consolidated-parent-equity-model-feasibility-20260914T104237Z/evidence.json"
FEASIBILITY_SHA256 = "fd701df519ec2bb5734e1faa9306b9914fa16f0aa5ee5fefc1b788d2019ba00f"
DISCOUNT_BASIS = ROOT / "runtime/valuation-research/moutai-discount-basis-20260909T120002401955Z/evidence.json"
DISCOUNT_BASIS_SHA256 = "6dea599866140d28b7058d60b7c9a0d235aaed1def4df902011fc46e854de709"
MARKET_BETA = ROOT / "runtime/valuation-research/moutai-market-beta-20260912T161052067136Z/evidence.json"
MARKET_BETA_SHA256 = "edb4592aa6a5d81f5f8c5e9c8c48578950d0b59f65b79f9db6f3b173546c7a3c"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Pinned input changed: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict[str, object]:
    feasibility = load(FEASIBILITY, FEASIBILITY_SHA256)
    basis = load(DISCOUNT_BASIS, DISCOUNT_BASIS_SHA256)
    beta = load(MARKET_BETA, MARKET_BETA_SHA256)
    if (feasibility.get("conclusion") != "candidate_scope_matched_but_not_admitted"
            or basis.get("approved_for_valuation") is not False
            or beta.get("company_wacc_approved") is not False):
        raise ValueError("Unexpected input approval boundary")
    estimate = beta["estimates"]["full_2015Feb_2025Dec"]
    lower, upper = map(Decimal, estimate["approximate_95pct_slope_interval_iid_assumption"])
    central = Decimal(str(estimate["equity_return_slope"]))
    risk_free_proxy = Decimal(basis["ten_year_sovereign_yield_to_maturity"])
    total_china_erp = Decimal(basis["china_total_equity_risk_premium"])
    if not (Decimal("0") < lower < central < upper and risk_free_proxy > 0 and total_china_erp > 0):
        raise ValueError("Invalid beta or premium ordering")
    cases = []
    with localcontext() as context:
        context.prec = 42
        for label, slope in (("lower_iid_slope_bound", lower), ("full_sample_slope", central),
                             ("upper_iid_slope_bound", upper)):
            cost = risk_free_proxy + slope * total_china_erp
            if cost <= risk_free_proxy:
                raise ValueError("Cost of equity did not exceed nominal rate proxy")
            cases.append({"case": label, "equity_return_slope": str(slope), "cost_of_equity_cny_nominal": str(cost)})
    return {
        "symbol": "600519",
        "contract_version": "moutai-consolidated-parent-equity-discount-range-v1",
        "model_scope": "Listed-company consolidated parent-attributable equity, matching the candidate parent-equity residual-income or dividend-capacity model.",
        "inputs": {
            "scope_assessment": {"path": str(FEASIBILITY.relative_to(ROOT)), "sha256": FEASIBILITY_SHA256},
            "risk_free_proxy": {
                "value": str(risk_free_proxy),
                "definition": "2026-09-08 CNY ten-year sovereign yield to maturity; a nominal maturity-matched proxy, not a zero-coupon risk-free rate.",
                "source": str(DISCOUNT_BASIS.relative_to(ROOT)),
            },
            "equity_risk_premium": {
                "value": str(total_china_erp),
                "definition": "Dated China total equity risk premium; it is used once and no separate country premium is added.",
                "source": str(DISCOUNT_BASIS.relative_to(ROOT)),
            },
            "beta_proxy": {
                "definition": "2015-02 to 2025-12 monthly total-return slope of the listed consolidated equity against H00300, with an IID-approximate interval.",
                "source": str(MARKET_BETA.relative_to(ROOT)),
            },
        },
        "formula": "Ke = CNY_10Y_yield_proxy + listed_equity_return_slope * China_total_equity_risk_premium",
        "cases": cases,
        "range": {
            "lower": cases[0]["cost_of_equity_cny_nominal"],
            "central": cases[1]["cost_of_equity_cny_nominal"],
            "upper": cases[2]["cost_of_equity_cny_nominal"],
        },
        "selection_status": "bounded_research_range_not_single_selected_rate",
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "limitations": [
            "The listed-equity slope is a descriptive historical co-movement measure, not an observed forward beta or a statistical confidence interval for cost of equity.",
            "The yield is a ten-year yield to maturity rather than a zero-coupon annual-effective rate; duration and compounding remain model assumptions.",
            "The premium snapshot and yield date are asynchronous and neither is issuer guidance or a guaranteed return.",
            "The range matches the consolidated parent-equity model scope better than industrial FCFF, but it does not approve forward ROE, retention, payout, or residual-income fade assumptions.",
            "The range is current-research evidence only and cannot be retroactively applied to historical daily decisions without separate point-in-time rate inputs.",
        ],
    }


def main() -> int:
    payload = build()
    output = ROOT / "runtime/valuation-research" / (
        "moutai-consolidated-parent-equity-discount-range-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "inputs": {
            str(FEASIBILITY.relative_to(ROOT)): FEASIBILITY_SHA256,
            str(DISCOUNT_BASIS.relative_to(ROOT)): DISCOUNT_BASIS_SHA256,
            str(MARKET_BETA.relative_to(ROOT)): MARKET_BETA_SHA256,
        },
        "script_sha256": digest(Path(__file__)),
        "outputs": {"evidence.json": digest(evidence)},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/valuation-research/moutai-consolidated-parent-equity-discount-range-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "range": payload["range"], "valuation_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
