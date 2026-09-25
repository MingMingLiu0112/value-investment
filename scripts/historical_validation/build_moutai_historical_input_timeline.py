#!/usr/bin/env python3
"""Bind every archived decision date to its point-in-time annual input case."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
DAILY_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if digest(DAILY) != DAILY_HASH:
        raise ValueError("Pinned daily inputs changed")
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json").read_text(encoding="utf-8"))
    evidence = ROOT / pointer["path"] / "evidence.json"
    if digest(evidence) != pointer["sha256"]:
        raise ValueError("Conditional-input evidence changed")
    package = json.loads(evidence.read_text(encoding="utf-8"))
    cases = {case["source"]["source_id"]: case for case in package["input_cases"]}
    rows = json.loads(DAILY.read_text(encoding="utf-8"))
    timeline = []
    for row in rows:
        case = cases.get(row["annual_source_id"])
        if case is None or case["available_at"] > row["decision_at"]:
            raise ValueError("Future or missing annual conditional input")
        timeline.append({"date": row["date"], "decision_at": row["decision_at"],
                         "annual_source_id": row["annual_source_id"], "report_period": case["report_period"],
                         "input_available_at": case["available_at"], "conditional_input_available": True,
                         "formal_fair_value": None, "trade_approved": False,
                         "blockers": case["blockers"]})
    if len(timeline) != 2674 or any(row["trade_approved"] for row in timeline):
        raise ValueError("Unexpected timeline coverage or approval")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-historical-input-timeline-{stamp}"
    output.mkdir()
    (output / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "sessions": len(timeline), "input_cases": len(cases),
               "point_in_time_violations": 0, "formal_fair_value": None, "trade_approved": False,
               "interpretation": "Every session has a then-available conditional input case; no session has an approved historical value or trade admission."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-input-timeline-latest.json").write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(output / "summary.json")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
