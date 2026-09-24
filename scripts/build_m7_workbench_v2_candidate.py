#!/usr/bin/env python3
"""Build the protected M7 v2 workbench with the M4/M5 joint layer.

The v1 builder remains the reproducible source for the original 90-page
workbench.  This entry point reuses the same protected graft implementation and
adds the standalone M4/M5 joint-checkpoint candidate as a seventh addon layer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


BASE_BUILDER = runpy.run_path(
    str(ROOT / "scripts" / "build_m7_workbench_candidate.py"),
    run_name="build_m7_workbench_candidate",
)


V2_MANIFEST_SCHEMA = "m7-workbench-candidate-v2"
DEFAULT_OUTPUT = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx"
)

JOINT_CHECKPOINT_SPEC = {
    "id": "m4_m5_joint_checkpoint",
    "path": ROOT / "A股价值投资_M4M5联合检查点候选_20260924.xlsx",
    "sha256": "353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612",
    "prefix": "M4M5联合_",
    "group": "M4/M5联合检查点",
    "overview_sheet": "M4M5联合_00_总览",
}

V2_ADDON_SPECS = (*BASE_BUILDER["ADDON_SPECS"], JOINT_CHECKPOINT_SPEC)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE_BUILDER["DEFAULT_BASE"])
    parser.add_argument(
        "--canonical",
        type=Path,
        default=BASE_BUILDER["DEFAULT_CANONICAL"],
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--expected-base-sha256",
        default=BASE_BUILDER["BASE_SHA256"],
    )
    parser.add_argument(
        "--expected-canonical-sha256",
        default=BASE_BUILDER["CANONICAL_SHA256"],
    )
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=BASE_BUILDER["DEFAULT_GENERATED_AT"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = BASE_BUILDER["build_candidate"](
        base=args.base,
        canonical=args.canonical,
        output=args.output,
        expected_base_sha256=args.expected_base_sha256,
        expected_canonical_sha256=args.expected_canonical_sha256,
        addon_specs=V2_ADDON_SPECS,
        generated_at=args.generated_at,
        manifest_schema=V2_MANIFEST_SCHEMA,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
