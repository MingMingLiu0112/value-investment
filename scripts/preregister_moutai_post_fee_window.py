#!/usr/bin/env python3
"""Pre-register the first 20-session 600519 window after the 2015 fee change.

The date is fixed by the ChinaClear fee effective date, not by a return,
valuation outcome, signal or benchmark result.  This creates no backtest.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMELINE_DIR = ROOT / "runtime/strategy-validation/moutai-historical-input-timeline-20260910T101416Z"
TIMELINE = TIMELINE_DIR / "timeline.json"
DISTRIBUTIONS = ROOT / "docs/reviewed-cash-distributions.json"
START = "2015-08-03"
SESSIONS = 20


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    rows = json.loads(TIMELINE.read_text(encoding="utf-8"))
    start = next((index for index, row in enumerate(rows) if row["date"] == START), None)
    if start is None:
        raise ValueError("Post-fee start date is absent from the input timeline")
    selected = rows[start:start + SESSIONS]
    if len(selected) != SESSIONS or selected[0]["date"] != START or selected[-1]["date"] != "2015-08-28":
        raise ValueError("The first post-fee 20-session window is incomplete")
    if len({row["annual_source_id"] for row in selected}) != 1:
        raise ValueError("Window crosses an annual-input availability boundary")
    actions = {event[key] for event in json.loads(DISTRIBUTIONS.read_text(encoding="utf-8"))["events"]
               if event["symbol"] == "600519" for key in ("record_date", "ex_date", "cash_payment_date")}
    in_window = sorted(row["date"] for row in selected if row["date"] in actions)
    if in_window:
        raise ValueError("Post-fee window contains a reviewed cash-action date")
    return {
        "symbol": "600519", "registration_version": "moutai-post-fee-window-v1",
        "window": {"start": selected[0]["date"], "end": selected[-1]["date"], "sessions": SESSIONS,
                   "annual_source_id": selected[0]["annual_source_id"], "report_period": selected[0]["report_period"]},
        "selection_rule": "First 20 consecutive timeline sessions starting on the first SSE session after ChinaClear's 2015-08-01 uniform transfer-fee effective date; no return, signal, value or benchmark outcome was consulted.",
        "excluded_reviewed_cash_action_dates": in_window,
        "inputs": {"timeline": {"path": str(TIMELINE.relative_to(ROOT)), "sha256": digest(TIMELINE)},
                   "distribution_registry": {"path": str(DISTRIBUTIONS.relative_to(ROOT)), "sha256": digest(DISTRIBUTIONS)}},
        "execution_scope": "The 2015-08-01 ChinaClear transfer-fee basis is applicable. Broker commission, minimum charge, rounding, liquidity, next-open fill and benchmark-version evidence remain separately required.",
        "status": "preregistered_not_replay_eligible", "historical_trade_backtest_complete": False,
        "formal_fair_value": None, "trade_approved": False, "live_eligible": False,
    }


def main() -> int:
    result = build()
    output = ROOT / "runtime/strategy-validation" / ("moutai-post-fee-window-registration-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "window": result["window"], "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
