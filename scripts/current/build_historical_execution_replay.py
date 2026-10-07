#!/usr/bin/env python3
"""Build a normalized replay from a hash-pinned frozen historical scenario."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.historical_validation.historical_execution_replay import (  # noqa: E402
    build_historical_execution_replay,
)
from value_investment_agent.application.historical_validation.ohlc_fill_feasibility import (  # noqa: E402
    audit_frozen_fill_bars,
)
from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.presentation.read_models.historical_execution_replay import (  # noqa: E402
    render_historical_execution_replay, render_historical_fill_feasibility,
)


def _write_journal(path: Path, value: list[dict]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--input-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument('--audit-existing', action='store_true')
    parser.add_argument('--result', type=Path)
    parser.add_argument('--result-sha256')
    parser.add_argument('--journal-input', type=Path)
    parser.add_argument('--journal-input-sha256')
    args = parser.parse_args()
    output = args.output.resolve()
    report = args.report.resolve()
    runtime = (ROOT / "runtime").resolve()
    if not all(path.is_relative_to(runtime) for path in (output, report)):
        raise ValueError("historical execution replay outputs must remain under runtime")
    if output.exists() or report.exists():
        raise FileExistsError("refusing to overwrite historical execution replay output")
    if args.audit_existing:
        if (any((args.input, args.input_sha256, args.journal))
                or not all((args.result, args.result_sha256,
                            args.journal_input, args.journal_input_sha256))):
            parser.error('audit-existing requires pinned result/journal-input and excludes replay inputs')
        payload = audit_frozen_fill_bars(root=ROOT, result_path=args.result,
            result_sha256=args.result_sha256, journal_path=args.journal_input,
            journal_sha256=args.journal_input_sha256)
        write_new_json(output, payload)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as handle:
            handle.write(render_historical_fill_feasibility(payload))
        print(json.dumps(dict(output=str(output), output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
            report=str(report), report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
            checked_fills=payload['checked_fills'], historical_execution_validated=False,
            action='no_order'), ensure_ascii=False))
        return 0
    if not args.input or not args.input_sha256 or not args.journal or any((
            args.result, args.result_sha256, args.journal_input, args.journal_input_sha256)):
        parser.error('replay requires input path/hash and journal output; excludes audit-existing inputs')
    journal_path = args.journal.resolve()
    if not journal_path.is_relative_to(runtime):
        raise ValueError('historical execution replay journal must remain under runtime')
    if journal_path.exists():
        raise FileExistsError('refusing to overwrite historical execution replay journal')
    payload, journal = build_historical_execution_replay(
        root=ROOT,
        input_path=args.input,
        input_sha256=args.input_sha256,
    )
    write_new_json(output, payload)
    _write_journal(journal_path, journal)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_historical_execution_replay(payload), encoding="utf-8")
    print(json.dumps({
        "symbol": payload["symbol"],
        "scenario": payload["scenario"],
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "journal": str(journal_path),
        "journal_sha256": hashlib.sha256(journal_path.read_bytes()).hexdigest(),
        "report": str(report),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "engineering_delivery": payload["engineering_delivery"],
        "current_research_admission": payload["current_research_admission"],
        "historical_execution_validated": payload["historical_execution_validated"],
        "strict_pit_admitted": payload["strict_pit_admitted"],
        "performance_claim_allowed": payload["performance_claim_allowed"],
        "action": payload["action"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
