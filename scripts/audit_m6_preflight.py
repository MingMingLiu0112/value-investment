#!/usr/bin/env python3
"""Run the local M6 operational readiness preflight.

This command never connects to a production database, changes a service,
creates an order, or substitutes simulated observations for real sessions.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m6_operational_readiness import (  # noqa: E402
    build_preflight_receipt,
    write_receipt,
)


def _git_files(root: Path) -> tuple[list[str], bool]:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    return (
        tracked.stdout.splitlines() if tracked.returncode == 0 else [],
        status.returncode == 0 and not status.stdout.strip(),
    )


def _load_optional_list(path: Path | None) -> list[dict]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "m6-operational-preflight-v1.json",
    )
    parser.add_argument("--sessions", type=Path)
    parser.add_argument("--calendar-evidence", type=Path)
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--verified-restore-receipt", type=Path)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    config = args.config.resolve()
    tracked_files, clean = _git_files(root)
    source = None
    target = None
    if args.verified_restore_receipt:
        source = os.environ.get('M6_DRILL_SOURCE_DSN')
        target = os.environ.get('M6_DRILL_RESTORE_DSN')
        if not source or not target:
            raise ValueError('M6_DRILL_SOURCE_DSN and M6_DRILL_RESTORE_DSN are required for live verification')
    receipt = build_preflight_receipt(
        root,
        config,
        tracked_files=tracked_files,
        clean=clean,
        session_records=_load_optional_list(args.sessions.resolve() if args.sessions else None),
        calendar_evidence=json.loads(args.calendar_evidence.read_text(encoding='utf-8'))
        if args.calendar_evidence else None,
        restore_records=_load_optional_list(args.restore.resolve() if args.restore else None),
        restore_receipt_path=args.verified_restore_receipt.resolve() if args.verified_restore_receipt else None,
        source_database_url=source,
        restore_database_url=target,
    )
    output = write_receipt(receipt, root=root)
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    print(f"engineering_status: {receipt['engineering_status']}")
    print(f"operational_acceptance_status: {receipt['operational_acceptance_status']}")
    print(f"done: {', '.join(receipt['summary']['done']) or '-'}")
    print(f"partial: {', '.join(receipt['summary']['partial']) or '-'}")
    print(
        "requires_authorization: "
        + (", ".join(receipt["summary"]["requires_authorization"]) or "-")
    )
    print("blockers:")
    for blocker in receipt["summary"]["blockers"]:
        print(f"  - {blocker}")
    print(f"receipt: {output['receipt_path']}")
    print(f"receipt sha256: {output['receipt_sha256']}")
    print("action: no_order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
