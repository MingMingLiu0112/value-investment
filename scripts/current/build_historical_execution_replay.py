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
from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.presentation.read_models.historical_execution_replay import (  # noqa: E402
    render_historical_execution_replay,
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
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    journal_path = args.journal.resolve()
    report = args.report.resolve()
    runtime = (ROOT / "runtime").resolve()
    if not all(path.is_relative_to(runtime) for path in (output, journal_path, report)):
        raise ValueError("historical execution replay outputs must remain under runtime")
    if output.exists() or journal_path.exists() or report.exists():
        raise FileExistsError("refusing to overwrite historical execution replay output")
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
