"""Reobserve retained originals now and prepare a separate, unapproved version."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import (
    load_json_object, normalize_symbol, require_inside, sha256_bytes, sha256_file,
    write_new_bytes, write_new_json,
)
from .daily_assets import inspect_daily_case_assets
from .source_bound_inputs import source_catalog_sha256, verify_package_local_sources
from ...m1_valuation_package_builder import build_descriptor
from ...quote_session_conversion import quote_snapshot_from_bundle_file


SCHEMA = 'current-local-source-reobservation-v1'
SCOPE = 'CURRENT_LOCAL_BYTES_NOT_HISTORICAL_ACQUISITION_OR_ECONOMIC_APPROVAL'
IMPLEMENTATION = 'src/value_investment_agent/application/product/source_reobservation.py'


def _binding(root, path):
    path = require_inside(root, path, 'reobservation binding')
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def _read(root, binding):
    path = require_inside(root, root / binding['path'], 'reobservation source')
    if _binding(root, path) != binding:
        raise ValueError('Source reobservation binding drift')
    return path


def _stamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > datetime.now(timezone.utc):
        raise ValueError('Source observation requires an available aware timestamp')
    return stamp


def _inputs(root, registry_binding, symbol, policy_binding):
    registry = load_json_object(_read(root, registry_binding), 'prior case registry')
    if registry.get('schema_version') != 'daily-trade-assistant-cases-v1' or registry.get('action') != 'no_order':
        raise ValueError('Source reobservation requires a no-order case registry')
    case = registry['cases'][symbol]
    inventory = inspect_daily_case_assets(root=root, case=case, agent_mode='none')
    if inventory['blockers']:
        raise ValueError('Source reobservation requires verified original case assets')
    package_binding = dict(path=case['package'], sha256=case['package_sha256'])
    package = load_json_object(_read(root, package_binding), 'prior input package')
    policy = load_json_object(_read(root, policy_binding), 'prior finite policy')
    if (package.get('schema_version') != 'm1-valuation-package-v2'
            or package.get('symbol') != symbol or policy.get('symbol') != symbol
            or policy.get('schema_version') != 'finite-earnings-path-proposal-v1'
            or policy.get('action') != 'no_order'
            or any(package.get(k) is not None for k in ('quote', 'research_reviews',
                'valuation_approval', 'entry_thesis', 'investment_consistency_review'))
            or package['research_case'].get('valuation_status') != 'CONDITIONAL_RESEARCH_PENDING_REVIEW'
            or package['source_contract'].get('distribution_input_status') != 'NOT_ADMITTED'
            or package['source_contract'].get('strict_contemporaneous_pit') != 'NOT_PROVEN'):
        raise ValueError('Source reobservation requires an unapproved source-bound package')
    verify_package_local_sources(root, package)
    if (package['source_contract'].get('schema_version') != 'source-bound-research-inputs-v1'
            or 'source_catalog_sha256' in package['source_contract']):
        raise ValueError('Existing pending producer cannot rebind a stricter source catalog; never downgrade it')
    parent = package['supersedes']
    parent_binding = dict(path=parent['path'], sha256=parent['sha256'])
    _read(root, parent_binding)
    if policy['source_package_sha256'] not in (package_binding['sha256'], parent_binding['sha256']):
        raise ValueError('Finite policy is not bound to the retained input lineage')
    if policy_binding not in [dict(path=s['local_path'], sha256=s['sha256']) for s in package['sources']]:
        raise ValueError('Finite policy is not retained in the source catalog')
    return case, package_binding, package, policy, inventory


def _reference_proof(root, source, manifest_binding, script_binding):
    manifest_path = _read(root, manifest_binding)
    manifest = load_json_object(manifest_path, 'derived reference manifest')
    script_path = _read(root, script_binding)
    if (script_binding['sha256'] != manifest['script_sha256']
            or manifest_path.parent != (root / source['local_path']).parent
            or manifest['outputs'].get(Path(source['local_path']).name) != source['sha256']
            or not manifest.get('inputs')):
        raise ValueError('Derived reference manifest does not bind the retained output and recipe')
    bindings = [manifest_binding, _binding(root, script_path)]
    for path, digest in manifest['inputs'].items():
        binding = dict(path=Path(path).as_posix(), sha256=digest)
        _read(root, binding)
        bindings.append(binding)
    return dict(kind='RETAINED_DERIVATION_HASHES_NOT_ISSUER_ECONOMIC_APPROVAL', bindings=bindings)


def _observations(root, package, source_ids, manifest_binding, script_binding):
    catalog = {s['id']: s for s in package['sources']}
    if not source_ids or len(set(source_ids)) != len(source_ids) or not set(source_ids) <= catalog.keys():
        raise ValueError('Source reobservation requires distinct existing source IDs')
    rows = []
    for identity in source_ids:
        source = catalog[identity]
        if _stamp(source['retrieved_at']) >= _stamp(source['source_available_at']):
            raise ValueError('Only inverted retained source chronology may be repaired')
        if source['kind'] == 'valuation_reference':
            proof = _reference_proof(root, source, manifest_binding, script_binding)
        elif source['kind'] == 'quote_session':
            path = root / source['local_path']
            historical = quote_snapshot_from_bundle_file(path, root, symbol=package['symbol'],
                ref_id=identity, expected_sha256=source['sha256'])
            if historical.status != 'verified_close':
                raise ValueError('Retained quote originals do not verify for the issuer')
            try:
                current = quote_snapshot_from_bundle_file(path, root, symbol=package['symbol'],
                    ref_id=identity, expected_sha256=source['sha256'],
                    now=datetime.now(timezone.utc), require_current_b1=True)
                current_status = current.status
            except ValueError:
                # A valid historical archive can be stale today; this never admits its price.
                current_status = 'unverified'
            proof = dict(kind='HISTORICAL_QUOTE_ARCHIVE_NOT_CURRENT_PRICE_ADMISSION',
                historical_session=str(historical.quote_date), current_status=current_status,
                price_admitted=False)
        else:
            raise ValueError('Unsupported source reobservation kind')
        _read(root, dict(path=source['local_path'], sha256=source['sha256']))
        rows.append(dict(prior_source=deepcopy(source), verification=proof))
    return rows


def _project(package, policy, receipt, receipt_binding):
    # Keep old producer IDs as provenance without colliding with the next producer's IDs.
    aliases = {s['id']: 'prior-' + receipt['package_binding']['sha256'][:12] + '-' + s['id']
        for s in package['sources'] if s['id'].startswith('candidate-') or s['id'] == 'pending-economic-proposal'}

    def rebind(value):
        if isinstance(value, dict):
            return {k: rebind(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rebind(v) for v in value]
        return aliases.get(value, value) if isinstance(value, str) else value

    successor = rebind(package)
    stamp = receipt['observed_at']
    day = _stamp(stamp).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    version = 'source-reobserved-' + receipt_binding['sha256'][:20]
    successor.update(package_version=version, descriptor_version=version, run_id=version,
        supersedes={**receipt['package_binding'], 'reason': SCOPE})
    successor['point_in_time'].update(research_as_of=day, computed_at=stamp, available_at=stamp)
    successor['research_case'].update(as_of=day, generated_at=stamp, run_id=version, research_version=version)
    for source in successor['sources']:
        if source['id'] in receipt['source_ids']:
            source.update(retrieved_at=stamp, source_available_at=stamp, availability_basis=SCOPE)
    successor['sources'].append(dict(id='source-reobservation-receipt', kind='research_artifact',
        location=receipt_binding['path'], local_path=receipt_binding['path'], sha256=receipt_binding['sha256'],
        retrieved_at=stamp, source_available_at=stamp, availability_basis=SCOPE))
    proofs = [receipt['implementation_binding'], receipt['package_binding'],
        receipt['policy_binding'], receipt['case_registry_binding']]
    for observation in receipt['observations']:
        proofs.extend(observation['verification'].get('bindings', []))
    for index, proof in enumerate(proofs):
        successor['sources'].append(dict(id=f'source-reobservation-proof-{index}', kind='research_artifact',
            location=proof['path'], local_path=proof['path'], sha256=proof['sha256'],
            retrieved_at=stamp, source_available_at=stamp, availability_basis=SCOPE))
    contract = successor['source_contract']
    contract['cutoff_at'] = stamp
    successor_policy = deepcopy(policy)
    return successor, successor_policy


def prepare_source_reobservation(*, root: Path, case_registry_binding: dict, symbol: str,
        policy_binding: dict, source_ids: list[str], reference_manifest_binding: dict,
        reference_script_binding: dict, output_dir: Path) -> dict:
    """Observe at the real clock; there is no caller-supplied date or approval input."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    output_dir = require_inside(root / 'runtime', output_dir, 'source reobservation output')
    if output_dir.exists():
        raise FileExistsError('Source reobservation output must be new')
    case, package_binding, package, policy, _ = _inputs(root, case_registry_binding, symbol, policy_binding)
    observations = _observations(root, package, source_ids, reference_manifest_binding, reference_script_binding)
    receipt = dict(schema_version=SCHEMA, action='no_order', scope=SCOPE, symbol=symbol,
        observed_at=datetime.now(timezone.utc).isoformat(), case_registry_binding=case_registry_binding,
        package_binding=package_binding, policy_binding=policy_binding, source_ids=source_ids,
        implementation_binding=_binding(root, root / IMPLEMENTATION),
        reference_manifest_binding=reference_manifest_binding, reference_script_binding=reference_script_binding,
        observations=observations, approval_changed=False, research_admitted=False, price_admitted=False)
    # Recheck before any output: a changed original is never repaired by accepting its new hash.
    _inputs(root, case_registry_binding, symbol, policy_binding)
    if _observations(root, package, source_ids, reference_manifest_binding, reference_script_binding) != observations:
        raise ValueError('Source proof changed during observation')
    registry_bytes = _read(root, case_registry_binding).read_bytes()
    if sha256_bytes(registry_bytes) != case_registry_binding['sha256']:
        raise ValueError('Prior case registry changed during observation')
    registry_snapshot = output_dir / 'prior-case-registry.json'
    write_new_bytes(registry_snapshot, registry_bytes)
    receipt['observed_case_registry'] = dict(original_path=case_registry_binding['path'],
        observed_sha256=case_registry_binding['sha256'])
    receipt['case_registry_binding'] = _binding(root, registry_snapshot)
    receipt_path = output_dir / 'acquisition-receipt.json'
    write_new_json(receipt_path, receipt)
    receipt_binding = _binding(root, receipt_path)
    successor, successor_policy = _project(package, policy, receipt, receipt_binding)
    verify_package_local_sources(root, successor)
    build_descriptor(successor, root=root)
    package_path = output_dir / 'package.json'
    write_new_json(package_path, successor)
    successor_policy['source_package_sha256'] = sha256_file(package_path)
    policy_path = output_dir / 'policy.json'
    write_new_json(policy_path, successor_policy)
    new_case = dict(package=package_path.relative_to(root).as_posix(), package_sha256=sha256_file(package_path),
        schedule_request=case['schedule_request'], schedule_request_sha256=case['schedule_request_sha256'],
        valuation_proposal_policy=policy_path.relative_to(root).as_posix(),
        valuation_proposal_policy_sha256=sha256_file(policy_path))
    if case.get('recovery_manifest'):
        recovery = load_json_object(root / case['recovery_manifest'], 'scoped original recovery')
        recovery['package_sha256'] = new_case['package_sha256']
        recovery_path = output_dir / 'original-recovery.json'
        write_new_json(recovery_path, recovery)
        new_case.update(recovery_manifest=recovery_path.relative_to(root).as_posix(),
            recovery_manifest_sha256=sha256_file(recovery_path))
    registry_path = output_dir / 'case-registry.json'
    write_new_json(registry_path, dict(schema_version='daily-trade-assistant-cases-v1', action='no_order',
        cases={symbol: new_case}))
    result = dict(schema_version=SCHEMA, action='no_order', scope=SCOPE, symbol=symbol,
        receipt_binding=receipt_binding, package_binding=_binding(root, package_path),
        policy_binding=_binding(root, policy_path), case_registry_binding=_binding(root, registry_path),
        source_catalog_sha256=source_catalog_sha256(successor['sources']))
    write_new_json(output_dir / 'manifest.json', result)
    verify_source_reobservation(root=root, binding=_binding(root, output_dir / 'manifest.json'))
    return result


