#!/usr/bin/env python3
"""Publish a verified workbook candidate to the WPS cloud workbook atomically."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--expected-destination-sha256", required=True)
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    destination = args.destination.resolve()
    backup_dir = args.backup_dir.resolve()
    expected = args.expected_destination_sha256.upper()

    if not candidate.is_file() or not destination.is_file():
        raise SystemExit("Candidate or destination workbook is missing.")
    actual = sha256(destination)
    if actual != expected:
        raise SystemExit(
            f"Destination changed since verification: expected {expected}, got {actual}."
        )

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / "canonical-before-publish.xlsx"
    shutil.copy2(destination, backup)
    if sha256(backup) != actual:
        raise SystemExit("Pre-publication backup hash verification failed.")

    stage = destination.with_name(f".{destination.name}.codex-stage")
    try:
        shutil.copy2(candidate, stage)
        if sha256(stage) != sha256(candidate):
            raise SystemExit("Staged candidate hash verification failed.")
        os.replace(stage, destination)
    finally:
        if stage.exists():
            stage.unlink()

    published = sha256(destination)
    candidate_hash = sha256(candidate)
    if published != candidate_hash:
        raise SystemExit("Published workbook hash does not match the verified candidate.")
    print(f"published_sha256={published}")
    print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
