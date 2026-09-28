#!/usr/bin/env python3
"""Thin CLI for the logical registry of root artifacts retained in place."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from value_investment_agent.application.architecture import (  # noqa: E402
    build_artifact_relocation_inventory,
)


def _tracked_paths(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return tuple(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def _configured_workbook_path(root: Path) -> Path:
    configured = os.environ.get("WORKBOOK_PATH")
    if not configured:
        env_file = root / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("WORKBOOK_PATH="):
                    configured = line.split("=", 1)[1].strip().strip("\"").strip("'")
                    break
    if not configured:
        raise ValueError("WORKBOOK_PATH is not configured")
    workbook = Path(configured).expanduser().resolve()
    if not workbook.is_file():
        raise ValueError("Configured WORKBOOK_PATH is not an accessible file")
    return workbook


def _registry_payload(
    root: Path, inventory: dict[str, object], workbook_path: Path
) -> dict[str, object]:
    pointer_path = root / "config" / "current-trial-workbook.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    workbook_hash = sha256(workbook_path.read_bytes()).hexdigest()
    if workbook_hash != pointer.get("canonical_workbook_sha256"):
        raise ValueError("WORKBOOK_PATH hash does not match the current trial pointer")

    records = []
    for item in inventory["artifacts"]:
        is_root_workbook = (
            item["path"] == "A股价值投资_Agent前端智能跟踪模板.xlsx"
        )
        records.append(
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "tracked": item["tracked"],
                "status": (
                    "REPOSITORY_REFERENCE_SNAPSHOT"
                    if is_root_workbook
                    else item["classification"]
                ),
                "current_or_historical": (
                    "HISTORICAL_OR_REFERENCE"
                    if is_root_workbook
                    else (
                        "CURRENT"
                        if item["classification"] == "CANONICAL_WORKBOOK"
                        else "HISTORICAL_OR_CANDIDATE"
                    )
                ),
                "successor": (
                    "WORKBOOK_PATH"
                    if is_root_workbook
                    else (
                        item["path"]
                        if item["classification"] == "CANONICAL_WORKBOOK"
                        else "config/current-trial-workbook.json"
                    )
                ),
                "recommended_action": (
                    "KEEP_AS_REFERENCE"
                    if is_root_workbook
                    else item["recommended_action"]
                ),
                "reason_kept": (
                    "Repository snapshot is not the configured user-facing workbook."
                    if is_root_workbook
                    else "Path, hash, pointer, manifest, or receipt provenance must remain valid."
                ),
                "relocation_blocker": "No content-addressed relocation verifier is approved for this artifact.",
                "reference_count": len(item["references"]),
            }
        )
    records.append(
        {
            "path": "WORKBOOK_PATH (local path redacted)",
            "sha256": workbook_hash,
            "size_bytes": workbook_path.stat().st_size,
            "tracked": False,
            "status": "CANONICAL_WORKBOOK",
            "current_or_historical": "CURRENT",
            "successor": "WORKBOOK_PATH",
            "recommended_action": "KEEP_CANONICAL",
            "reason_kept": "Locally resolved configured workbook; SHA-256 matches config/current-trial-workbook.json.",
            "relocation_blocker": "External configured asset; its user path is intentionally not stored in this registry.",
            "reference_count": 1,
            "location_scope": "EXTERNAL_LOCAL_CONFIGURED_PATH",
            "verified_against_pointer": True,
        }
    )
    return {
        "schema_version": "current-artifact-registry-v2",
        "action": "no_order",
        "policy": "Logical current/historical navigation. The canonical workbook is resolved from local WORKBOOK_PATH; personal paths are omitted.",
        "artifact_count": len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory = build_artifact_relocation_inventory(
        root, tracked_paths=_tracked_paths(root)
    ).as_dict()
    payload = _registry_payload(root, inventory, _configured_workbook_path(root))
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = (args.output or root / "artifacts" / "current" / "artifact-registry-v2.json").resolve()
    if not output.is_relative_to(root):
        raise ValueError("Registry output must remain under the project root")
    if output.name == "artifact-registry-v1.json" and output.exists():
        raise ValueError("The v1 registry is a preserved historical snapshot")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
