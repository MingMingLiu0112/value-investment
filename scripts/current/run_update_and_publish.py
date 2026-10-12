"""Update the registered research and safely publish through existing adapters."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from value_investment_agent.application.product.common import load_json_object, sha256_file, require_inside
from value_investment_agent.application.product.user_research_workflow import read_published_research, verify_user_update_registry
from value_investment_agent.application.product.daily_product_update import run_product_update
from value_investment_agent.presentation.daily_product_composition import compose_daily_product
from value_investment_agent.presentation.daily_product_discovery_v2 import compose_daily_product_v2, verify_discovery_bindings
from scripts.current.product_update_publication import publish_product_update, recover_interrupted_product_publications
from value_investment_agent.settings import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--symbols')
    parser.add_argument('--case-registry', type=Path)
    parser.add_argument('--case-registry-sha256')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--no-publish', '--report-only', dest='no_publish', action='store_true')
    parser.add_argument('--quote-bundle', type=Path)
    parser.add_argument('--no-collect-quote', action='store_true')
    parser.add_argument('--collect-events', action='store_true')
    parser.add_argument('--no-collect-events', action='store_true')
    parser.add_argument('--no-scan-hotspots', action='store_true')
    parser.add_argument('--agent-mode', choices=('offline', 'mock', 'none'), default='offline')
    parser.add_argument('--extensions', type=Path)
    parser.add_argument('--extensions-sha256')
    parser.add_argument('--m2-discovery-report', type=Path)
    parser.add_argument('--m2-discovery-sha256')
    parser.add_argument('--m2-queue', type=Path)
    parser.add_argument('--m2-queue-sha256')
    parser.add_argument('--m2-pending', type=Path)
    parser.add_argument('--m2-pending-sha256')
    parser.add_argument('--private-risk-config', type=Path)
    parser.add_argument('--private-risk-config-sha256')
    args = parser.parse_args()
    if (args.private_risk_config is None) != (args.private_risk_config_sha256 is None):
        parser.error('private risk config requires path and hash')
    workbook = get_settings().workbook_path.resolve()
    recover_interrupted_product_publications(root=ROOT, workbook=workbook)
    published = read_published_research(root=ROOT, workbook=workbook)
    symbols = args.symbols.split(',') if args.symbols else list(published['pending_candidates'])
    registry = verify_user_update_registry(root=ROOT, published=published, symbols=symbols)
    if (args.case_registry is None) != (args.case_registry_sha256 is None):
        parser.error('registry requires both path and hash')
    if args.case_registry and (require_inside(ROOT, ROOT/args.case_registry, 'registry') != registry
                             or sha256_file(registry) != args.case_registry_sha256):
        parser.error('registry differs from the publication-bound user registry')
    if (args.extensions is None) != (args.extensions_sha256 is None):
        parser.error('extensions require path and hash')
    extensions = {}
    if args.extensions:
        path = require_inside(ROOT, ROOT/args.extensions, 'extensions')
        if sha256_file(path) != args.extensions_sha256:
            raise ValueError('extension configuration hash mismatch')
        config = load_json_object(path, 'product extensions')
        if config.get('action') != 'no_order':
            raise ValueError('extension configuration scope mismatch')
        extensions = config['bindings']
    for role, path, digest in (
        ('value_discovery_report', args.m2_discovery_report, args.m2_discovery_sha256),
        ('value_research_queue', args.m2_queue, args.m2_queue_sha256),
        ('m2_pending_research', args.m2_pending, args.m2_pending_sha256),
    ):
        if (path is None) != (digest is None):
            parser.error(role + ' requires both path and SHA-256')
        if path is not None:
            bound = require_inside(ROOT/'runtime', ROOT/path, role)
            if sha256_file(bound) != digest:
                raise ValueError(role + ' hash mismatch')
            if role in extensions:
                parser.error(role + ' was supplied twice')
            extensions[role] = dict(path=bound.relative_to(ROOT).as_posix(), sha256=digest)
    verify_discovery_bindings(ROOT, extensions)
    if args.private_risk_config and 'dual_sleeve_report' in extensions:
        parser.error('private risk config excludes a supplied risk report')
    folder = ROOT/(args.output_dir or Path('runtime/daily-trade-assistant')/
                  (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-product'))
    def research(target):
        command = [sys.executable, '-X', 'utf8', str(ROOT/'scripts/current/run_daily_trade_assistant.py'),
                   '--symbols', ','.join(symbols), '--case-registry', str(registry),
                   '--case-registry-sha256', sha256_file(registry), '--output-dir', str(target),
                   '--report-only', '--review-packet', '--monthly-review', '--agent-mode', args.agent_mode]
        if args.no_collect_quote: command.append('--no-collect-quote')
        if args.quote_bundle: command.extend(['--quote-bundle', str(args.quote_bundle)])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
        from value_investment_agent.application.product.common import write_new_json
        write_new_json(folder/'research-command.json', dict(action='no_order',
                      exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise ValueError('研究更新未全部完成：'+(result.stderr or result.stdout)[-2000:])
        batch_path = target/'batch-receipt.json'
        if not batch_path.is_file() and len(symbols) == 1:
            path = target/'receipt.json'
            receipt = load_json_object(path, 'single company receipt')
            write_new_json(batch_path, dict(action='no_order',
                failed_case_count=int(receipt['status'] not in {
                    'RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS', 'BLOCKED_RESEARCH_ASSETS'}),
                blocked_asset_count=int(receipt['status'] == 'BLOCKED_RESEARCH_ASSETS'),
                partial_product_count=int(bool(receipt.get('preview_error'))),
                cases=[dict(symbol=symbols[0], research_as_of=receipt.get('research_as_of'),
                    receipt=dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path)))]))
        return batch_path
    def compose(target, prior, batch):
        bindings = dict(extensions)
        if args.collect_events or not args.no_collect_events:
            from datetime import date
            from zoneinfo import ZoneInfo
            from value_investment_agent.application.product.daily_event_observation import collect_daily_event_observation
            from value_investment_agent.application.product.common import write_new_json
            cases = load_json_object(registry, 'registry')['cases']
            for row in batch['cases']:
                original_binding = row['receipt']
                receipt = load_json_object(ROOT/original_binding['path'], 'company receipt')
                package = load_json_object(ROOT/cases[row['symbol']]['package'], 'research package')
                event_dir = target/'official-events'/row['symbol']
                try:
                    collect_daily_event_observation(root=ROOT, symbol=row['symbol'],
                        issuer_name=package['name'], start=date.fromisoformat(row['research_as_of']),
                        end=datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date(),
                        output_dir=event_dir, retain_raw_index=True)
                    event_path = event_dir/'observation.json'
                except (ValueError, OSError) as error:
                    event_path = target/(row['symbol']+'-official-event-failure.json')
                    write_new_json(event_path, dict(action='no_order', symbol=row['symbol'],
                        collection_status='COLLECTION_FAILED', error=str(error),
                        materiality_approved=False, research_date_advanced=False))
                receipt['outputs']['event_observation'] = dict(path=event_path.relative_to(ROOT).as_posix(),
                    sha256=sha256_file(event_path))
                receipt['original_daily_receipt_binding'] = original_binding
                path = target/(row['symbol']+'-product-research-receipt.json')
                write_new_json(path, receipt)
                row['receipt'] = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path))
        if 'hotspot_report' not in bindings and not args.no_scan_hotspots:
            from value_investment_agent.application.hotspot.manual import run_manual_scan
            try:
                scan = run_manual_scan(root=ROOT, output=target/'hotspot-observation')
                bindings['hotspot_report'] = dict(path=scan['report_path'], sha256=scan['sha256'])
            except (ValueError, OSError, KeyError, TypeError) as error:
                from value_investment_agent.application.product.common import write_new_json
                path = target/'hotspot-source-failure.json'
                state = dict(action='no_order', status='SOURCE_UNVERIFIED', observation_list=[],
                    confirmed_market_date=None, entry_review_eligible=False, reason=str(error),
                    missing_features=['verified_market_sources'])
                write_new_json(path, dict(state, semantic_content=state))
                bindings['hotspot_report'] = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path))
        if 'dual_sleeve_report' not in bindings:
            from value_investment_agent.application.product.dual_sleeve_risk import run_dual_sleeve_review
            path = target/'dual-sleeve-risk.json'
            if args.private_risk_config:
                from value_investment_agent.application.product.dual_sleeve_public_summary import export_private_risk_summary
                export_private_risk_summary(root=ROOT, config_path=args.private_risk_config,
                    config_sha256=args.private_risk_config_sha256, output_path=path)
            else:
                run_dual_sleeve_review(root=ROOT, output_path=path)
            bindings['dual_sleeve_report'] = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path))
        if 'value_discovery_report' in bindings:
            return compose_daily_product_v2(root=ROOT, folder=target, published=prior,
                                            batch=batch, extensions=bindings)
        return compose_daily_product(root=ROOT, folder=target, published=prior, batch=batch, extensions=bindings)
    result = run_product_update(root=ROOT, output_dir=folder, published=published, research_runner=research,
        composer=compose,
        publisher=lambda target, product, before: publish_product_update(root=ROOT, folder=target,
                            product=product, workbook=workbook, expected_before=before),
        publish=not args.no_publish)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['blockers'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
