#!/usr/bin/env python3
"""Materialize the non-tradeable ledger for the frozen Moutai decision trace."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.paper_ledger import build_blocked_ledger


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_decisions() -> tuple[list[dict], dict]:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-paper-decisions-latest.json").read_text(encoding="utf-8"))
    directory = ROOT / pointer["path"]
    summary = directory / "summary.json"
    if digest(summary) != pointer["summary_sha256"]:
        raise ValueError("Pinned paper-decision summary changed")
    decisions = json.loads((directory / "daily-decisions.json").read_text(encoding="utf-8"))
    if len(decisions) != 2674 or any(row["trade_approved"] for row in decisions):
        raise ValueError("Unexpected decision-trace scope")
    return decisions, json.loads(summary.read_text(encoding="utf-8"))


def main() -> int:
    decisions, summary = read_decisions()
    ledger = build_blocked_ledger(decisions)
    if any(row["pending_order"] or row["executed_order"] or row["performance_available"] for row in ledger):
        raise ValueError("Blocked ledger must not report orders or performance")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-blocked-paper-ledger-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "daily-ledger.json"
    evidence.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"symbol": "600519", "sessions": len(ledger), "orders": 0, "executions": 0,
              "performance_available": False, "trade_approved": False,
              "decision_summary_sha256": digest(ROOT / json.loads((ROOT / "runtime/strategy-validation/moutai-paper-decisions-latest.json").read_text(encoding="utf-8"))["path"] / "summary.json"),
              "interpretation": "A chronological blocked paper ledger records decision evidence and next eligible execution dates. It has no approved account capital, orders, executions or performance."}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": digest(Path(__file__)), "decision_rule_version": summary["rule_version"],
                "outputs": {path.name: digest(path) for path in output.iterdir() if path.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-blocked-paper-ledger-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(output / "summary.json")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
