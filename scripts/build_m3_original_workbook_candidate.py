#!/usr/bin/env python3
"""Build a hash-pinned M3 decision-review candidate for the original workbook.

The candidate replaces only the derived ``00_决策复核`` sheet.  All other
sheet XML parts are retained byte-for-byte, the frozen M1 input and M1
preregistration are verified by SHA-256, and no sheet is atomically published
by this script.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_sample_preregistration import (
    load_m1_sample_preregistration,
)
from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
    load_integrated_runs,
)
from value_investment_agent.m3_decision_review_sheet import (
    TARGET_SHEET,
    write_m3_decision_review_addon,
)


STAGE_FRONTEND = runpy.run_path(
    str(ROOT / "scripts" / "stage_frontend_package.py"),
    run_name="stage_frontend_package",
)

MANIFEST_SCHEMA = "m3-original-workbook-candidate-v1"
DEFAULT_CANONICAL = ROOT / "A股价值投资_Agent前端智能跟踪模板.xlsx"
DEFAULT_INPUT = (
    ROOT / "runtime" / "m1-post-review-20260923T114228Z" / "integrated-runs.json"
)
DEFAULT_PREREGISTRATION = (
    ROOT / "config" / "m1-fixed-sample-preregistration-v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx"
)
DEFAULT_CANONICAL_SHA256 = (
    "64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911"
)
DEFAULT_INPUT_SHA256 = (
    "b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459"
)
DEFAULT_PREREGISTRATION_SHA256 = (
    "5b7df98f8781080f66e5e053b8d0015f0b7c7eee9e27e8a10f7b0fe7990ab5b1"
)
DEFAULT_GENERATED_AT = datetime(
    2026, 9, 23, 11, 42, 28, 970300, tzinfo=timezone.utc
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pinned(path: Path, expected: str, label: str) -> None:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"{label} changed: expected {expected}, got {actual}")


def build_candidate(
    *,
    source: Path,
    input_path: Path,
    preregistration_path: Path,
    output: Path,
    expected_source_sha256: str,
    expected_input_sha256: str,
    expected_preregistration_sha256: str,
    generated_at: datetime,
    project_root: Path | None = None,
) -> dict:
    project_root = (project_root or ROOT).resolve()
    source = source.resolve()
    input_path = input_path.resolve()
    preregistration_path = preregistration_path.resolve()
    output = output.resolve()
    if not output.is_relative_to(project_root):
        raise ValueError("M3 original workbook candidate must stay under project root")
    if not input_path.is_relative_to(project_root):
        raise ValueError("M3 frozen input must stay under project root")
    if output.exists():
        raise ValueError(f"M3 original workbook candidate already exists: {output}")

    _verify_pinned(source, expected_source_sha256, "Canonical workbook")
    _verify_pinned(input_path, expected_input_sha256, "Frozen M1 integrated runs")
    _verify_pinned(
        preregistration_path,
        expected_preregistration_sha256,
        "M1 preregistration",
    )

    payload, input_receipt = load_integrated_runs(project_root, input_path)
    names = {
        entry.symbol: entry.name
        for entry in load_m1_sample_preregistration(preregistration_path).companies
    }
    collection = build_nonpersonal_decision_card_collection(
        payload,
        generated_at=generated_at,
        source_run_id=input_path.parent.name,
    )
    addon = output.with_name(output.stem + ".m3-decision-addon.xlsx")
    if addon.exists():
        raise ValueError(f"M3 decision addon already exists: {addon}")
    addon_result = write_m3_decision_review_addon(
        collection,
        output=addon,
        root=project_root,
        security_names=names,
    )
    graft_receipt = STAGE_FRONTEND["replace_sheet"](
        source,
        addon,
        output,
        expected_source_sha256,
        TARGET_SHEET,
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "action": "no_order",
        "source": str(source),
        "source_sha256": expected_source_sha256,
        "candidate": str(output),
        "candidate_sha256": digest(output),
        "addon": str(addon),
        "addon_sha256": digest(addon),
        "input": input_receipt,
        "preregistration": {
            "path": str(preregistration_path.relative_to(project_root)),
            "sha256": expected_preregistration_sha256,
        },
        "target_sheet": TARGET_SHEET,
        "original_sheets_preserved": graft_receipt["original_sheets_preserved"],
        "derived_sheets_replaced": graft_receipt["derived_sheets_replaced"],
        "original_parts_unchanged": graft_receipt["original_parts_unchanged"],
        "card_count": addon_result["card_count"],
        "positive_review_count": addon_result["positive_review_count"],
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
    parser.add_argument("--source", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--preregistration", type=Path, default=DEFAULT_PREREGISTRATION
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--expected-canonical-sha256", default=DEFAULT_CANONICAL_SHA256
    )
    parser.add_argument("--expected-input-sha256", default=DEFAULT_INPUT_SHA256)
    parser.add_argument(
        "--expected-preregistration-sha256",
        default=DEFAULT_PREREGISTRATION_SHA256,
    )
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=DEFAULT_GENERATED_AT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_candidate(
        source=args.source,
        input_path=args.input,
        preregistration_path=args.preregistration,
        output=args.output,
        expected_source_sha256=args.expected_canonical_sha256,
        expected_input_sha256=args.expected_input_sha256,
        expected_preregistration_sha256=args.expected_preregistration_sha256,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
