"""Exact source-native research intake, separate from frozen finite v1 compilers.

Shared review callers need an explicit schema dispatcher before registration or
signing. This module never emits a fake v1 candidate or signs/approves anything.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .common import load_json_object, require_inside, sha256_file, write_new_json, write_new_bytes
from .company_research import _serialize_outcome
from .decision_surface import verify_current_decision_workbench
from .incremental_validity import read_bound_json
from .research_review_packet import project_research_review_packet
from .research_reviews import build_research_review_model_context
from .source_bound_inputs import verify_package_local_sources
from .pending_research_candidate import verify_pending_research_candidate as _verify_frozen_v1
from ...domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs
from ...m1_valuation_package_builder import build_descriptor
from ...research_application import ResearchApplicationService
from ...research_input import build_research_run_spec


SCHEMA = 'source-native-pending-research-candidate-v2'
IMPLEMENTATIONS = (
    'src/value_investment_agent/application/product/source_native_candidate_v2.py',
    'src/value_investment_agent/domain/valuation/source_native_cash_v1.py',
)
GROUP_FIELDS = {
    'EARNINGS': ['facts.operating_inputs', 'facts.scenario_inputs'],
    'DISTRIBUTION': ['research_case.financial_summary', 'assumptions'],
    'DURATION': ['facts.scenario_inputs', 'assumption_bindings'],
    'COST_TERMINAL': ['facts.scenario_inputs', 'facts.valuation_timing'],
    'EVENT_MODEL': ['model_validity_input', 'source_contract'],
}
CANDIDATE_FIELDS = set('schema_version symbol status action generated_at input_mode source_package_binding '
    'native_cash_ledger_binding candidate_research_as_of model_context model_context_scope candidate_valuation '
    'execution_status research_blockers schedule_gate schedule_consumed review_groups review_packet_binding '
    'implementation_bindings approval_changed research_admitted price_admitted canonical_written '
    'registered_current_case_changed primary_registered position_guidance strict_contemporaneous_pit '
    'source_bindings'.split())


def _groups():
    return [dict(id=name, field_paths=fields, question='Review exact consumed '+name+' inputs.',
        support='Bound original financial facts and conditional cash/equity ledger are attached.',
        countercase='Timing, remittance, maintenance, cash floor and terminal conditions can fail.',
        impact='Group review is not whole-model G3, current market validity or order approval.')
        for name, fields in GROUP_FIELDS.items()]


def _bound(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def _stamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('Source-native availability requires a timezone')
    return result


def _equal_numbers(left, right):
    if isinstance(right, dict):
        return isinstance(left, dict) and set(left) == set(right) and all(
            _equal_numbers(left[key], value) for key, value in right.items())
    if isinstance(right, list):
        return isinstance(left, list) and len(left) == len(right) and all(
            _equal_numbers(a, b) for a, b in zip(left, right))
    try:
        return not isinstance(left, bool) and Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def replay_source_native_inputs(*, root: Path, package_binding: dict, ledger_binding: dict,
                               now: datetime) -> dict:
    """Cold-run existing typed application; no scheduler/registry/output writes."""
    root = root.resolve()
    package_binding, ledger_binding = deepcopy(package_binding), deepcopy(ledger_binding)
    if now.utcoffset() is None:
        raise ValueError('Source-native replay requires an aware trusted clock')
    package_path, package = read_bound_json(root, package_binding, 'source-native original package')
    ledger_path, ledger = read_bound_json(root, ledger_binding, 'source-native cash ledger')
    if _bound(root, package_path) != package_binding or _bound(root, ledger_path) != ledger_binding:
        raise ValueError('Source-native inputs require exact canonical project path/hash identities')
    if (package.get('schema_version') != 'm1-valuation-package-v2' or package.get('quote') is not None
            or any(package.get(key) is not None for key in ('valuation_approval', 'human_research_approval',
                'research_reviews', 'event_materiality_review', 'entry_thesis', 'investment_consistency_review'))
            or package['facts']['confidence'] != '\u4f4e' or ledger.get('action') != 'no_order'):
        raise ValueError('Source-native intake requires unapproved LOW source-bound inputs')
    pit = package['point_in_time']
    if any(_stamp(pit[field]) > now for field in ('computed_at', 'available_at')):
        raise ValueError('Source-native package is not yet available')
    if 'generated_at' in ledger and _stamp(ledger['generated_at']) > min(now, _stamp(pit['available_at'])):
        raise ValueError('Source-native ledger is not yet available at the package cutoff')
    if ledger['financial_basis'] != pit['valuation_date'] or package['facts']['as_of'] != pit['valuation_date']:
        raise ValueError('Source-native financial/valuation basis mismatch')
    catalog = package['sources']
    ledger_sources = [source for source in catalog if source.get('local_path') == ledger_binding['path']
                      and source.get('sha256') == ledger_binding['sha256']]
    if len(ledger_sources) != 1:
        raise ValueError('Cash ledger is not a unique bound package research source')
    ledger_id = ledger_sources[0]['id']
    declarations = [value for value in package['research_case']['financial_summary'].values()
        if isinstance(value, dict) and 'joint_assumptions' in value and 'source_result_sha256' in value]
    if (len(declarations) != 1 or declarations[0].get('scope') != 'CONDITIONAL_RESEARCH_NOT_G3'
            or declarations[0].get('branch') != 'TIMING_DELAY'
            or declarations[0]['source_result_sha256'] != ledger_binding['sha256']
            or declarations[0]['joint_assumptions'] != ledger['plan']
            or declarations[0].get('historical_cash_bridge') != ledger['history']):
        raise ValueError('Source-native economic narrative differs from bound cash assumptions/history')
    if not any(ref.get('id') == ledger_id and all(ref.get(k) == ledger_binding[k]
            for k in ('path', 'sha256')) for ref in package['facts']['evidence_refs']):
        raise ValueError('Cash ledger is not bound to consumed facts')
    sources = verify_package_local_sources(root, package)
    # Freeze expected identities before computation; never reseal changed bytes.
    closure = {}
    for ref in [package_binding, ledger_binding,
                *[dict(path=path.relative_to(root).as_posix(), sha256=digest) for path, digest in sources]]:
        if ref['path'] in closure and closure[ref['path']] != ref:
            raise ValueError('Source-native consumed source identity conflict')
        closure[ref['path']] = deepcopy(ref)
    scenarios = replay_timing_delay_inputs(plan=ledger['plan'],
        scenarios=ledger['cases']['TIMING_DELAY'], history=ledger['history'],
        opening_book=package['facts']['operating_inputs']['start_book_equity'])
    if not _equal_numbers(package['facts']['scenario_inputs'], scenarios):
        raise ValueError('Source-native scenarios differ from recomputed cash/equity inputs')
    for assumption in package['assumptions']['assumptions']:
        if not any(ref.get('id') == ledger_id and all(ref.get(k) == ledger_binding[k]
                for k in ('path', 'sha256')) for ref in assumption['evidence_refs']):
            raise ValueError('Source-native assumption lacks cash-ledger evidence')
    descriptor = build_descriptor(package, root=root)
    spec = build_research_run_spec(descriptor)
    outcome = ResearchApplicationService(now_utc=lambda: now).run_company_research(spec)
    native = _serialize_outcome(outcome)
    if (not native.get('valuation') or native['valuation']['confidence'] != '\u4f4e'
            or native['valuation']['status'] != 'conditional_research_only'
            or native['decision_recommendation'].get('recommendation_type',
                native['decision_recommendation'].get('recommendation_action')) != 'NO_ACTION'):
        raise ValueError('Source-native replay cannot grant investment authority')
    workbench = dict(schema_version='product-current-workbench-request-v1', generated_at=now.isoformat(),
        command='current_workbench', symbol=package['symbol'], action='no_order',
        research_status=native['status'], research_blockers=native['blockers'],
        portfolio_input_status='BLOCKED_PRIVATE_INPUT', position_guidance=None,
        schedule_gate=None, evidence_stops=[], canonical_workbook_written=False,
        suggested_state='NO_ACTION', input_descriptor_sha256=descriptor.input_sha256,
        research_receipt=dict(command='company_research', symbol=package['symbol'], action='no_order',
            input_sha256=dict(valuation_package=package_binding['sha256'])),
        source_verification=dict(status='LOCAL_BYTES_VERIFIED',
            scope='byte_integrity_not_fact_semantics_or_investment_approval',
            source_contract_status='SOURCE_CUTOFF_AND_SCENARIO_BINDINGS_VALIDATED'))
    for field in ('current_status', 'valuation', 'price_bridge', 'price_attractiveness',
                  'pre_decision_eligibility', 'decision_recommendation', 'artifact_bundle'):
        workbench[field] = native[field]
    verify_current_decision_workbench(workbench)
    context = build_research_review_model_context(descriptor=descriptor, spec=spec)
    read_bound_json(root, package_binding, 'source-native original package final read')
    read_bound_json(root, ledger_binding, 'source-native cash ledger final read')
    for ref in closure.values():
        original = require_inside(root, root/ref['path'], 'source-native source')
        if original.relative_to(root).as_posix() != ref['path'] or sha256_file(original) != ref['sha256']:
            raise ValueError('Source-native source changed during replay')
    return dict(workbench=workbench, model_context=context,
        scenario_inputs=scenarios, source_bindings=list(closure.values()))


def _economic_workbench(payload):
    result = deepcopy(payload)
    # Repository persistence time is not a financial/PIT input or payload hash.
    for record in result['artifact_bundle']['artifacts']:
        record.pop('created_at', None)
    return result


def prepare_source_native_candidate(*, root: Path, package_binding: dict, ledger_binding: dict,
                                    output_dir: Path, now: datetime | None = None) -> dict:
    root = root.resolve()
    package_binding, ledger_binding = deepcopy(package_binding), deepcopy(ledger_binding)
    clock = now or datetime.now(timezone.utc)
    replay = replay_source_native_inputs(root=root, package_binding=package_binding,
        ledger_binding=ledger_binding, now=clock)
    target = require_inside(root/'runtime', output_dir, 'source-native candidate output')
    if target.exists():
        raise FileExistsError('Source-native candidate output must be new')
    implementations = [_bound(root, root/name) for name in IMPLEMENTATIONS]
    target.mkdir(parents=True)
    package_path = target/'package.json'
    write_new_bytes(package_path, (root/package_binding['path']).read_bytes())
    workbench_path = target/'workbench.json'
    write_new_json(workbench_path, replay['workbench'])
    packet = project_research_review_packet(root=root, package_path=package_path,
        package_sha256=package_binding['sha256'], workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path))
    packet_path = target/'consumed-review.json'
    write_new_json(packet_path, packet)
    candidate = dict(schema_version=SCHEMA, symbol=replay['workbench']['symbol'], status='PENDING_REVIEW',
        action='no_order', generated_at=clock.isoformat(), input_mode='SOURCE_NATIVE_EXACT_INPUT_V1',
        source_package_binding=deepcopy(package_binding), native_cash_ledger_binding=deepcopy(ledger_binding),
        candidate_research_as_of=packet['research_as_of'], model_context=replay['model_context'],
        model_context_scope='ACTUALLY_CONSUMED', candidate_valuation=replay['workbench']['valuation'],
        execution_status='NO_ACTION', research_blockers=replay['workbench']['research_blockers'],
        schedule_gate=None, schedule_consumed=False, review_groups=_groups(),
        review_packet_binding=_bound(root, packet_path), implementation_bindings=implementations,
        approval_changed=False, research_admitted=False, price_admitted=False,
        canonical_written=False, registered_current_case_changed=False, primary_registered=False,
        position_guidance=None, strict_contemporaneous_pit='NOT_PROVEN',
        source_bindings=list({ref['path']:ref for ref in [*replay['source_bindings'],
            *packet['source_bindings'], *implementations, _bound(root, packet_path)]}.values()))
    path = target/'candidate.json'
    write_new_json(path, candidate)
    verify_source_native_candidate(root=root, path=path, expected_sha256=sha256_file(path), now=clock)
    return candidate


def verify_source_native_candidate(*, root: Path, path: Path, expected_sha256: str,
                                    now: datetime | None = None) -> dict:
    root = root.resolve()
    path = require_inside(root/'runtime', path, 'source-native candidate')
    if sha256_file(path) != expected_sha256:
        raise ValueError('Source-native candidate hash mismatch')
    candidate = load_json_object(path, 'source-native candidate')
    if (set(candidate) != CANDIDATE_FIELDS or candidate.get('schema_version') != SCHEMA or candidate.get('action') != 'no_order'
            or candidate.get('status') != 'PENDING_REVIEW' or candidate.get('review_groups') != _groups()
            or any(candidate.get(key) is not False for key in ('approval_changed', 'research_admitted',
                'price_admitted', 'canonical_written', 'registered_current_case_changed',
                'primary_registered', 'schedule_consumed')) or candidate.get('position_guidance') is not None
            or candidate.get('strict_contemporaneous_pit') != 'NOT_PROVEN'
            or candidate.get('input_mode') != 'SOURCE_NATIVE_EXACT_INPUT_V1'
            or candidate.get('model_context_scope') != 'ACTUALLY_CONSUMED'
            or candidate.get('schedule_gate') is not None):
        raise ValueError('Source-native candidate authority or review scope mismatch')
    clock = now or datetime.now(timezone.utc)
    generated = _stamp(candidate['generated_at'])
    if generated > clock:
        raise ValueError('Source-native candidate is not yet available')
    expected_impl = [_bound(root, root/name) for name in IMPLEMENTATIONS]
    if candidate.get('implementation_bindings') != expected_impl:
        raise ValueError('Source-native implementation bindings mismatch')
    for ref in candidate['source_bindings']:
        if sha256_file(require_inside(root, root/ref['path'], 'source-native bound source')) != ref['sha256']:
            raise ValueError('Source-native candidate source drift')
    replay = replay_source_native_inputs(root=root, package_binding=candidate['source_package_binding'],
        ledger_binding=candidate['native_cash_ledger_binding'], now=generated)
    package_path, workbench_path = path.parent/'package.json', path.parent/'workbench.json'
    if sha256_file(package_path) != candidate['source_package_binding']['sha256']:
        raise ValueError('Source-native package bytes were altered')
    workbench = load_json_object(workbench_path, 'source-native consumed workbench')
    if _economic_workbench(workbench) != _economic_workbench(replay['workbench']):
        raise ValueError('Source-native workbench differs from cold application replay')
    if (candidate.get('symbol') != workbench['symbol']
            or candidate.get('candidate_valuation') != workbench['valuation']
            or candidate.get('model_context') != replay['model_context']
            or candidate.get('candidate_research_as_of') != load_json_object(package_path, 'source-native package')['point_in_time']['research_as_of']
            or candidate.get('execution_status') != workbench['suggested_state']
            or candidate.get('research_blockers') != workbench['research_blockers']):
        raise ValueError('Source-native candidate differs from consumed inputs')
    packet = project_research_review_packet(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path))
    packet_path = path.parent/'consumed-review.json'
    required = list({ref['path']:ref for ref in [*replay['source_bindings'], *packet['source_bindings'],
        *expected_impl, _bound(root, packet_path)]}.values())
    if (candidate['source_bindings'] != required or candidate['review_packet_binding'] != _bound(root, packet_path)
            or load_json_object(packet_path, 'source-native review packet') != packet):
        raise ValueError('Source-native packet or binding closure differs from consumed inputs')
    for ref in required:
        if sha256_file(root/ref['path']) != ref['sha256']:
            raise ValueError('Source-native final source drift')
    if sha256_file(path) != expected_sha256:
        raise ValueError('Source-native candidate changed during verification')
    return candidate


def verify_review_candidate(*, root: Path, path: Path, expected_sha256: str) -> dict:
    """Root's explicit mutable-callsite hook; no legacy schema reinterpretation."""
    path = require_inside(root.resolve()/'runtime', path, 'versioned review candidate')
    if sha256_file(path) != expected_sha256:
        raise ValueError('Versioned review candidate hash mismatch')
    schema = load_json_object(path, 'versioned review candidate').get('schema_version')
    if schema == SCHEMA:
        return verify_source_native_candidate(root=root, path=path, expected_sha256=expected_sha256)
    if schema == 'pending-research-candidate-v1':
        return _verify_frozen_v1(root=root, path=path, expected_sha256=expected_sha256)
    raise ValueError('Unsupported review candidate schema')


