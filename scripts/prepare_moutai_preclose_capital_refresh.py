#!/usr/bin/env python3
"""Freeze a bounded CNINFO capital-event receipt before an SSE close.

This is preparation evidence only.  A later model must still bind this receipt,
the close-time quote and its own dated policy before it can be used for paper
research.  Any result that contains an announcement fails closed because the
capital bridge then needs a specific review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8))
LATEST_START = "2026-09-14"
CUTOFF = time(15, 0)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_preclose(now: datetime, through: date) -> None:
    local = now.astimezone(SHANGHAI)
    if local.date() != through:
        raise ValueError("Receipt date must equal the local collection date")
    if local.weekday() > 4:
        raise ValueError("Capital refresh must run on a weekday")
    if local.time() >= CUTOFF:
        raise ValueError("Capital refresh started too late for a close-time model")


def final_json(output: str, context: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise ValueError(context + " returned no result")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise ValueError(context + " returned invalid final JSON") from error


def index_directory(result: dict) -> Path:
    directory = result.get("directory")
    if not isinstance(directory, str) or not directory:
        raise ValueError("Filing-index result must include a directory")
    return Path(directory).resolve()


def run(*args: str) -> dict:
    python = Path(os.environ.get("VALUE_INVESTMENT_PYTHON", sys.executable)).resolve()
    if not python.is_file():
        raise RuntimeError("Configured project Python is unavailable: " + str(python))
    completed = subprocess.run([str(python), "-X", "utf8", *args], cwd=ROOT,
                               text=True, encoding="utf-8", capture_output=True,
                               env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    if completed.returncode:
        raise RuntimeError("Command failed: " + " ".join(args) + "\n" + completed.stderr[-2000:])
    return final_json(completed.stdout, args[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", help="YYYY-MM-DD; defaults to Shanghai today")
    parser.add_argument("--now", help="ISO timestamp, for controlled tests")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(SHANGHAI)
    if now.tzinfo is None:
        raise ValueError("Collection time must include a timezone")
    through = date.fromisoformat(args.through) if args.through else now.astimezone(SHANGHAI).date()
    require_preclose(now, through)

    started = now.astimezone(SHANGHAI)
    index = run("scripts/collect_historical_filing_index.py", "--company", "600519", "贵州茅台",
                "--all-categories", "--start", LATEST_START, "--end", through.isoformat())
    finished = datetime.now(SHANGHAI)
    if finished.time() >= CUTOFF:
        raise ValueError("Capital refresh completed after close; do not use it for this close-time model")
    index_dir = index_directory(index)
    index_records = list(index_dir.glob("600519-*.json"))
    if len(index_records) != 1:
        raise ValueError("Expected exactly one bounded 600519 index record")
    refresh = run("scripts/assess_moutai_current_capital_refresh.py", "--index-dir", str(index_dir),
                  "--start", LATEST_START, "--through", through.isoformat())
    receipt_dir = ROOT / "runtime/company-research" / ("600519-preclose-capital-receipt-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    receipt_dir.mkdir(parents=True, exist_ok=False)
    receipt = {
        "symbol": "600519", "receipt_version": "moutai-preclose-capital-receipt-v1",
        "collection_started_at": started.isoformat(), "collection_finished_at": finished.isoformat(),
        "through": through.isoformat(), "preclose_complete": True,
        "query_index": {"path": str(index_records[0].relative_to(ROOT)), "sha256": digest(index_records[0])},
        "capital_refresh": {"path": str(Path(refresh["output"]).relative_to(ROOT) / "evidence.json"),
                            "sha256": digest(Path(refresh["output"]) / "evidence.json")},
        "next_step": "Rebuild a dated policy, current model and admission chain after the close. This receipt alone does not approve a valuation, simulation or order.",
        "trade_approved": False,
    }
    evidence = receipt_dir / "evidence.json"
    evidence.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (receipt_dir / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(receipt_dir), "preclose_complete": True, "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
