#!/usr/bin/env python3
"""Build a hash-pinned M3 history overlay candidate for the M3 workbook.

The candidate appends the five-page simulated history-chain addon to the
already protected M3 decision-review candidate. It never writes the canonical
WPS workbook and does not publish or order anything.
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


STAGE_FRONTEND = runpy.run_path(
    str(ROOT / "scripts" / "stage_frontend_package.py"),
    run_name="stage_frontend_package",
)


MANIFEST_SCHEMA = "m3-history-original-workbook-candidate-v1"
DEFAULT_SOURCE = (
    ROOT / "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx"
)
DEFAULT_ADDON = ROOT / "A股价值投资_M3历史链候选_20260924.xlsx"
DEFAULT_OUTPUT = (
    ROOT / "A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx"
)
DEFAULT_HISTORY_INPUT = ROOT / "tests" / "fixtures" / "m3_history_demo.json"
DEFAULT_SOURCE_SHA256 = (
    "ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3"
)
DEFAULT_ADDON_SHA256 = (
    "5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0"
)
DEFAULT_HISTORY_INPUT_SHA256 = (
    "4969a5d3b8bb80dfa743807053a75bc4e1595a5081953ecff1a83ba56c8f057c"
)
DEFAULT_GENERATED_AT = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pinned(path: Path, expected: str, label: str) -> None:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"{label} changed: expected {expected}, got {actual}")


def build_candidate(
    *,
    source: Path,
    addon: Path,
    history_input: Path,
    output: Path,
    expected_source_sha256: str,
    expected_addon_sha256: str,
    expected_history_input_sha256: str,
    generated_at: datetime,
    project_root: Path | None = None,
) -> dict:
    """Graft the fixed simulated history workbook without replacing a source sheet."""
    project_root = (project_root or ROOT).resolve()
    source = source.resolve()
    addon = addon.resolve()
    history_input = history_input.resolve()
    output = output.resolve()
    for label, path in (
        ("M3 history source", source),
        ("M3 history addon", addon),
        ("M3 history input", history_input),
        ("M3 history output", output),
    ):
        if not path.is_relative_to(project_root):
            raise ValueError(f"{label} must stay under project root")
    if output.exists():
        raise ValueError(f"M3 history overlay candidate already exists: {output}")

    _verify_pinned(source, expected_source_sha256, "M3 history source")
    _verify_pinned(addon, expected_addon_sha256, "M3 history addon")
    _verify_pinned(
        history_input,
        expected_history_input_sha256,
        "M3 simulated history input",
    )

    graft_receipt = STAGE_FRONTEND["graft"](
        source,
        addon,
        output,
        expected_source_sha256,
    )
    manifest_path = output.with_name(output.stem + ".candidate.manifest.json")
    if manifest_path.exists():
        raise ValueError(f"M3 history overlay manifest already exists: {manifest_path}")
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "action": "no_order",
        "source": str(source.relative_to(project_root)),
        "source_sha256": expected_source_sha256,
        "addon": str(addon.relative_to(project_root)),
        "addon_sha256": expected_addon_sha256,
        "history_input": str(history_input.relative_to(project_root)),
        "history_input_sha256": expected_history_input_sha256,
        "candidate": str(output.relative_to(project_root)),
        "candidate_sha256": digest(output),
        "sheet_count": len(graft_receipt["new_sheets"])
        + graft_receipt["original_sheets_preserved"],
        "new_sheets": graft_receipt["new_sheets"],
        "original_sheets_preserved": graft_receipt["original_sheets_preserved"],
        "original_parts_unchanged": graft_receipt["original_parts_unchanged"],
        "namespace": "simulated",
        "status": "candidate_verified_not_published",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--addon", type=Path, default=DEFAULT_ADDON)
    parser.add_argument("--history-input", type=Path, default=DEFAULT_HISTORY_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--expected-source-sha256",
        default=DEFAULT_SOURCE_SHA256,
    )
    parser.add_argument(
        "--expected-addon-sha256",
        default=DEFAULT_ADDON_SHA256,
    )
    parser.add_argument(
        "--expected-history-input-sha256",
        default=DEFAULT_HISTORY_INPUT_SHA256,
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
        addon=args.addon,
        history_input=args.history_input,
        output=args.output,
        expected_source_sha256=args.expected_source_sha256,
        expected_addon_sha256=args.expected_addon_sha256,
        expected_history_input_sha256=args.expected_history_input_sha256,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
