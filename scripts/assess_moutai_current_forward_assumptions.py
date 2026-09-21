#!/usr/bin/env python3
"""Assess whether the current Moutai forward-policy assumptions are bounded and evidenced."""
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
    facts, facts_ref = pinned_json(model["inputs"]["facts"])
    capital, capital_ref = pinned_json(model["inputs"]["capital_review"])
    peer, peer_ref = pinned_json(model["inputs"]["peer_counterevidence"])
    valuation_at = datetime.fromisoformat(model["valuation_at"])
    if (policy.get("symbol") != "600519" or datetime.fromisoformat(policy["registered_at"]) >= valuation_at
            or policy.get("earnings_anchor") != "lower_of_reported_and_issuer_ex_nonrecurring_ttm"
            or policy.get("terminal_roe_policy") != "cost_of_equity_no_permanent_excess_return"):
        raise ValueError("Unexpected forward-policy scope")
    current = facts.get("current_disclosed_basis") or {}
    reported = Decimal(current["ttm_parent_profit_cny"])
    ex_nonrecurring = Decimal(current["ttm_ex_nonrecurring_parent_profit_cny"])
    anchor = Decimal(model["profit_anchor_cny"])
    if anchor != min(reported, ex_nonrecurring) or not Decimal("0") < anchor:
        raise ValueError("Earnings anchor is not the registered conservative issuer-based anchor")
    scenarios = policy["scenarios"]
    expected_growth = {"bear": "-0.05", "base": "0", "bull": "0.05"}
    if {key: value.get("income_growth") for key, value in scenarios.items()} != expected_growth:
        raise ValueError("Forward income scenarios changed")
    payout = Decimal(policy["payout_ratio"])
    sensitivity = policy["sensitivity"]
    if (not Decimal("0") < payout < Decimal("1")
            or [Decimal(value) for value in sensitivity["payout_ratios"]] != [Decimal("0.50"), Decimal("0.85")]
            or sensitivity["fade_years"] != [0, 10]
            or Decimal(sensitivity["extra_cost_of_equity"]) != Decimal("0.02")):
        raise ValueError("Payout or fade stress policy changed")
    if (capital.get("current_forecast_event_review_complete") is not True
            or capital.get("assumption_decision", "").startswith("Retain existing") is not True
            or not peer):
        raise ValueError("Price-event or peer counterevidence is incomplete")
    checks = model.get("checks") or {}
    if checks.get("forecast_separate_from_book_compounding") is not True or checks.get("no_permanent_excess_roe") is not True:
        raise ValueError("Model does not enforce bounded forecast mechanics")
    return {
        "symbol": "600519",
        "assessment_version": "moutai-current-forward-assumptions-v1",
        "as_of": valuation_at.date().isoformat(),
        "assessment_scope": "bounded conditional earnings, payout and franchise-fade policy for current paper research only",
        "passed": True,
        "earnings_policy": {
            "anchor_cny": str(anchor), "reported_ttm_cny": str(reported),
            "issuer_ex_nonrecurring_ttm_cny": str(ex_nonrecurring),
            "scenarios": expected_growth,
        },
        "capital_and_fade_policy": {
            "payout_ratio": str(payout), "payout_stresses": sensitivity["payout_ratios"],
            "forecast_years": policy["forecast_years"], "fade_years": policy["fade_years"],
            "fade_stresses": sensitivity["fade_years"],
            "terminal_roe_policy": policy["terminal_roe_policy"],
        },
        "counterevidence": [
            "FY2025 and H1 2026 issuer profit trends do not support an automatic recovery; the base path is zero growth.",
            "Peer interim evidence is retained as counterevidence and is not transferred as a Moutai forecast.",
            "The July price change is treated as a one-time level event; no unobserved company-wide uplift is stacked into forecast growth.",
            "Payout, remittances and future capital needs remain uncertain; the 50% and 85% stresses remain visible.",
        ],
        "evidence": {"current_model": model_ref, "policy": policy_ref, "facts": facts_ref,
                     "capital_event_review": capital_ref, "peer_counterevidence": peer_ref},
        "limitations": [
            "Passing this review means the assumptions are frozen, sourced and counterevidence-aware; it does not establish that future earnings, payout or franchise duration will occur.",
            "The output remains a conditional research range, not a formal fair value or target price.",
            "New disclosure, an event that changes the capital bridge, or a later valuation date requires a new policy review.",
        ],
        "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False,
        "trade_approved": False, "live_eligible": False,
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/company-research" / (
        "600519-current-forward-assumptions-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-current-forward-assumptions-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": True, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
