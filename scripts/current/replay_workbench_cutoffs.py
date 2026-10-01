"""Replay a pinned workbench at explicit observation cutoffs, without orders."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from value_investment_agent.application.historical_validation.workbench_cutoff_replay import replay_workbench_cutoffs
from value_investment_agent.presentation.read_models.existing_research_report import render_cutoff_replay_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbench', type=Path, required=True)
    parser.add_argument('--workbench-sha256', required=True)
    parser.add_argument('--cutoff', type=datetime.fromisoformat, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = None if args.report is None else (ROOT / args.report).resolve()
    if report is not None and (not report.is_relative_to(ROOT / 'runtime') or report.exists()):
        raise ValueError('report requires a new runtime path')
    result = replay_workbench_cutoffs(root=ROOT, workbench_path=ROOT / args.workbench,
        workbench_sha256=args.workbench_sha256, cutoffs=args.cutoff, output=ROOT / args.output)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as handle:
            handle.write(render_cutoff_replay_report(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
