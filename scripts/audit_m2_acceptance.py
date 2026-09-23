#!/usr/bin/env python3
"""Recompute the M2 AC1-AC12 acceptance evidence from immutable local inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_acceptance_audit import (  # noqa: E402
    audit,
    write_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run the full local offline regression suite before auditing.",
    )
    parser.add_argument(
        "--ci-status",
        choices=("success", "failure", "pending"),
        help="Use an observed GitHub Actions status for the audited commit.",
    )
    parser.add_argument(
        "--wps-workbook",
        type=Path,
        help="Optional live WPS production workbook path for the AC10 hash check.",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    root = args.root.resolve()
    ci_evidence = {"status": args.ci_status} if args.ci_status else None
    wps_path = args.wps_workbook.resolve() if args.wps_workbook else None
    receipt = audit(
        root,
        run_tests=args.run_tests,
        ci_evidence=ci_evidence,
        wps_canonical_path=wps_path,
    )
    output = write_receipt(receipt, root=root)
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    print(f"M2 acceptance status: {receipt['status']}")
    print(f"done: {', '.join(receipt['summary']['done'])}")
    print(f"partial: {', '.join(receipt['summary']['partial'])}")
    print(f"pending_ci: {', '.join(receipt['summary']['pending_ci'])}")
    print(
        "pending_human_review: "
        + ", ".join(receipt["summary"]["pending_human_review"])
    )
    print(f"next_action: {receipt['summary']['next_action']}")
    print(f"receipt: {output['receipt_path']}")
    print(f"receipt sha256: {output['receipt_sha256']}")
    print("action: no_order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