def verify_source_reobservation(*, root: Path, binding: dict) -> dict:
    """Reproduce the metadata-only revision; caller-rehashed economic changes fail."""
    root = root.resolve()
    result = load_json_object(_read(root, binding), 'source revision manifest')
    receipt = load_json_object(_read(root, result['receipt_binding']), 'source acquisition receipt')
    if (receipt.get('schema_version') != SCHEMA or receipt.get('scope') != SCOPE
            or receipt.get('action') != 'no_order' or result.get('scope') != SCOPE
            or result.get('action') != 'no_order' or result.get('schema_version') != SCHEMA
            or result.get('symbol') != receipt.get('symbol')
            or any(receipt.get(k) is not False for k in ('approval_changed', 'research_admitted', 'price_admitted'))):
        raise ValueError('Source reobservation boundary mismatch')
    _read(root, receipt['implementation_binding'])
    if receipt['implementation_binding']['path'] != IMPLEMENTATION:
        raise ValueError('Source observation implementation differs')
    if receipt['case_registry_binding']['sha256'] != receipt['observed_case_registry']['observed_sha256']:
        raise ValueError('Retained case registry differs from the observed registry bytes')
    old_case, package_binding, package, policy, _ = _inputs(root, receipt['case_registry_binding'],
        receipt['symbol'], receipt['policy_binding'])
    if receipt['package_binding'] != package_binding or _stamp(receipt['observed_at']) < _stamp(package['point_in_time']['computed_at']):
        raise ValueError('Source observation predates or differs from its retained package')
    observations = _observations(root, package, receipt['source_ids'],
        receipt['reference_manifest_binding'], receipt['reference_script_binding'])
    if observations != receipt['observations']:
        raise ValueError('Source observations differ from verified originals')
    expected, expected_policy = _project(package, policy, receipt, result['receipt_binding'])
    actual = load_json_object(_read(root, result['package_binding']), 'reobserved package')
    expected_policy['source_package_sha256'] = result['package_binding']['sha256']
    if (actual != expected or load_json_object(_read(root, result['policy_binding']), 'rebound policy') != expected_policy):
        raise ValueError('Source reobservation changed inputs beyond the metadata revision')
    if result.get('source_catalog_sha256') != source_catalog_sha256(actual['sources']):
        raise ValueError('Reobserved source catalog hash mismatch')
    build_descriptor(actual, root=root)
    registry = load_json_object(_read(root, result['case_registry_binding']), 'new case registry')
    case = registry['cases'][receipt['symbol']]
    expected_case = dict(package=result['package_binding']['path'], package_sha256=result['package_binding']['sha256'],
        valuation_proposal_policy=result['policy_binding']['path'],
        valuation_proposal_policy_sha256=result['policy_binding']['sha256'],
        schedule_request=old_case['schedule_request'], schedule_request_sha256=old_case['schedule_request_sha256'])
    if old_case.get('recovery_manifest'):
        recovery_path = (root / result['case_registry_binding']['path']).parent / 'original-recovery.json'
        recovery = load_json_object(root / old_case['recovery_manifest'], 'retained original recovery')
        recovery['package_sha256'] = result['package_binding']['sha256']
        if load_json_object(recovery_path, 'new scoped recovery') != recovery:
            raise ValueError('Source reobservation changed the original recovery mapping')
        expected_case.update(recovery_manifest=recovery_path.relative_to(root).as_posix(),
            recovery_manifest_sha256=sha256_file(recovery_path))
    if (registry != dict(schema_version='daily-trade-assistant-cases-v1', action='no_order',
                cases={receipt['symbol']: expected_case})
            or inspect_daily_case_assets(root=root, case=case, agent_mode='none')['blockers']):
        raise ValueError('Reobserved case registry bindings are invalid')
    _read(root, binding)
    return result


