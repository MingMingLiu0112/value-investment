#!/usr/bin/env python3
"""Thin CLI for the historical-validation receipt audit application service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from value_investment_agent.application.historical_validation import (  # noqa: E402
    digest,
    resolve_bundle,
    verify_bundle,
)


DEFAULT_POINTER = ROOT / "runtime" / "historical-validation-600519-latest.json"

# DEPRECATED_COMPATIBILITY_SHIM: keep the former private name for existing callers.
_resolve_bundle = resolve_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = args.receipt_dir or resolve_bundle(root, args.pointer)
    result = verify_bundle(root, bundle)
    if args.output:
        output = args.output.resolve()
        if not output.is_relative_to(root):
            raise ValueError("Audit output must remain under the project root")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
