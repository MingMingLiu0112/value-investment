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
from value_investment_agent.application.historical_validation.event_source_review import prepare_event_source_review
from value_investment_agent.application.historical_validation.execution_scenario import replay_execution_scenario
from value_investment_agent.application.historical_validation.reverse_equity_expectations import reverse_equity_expectations
from value_investment_agent.application.historical_validation.disclosed_metric_review import review_disclosed_metrics
from value_investment_agent.application.historical_validation.reported_cash_proxy import reported_cash_proxies
from value_investment_agent.application.historical_validation.decision_input_review import review_historical_decision_inputs, render_decision_input_review


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
    parser.add_argument('--event-source-pages', action='store_true')
    parser.add_argument('--execution-scenario', type=Path)
    parser.add_argument('--execution-scenario-sha256')
    parser.add_argument('--reverse-equity-expectations', action='store_true')
    parser.add_argument('--metric-transcription', type=Path)
    parser.add_argument('--metric-transcription-sha256')
    parser.add_argument('--reported-cash-proxy', action='store_true')
    parser.add_argument('--decision-input-review', action='store_true')
    args = parser.parse_args()
    recovered_originals = {}
    for binding in args.recovered_event_original:
        evidence_id, separator, path = binding.partition('=')
        if not separator or not evidence_id or not path or evidence_id in recovered_originals:
            raise ValueError('recovered originals require unique ID=PATH bindings')
        recovered_originals[evidence_id] = ROOT / path
    if recovered_originals and args.event_scan is None:
        raise ValueError('recovered originals require an event scan')
    if args.event_source_pages and not all((args.event_scan, args.event_scan_sha256)):
        raise ValueError('event source pages require paired scan path and hash')
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
    if args.metric_transcription is not None or args.metric_transcription_sha256 is not None:
        if not all((args.metric_transcription, args.metric_transcription_sha256)):
            raise ValueError('metric transcription requires paired path and hash')
        result['disclosed_metric_review'] = review_disclosed_metrics(root=ROOT,
            path=ROOT / args.metric_transcription, expected_sha256=args.metric_transcription_sha256,
            workbench_path=ROOT / args.workbench, workbench_sha256=args.workbench_sha256)
    if args.reported_cash_proxy:
        if 'disclosed_metric_review' not in result:
            raise ValueError('cash proxy requires pinned metric transcription')
        result['reported_cash_proxy'] = reported_cash_proxies(result['disclosed_metric_review'])
    if args.reverse_equity_expectations:
        if not all((args.arithmetic_input, args.arithmetic_input_sha256, args.quote_bundle, args.quote_bundle_sha256)):
            raise ValueError('reverse expectations require pinned arithmetic and quote inputs')
        result['reverse_equity_expectations'] = reverse_equity_expectations(root=ROOT,
            workbench_path=ROOT / args.workbench, workbench_sha256=args.workbench_sha256,
            arithmetic_path=ROOT / args.arithmetic_input, arithmetic_sha256=args.arithmetic_input_sha256,
            quote_path=ROOT / args.quote_bundle, quote_sha256=args.quote_bundle_sha256)
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
    if args.event_source_pages:
        result['event_source_review'] = prepare_event_source_review(root=ROOT,
            path=ROOT / args.event_scan, expected_sha256=args.event_scan_sha256,
            symbol=result['symbol'], recovered_originals=recovered_originals)
    if args.execution_scenario is not None or args.execution_scenario_sha256 is not None:
        if not all((args.execution_scenario, args.execution_scenario_sha256)):
            raise ValueError('execution scenario requires paired path and hash')
        result['execution_engineering_scenario'] = replay_execution_scenario(root=ROOT,
            path=ROOT / args.execution_scenario, expected_sha256=args.execution_scenario_sha256,
            symbol=result['symbol'])
    if args.decision_input_review:
        if not all(key in result for key in ('reconstructed_financial_inputs', 'historical_price_bridge')):
            raise ValueError('decision input review requires reconstruction and historical bridge')
        result['historical_decision_input_review'] = review_historical_decision_inputs(
            result['reconstructed_financial_inputs'], result['historical_price_bridge'])
    write_new_json(output, result)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as handle:
            handle.write(render_cutoff_replay_report(result))
            if args.decision_input_review:
                handle.write('\n\n' + render_decision_input_review(result['historical_decision_input_review']))
    console_result = result
    if args.decision_input_review:
        console_result = dict(output=str(output), report=None if report is None else str(report),
            symbol=result['symbol'], decision_input_rows=len(result['historical_decision_input_review']['rows']),
            historical_execution_validated=False, action='no_order')
    elif args.event_source_pages:
        review = result['event_source_review']
        console_result = dict(output=str(output), report=None if report is None else str(report),
            symbol=result['symbol'], event_source_status=review['status'],
            announcement_count=len(review['events']), materiality_approved=False,
            action='no_order')
    print(json.dumps(console_result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