def run_reobserved_candidate(*, root: Path, binding: dict, choice_id: str) -> dict:
    """Use the existing candidate/intake APIs; never register, sign or publish."""
    from .pending_research_candidate import prepare_pending_research_candidate, verify_pending_research_candidate
    from .research_reviews import prepare_pending_review_intake

    root = root.resolve()
    result = verify_source_reobservation(root=root, binding=binding)
    registry = load_json_object(_read(root, result['case_registry_binding']), 'reobserved case registry')
    case = registry['cases'][result['symbol']]
    output = (root / binding['path']).parent
    candidate_dir = output / 'pending-candidate'
    request_binding = dict(path=case['schedule_request'], sha256=case['schedule_request_sha256'])
    request = load_json_object(_read(root, request_binding), 'retained schedule request')
    candidate = prepare_pending_research_candidate(root=root,
        package_path=_read(root, result['package_binding']), package_sha256=result['package_binding']['sha256'],
        policy_path=_read(root, result['policy_binding']), policy_sha256=result['policy_binding']['sha256'],
        choice_id=choice_id, output_dir=candidate_dir, schedule_request=request,
        schedule_request_sha256=request_binding['sha256'])
    candidate_binding = _binding(root, candidate_dir / 'candidate.json')
    verify_pending_research_candidate(root=root, path=root / candidate_binding['path'],
        expected_sha256=candidate_binding['sha256'])
    intake = prepare_pending_review_intake(root=root, candidate_path=root / candidate_binding['path'],
        candidate_sha256=candidate_binding['sha256'])
    verify_source_reobservation(root=root, binding=binding)
    write_new_json(candidate_dir / 'review-intake.json', intake)
    result.update(candidate_binding=candidate_binding, review_status=intake['status'],
        model_context_scope=candidate['model_context_scope'], approval_changed=False,
        research_admitted=False, price_admitted=False, canonical_written=False,
        registered_current_case_changed=False, position_guidance=None)
    write_new_json(output / 'candidate-run.json', result)
    return result
