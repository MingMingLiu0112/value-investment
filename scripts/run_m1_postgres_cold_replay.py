"""Run the M1 application through an isolated PostgreSQL cold restart."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_postgres_cold_replay import (  # noqa: E402
    run_m1_postgres_cold_replay,
)


def _report(receipt: dict) -> str:
    lines = [
        "M1 POSTGRES COLD REPLAY",
        f"status: {receipt['status']}",
        f"host: {receipt['host']}:{receipt['port']}",
        f"postgres: {receipt['postgres_version'].split(' on ')[0]}",
        (
            "first run: "
            f"{receipt['first_run']['artifact_count']} artifacts, "
            f"{receipt['first_run']['duration_seconds']}s"
        ),
        (
            "cold restart: "
            f"{receipt['cold_restart']['verified_artifact_count']} verified, "
            f"{receipt['cold_restart']['duration_seconds']}s, "
            f"semantic_equality={receipt['cold_restart']['semantic_equality']}"
        ),
        f"receipt: {receipt['receipt_path']}",
        f"receipt sha256: {receipt['receipt_sha256']}",
        f"action: {receipt['action']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Fresh replay directory under ROOT/runtime.",
    )
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--postgres-bin-dir", type=Path, default=None)
    parser.add_argument(
        "--discard-data",
        action="store_true",
        help="Remove the PostgreSQL data directory after the receipt is written.",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    root = args.root.resolve()
    work_dir = args.work_dir
    if work_dir is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        work_dir = root / "runtime" / f"m1-postgres-cold-replay-{timestamp}"

    receipt = run_m1_postgres_cold_replay(
        root=root,
        work_dir=work_dir,
        postgres_bin_dir=args.postgres_bin_dir,
        port=args.port,
        keep_data=not args.discard_data,
    )
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(_report(receipt))
    if receipt.get("action") != "no_order":
        print("ERROR: no_order contract violated", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
