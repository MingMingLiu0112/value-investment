#!/usr/bin/env python3
"""Safely publish the Moutai case display to the canonical workbook."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True,
                   env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})


def wait_for_complete_file(path: Path, attempts: int = 40, delay_seconds: float = 0.25) -> None:
    """Avoid reading a briefly zero-length workbook while the writer closes it."""
    previous_size = None
    for _ in range(attempts):
        if path.is_file():
            size = path.stat().st_size
            if size > 0 and size == previous_size:
                return
            previous_size = size
        time.sleep(delay_seconds)
    raise TimeoutError(f"Workbook did not become stable: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    if workbook.suffix.lower() != ".xlsx" or not workbook.is_file():
        raise ValueError("Canonical workbook must be an existing .xlsx file")
    output_dir = ROOT / "runtime/workbook-backups" / ("moutai-paper-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output_dir.mkdir(parents=True, exist_ok=False)
    before = digest(workbook)
    snapshot, ready = output_dir / "original.xlsx", output_dir / "ready.xlsx"
    shutil.copy2(workbook, snapshot)
    if digest(snapshot) != before:
        raise ValueError("Snapshot hash mismatch")
    python = ROOT / "runtime/venv/Scripts/python.exe"
    payload = ROOT / "runtime/server-export-payload.json"
    run(str(python), "scripts/sync_workbook.py", str(snapshot), str(payload), str(ready))
    wait_for_complete_file(ready)
    run(str(python), "scripts/validate_workbook_output.py", str(snapshot), str(payload), str(ready))
    run(str(python), "scripts/verify_moutai_workbook_case.py", str(ready))
    if args.dry_run:
        print(json.dumps({"run": str(output_dir), "dry_run": True, "ready_sha256": digest(ready)}, ensure_ascii=False))
        return 0
    if digest(workbook) != before:
        raise ValueError("Canonical workbook changed during validation; refusing overwrite")
    staged = workbook.with_name("." + workbook.stem + ".moutai-stage.xlsx")
    try:
        shutil.copy2(ready, staged)
        if digest(staged) != digest(ready):
            raise ValueError("Staged hash mismatch")
        os.replace(staged, workbook)
    finally:
        if staged.exists():
            staged.unlink()
    after = digest(workbook)
    if after != digest(ready):
        raise ValueError("Published hash mismatch")
    publication = {"published_at": datetime.now(timezone.utc).isoformat(), "workbook": str(workbook),
                   "source_sha256": before, "published_sha256": after, "backup": str(snapshot),
                   "moutai_paper_status_verified": True}
    (output_dir / "publication.json").write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(publication, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
