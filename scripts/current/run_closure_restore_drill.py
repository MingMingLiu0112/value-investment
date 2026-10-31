#!/usr/bin/env python3
"""Run the isolated encrypted backup and restore drill (thin CLI wrapper)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.operations.closure_restore_drill import run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--drill-root", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    receipt = run(args.root, drill_root=args.drill_root)
    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if receipt["verdicts"]["RESTORE_DRILL_PASS"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())