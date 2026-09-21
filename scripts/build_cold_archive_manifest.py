#!/usr/bin/env python3
"""Create a hash-verified, copy-only cold-archive manifest on the server."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.db import connect
from value_investment_agent.evidence_tiering import build_cold_archive_manifest
from value_investment_agent.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, help="Only consider files fetched before YYYY-MM-DD")
    parser.add_argument("--retain-symbols", default="600519,000333,601088")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = date.fromisoformat(args.before)
    retain = {symbol.strip() for symbol in args.retain_symbols.split(",") if symbol.strip()}
    if not retain or any(not symbol.isdigit() or len(symbol) != 6 for symbol in retain):
        raise ValueError("--retain-symbols must contain six-digit codes")
    settings = get_settings()
    with connect(settings.database_url) as connection:
        rows = connection.execute("""
            SELECT disclosure_id, symbol, report_period, report_kind, published_at,
                   fetched_at, sha256, local_path, extraction_status
            FROM official_disclosures
            WHERE local_path IS NOT NULL
            ORDER BY fetched_at, symbol, report_period, disclosure_id
        """).fetchall()
    manifest = build_cold_archive_manifest(
        [dict(row) for row in rows], evidence_root=settings.evidence_directory,
        retain_symbols=retain, before=before,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidate_count": manifest["candidate_count"],
                      "candidate_bytes": manifest["candidate_bytes"], "deletion_permitted": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
