#!/usr/bin/env python3
"""Build a hash-pinned M2 original-workbook candidate without publishing it.

The M2 presentation workbook is treated as a disposable addon.  The canonical
WPS workbook is read, its original sheet parts are retained byte-for-byte, and
the M2 sheets are grafted in front only after the source SHA-256 is confirmed.
This script never atomically replaces the canonical workbook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_discovery_engine import M2ScreeningPolicy
from value_investment_agent.m2_discovery_workbook import build_discovery_workbook
from value_investment_agent.m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    DiscoveryRunReceipt,
    discovery_receipt_from_payload,
)


STAGE_FRONTEND = runpy.run_path(
    str(ROOT / "scripts" / "stage_frontend_package.py"),
    run_name="stage_frontend_package",
)
MANIFEST_SCHEMA = "m2-original-workbook-candidate-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_receipt(path: Path) -> tuple[DiscoveryRunReceipt, str]:
    if not path.is_file():
        raise ValueError(f"M2 receipt does not exist: {path}")
    data = path.read_bytes()
    receipt = discovery_receipt_from_payload(json.loads(data.decode("utf-8")))
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("M2 original workbook candidate requires action=no_order")
    return receipt, digest(path)


def build_candidate(
    *,
    source: Path,
    receipt_path: Path,
    output: Path,
    expected_source_sha256: str,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    receipt_path = receipt_path.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("M2 original workbook candidate must stay under project root")
    if output.exists():
        raise ValueError(f"M2 original workbook candidate already exists: {output}")
    if digest(source) != expected_source_sha256:
        raise ValueError("Canonical workbook changed since inspection; refusing candidate build")
    receipt, receipt_sha256 = load_receipt(receipt_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    addon = output.with_name(output.stem + ".m2-addon.xlsx")
    if addon.exists():
        raise ValueError(f"M2 addon already exists: {addon}")

    workbook = build_discovery_workbook(receipt, M2ScreeningPolicy())
    workbook.save(addon)
    graft_receipt = STAGE_FRONTEND["graft"](
        source,
        addon,
        output,
        expected_source_sha256,
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "source": str(source),
        "source_sha256": expected_source_sha256,
        "candidate": str(output),
        "candidate_sha256": digest(output),
        "addon": str(addon),
        "addon_sha256": digest(addon),
        "m2_receipt": str(receipt_path),
        "m2_receipt_sha256": receipt_sha256,
        "m2_run_id": receipt.run_id,
        "m2_rule_version": receipt.rule_version,
        "coverage_signature": receipt.coverage_signature,
        "candidate_signature": receipt.candidate_signature,
        "original_sheets_preserved": graft_receipt["original_sheets_preserved"],
        "original_parts_unchanged": graft_receipt["original_parts_unchanged"],
        "new_sheets": graft_receipt["new_sheets"],
        "status": "candidate_verified_not_published",
    }
    manifest_path = output.with_name(output.stem + ".candidate.manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_candidate(
        source=args.source,
        receipt_path=args.receipt,
        output=args.output,
        expected_source_sha256=args.expected_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
