#!/usr/bin/env python3
"""Atomically publish an already verified workbook candidate with source-hash protection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    candidate, snapshot, workbook = (path.resolve() for path in (args.candidate, args.snapshot, args.workbook))
    if not candidate.is_file() or not snapshot.is_file() or not workbook.is_file():
        raise FileNotFoundError("Candidate, snapshot and target workbook must exist")
    source_hash, current_hash, candidate_hash = digest(snapshot), digest(workbook), digest(candidate)
    if current_hash != source_hash:
        raise ValueError("Target workbook changed since the verified candidate snapshot; refusing overwrite")
    stage = workbook.with_name("." + workbook.stem + ".verified-stage.xlsx")
    if stage.exists():
        raise FileExistsError(f"Refusing to replace an existing stage file: {stage}")
    try:
        shutil.copy2(candidate, stage)
        if digest(stage) != candidate_hash:
            raise ValueError("Staged workbook hash mismatch")
        os.replace(stage, workbook)
    finally:
        if stage.exists():
            stage.unlink()
    published_hash = digest(workbook)
    if published_hash != candidate_hash:
        raise ValueError("Published workbook hash mismatch")
    receipt = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "workbook": str(workbook), "snapshot_sha256": source_hash,
        "candidate_sha256": candidate_hash, "published_sha256": published_hash,
        "source_snapshot": str(snapshot), "candidate": str(candidate),
    }
    receipt_path = candidate.parent / "verified-publication.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
