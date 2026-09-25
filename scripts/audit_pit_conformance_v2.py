#!/usr/bin/env python3
"""Thin CLI for the read-only PIT conformance verifier v2."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.historical_validation import (  # noqa: E402
    verify_pit_conformance_v2,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify replay/admission point-in-time evidence without changing state."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--subject", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--verified-at", type=datetime.fromisoformat)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_pit_conformance_v2(
            args.root,
            subject_path=args.subject,
            manifest_path=args.manifest,
            verified_at=args.verified_at,
        )
    except (OSError, ValueError) as error:
        result = {
            "schema_version": "pit-conformance-verifier-v2",
            "status": "FAIL",
            "action": "no_order",
            "error": str(error),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "PASS":
        return 0
    if result.get("status") == "NOT_PROVEN":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
