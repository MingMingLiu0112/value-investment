#!/usr/bin/env python3
"""Audit fixed safety-margin coverage of the cash-anchor equity research range."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = (Decimal("0.20"), Decimal("0.30"), Decimal("0.40"))
SCENARIOS = ("bear", "base", "bull")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    pointer_path = ROOT / "runtime/strategy-validation/moutai-historical-cash-anchor-equity-range-latest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    values_path = directory / "daily-values.json"
    summary_path = directory / "summary.json"
    if (not directory.is_relative_to(ROOT.resolve()) or digest(values_path) != pointer["daily_values_sha256"]
            or digest(summary_path) != pointer["summary_sha256"]):
        raise ValueError("Pinned cash-anchor equity evidence changed")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("valuation_approved") or summary.get("trade_approved"):
        raise ValueError("Research-only cash-anchor range unexpectedly approved")
    rows = json.loads(values_path.read_text(encoding="utf-8"))
    eligible = [row for row in rows if row["status"] == "cash_distribution_anchored_research_only"]
    coverage = {}
    for scenario in SCENARIOS:
        coverage[scenario] = {}
        for threshold in THRESHOLDS:
            matches = []
            for row in eligible:
                case = next((item for item in row["cases"] if item["scenario"] == scenario), None)
                if case is None:
                    raise ValueError("Incomplete scenario set")
                value = Decimal(case["conditional_value_per_share_cny"])
                if (value - Decimal(row["price_close_cny"])) / value >= threshold:
                    matches.append(row["date"])
            coverage[scenario][str(threshold)] = {"sessions": len(matches),
                                                   "first_date": matches[0] if matches else None,
                                                   "last_date": matches[-1] if matches else None}
    output = ROOT / "runtime/strategy-validation" / ("moutai-cash-anchor-equity-coverage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"symbol": "600519", "rule_version": summary["rule_version"],
                "input_path": str(values_path.relative_to(ROOT)), "input_sha256": digest(values_path),
                "eligible_sessions": len(eligible), "fixed_safety_margin_coverage": coverage,
                "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False,
                "trade_approved": False,
                "interpretation": "Coverage is a counterevidence check over frozen research assumptions. It does not lower thresholds, select an optimistic endpoint, create an order, demonstrate performance, or approve a trade."}
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-cash-anchor-equity-coverage-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **evidence}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
