"""Source-replayed observation work queue on top of the existing M2 policy."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from ...domain.discovery.value_candidate_selection import (
    CRITERIA, VERSION, fingerprint, observation_conditions, rank_research_candidates,
)
from ...financial_institutions import provisional_financial_type
from ...m2_discovery_engine import CYCLICAL_SECTORS, M2ScreeningPolicy
from ...m2_opportunity_discovery import discovery_receipt_from_payload
from .current_scan import _bound_json, current_scan_details
from .public_financial_input import verify_public_supplement


def select_current_value_candidates(*, root: Path, now: datetime, limit: int = 30) -> dict:
    """Read only the bound latest run. Never discover a supposedly newer directory."""
    root = root.resolve()
    try:
        path = root / '.tmp/daily-workbench-latest-run.json'
        if path.is_symlink() or path.stat().st_size > 512_000:
            raise ValueError('invalid latest-run pointer')
        run = json.loads(path.read_text(encoding='utf-8-sig'))
        if (run['schema_version'] != 'daily-workbench-run-v1' or run['action'] != 'no_order'
                or run['mode'] != 'SAFE_REFRESH' or run['marketwide_screen']['status'] != 'RESEARCH_ONLY'):
            raise ValueError('unsupported latest run')
        binding = dict(path=run['marketwide_screen']['manifest_path'],
                       sha256=run['marketwide_screen']['manifest_sha256'])
        return select_value_candidates(root=root, manifest_binding=binding, now=now, limit=limit)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        return _unavailable(error)


def _unavailable(error):
    return dict(schema_version=VERSION, rule_version=VERSION, items=[], shortlist=[], coverage={},
        source_bindings=[], blockers=['SOURCE_REVALIDATION_FAILED'], error_type=type(error).__name__,
        data_status='SOURCE_REVALIDATION_FAILED', formal_eligibility=False, action='no_order')


def select_value_candidates(*, root: Path, manifest_binding: dict, now: datetime, limit: int = 30) -> dict:
    """Explicit bound-manifest input for replay/integration; invalid evidence raises."""
    if now.tzinfo is None:
        raise ValueError('timezone-aware cutoff required')
    root = root.resolve()
    base = root / 'runtime/daily-marketwide'
    manifest = _bound_json(root, manifest_binding, base, 512_000)
    if manifest['schema_version'] != 'm2-run-manifest-v1' or manifest['summary']['action'] != 'no_order':
        raise ValueError('unsupported M2 manifest')
    scan = current_scan_details(root, manifest)
    if scan['status'] != 'SOURCE_REVALIDATED':
        raise ValueError('M2 sources failed revalidation')
    files = manifest['files']
    receipt_payload = _bound_json(root, files['receipt'], base, 20_000_000)
    receipt = discovery_receipt_from_payload(receipt_payload)
    if receipt.generated_at > now or receipt.quote_date > now.date().isoformat():
        raise ValueError('M2 snapshot not available at cutoff')
    for ref in receipt.evidence_refs:
        if ref.fetched_at > now:
            raise ValueError('M2 evidence not available at cutoff')
    financial = _bound_json(root, files['financial'], base, 150_000_000)
    ref = next(ref for ref in receipt.evidence_refs if ref.id == 'financial')
    if (ref.sha256 != files['financial']['sha256']
            or (root / ref.path).resolve() != (root / files['financial']['path']).resolve()):
        raise ValueError('financial input not consumed by M2 receipt')
    verify_public_supplement(root=root, payload=financial, evaluation_at=now)
    policy = _bound_json(root, files['policy'], base, 512_000)
    # Replay the recorded policy, not whatever future defaults happen to be.
    if policy != M2ScreeningPolicy().as_policy():
        raise ValueError('unrecognized M2 policy; explicit adapter required')
    points = {}
    for point in financial.get('points', []):
        points.setdefault(point['symbol'], []).append(point)
    evaluations = {}
    for channel, result in receipt_payload['channel_results'].items():
        for evaluation in result.get('evaluations', []):
            evaluations.setdefault(evaluation['symbol'], {})[channel] = evaluation
    # Existing receipt evaluation owns cheap-screen pass/fail; no second PE engine.
    rows = []
    for security in receipt.universe.records:
        evaluation = evaluations.get(security.symbol, {})
        industry = next((entry.get('trigger_metrics', {}).get('industry')
            for entry in evaluation.values() if entry.get('trigger_metrics', {}).get('industry')), None)
        institution = provisional_financial_type(security.name, industry or security.official_industry)
        conditions, period = observation_conditions(points.get(security.symbol, []), now=now)
        specialized = bool(institution) or any(
            entry.get('profile_status') == 'UNSUPPORTED' for entry in evaluation.values())
        if specialized:
            for condition in conditions:
                condition.update(favorable=None, applicability='NOT_APPLICABLE_FINANCIAL_INSTITUTION')
        channels = sorted(channel for channel, entry in evaluation.items()
            if entry['status'] in {'PASS', 'BUDGET_EXCLUDED'})
        cyclical = industry in CYCLICAL_SECTORS
        gaps = ['OFFICIAL_FINANCIAL_ADMISSION_REQUIRED', 'BUSINESS_AND_CAPITAL_ALLOCATION_RESEARCH_REQUIRED',
                'APPLICABLE_VALUATION_AND_PRICE_BRIDGE_REQUIRED',
                'BALANCE_SHEET_DEBT_AND_CASH_CONVERSION_NOT_ASSESSED',
                'DIVIDEND_SUSTAINABILITY_NOT_ASSESSED']
        if specialized:
            gaps.append('FINANCIAL_INSTITUTION_SPECIALIZED_RESEARCH_REQUIRED')
        if cyclical:
            gaps.append('NORMALIZED_EARNINGS_AND_NORMALIZED_DIVIDEND_REQUIRED')
        gaps.extend('OBSERVATION_' + c['status'].upper() + ':' + c['field']
                    for c in conditions if c['status'] != 'observed')
        rows.append(dict(symbol=security.symbol, company_name=security.name, industry=industry,
            profile_status='SPECIALIZED_RESEARCH_REQUIRED' if specialized else 'GENERAL_RESEARCH',
            cycle_status='NORMALIZATION_REQUIRED' if cyclical else 'NOT_CLASSIFIED_CYCLICAL',
            risk_warning='ST' in security.name.upper(),
            price_conflict=any(entry['status'] == 'CONFLICT' for entry in evaluation.values()),
            channels=channels, channel_evaluations=[dict(channel=channel, status=entry['status'],
                reason=entry['reason'], policy_version=entry.get('policy_version'))
                for channel, entry in sorted(evaluation.items())],
            conditions=conditions, period=period, blockers=gaps,
            rationale='Research work queue from observed annual indicators and inherited M2 leads; not quality admission or a buy list.',
            data_status='PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS'))
    items, shortlist = rank_research_candidates(rows, limit=limit)
    info = financial.get('public_financial_input') or {}
    bindings = [manifest_binding, *files.values()]
    if info.get('manifest'):
        bindings.append(info['manifest'])
    parameters = dict(version=VERSION, inherited_policy=policy, observation_criteria=CRITERIA,
        financial_formula_version='financial-quality-general-v1',
        ranking='eligible,favorable_desc,unfavorable_asc,missing_asc,m2_channels_desc,symbol',
        purpose='RESEARCH_SCHEDULING_ONLY', limit=limit)
    result = dict(schema_version=VERSION, rule_version=VERSION, parameters=parameters,
        parameter_sha256=fingerprint(parameters), source_bindings=bindings,
        input_sha256=fingerprint(bindings), as_of=receipt.as_of.isoformat(),
        quote_date=receipt.quote_date, available_at=receipt.generated_at.isoformat(),
        data_status='PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS', items=items, shortlist=shortlist,
        coverage=dict(universe_count=len(items), observation_company_count=sum(bool(points.get(row['symbol'])) for row in items),
            observation_count=info.get('observation_count'), research_queue_count=sum(row['research_priority_eligible'] for row in items),
            specialized_count=sum(row['profile_status'] != 'GENERAL_RESEARCH' for row in items),
            shortlist_count=len(shortlist), official_fact_admission_count=0),
        blockers=['RESEARCH_PRIORITY_NOT_BUY_SIGNAL', 'PROVIDER_OBSERVATIONS_NOT_SOURCE_VERIFIED',
                  *scan['summary']['blockers']], formal_eligibility=False, buy_eligible=False,
        strategy_validation_status='NOT_GRANTED', action='no_order')
    result['selection_sha256'] = fingerprint(result)
    return result
