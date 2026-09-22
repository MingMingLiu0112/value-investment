"""Map Moutai's frozen named assumptions into the generic assumption contract.

This adapter re-registers existing research assumptions without changing one
parameter. It does not recalculate the residual-income model or produce a new
fair value.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.valuation_assumptions import (
    ValuationAssumption,
    build_valuation_assumption_set,
)


ROOT = Path(__file__).resolve().parents[1]

FORWARD = ROOT / "runtime/company-research/600519-current-forward-assumptions-20260921T124252Z/evidence.json"
FORWARD_SHA256 = "373ee3a900ecfcf51b7abacc8500cad47ead5446dc23846ac349eab1d25ac1a4"
CURRENT_MODEL = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-20260921T124252Z/evidence.json"
CURRENT_MODEL_SHA256 = "8ffe43ccf6acba184496eec12d7ed65082ec91d4ba38f7cfd5604a32fe648f30"
DISCOUNT = ROOT / "runtime/valuation-research/moutai-consolidated-parent-equity-discount-range-20260914T104355Z/evidence.json"
DISCOUNT_SHA256 = "d53f204548a2a97c83c046572b93e331af3963e53773f0b3f8d4962a819dd154"

OUT = ROOT / "runtime/valuation-assumptions/moutai-current-20260921"
POINTER = ROOT / "runtime/valuation-assumptions/600519-current-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Pinned Moutai assumption input changed: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict:
    forward = load_pinned(FORWARD, FORWARD_SHA256)
    current_model = load_pinned(CURRENT_MODEL, CURRENT_MODEL_SHA256)
    discount = load_pinned(DISCOUNT, DISCOUNT_SHA256)
    if (
        forward.get("symbol") != "600519"
        or forward.get("assessment_version") != "moutai-current-forward-assumptions-v1"
        or forward.get("passed") is not True
    ):
        raise ValueError("Moutai forward-assumption review changed its contract")
    if (
        current_model.get("model_version")
        != "moutai-current-parent-equity-residual-income-v1"
    ):
        raise ValueError("Moutai current model changed its contract")
    if discount.get("contract_version") != "moutai-consolidated-parent-equity-discount-range-v1":
        raise ValueError("Moutai cost-of-equity evidence changed its contract")

    policy = forward["capital_and_fade_policy"]
    growth = forward["earnings_policy"]["scenarios"]
    payout = Decimal(policy["payout_ratio"])
    retention = Decimal("1") - payout
    rate_range = discount["range"]
    terminal_growth = Decimal(current_model["model_policy"]["terminal_growth"])

    assumptions = [
        ValuationAssumption(
            name="income_growth",
            unit="percent/year",
            bear=Decimal(growth["bear"]),
            base=Decimal(growth["base"]),
            bull=Decimal(growth["bull"]),
            basis="FY2025 and H1 2026 issuer parent-profit trends plus explicit bounded scenario policy",
            rationale=forward["capital_and_fade_policy"].get(
                "rationale",
                "Five annual -5/0/+5 percent paths are research scenarios, not forecasts",
            ),
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="payout_ratio",
            unit="ratio",
            bear=payout,
            base=payout,
            bull=payout,
            basis="FY2025 issuer combined cash-distribution observation and current research policy",
            rationale="75 percent payout is a research assumption below the latest observed ratio, not a company commitment",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="medium",
            sensitivity="medium",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="retention_ratio",
            unit="ratio",
            bear=retention,
            base=retention,
            bull=retention,
            basis="Clean-surplus complement of the registered payout assumption",
            rationale="Retention is not independently forecast; it follows the payout assumption and clean-surplus accounting",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="medium",
            sensitivity="medium",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="forecast_years",
            unit="years",
            bear=Decimal(policy["forecast_years"]),
            base=Decimal(policy["forecast_years"]),
            bull=Decimal(policy["forecast_years"]),
            basis="Registered bounded research horizon",
            rationale="Five explicit years are a research choice and do not imply a five-year forecast certainty",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="high",
            sensitivity="low",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="fade_years",
            unit="years",
            bear=Decimal(policy["fade_years"]),
            base=Decimal(policy["fade_years"]),
            bull=Decimal(policy["fade_years"]),
            basis="Registered terminal franchise-fade policy",
            rationale="Linear fade over five years removes permanent excess returns and is stress-tested at zero and ten years",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="high",
            sensitivity="high",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="terminal_growth",
            unit="percent/year",
            bear=terminal_growth,
            base=terminal_growth,
            bull=terminal_growth,
            basis="Long-run nominal growth assumption in the retained terminal regime",
            rationale="Two percent terminal growth is bounded by the model's no-permanent-excess-return policy",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="low",
            sensitivity="medium",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
        ValuationAssumption(
            name="cost_of_equity",
            unit="percent/year",
            bear=Decimal(rate_range["upper"]),
            base=Decimal(rate_range["central"]),
            bull=Decimal(rate_range["lower"]),
            basis="CNY ten-year yield proxy plus listed-equity beta proxy times China total ERP",
            rationale="Upper, central and lower bounded cases map to bear, base and bull; no single approved rate exists",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "moutai_cost_of_equity_range"}],
            blockers=[],
            ordering="descending",
        ),
        ValuationAssumption(
            name="terminal_roe_policy",
            unit="policy",
            bear=policy["terminal_roe_policy"],
            base=policy["terminal_roe_policy"],
            bull=policy["terminal_roe_policy"],
            basis="Registered terminal return-on-equity policy",
            rationale="Terminal ROE equals the scenario cost of equity so no permanent excess return is embedded",
            as_of=date.fromisoformat(forward["as_of"]),
            confidence="medium",
            sensitivity="high",
            evidence_refs=[{"id": "moutai_current_forward_assumptions"}],
            blockers=[],
        ),
    ]
    evidence_refs = [
        {
            "id": "moutai_current_forward_assumptions",
            "path": str(FORWARD.relative_to(ROOT)),
            "sha256": FORWARD_SHA256,
            "description": "Frozen Moutai current earnings, payout and fade assumptions",
        },
        {
            "id": "moutai_cost_of_equity_range",
            "path": str(DISCOUNT.relative_to(ROOT)),
            "sha256": DISCOUNT_SHA256,
            "description": "Frozen Moutai bounded cost-of-equity range",
        },
        {
            "id": "moutai_current_model",
            "path": str(CURRENT_MODEL.relative_to(ROOT)),
            "sha256": CURRENT_MODEL_SHA256,
            "description": "Frozen Moutai current residual-income research model policy",
        },
    ]
    assumption_set = build_valuation_assumption_set(
        symbol="600519",
        profile_id="quality_compounder",
        model_type="residual_income_or_equity_value",
        as_of=date.fromisoformat(forward["as_of"]),
        assumptions=assumptions,
        evidence_refs=evidence_refs,
    )
    return {
        "package_version": "moutai-current-assumption-set-v1",
        "symbol": "600519",
        "mapping_only": True,
        "parameters_changed": False,
        "valuation_recalculated": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "assumption_set": assumption_set.as_policy(),
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
                "forward_assumptions_sha256": FORWARD_SHA256,
                "current_model_sha256": CURRENT_MODEL_SHA256,
                "cost_of_equity_range_sha256": DISCOUNT_SHA256,
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
                "assumption_status": payload["assumption_set"]["status"],
                "parameters_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
