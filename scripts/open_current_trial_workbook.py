"""Resolve, verify and optionally open the one current M7 read-only trial workbook."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / "config" / "current-trial-workbook.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the current read-only M7 trial workbook.")
    parser.add_argument("--open", action="store_true", help="Open the verified workbook with the default Windows application.")
    args = parser.parse_args()
    contract = json.loads(POINTER.read_text(encoding="utf-8"))
    workbook = (ROOT / contract["workbook"]).resolve()
    manifest = (ROOT / contract["manifest"]).resolve()
    receipt = (ROOT / contract["wps_receipt"]).resolve()
    if not workbook.is_file() or not manifest.is_file() or not receipt.is_file():
        raise ValueError("current trial workbook evidence set is incomplete")
    actual_sha = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if actual_sha != contract["workbook_sha256"]:
        raise ValueError("current trial workbook hash does not match the pinned pointer")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    if manifest_payload.get("workbook_sha256") != actual_sha:
        raise ValueError("current trial manifest does not bind the workbook")
    if receipt_payload.get("sha256") != actual_sha or receipt_payload.get("status") != "passed":
        raise ValueError("current trial WPS receipt is missing or failed")
    if manifest_payload.get("action") != "no_order" or receipt_payload.get("action") != "no_order":
        raise ValueError("current trial workbook must remain no_order")
    result = {
        "status": contract["status"],
        "workbook": str(workbook),
        "sha256": actual_sha,
        "m6_operational_status": contract["m6_operational_status"],
        "initial_assisted_use": contract["initial_assisted_use"],
        "action": "no_order",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.open:
        if os.name != "nt":
            raise ValueError("--open is supported only on Windows")
        os.startfile(workbook)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
