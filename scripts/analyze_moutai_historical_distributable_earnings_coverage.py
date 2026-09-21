#!/usr/bin/env python3
"""Audit fixed safety-margin coverage of the distributable-earnings experiment."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = (Decimal("0.20"), Decimal("0.30"), Decimal("0.40"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-distributable-earnings-latest.json").read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    summary_path, values_path = directory / "summary.json", directory / "daily-values.json"
    if (not directory.is_relative_to(ROOT.resolve()) or digest(summary_path) != pointer["summary_sha256"]
            or digest(values_path) != pointer["daily_values_sha256"]):
        raise ValueError("Pinned distributable-earnings evidence changed")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = json.loads(values_path.read_text(encoding="utf-8"))
    eligible = [row for row in rows if row["status"] == "conditional_research_only"]
    coverage = {}
    for threshold in THRESHOLDS:
        matches = []
        for row in eligible:
            value, price = Decimal(row["conditional_value_low_cny"]), Decimal(row["price_close_cny"])
            if (value - price) / value >= threshold:
                matches.append(row["date"])
        coverage[str(threshold)] = {"sessions": len(matches), "first_date": matches[0] if matches else None,
                                    "last_date": matches[-1] if matches else None}
    scenario_coverage = {}
    for scenario in ("bear", "base", "bull"):
        scenario_coverage[scenario] = {}
        for threshold in THRESHOLDS:
            matches = []
            for row in eligible:
                case = next((item for item in row["cases"] if item["scenario"] == scenario), None)
                if case is None:
                    raise ValueError("Incomplete scenario set")
                value, price = Decimal(case["conditional_value_per_share_cny"]), Decimal(row["price_close_cny"])
                if (value - price) / value >= threshold:
                    matches.append(row["date"])
            scenario_coverage[scenario][str(threshold)] = {"sessions": len(matches),
                                                             "first_date": matches[0] if matches else None,
                                                             "last_date": matches[-1] if matches else None}
    out = ROOT / "runtime/strategy-validation" / ("moutai-distributable-earnings-coverage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=False)
    evidence = {"symbol": "600519", "rule_version": summary["rule_version"],
                "input_path": str(values_path.relative_to(ROOT)), "input_sha256": digest(values_path),
                "sessions": len(rows), "eligible_sessions": len(eligible),
                "pre_registered_safety_margin_coverage": coverage,
                "scenario_safety_margin_coverage": scenario_coverage,
                "valuation_approved": False, "trade_approved": False,
                "interpretation": "Coverage is a fixed-input counterevidence check. The lower-bound rule has no signal at any threshold; any signal limited to a higher scenario is valuation-sensitive and does not permit an entry. This does not tune parameters, choose a window, produce orders, or demonstrate strategy performance."}
    path = out / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-distributable-earnings-coverage-latest.json").write_text(json.dumps({"path": str(out.relative_to(ROOT)), "sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **evidence}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
