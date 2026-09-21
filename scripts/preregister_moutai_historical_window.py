#!/usr/bin/env python3
"""Pre-register the first isolated historical 600519 validation window."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW_SESSIONS = 20


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    timeline_pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-input-timeline-latest.json").read_text(encoding="utf-8"))
    timeline_path = ROOT / timeline_pointer["path"] / "timeline.json"
    if digest(ROOT / timeline_pointer["path"] / "summary.json") != timeline_pointer["sha256"]:
        raise ValueError("Historical input timeline pointer changed")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    events = json.loads((ROOT / "docs/reviewed-cash-distributions.json").read_text(encoding="utf-8"))["events"]
    action_dates = {event[key] for event in events if event["symbol"] == "600519"
                    for key in ("record_date", "ex_date", "cash_payment_date")}
    selected = None
    for start in range(len(timeline) - WINDOW_SESSIONS + 1):
        rows = timeline[start:start + WINDOW_SESSIONS]
        if len({row["annual_source_id"] for row in rows}) != 1 or any(row["date"] in action_dates for row in rows):
            continue
        selected = rows
        break
    if selected is None:
        raise ValueError("No isolated historical window found")
    output = ROOT / "runtime/strategy-validation" / ("moutai-historical-window-registration-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = {
        "symbol": "600519", "registration_version": "moutai-historical-window-v1",
        "window": {"start": selected[0]["date"], "end": selected[-1]["date"], "sessions": len(selected),
                   "annual_source_id": selected[0]["annual_source_id"], "report_period": selected[0]["report_period"]},
        "selection_rule": "Earliest 20 consecutive timeline sessions with one then-available annual input and no registered cash-action date.",
        "inputs": {"timeline": {"path": str(timeline_path.relative_to(ROOT)), "sha256": digest(timeline_path)},
                   "distribution_registry": {"path": "docs/reviewed-cash-distributions.json", "sha256": digest(ROOT / "docs/reviewed-cash-distributions.json")}},
        "required_before_replay": ["Point-in-time approved value model for the registered annual input.",
                                   "Dated fee, liquidity and next-open execution contract.",
                                   "Same-period benchmark acceptance."],
        "status": "preregistered_not_replay_eligible", "formal_fair_value": None,
        "trade_approved": False, "live_eligible": False,
    }
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "window": evidence["window"], "status": evidence["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
