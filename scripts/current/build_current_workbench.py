"""Build a symbol-neutral current-workbench request from shared research output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import build_current_workbench_for_symbol  # noqa: E402
from value_investment_agent.presentation.read_models.existing_research_report import render_existing_research_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--existing-manifest", type=Path)
    parser.add_argument("--existing-manifest-sha256")
    parser.add_argument("--arithmetic-input", type=Path)
    parser.add_argument("--arithmetic-input-sha256")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    package = None if args.package is None else (
        args.package if args.package.is_absolute() else ROOT / args.package
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = None if args.report is None else (ROOT / args.report).resolve()
    if report is not None:
        if not report.is_relative_to((ROOT / "runtime").resolve()) or report.exists():
            parser.error("report requires a new runtime path")
        if args.existing_manifest is None:
            parser.error("report requires existing-result mode")
    result = build_current_workbench_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        package_path=package,
        output_path=output,
        existing_manifest_path=None if args.existing_manifest is None else ROOT / args.existing_manifest,
        existing_manifest_sha256=args.existing_manifest_sha256,
        arithmetic_input_path=None if args.arithmetic_input is None else ROOT / args.arithmetic_input,
        arithmetic_input_sha256=args.arithmetic_input_sha256,
    )
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_existing_research_report(result["result"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