def project_source_native_review_materials(*, root: Path, candidate_binding: dict,
                                         now: datetime | None = None) -> dict:
    """Root's read-model hook: verified ledger and actual model output, no approval."""
    root = root.resolve()
    path = root/candidate_binding['path']
    candidate = verify_source_native_candidate(root=root, path=path,
        expected_sha256=candidate_binding['sha256'], now=now)
    _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'native review cash ledger')
    _, package = read_bound_json(root, candidate['source_package_binding'], 'native review source package')
    result = dict(schema_version='source-native-economic-review-materials-v1', symbol=candidate['symbol'],
        scope='SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_G3', action='no_order',
        confidence=candidate['candidate_valuation']['confidence'],
        point_in_time=deepcopy(package['point_in_time']),
        valuation_timing=deepcopy(package['facts'].get('valuation_timing')),
        valuation_timing_status=('EXPLICIT_MODEL_TIMING' if package['facts'].get('valuation_timing')
            else 'MISSING_EXPLICIT_MODEL_TIMING'),
        historical_cash_bridge=deepcopy(ledger['history']), joint_assumptions=deepcopy(ledger['plan']),
        scenarios={name:dict(cash_ledger=deepcopy(ledger['cases']['TIMING_DELAY'][name]['annual_rows']),
            inputs=deepcopy(package['facts']['scenario_inputs'][name]),
            per_share_value=candidate['candidate_valuation'][name+'_value']) for name in ('bear', 'base', 'bull')},
        review_groups=deepcopy(candidate['review_groups']), research_admitted=False, primary_registered=False,
        approval_changed=False, strict_contemporaneous_pit='NOT_PROVEN', source_bindings=deepcopy(candidate['source_bindings']))
    if verify_source_native_candidate(root=root, path=path,
            expected_sha256=candidate_binding['sha256'], now=now) != candidate:
        raise ValueError('Source-native candidate changed during material projection')
    return result
