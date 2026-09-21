#!/usr/bin/env python3
"""Quantify why the archived 600519 history is not yet a tradeable backtest."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(rows: list[dict]) -> dict:
    if len(rows) != 2674 or rows[0]["date"] != "2015-01-05" or rows[-1]["date"] != "2025-12-31":
        raise ValueError("Unexpected daily history coverage")
    blockers = Counter(reason for row in rows for reason in row["blockers"])
    sources = Counter(row["annual_source_id"] for row in rows)
    value_present = sum(row.get("trade_value") is not None for row in rows)
    value_approved = sum(row.get("trade_approved") is True for row in rows)
    distribution_bridge = sum(bool(row.get("distributions_since_report")) for row in rows)
    post_repurchase_program = [row for row in rows if row["date"] >= "2025-01-02"]
    share_snapshot = sum(row.get("latest_disclosed_repurchase_source") is not None for row in post_repurchase_program)
    return {
        "symbol": "600519", "window": [rows[0]["date"], rows[-1]["date"]], "sessions": len(rows),
        "historical_value": {"present_sessions": value_present, "approved_sessions": value_approved,
                               "required": "For every decision date: a point-in-time available, reproducible, approved value model with source inputs and version."},
        "execution": {"required": "A frozen paper account, next-session fill rules, transaction costs, corporate actions and benchmark acceptance."},
        "capital_and_distribution": {"sessions_after_disclosed_distribution": distribution_bridge,
                                     "sessions_after_2025_repurchase_program_start": len(post_repurchase_program),
                                     "sessions_with_disclosed_repurchase_snapshot": share_snapshot,
                                     "sessions_without_disclosed_repurchase_snapshot": len(post_repurchase_program) - share_snapshot,
                                     "required": "For each applicable session, determine whether issued shares, treasury shares or both match the per-share valuation denominator; do not turn a disclosed repurchase snapshot into a cancellation fact."},
        "blocker_counts": dict(sorted(blockers.items())),
        "annual_source_session_counts": dict(sorted(sources.items())),
        "admission": {"historical_trade_backtest_complete": False, "trade_approved": False,
                      "conclusion": "No session can enter a trading strategy replay until the required historical valuation and execution contracts are met."},
    }


def main() -> int:
    if digest(INPUT) != INPUT_HASH:
        raise ValueError("Pinned historical input changed")
    result = audit(json.loads(INPUT.read_text(encoding="utf-8")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-historical-admission-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"input": str(INPUT.relative_to(ROOT)), "input_sha256": INPUT_HASH,
        "outputs": {"evidence.json": digest(evidence)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-admission-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"output": str(output), **result["admission"], "sessions": result["sessions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
