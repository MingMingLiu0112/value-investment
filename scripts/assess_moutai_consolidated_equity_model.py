#!/usr/bin/env python3
"""Assess a scope-matched parent-equity model path without valuing 600519."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T104011Z/evidence.json"
INPUT_SHA256 = "3ba2b4caa8584100fc41c2ec76ad04794a49dde215cc334abe5a879275dba728"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    if digest(INPUT) != INPUT_SHA256:
        raise ValueError("Pinned parent-equity input changed")
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    chain = source.get("chain") or []
    if (source.get("contract_version") != "moutai-consolidated-parent-equity-inputs-v2"
            or len(chain) != 12
            or chain[0].get("period_end") != "2014-12-31"
            or chain[-1].get("period_end") != "2025-12-31"):
        raise ValueError("Unexpected parent-equity input coverage")
    historical_returns = []
    for row in chain:
        equity = Decimal(row["parent_equity_cny"])
        profit = Decimal(row["parent_profit_cny"])
        shares = Decimal(row["ending_issued_shares"])
        if min(equity, profit, shares) <= 0 or not row.get("available_at") or not row.get("source_url"):
            raise ValueError("Incomplete point-in-time parent-equity input")
        historical_returns.append({
            "period_end": row["period_end"],
            "available_at": row["available_at"],
            "ending_equity_profit_ratio": str(profit / equity),
            "book_value_per_issued_share_cny": str(equity / shares),
            "profit_per_issued_share_cny": str(profit / shares),
        })
    latest = historical_returns[-1]
    return {
        "symbol": "600519",
        "assessment_version": "moutai-consolidated-parent-equity-model-feasibility-v2",
        "input": {"path": str(INPUT.relative_to(ROOT)), "sha256": INPUT_SHA256},
        "candidate_model": {
            "name": "consolidated_parent_equity_residual_income_or_dividend_capacity",
            "economic_scope": "Listed-company parent-attributable consolidated equity, parent-attributable profit, and issued-share denominator.",
            "scope_match": "The starting book equity, earnings and share denominator all describe the same parent-attributable listed equity claim.",
            "why_considered": "It avoids using an industrial FCFF estimate together with a separately valued finance subsidiary and a later enterprise-to-equity bridge.",
        },
        "point_in_time_facts": historical_returns,
        "latest_fact_summary": latest,
        "scope_findings": {
            "industrial_finance_carveout_required": False,
            "enterprise_to_equity_bridge_required": False,
            "reason": "This candidate values the parent-attributable equity claim directly. These findings do not repair or approve the existing industrial FCFF model.",
        },
        "unresolved_required_inputs": [
            "A dated, scope-matched CNY cost-of-equity range and a rule for its historical point-in-time version.",
            "Economically supported bear/base/bull return-on-equity, retention, payout, and fade assumptions; historical end-equity ratios are observations, not forecasts.",
            "A current ordinary-share and post-2025 capital-action treatment for a current per-share output.",
            "Independent arithmetic and accounting-policy checks before any value may become formal.",
        ],
        "separate_execution_requirements": "A dated daily simulation contract with prices/status/actions, fees, adverse slippage, order limits and prior-session capacity; historical queue proof is not required for ordinary daily simulation.",
        "conclusion": "candidate_scope_matched_but_not_admitted",
        "allowed_output": "The fact chain may support model research and a future bounded residual-income or dividend-capacity contract. It does not produce a fair value, safety margin, order, historical strategy return, or simulation admission.",
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
    }


def main() -> int:
    evidence_data = build()
    output = ROOT / "runtime/company-research" / (
        "600519-consolidated-parent-equity-model-feasibility-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(evidence_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "inputs": {str(INPUT.relative_to(ROOT)): INPUT_SHA256},
        "script_sha256": digest(Path(__file__)),
        "outputs": {"evidence.json": digest(evidence)},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "conclusion": evidence_data["conclusion"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
