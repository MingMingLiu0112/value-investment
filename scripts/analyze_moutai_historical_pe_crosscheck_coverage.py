#!/usr/bin/env python3
"""Count frozen margin conditions for the research-only historical PE range."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARGINS = (Decimal("0.20"), Decimal("0.30"), Decimal("0.40"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row["status"] == "historical_relative_pe_research_only"]
    counts = {case: {str(margin): 0 for margin in MARGINS} for case in ("low", "mid", "high")}
    for row in eligible:
        price = Decimal(row["price_close_cny"])
        for case in row["cases"]:
            value = Decimal(case["conditional_value_per_share_cny"])
            for margin in MARGINS:
                if price <= value * (Decimal(1) - margin):
                    counts[case["scenario"]][str(margin)] += 1
    return {"eligible_sessions": len(eligible), "margin_condition_counts": counts,
            "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
            "interpretation": "Counts compare current price to a prior-only relative-PE range. They are diagnostics, not orders, returns, or an approved valuation signal."}


def main() -> int:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-pe-crosscheck-latest.json").read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    daily = directory / "daily-values.json"
    if not directory.is_relative_to(ROOT.resolve()) or digest(daily) != pointer["daily_values_sha256"]:
        raise ValueError("Pinned PE cross-check input changed")
    result = analyze(json.loads(daily.read_text(encoding="utf-8")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-historical-pe-crosscheck-coverage-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    report = output / "summary.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"input": pointer, "script_sha256": digest(Path(__file__)), "outputs": {"summary.json": digest(report)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
