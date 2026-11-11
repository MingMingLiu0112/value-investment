"""Prepare an independent, unsigned event-review version from retained windows."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .common import require_inside, sha256_file, write_new_json
from .daily_event_observation import verify_retained_event_coverage
from .research_materiality_reviews import (
    build_materiality_review_descriptor, prepare_materiality_review_handoff,
)
from .source_bound_inputs import source_catalog_sha256, verify_package_local_sources
from ...event_scan import EventScanResult, event_scan_from_payload
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec, descriptor_from_payload

SCHEMA = 'event-scan-research-supplement-v1'


def _read(root, binding):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or Path(binding['path']).is_absolute()
            or '..' in Path(binding['path']).parts
            or not isinstance(binding['sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('Supplement requires explicit project-relative path/SHA-256 bindings')
    path = require_inside(root, root / binding['path'], 'supplement source')
    if path.stat().st_size > 32_000_000 or sha256_file(path) != binding['sha256']:
        raise ValueError('Supplement source hash/budget mismatch: ' + binding['path'])
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError('Supplement source must be a JSON object')
    return payload


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def _scan(root, package, observations, coverage_from, review_cutoff, generated_at):
    if not isinstance(observations, list) or not 1 <= len(observations) <= 3:
        raise ValueError('Supplement requires one to three explicit retained windows')
    validity = package.get('model_validity_input')
    if not isinstance(validity, dict) or validity.get('events'):
        raise ValueError('Supplement requires non-conflicting declared model validity')
    valid_from = date.fromisoformat(validity['valid_from'])
    if not coverage_from < valid_from <= review_cutoff:
        raise ValueError('Supplement must cover both pre-model and model validity windows')
    next_day, announcements, refs, acquired = coverage_from, {}, [], []
    for index, binding in enumerate(observations):
        observation = _read(root, binding)
        start, end = (date.fromisoformat(observation[key]) for key in ('scan_from', 'scan_to'))
        if start != next_day or end > review_cutoff:
            raise ValueError('Supplement windows must be ordered, exact and contiguous')
        verify_retained_event_coverage(root, observation, symbol=package['symbol'],
            required_from=start, required_to=end, now=generated_at)
        scan = event_scan_from_payload(_read(root, observation['scan_binding']))
        prefix = 'window-' + str(index) + ':'
        refs.append(dict(id=prefix + 'observation', **binding))
        refs.append(dict(id=prefix + 'scan', **observation['scan_binding']))
        refs.extend(dict(ref, id=prefix + ref['id']) for ref in scan.evidence_refs)
        acquired.append(scan.retrieved_at)
        for item in scan.announcements:
            if item.announcement_id in announcements:
                raise ValueError('Conflicting or repeated announcement across retained windows')
            announcements[item.announcement_id] = replace(item,
                pre_model=item.published_at.date() < valid_from,
                review_status='PENDING_HUMAN_REVIEW', materiality_candidate=True,
                evidence_refs=tuple(dict(ref, id=prefix + ref['id']) for ref in item.evidence_refs))
        next_day = end + timedelta(days=1)
    if next_day != review_cutoff + timedelta(days=1):
        raise ValueError('Supplement does not cover the requested complete cutoff')
    if not any(item.pre_model for item in announcements.values()):
        raise ValueError('Supplement requires explicit acquired pre-model announcements for review')
    if len(announcements) > 128:
        raise ValueError('Supplement exceeds 128-announcement review budget')
    previous_ref = validity.get('event_scan_ref')
    if previous_ref:
        previous = event_scan_from_payload(_read(root, {key: previous_ref[key] for key in ('path', 'sha256')}))
        for item in previous.announcements:
            current = announcements.get(item.announcement_id)
            if (current is None or (item.title, item.source_url, item.published_at) !=
                    (current.title, current.source_url, current.published_at)
                    or {(r['path'], r['sha256']) for r in item.evidence_refs} !=
                       {(r['path'], r['sha256']) for r in current.evidence_refs}):
                raise ValueError('Supplement cannot omit or replace previously bound announcements')
    scan = EventScanResult(schema_version='m1-event-scan-v1', symbol=package['symbol'], provider='cninfo',
        scan_from=coverage_from, scan_to=review_cutoff, validity_from=valid_from, validity_to=review_cutoff,
        status='PENDING_HUMAN_REVIEW', coverage_status='COMPLETE',
        pre_model_review_status='PENDING_HUMAN_REVIEW', announcements=tuple(announcements.values()),
        blockers=('PRE_MODEL_AND_VALIDITY_EVENTS_REQUIRE_EXACT_MODEL_REVIEW',),
        evidence_refs=tuple(refs), retrieved_at=max(acquired),
        parser_version='retained-cninfo-window-composition-v1')
    return dict(scan.as_policy(), composition=dict(generated_at=generated_at.isoformat(),
        observation_bindings=observations, acquisition_time_basis='LATEST_RETAINED_ACQUISITION_NOT_NEW_FETCH'))


def _package(original, predecessor, scan_binding, generated_at):
    package = deepcopy(original)
    now = generated_at.astimezone(ZoneInfo('Asia/Shanghai'))
    stamp, day = now.isoformat(), now.date().isoformat()
    version = 'event-supplement-' + now.strftime('%Y%m%dT%H%M%S%f') + '-' + scan_binding['sha256'][:12]
    package.update(package_version=version, descriptor_version=version, run_id=version,
        quote=None, valuation_approval=None, entry_thesis=None, investment_consistency_review=None)
    package.pop('input_sha256', None)
    for key in ('human_research_approval', 'event_materiality_review', 'research_reviews'):
        package.pop(key, None)
    package['point_in_time'].update(research_as_of=day, available_at=stamp, computed_at=stamp)
    case = package['research_case']
    case.update(as_of=day, generated_at=stamp, run_id=version, research_version=version,
                research_status='DATA_CHECK', valuation_status='NOT_ASSESSED', quote_date=None)
    case['missing_date_reasons'] = dict(case.get('missing_date_reasons') or {},
        quote_date='Unsigned event supplement does not acquire or admit a quote')
    case['financial_summary'] = dict(case.get('financial_summary') or {}, event_scan_supplement=dict(
        predecessor=predecessor, prior_research_as_of=original['point_in_time']['research_as_of'],
        valuation_date_retained=original['point_in_time']['valuation_date'],
        valuation_recomputed=False, economic_approval=False))
    package['facts']['verified'] = False
    package['supersedes'] = dict(predecessor, reason='Independent unsigned event-review context')
    ref = dict(id='event-supplement-' + scan_binding['sha256'], symbol=package['symbol'], **scan_binding)
    package['model_validity_input'] = dict(package['model_validity_input'], event_scan_ref=ref,
        event_scan_evidence_refs=[ref], blockers=list(dict.fromkeys([
            *package['model_validity_input'].get('blockers', []), 'pending_complete_event_materiality_review'])))
    package['dependencies']['scan_watermark'] = scan_binding['sha256']
    package['sources'].append(dict(id=ref['id'], kind='research_artifact', location=ref['path'],
        local_path=ref['path'], sha256=ref['sha256'], retrieved_at=stamp, source_available_at=stamp,
        availability_basis='ACTUAL_READ_AND_COMPOSITION_NOT_HISTORICAL_ACQUISITION',
        parser_version='retained-cninfo-window-composition-v1'))
    contract = package['source_contract']
    contract.update(cutoff_at=stamp, event_coverage_status='COMPLETE', strict_contemporaneous_pit='NOT_PROVEN',
                    source_catalog_sha256=source_catalog_sha256(package['sources']))
    return package


def prepare_event_scan_supplement(*, root: Path, package_binding: dict, observation_bindings: list[dict],
                                  coverage_from: date, review_cutoff: date, output_dir: Path) -> dict:
    root = root.resolve()
    runtime = require_inside(root, root / 'runtime', 'event supplement runtime')
    output = require_inside(runtime, output_dir, 'event supplement output')
    if output.exists():
        raise FileExistsError('Event supplement requires a fresh independent output directory')
    original = _read(root, package_binding)
    if original.get('schema_version') != 'm1-valuation-package-v2':
        raise ValueError('Event supplement requires an existing source-bound research package')
    verify_package_local_sources(root, original)
    build_descriptor(original, root=root)
    generated_at = datetime.now(timezone.utc)
    scan = _scan(root, original, observation_bindings, coverage_from, review_cutoff, generated_at)
    output.mkdir(parents=True)
    scan_path = output / 'event-scan.json'
    write_new_json(scan_path, scan)
    scan_binding = _binding(root, scan_path)
    package = _package(original, package_binding, scan_binding, generated_at)
    verify_package_local_sources(root, package)
    descriptor = build_descriptor(package, root=root)
    package_path = output / 'package.json'
    write_new_json(package_path, package)
    new_package = _binding(root, package_path)
    descriptor = build_materiality_review_descriptor(root=root, package_binding=new_package, scan_binding=scan_binding)
    build_research_run_spec(descriptor)
    write_new_json(output / 'descriptor.json', descriptor.as_policy())
    handoff = prepare_materiality_review_handoff(root=root, package_path=package_path,
        package_sha256=new_package['sha256'], scan_path=scan_path, scan_sha256=scan_binding['sha256'])
    write_new_json(output / 'materiality-handoff.json', handoff)
    result = dict(schema_version=SCHEMA, status='EXTERNAL_REVIEW_REQUIRED', action='no_order',
        symbol=package['symbol'], generated_at=generated_at.isoformat(), predecessor=package_binding,
        observation_bindings=observation_bindings, coverage_from=coverage_from.isoformat(),
        review_cutoff=review_cutoff.isoformat(), package_binding=new_package, scan_binding=scan_binding,
        descriptor_binding=_binding(root, output / 'descriptor.json'),
        handoff_binding=_binding(root, output / 'materiality-handoff.json'), model_context=handoff['model_context'],
        pre_model_announcement_count=sum(item['pre_model'] for item in scan['announcements']),
        announcement_count=len(scan['announcements']), approval_changed=False, materiality_approved=False,
        research_admitted=False, price_admitted=False, valuation_recomputed=False, position_guidance=None)
    write_new_json(output / 'supplement.json', result)
    verify_event_scan_supplement(root=root, binding=_binding(root, output / 'supplement.json'))
    return result


def verify_event_scan_supplement(*, root: Path, binding: dict) -> dict:
    root = root.resolve()
    result = _read(root, binding)
    if (result.get('schema_version') != SCHEMA or result.get('status') != 'EXTERNAL_REVIEW_REQUIRED'
            or result.get('action') != 'no_order' or result.get('position_guidance') is not None
            or any(result.get(key) is not False for key in ('approval_changed', 'materiality_approved',
                'research_admitted', 'price_admitted', 'valuation_recomputed'))):
        raise ValueError('Event supplement cannot carry economic admission or approvals')
    generated_at = datetime.fromisoformat(result['generated_at'])
    if generated_at.utcoffset() is None or generated_at > datetime.now(timezone.utc):
        raise ValueError('Supplement construction time must be aware and available')
    original = _read(root, result['predecessor'])
    verify_package_local_sources(root, original)
    build_descriptor(original, root=root)
    expected_scan = _scan(root, original, result['observation_bindings'], date.fromisoformat(result['coverage_from']),
                          date.fromisoformat(result['review_cutoff']), generated_at)
    scan = _read(root, result['scan_binding'])
    if scan != expected_scan or _read(root, result['package_binding']) != _package(
            original, result['predecessor'], result['scan_binding'], generated_at):
        raise ValueError('Supplement differs from replayed sources or registered predecessor')
    descriptor = build_materiality_review_descriptor(root=root, package_binding=result['package_binding'],
                                                     scan_binding=result['scan_binding'])
    saved_descriptor = _read(root, result['descriptor_binding'])
    descriptor_from_payload(saved_descriptor)
    if saved_descriptor != descriptor.as_policy():
        raise ValueError('Supplement descriptor differs from replay')
    expected_handoff = prepare_materiality_review_handoff(root=root,
        package_path=root / result['package_binding']['path'], package_sha256=result['package_binding']['sha256'],
        scan_path=root / result['scan_binding']['path'], scan_sha256=result['scan_binding']['sha256'])
    if (_read(root, result['handoff_binding']) != expected_handoff or
            result['model_context'] != expected_handoff['model_context'] or result['symbol'] != original['symbol']
            or result['announcement_count'] != len(scan['announcements'])
            or result['pre_model_announcement_count'] != sum(item['pre_model'] for item in scan['announcements'])):
        raise ValueError('Supplement handoff/context/announcement set differs from replay')
    _read(root, binding)
    return result


def _consumption_scope(package):
    return dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='event_scan_supplement_independent_consumption',
        blocker_id='pending_complete_event_materiality_review',
        reopen_condition_met=False, new_evidence_ids=[])


def _event_only_consumption(root, supplement_binding, schedule_binding, workbench_binding, packet_binding):
    from .research_review_packet import project_research_review_packet

    supplement = verify_event_scan_supplement(root=root, binding=supplement_binding)
    package = _read(root, supplement['package_binding'])
    if _read(root, schedule_binding) != _consumption_scope(package):
        raise ValueError('Event supplement consumption requires its exact non-reopening research scope')
    workbench = _read(root, workbench_binding)
    packet = project_research_review_packet(root=root,
        package_path=root / supplement['package_binding']['path'],
        package_sha256=supplement['package_binding']['sha256'],
        workbench_path=root / workbench_binding['path'], workbench_sha256=workbench_binding['sha256'])
    handoff = _read(root, supplement['handoff_binding'])
    context = supplement['model_context']
    valuation = workbench.get('valuation') or {}
    if (workbench.get('input_descriptor_sha256') != context['input_descriptor_sha256']
            or packet['input_descriptor_sha256'] != context['input_descriptor_sha256']
            or handoff['model_context'] != context
            or _read(root, packet_binding) != packet
            or workbench['research_receipt']['input_sha256'].get('schedule_request') != schedule_binding['sha256']
            or package['facts']['verified'] is not False
            or package['research_case']['valuation_status'] != 'NOT_ASSESSED'
            or valuation.get('status') != 'not_ready'
            or any(valuation.get(key) is not None for key in ('bear_value', 'base_value', 'bull_value'))):
        raise ValueError('Event-only consumption cannot claim a valued or differently bound G3 candidate')
    handoff_ref = supplement['handoff_binding']
    consumer = dict(entrypoint='scripts/current/review_materiality.py', arguments=[
        'consume', '--handoff', handoff_ref['path'], '--handoff-sha256', handoff_ref['sha256'],
        '--response', '<SIGNED_RESPONSE_PATH>', '--response-sha256', '<SIGNED_RESPONSE_SHA256>',
        '--trust-root', '<PINNED_TRUST_ROOT_PATH>', '--trust-root-sha256', '<PINNED_TRUST_ROOT_SHA256>',
        '--output', '<NEW_RUNTIME_DIRECTORY>'])
    return dict(schema_version='consumed-event-scan-supplement-v1', status='EVENT_MATERIALITY_SIGNATURE_REQUIRED',
        action='no_order', symbol=supplement['symbol'], supplement_binding=supplement_binding,
        schedule_binding=schedule_binding, workbench_binding=workbench_binding,
        review_packet_binding=packet_binding, handoff_binding=handoff_ref, model_context=context,
        model_context_scope='ACTUALLY_CONSUMED', candidate_binding=None,
        g3_candidate_status='UNAVAILABLE_UNASSESSED_VALUATION', valuation_status=valuation['status'],
        valuation_artifact_created=True, valuation_recomputed=False,
        announcement_count=supplement['announcement_count'],
        pre_model_announcement_count=supplement['pre_model_announcement_count'],
        approval_changed=False, materiality_approved=False, research_admitted=False,
        price_admitted=False, position_guidance=None, consumer=consumer)


def consume_event_scan_supplement(*, root: Path, supplement_binding: dict, output_dir: Path) -> dict:
    """Consume through the ordinary scheduler/application; prepare event signing only.

    The shared model emits its genuine not-ready valuation artifact. This path
    never marks facts verified, selects economics or constructs a G3 candidate.
    Evidence-stop reopening would write shared claims and needs its existing flow.
    """
    from ...domain.research.evidence_stop import evidence_stops_from_payload
    from ...infrastructure.evidence.evidence_stop_schedule import resolved_evidence_stop_ids
    from .workbench import build_current_workbench_for_symbol
    from .research_review_packet import build_research_review_packet

    root = root.resolve()
    runtime = require_inside(root, root / 'runtime', 'event consumption runtime')
    output = require_inside(runtime, output_dir, 'event consumption output')
    if output.exists():
        raise FileExistsError('Event consumption requires a fresh independent output directory')
    supplement = verify_event_scan_supplement(root=root, binding=supplement_binding)
    package = _read(root, supplement['package_binding'])
    ledger_path = root / 'config/research-evidence-stop-ledger-v1.json'
    ledger = _binding(root, ledger_path)
    stops = evidence_stops_from_payload(_read(root, ledger))
    resolved = resolved_evidence_stop_ids(root)
    if any(stop.symbol == supplement['symbol'] and stop.stop_id not in resolved for stop in stops):
        raise ValueError('Active Evidence Stop requires the existing scoped reopen flow; no shared claim written')
    output.mkdir(parents=True)
    scope = _consumption_scope(package)
    scope_path = output / 'schedule-request.json'
    write_new_json(scope_path, scope)
    scope_binding = _binding(root, scope_path)
    workbench_path = output / 'workbench.json'
    build_current_workbench_for_symbol(root=root, symbol=supplement['symbol'],
        package_path=root / supplement['package_binding']['path'], output_path=workbench_path,
        schedule_request=scope, schedule_request_sha256=scope_binding['sha256'])
    packet_path = output / 'consumed-review.json'
    build_research_review_packet(root=root, package_path=root / supplement['package_binding']['path'],
        package_sha256=supplement['package_binding']['sha256'], workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path), output_path=packet_path)
    result = _event_only_consumption(root, supplement_binding, scope_binding,
                                    _binding(root, workbench_path), _binding(root, packet_path))
    _read(root, ledger)
    write_new_json(output / 'consumption.json', result)
    return verify_consumed_event_scan_supplement(root=root, binding=_binding(root, output / 'consumption.json'))


def verify_consumed_event_scan_supplement(*, root: Path, binding: dict) -> dict:
    """Replay consumed artifact bindings and the production review-packet projection."""
    root = root.resolve()
    result = _read(root, binding)
    expected = _event_only_consumption(root, result['supplement_binding'], result['schedule_binding'],
                                     result['workbench_binding'], result['review_packet_binding'])
    if result != expected:
        raise ValueError('Consumed event supplement differs from verified inputs and signing scope')
    _read(root, binding)
    return result
