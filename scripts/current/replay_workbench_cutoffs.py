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
from value_investment_agent.application.historical_validation.reconstructed_equity_input import reconstruct_equity_inputs
from value_investment_agent.application.product.common import write_new_json
from value_investment_agent.application.historical_validation.event_evidence_audit import audit_event_evidence
from value_investment_agent.application.historical_validation.historical_price_bridge import replay_historical_bridge


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbench', type=Path, required=True)
    parser.add_argument('--workbench-sha256', required=True)
    parser.add_argument('--cutoff', type=datetime.fromisoformat, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--arithmetic-input', type=Path)
    parser.add_argument('--arithmetic-input-sha256')
    parser.add_argument('--disclosure-index', type=Path)
    parser.add_argument('--disclosure-index-sha256')
    parser.add_argument('--event-scan', type=Path)
    parser.add_argument('--event-scan-sha256')
    parser.add_argument('--quote-bundle', type=Path)
    parser.add_argument('--quote-bundle-sha256')
    parser.add_argument('--recovered-event-original', action='append', default=[], metavar='ID=PATH')
    args = parser.parse_args()
    recovered_originals = {}
    for binding in args.recovered_event_original:
        evidence_id, separator, path = binding.partition('=')
        if not separator or not evidence_id or not path or evidence_id in recovered_originals:
            raise ValueError('recovered originals require unique ID=PATH bindings')
        recovered_originals[evidence_id] = ROOT / path
    if recovered_originals and args.event_scan is None:
        raise ValueError('recovered originals require an event scan')
    report = None if args.report is None else (ROOT / args.report).resolve()
    if report is not None and (not report.is_relative_to(ROOT / 'runtime') or report.exists()):
        raise ValueError('report requires a new runtime path')
    result = replay_workbench_cutoffs(root=ROOT, workbench_path=ROOT / args.workbench,
        workbench_sha256=args.workbench_sha256, cutoffs=args.cutoff)
    reconstruction_args = [args.arithmetic_input, args.arithmetic_input_sha256,
                           args.disclosure_index, args.disclosure_index_sha256]
    if any(value is not None for value in reconstruction_args):
        if not all(value is not None for value in reconstruction_args):
            raise ValueError('reconstruction requires paired arithmetic and index paths/hashes')
        result['reconstructed_financial_inputs'] = reconstruct_equity_inputs(
            root=ROOT, workbench_path=ROOT / args.workbench, workbench_sha256=args.workbench_sha256,
            arithmetic_path=ROOT / args.arithmetic_input, arithmetic_sha256=args.arithmetic_input_sha256,
            index_path=ROOT / args.disclosure_index, index_sha256=args.disclosure_index_sha256,
            cutoffs=args.cutoff)
    output = (ROOT / args.output).resolve()
    if args.event_scan is not None or args.event_scan_sha256 is not None:
        if args.event_scan is None or args.event_scan_sha256 is None:
            raise ValueError('event scan requires paired path and hash')
        result['event_evidence_audit'] = audit_event_evidence(root=ROOT,
            path=ROOT / args.event_scan, expected_sha256=args.event_scan_sha256,
            symbol=result['symbol'], recovered_originals=recovered_originals)
    if args.quote_bundle is not None or args.quote_bundle_sha256 is not None:
        if not all((args.quote_bundle, args.quote_bundle_sha256, args.event_scan, args.event_scan_sha256)):
            raise ValueError('historical bridge requires paired quote and event paths/hashes')
        result['historical_price_bridge'] = replay_historical_bridge(root=ROOT,
            workbench_path=ROOT / args.workbench, workbench_sha256=args.workbench_sha256,
            quote_path=ROOT / args.quote_bundle, quote_sha256=args.quote_bundle_sha256,
            scan_path=ROOT / args.event_scan, scan_sha256=args.event_scan_sha256,
            cutoffs=args.cutoff, recovered_originals=recovered_originals)
    if not output.is_relative_to(ROOT / 'runtime'):
        raise ValueError('replay output must remain under runtime')
    write_new_json(output, result)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as handle:
            handle.write(render_cutoff_replay_report(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
