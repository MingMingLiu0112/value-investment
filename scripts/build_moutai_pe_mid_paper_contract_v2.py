#!/usr/bin/env python3
"""Extend the immutable median-PE research experiment through 2025.

This is a versioned research contract, not a replacement for v1.  It preserves
the existing entry/exit rule and records the point-in-time share-event boundary
as context; it does not convert relative PE into intrinsic value.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_moutai_2025_share_timeline import build_timeline
from build_moutai_pe_mid_paper_contract import QUANTITY, build_decisions
from build_moutai_real_execution_contract import build_contract as build_execution_contract


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_research_contract() -> tuple[dict, list[dict], dict, dict]:
    pointer_path = ROOT / "runtime/strategy-validation/moutai-historical-pe-crosscheck-latest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    values_path = directory / "daily-values.json"
    if not directory.is_relative_to(ROOT.resolve()) or digest(values_path) != pointer["daily_values_sha256"]:
        raise ValueError("Pinned PE cross-check values changed")
    values = json.loads(values_path.read_text(encoding="utf-8"))
    if len(values) != 2674 or values[0]["date"] != "2015-01-05" or values[-1]["date"] != "2025-12-31":
        raise ValueError("Unexpected PE research coverage")
    orders, trace = build_decisions(values, window_end=None)
    execution = build_execution_contract()
    if [row["date"] for row in execution["sessions"]] != [row["date"] for row in values]:
        raise ValueError("Execution and PE session dates differ")
    timeline = build_timeline()
    expected_event = timeline["events"][0]
    if not expected_event["usable_for_2025_point_in_time_share_basis"]:
        raise ValueError("Expected share event was unexpectedly unavailable")
    contract = {
        **execution,
        "contract_version": "moutai-pe-mid-paper-contract-v2-2025-extension",
        "decisions": orders,
        "research_simulation_eligible": True,
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "research_rule": {
            "relative_value": "median of prior observed daily PE values",
            "entry_margin": "30% unchanged from v1",
            "quantity": QUANTITY,
            "exit": "close exceeds that day's median-relative value",
        },
        "share_event_context": {
            "contemporaneous_expected_cancellation_available_at": expected_event["known_at"],
            "expected_effective_date": expected_event["effective_date_claimed"],
            "share_delta": expected_event["shares"],
            "treatment": "Recorded as point-in-time corporate-action context only. The PE input remains price divided by then-available reported annual EPS; no daily share count, treasury carrying value, or retroactive annual-EPS adjustment is inferred.",
            "ex_post_confirmation_prohibited_for_2025_decisions": True,
        },
        "interpretation": "Versioned 2015-2025 extension of the existing median-prior-PE research experiment. It is relative valuation only, not intrinsic value, a formal valuation, a validated strategy, or a live-trading input.",
    }
    return contract, trace, pointer, timeline


def main() -> int:
    contract, trace, pointer, timeline = build_research_contract()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-pe-mid-paper-contract-v2-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    input_path = output / "input.json"
    trace_path = output / "daily-decisions.json"
    input_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "symbol": "600519", "rule_version": contract["contract_version"], "window_end": "2025-12-31",
        "sessions": len(contract["sessions"]), "cash_events": len(contract["cash_events"]),
        "blocked_sessions": sum(row["state"] == "blocked" for row in trace),
        "research_decision_sessions": sum(row["state"] != "blocked" for row in trace),
        "proposed_entries": sum(row["state"] == "proposed_entry" for row in trace),
        "proposed_exits": sum(row["state"] == "proposed_reduce" for row in trace),
        "2025_sessions": sum(row["date"] >= "2025-01-01" for row in contract["sessions"]),
        "share_event_context": contract["share_event_context"],
        "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
        "interpretation": "A separate, non-live research extension. It does not alter v1 results or prove performance, valuation validity, or an investment recommendation.",
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "pe_crosscheck_pointer": pointer,
        "share_timeline_evidence": timeline,
        "script_sha256": digest(Path(__file__)),
        "outputs": {path.name: digest(path) for path in (input_path, trace_path, summary_path)},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-pe-mid-paper-contract-v2-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
