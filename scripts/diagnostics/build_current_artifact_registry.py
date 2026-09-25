#!/usr/bin/env python3
"""Thin CLI for the logical registry of root artifacts retained in place."""

from __future__ import annotations

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory = build_artifact_relocation_inventory(
        root, tracked_paths=_tracked_paths(root)
    ).as_dict()
    records = []
    for item in inventory["artifacts"]:
        records.append(
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "tracked": item["tracked"],
                "status": item["classification"],
                "current_or_historical": (
                    "CURRENT" if item["classification"] == "CANONICAL_WORKBOOK" else "HISTORICAL_OR_CANDIDATE"
                ),
                "successor": (
                    item["path"]
                    if item["classification"] == "CANONICAL_WORKBOOK"
                    else "config/current-trial-workbook.json"
                ),
                "recommended_action": item["recommended_action"],
                "reason_kept": "Path, hash, pointer, manifest, or receipt provenance must remain valid.",
                "relocation_blocker": "No content-addressed relocation verifier is approved for this artifact.",
                "reference_count": len(item["references"]),
            }
        )
    payload = {
        "schema_version": "current-artifact-registry-v1",
        "action": "no_order",
        "policy": "Logical current/historical navigation only; this registry does not move or supersede provenance.",
        "artifact_count": len(records),
        "records": records,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = (args.output or root / "artifacts" / "current" / "artifact-registry-v1.json").resolve()
    if not output.is_relative_to(root):
        raise ValueError("Registry output must remain under the project root")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
