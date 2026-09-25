"""Write an offline blocked ResearchInputDescriptor from hash-pinned M5 evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_event_run import M5EventRunReceipt  # noqa: E402
from value_investment_agent.m5_pending_research_input import build_pending_research_input  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--facts", required=True, type=Path)
    parser.add_argument("--equity-pointer", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Pending descriptor output is write-once")
    source_root = args.source_root.resolve()
    pointer = json.loads(args.equity_pointer.read_text(encoding="utf-8"))
    equity_path = (source_root / pointer["path"] / "evidence.json").resolve()
    if not equity_path.is_relative_to(source_root) or not equity_path.is_file():
        raise ValueError("Equity pointer escapes or misses its source root")
    equity_sha = hashlib.sha256(equity_path.read_bytes()).hexdigest()
    if equity_sha != pointer["sha256"]:
        raise ValueError("Archived equity pointer hash mismatch")
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    descriptor = build_pending_research_input(
        receipt=M5EventRunReceipt.from_payload(load(args.receipt)),
        facts_file_bytes=args.facts.read_bytes(),
        equity_file_bytes=equity_path.read_bytes(),
        name=args.name, profile_id=args.profile_id,
        evaluated_at=datetime.now(timezone.utc),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(descriptor.as_policy(), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"path": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "input_sha256": descriptor.input_sha256, "blockers": list(descriptor.blockers),
                      "model_executed": False, "action": "no_order"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
