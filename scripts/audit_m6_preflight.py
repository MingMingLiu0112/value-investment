#!/usr/bin/env python3
"""Run the local M6 operational readiness preflight.

This command never connects to a production database, changes a service,
creates an order, or substitutes simulated observations for real sessions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
from value_investment_agent.quote_session_collection import resolve_session_reference  # noqa: E402


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


def _calendar_from_bundle(path: Path, symbol: str) -> dict:
    raw = path.read_bytes()
    bundle = json.loads(raw)
    report = json.loads(path.with_name('report.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(raw).hexdigest()
    if (bundle.get('version') != 'quote-session-collection-v1'
            or bundle.get('status') != 'collected_not_verified'
            or bundle.get('request_failures')
            or report.get('bundle_sha256') != digest
            or report.get('bundle_bytes') != len(raw)
            or report.get('status') != bundle['status']):
        raise ValueError('Calendar bundle and collection report are not bound')
    reference = bundle['references'][symbol]
    resolved = resolve_session_reference(reference, bundle['documents'])
    documents = resolved['calendar_documents']
    venue = reference.get('calendar_exchange')
    if (reference.get('symbol') != symbol or not documents
            or not ((symbol.startswith('6') and venue == 'SSE')
                    or (symbol.startswith(('0', '3')) and venue == 'SZSE'))):
        raise ValueError('Official exchange calendar reference is missing')
    cutoff = datetime.fromisoformat(bundle['finished_at'])
    if cutoff.tzinfo is None or cutoff > datetime.now(timezone.utc):
        raise ValueError('Calendar collection cutoff is in the future')
    return {
        'venue': venue,
        'documents': documents,
        'observation_cutoff': bundle['finished_at'],
        'source_bundle_sha256': digest,
        'source_report_sha256': hashlib.sha256(path.with_name('report.json').read_bytes()).hexdigest(),
    }


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
    parser.add_argument("--calendar-bundle", type=Path)
    parser.add_argument("--calendar-symbol")
    parser.add_argument("--verify-live-calendar", action="store_true")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--verified-restore-receipt", type=Path)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if args.calendar_bundle and (args.calendar_evidence or not args.calendar_symbol):
        parser.error('--calendar-bundle requires --calendar-symbol and excludes --calendar-evidence')
    if args.verify_live_calendar and not (args.calendar_bundle or args.calendar_evidence):
        parser.error('--verify-live-calendar requires archived calendar evidence')

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
        calendar_evidence=(_calendar_from_bundle(args.calendar_bundle.resolve(), args.calendar_symbol)
                           if args.calendar_bundle else
                           json.loads(args.calendar_evidence.read_text(encoding='utf-8'))
                           if args.calendar_evidence else None),
        verify_live_calendar=args.verify_live_calendar,
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
