"""Classify the Midea finance-company scope as an explicit materiality issue.

The retained issuer-linked size observation is quantified, but this package
only judges whether the unresolved financial-business scope is LOW/MEDIUM/HIGH/
UNKNOWN. Materiality is one applicability input and cannot unlock FCFF.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.materiality import (
    MATERIALITY_LOW,
    TREATMENT_MODEL_AS_RANGE,
    ScopeMaterialityAssessment,
    materiality_applicability_effect,
)


ROOT = Path(__file__).resolve().parents[1]
FINANCE_POINTER = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"
APPLICABILITY_POINTER = ROOT / "runtime/company-research/midea-valuation-applicability-latest.json"
OUT = ROOT / "runtime/company-research/midea-finance-materiality-20260922"
POINTER = ROOT / "runtime/company-research/000333-finance-materiality-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned_pointer(pointer: Path, filename: str = "evidence.json") -> tuple[dict, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / filename).resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Pinned path escapes project root: {pointer.name}")
    if digest(target) != pin["sha256"]:
        raise ValueError(f"Pinned evidence changed: {pointer.name}")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"]


def build() -> dict:
    finance, finance_sha256 = load_pinned_pointer(FINANCE_POINTER)
    applicability, applicability_sha256 = load_pinned_pointer(APPLICABILITY_POINTER)
    if (
        finance.get("symbol") != "000333"
        or finance.get("status") != "OBSERVATION_NOT_MODEL_INPUT"
        or finance.get("valuation_status") != "VALUATION_NOT_READY"
    ):
        raise ValueError("Midea finance-company observation changed its fail-closed contract")
    if applicability.get("scope_assessment", {}).get("industrial_fcff_carve_out") != "MODEL_NOT_APPLICABLE":
        raise ValueError("Midea applicability evidence changed its model status")

    scale = finance["derived_scale_candidates"]
    profit_ratio = Decimal(scale["audited_net_profit_to_midea_consolidated_attributable_ordinary_net_profit"])
    equity_ratio = Decimal(scale["audited_net_assets_to_midea_consolidated_attributable_ordinary_equity"])
    assessment = ScopeMaterialityAssessment(
        symbol="000333",
        issue_id="finance_business_carve_out",
        metric="finance_company_share_of_consolidated_attributable_equity_and_profit",
        estimated_exposure_ratio=profit_ratio,
        downside_impact=-equity_ratio,
        upside_impact=equity_ratio,
        materiality=MATERIALITY_LOW,
        treatment=TREATMENT_MODEL_AS_RANGE,
        rationale=(
            "The audited 2025 finance-company profit is about 0.93 percent of Midea "
            "attributable ordinary profit and its net assets are about 3.52 percent of "
            "attributable ordinary equity. A full inclusion/exclusion bound is below "
            "five percent, but the absence of standalone statements means the item "
            "must be modelled as a bounded range, not ignored."
        ),
        evidence_refs=[
            {
                "id": "midea_finance_company_size_observation",
                "path": str((ROOT / json.loads(FINANCE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": finance_sha256,
                "description": "Issuer-linked audited and unaudited 2025 Midea finance-company size observations",
            },
            {
                "id": "midea_valuation_applicability",
                "path": str((ROOT / json.loads(APPLICABILITY_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
                "sha256": applicability_sha256,
                "description": "Current Midea industrial-FCFF applicability decision",
            },
        ],
        blockers=[
            "MODEL_NOT_APPLICABLE:industrial_fcff_carve_out",
            "finance_company_figures_are_not_full_standalone_statements",
        ],
    )
    effect = materiality_applicability_effect(assessment, "MODEL_NOT_APPLICABLE")
    return {
        "package_version": "midea-finance-materiality-v1",
        "symbol": "000333",
        "assessment": assessment.as_policy(),
        "applicability_effect": effect,
        "industrial_fcff_carve_out": "MODEL_NOT_APPLICABLE",
        "consolidated_enterprise_value_bridge": applicability["scope_assessment"][
            "consolidated_enterprise_value_bridge"
        ],
        "registered_valuation_model": None,
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
        "conclusion": (
            "The finance-company issue is LOW by quantified profit and equity bounds, "
            "but FCFF remains MODEL_NOT_APPLICABLE because materiality does not create "
            "the missing standalone statements, invested-capital allocation or "
            "enterprise-value bridge."
        ),
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_digest = digest(target)
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "script_sha256": digest(Path(__file__).resolve()),
                "evidence_sha256": output_digest,
                "finance_observation_sha256": load_pinned_pointer(FINANCE_POINTER)[1],
                "applicability_sha256": load_pinned_pointer(APPLICABILITY_POINTER)[1],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    POINTER.write_text(
        json.dumps(
            {"path": OUT.relative_to(ROOT).as_posix(), "sha256": output_digest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": target.relative_to(ROOT).as_posix(),
                "sha256": output_digest,
                "materiality": payload["assessment"]["materiality"],
                "industrial_fcff_carve_out": payload["industrial_fcff_carve_out"],
                "model_unlocked": payload["applicability_effect"]["model_unlocked"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
