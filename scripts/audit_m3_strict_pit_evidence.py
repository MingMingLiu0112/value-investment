"""Audit a user-provided strict contemporaneous-rule evidence packet.

The command is read-only except for writing a versioned runtime receipt. It
does not approve a trade, valuation or historical decision.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m3_strict_pit_evidence import (  # noqa: E402
    ACTION_NO_ORDER,
    audit,
)


DEFAULT_REPLAY = (
    ROOT
    / "runtime"
    / "m3-historical-research-replay-20260924-v1"
    / "replay.json"
)
DEFAULT_CANDIDATE = ROOT / "runtime" / "m3-strict-pit-evidence" / "candidate.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--as-of",
        type=lambda value: datetime.fromisoformat(value),
        default=None,
    )
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    as_of = args.as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    candidate = args.candidate if args.candidate.is_file() else None
    receipt = audit(ROOT, args.replay, candidate)
    receipt["audited_at"] = as_of.isoformat()
    output_dir = args.output_dir or (
        ROOT / "runtime" / f"m3-strict-pit-evidence-audit-{as_of:%Y%m%dT%H%M%SZ}"
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pointer = ROOT / "runtime" / "m3-strict-pit-evidence-audit-latest.json"
    pointer.write_text(
        json.dumps(
            {
                "path": str(output_dir.relative_to(ROOT)),
                "sha256": _digest(receipt_path),
                "action": ACTION_NO_ORDER,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
