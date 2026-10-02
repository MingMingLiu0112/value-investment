"""Check source-bound daily inputs, separately from M6 authorization/counting."""
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

from ..application.product.common import load_json_object, require_inside, sha256_file
from ..quote_session_conversion import quote_snapshot_from_bundle_file

ROLES = ('quote', 'event', 'research', 'model', 'decision', 'portfolio', 'product', 'run_receipt')
DAG_NODES = ('research', 'model_validity', 'price_bridge', 'decision_gate', 'portfolio_gate', 'product')
CST = timezone(timedelta(hours=8))


def consume_shadow_daily_input(*, root: Path, path: Path, expected_sha256: str,
                               now: datetime, operational_inputs: Path | None = None,
                               operational_inputs_sha256: str | None = None) -> dict:
    """Intersect daily content checks with existing admission, never sign or deploy."""
    audit = audit_shadow_daily_input(root=root, path=path,
        expected_sha256=expected_sha256, now=now)
    if bool(operational_inputs) != bool(operational_inputs_sha256):
        raise ValueError('operational inputs require paired path/hash')
    result = dict(audit=audit, daily_consumer_status='NOT_ADMITTED',
                  verified_real_session_count=0, action='no_order')
    if operational_inputs is None:
        result['blockers'] = list(audit['blockers']) + ['EXISTING_OPERATIONAL_ADMISSION_REQUIRED']
        return result
    request_path = require_inside(root, operational_inputs, 'operational input bindings')
    if sha256_file(request_path) != operational_inputs_sha256:
        raise ValueError('operational input bindings hash mismatch')
    request = load_json_object(request_path, 'operational input bindings')
    if request.get('schema_version') != 'shadow-daily-consumer-inputs-v1' or request.get('action') != 'no_order':
        raise ValueError('operational consumer input scope mismatch')
    refs = request['bindings']
    if set(refs) != {'bundle', 'trust_root', 'schedule'}:
        raise ValueError('existing bundle/trust root/schedule bindings required')
    loaded = {}
    for role, binding in refs.items():
        source = require_inside(root, root / binding['path'], role)
        if sha256_file(source) != binding['sha256']:
            raise ValueError('operational consumer artifact hash mismatch')
        loaded[role] = load_json_object(source, role)
    from ..m6_shadow_admission import verify_operational_shadow_bundle
    verified = verify_operational_shadow_bundle(loaded['bundle'], loaded['trust_root'],
        loaded['schedule'], now, required_sessions=20, required_events=1)
    audit = audit_shadow_daily_input(root=root, path=path,
        expected_sha256=expected_sha256, now=now)
    result['audit'] = audit
    manifest = load_json_object(path, 'daily input manifest')
    receipt = load_json_object(root / manifest['bindings']['run_receipt']['path'], 'daily receipt')
    day = audit['session_date']
    sessions = loaded['bundle']['candidate_bundle']['sessions']
    matches = [item['session']['payload'] for item in sessions
               if item['session']['payload']['session_date'] == day]
    blockers = list(audit['blockers'])
    if day not in verified or len(matches) != 1:
        blockers.append('MATCHING_ADMITTED_OPERATIONAL_SESSION_REQUIRED')
    else:
        session = matches[0]
        generated = _timestamp(manifest['generated_at'])
        if (session['artifact_sha256'] != expected_sha256
                or session['run_id'] != receipt['run_id']
                or not _timestamp(session['started_at']) <= generated <= _timestamp(session['completed_at'])):
            blockers.append('SIGNED_SESSION_DAILY_ARTIFACT_BINDING_MISMATCH')
    for role, binding in refs.items():
        if sha256_file(root / binding['path']) != binding['sha256']:
            raise ValueError('operational artifact changed during consumption')
    if sha256_file(request_path) != operational_inputs_sha256 or sha256_file(path) != expected_sha256:
        raise ValueError('consumer input changed during consumption')
    result.update(blockers=blockers, daily_consumer_status='NOT_ADMITTED' if blockers else 'ADMITTED',
                  verified_real_session_count=0 if blockers else 1)
    return result


def _timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('daily input timestamp requires timezone')
    return result


def _research_projection_blockers(artifacts, hashes, symbols, day):
    """Check computation-to-projection lineage; do not recalculate financial rules."""
    blockers = []
    research = artifacts.get('research', {})
    result = research.get('result', {})
    if not isinstance(result, dict) or result.get('action') != 'no_order' or result.get('symbol') not in symbols:
        blockers.append('SHARED_RESEARCH_RESULT_BINDING_REQUIRED')
        result = {}
    receipt = research.get('application_receipt', {})
    inputs = receipt.get('input_sha256', {})
    event = artifacts.get('event', {})
    event_hash = event.get('raw_scan', {}).get('sha256', hashes.get('event'))
    if (receipt.get('action') != 'no_order' or not inputs.get('valuation_package')
            or inputs.get('quote') != hashes.get('quote') or 'quote' not in hashes
            or inputs.get('event') != event_hash or 'event' not in hashes):
        blockers.append('SHARED_RESEARCH_DAILY_INPUT_CONSUMPTION_NOT_PROVEN')
    model = artifacts.get('model', {})
    for target, source in (('model_validity', 'model_validity'), ('price_bridge', 'price_bridge'),
                           ('valuation_result', 'valuation')):
        if source not in result or target not in model or model[target] != result[source]:
            blockers.append('MODEL_RESEARCH_PROJECTION_MISMATCH:' + target)
    decision = artifacts.get('decision', {})
    review_payload = decision.get('review')
    predecision_payload = result.get('pre_decision_eligibility')
    if not isinstance(review_payload, dict) or not isinstance(predecision_payload, dict):
        blockers.append('SHARED_DECISION_REVIEW_LINEAGE_REQUIRED')
    else:
        from ..investment_decision import investment_decision_review_from_payload
        from ..pre_decision_eligibility import pre_decision_eligibility_from_payload
        try:
            review = investment_decision_review_from_payload(review_payload)
            predecision = pre_decision_eligibility_from_payload(predecision_payload)
            if (review.symbol != result.get('symbol') or predecision.symbol != review.symbol
                    or review.decision_as_of.isoformat() != day
                    or predecision.decision_as_of != review.decision_as_of
                    or review.predecision_status != predecision.status
                    or decision.get('suggested_state') != review.status
                    or decision.get('blockers') != list(review.blockers)):
                blockers.append('DECISION_RESEARCH_PROJECTION_MISMATCH')
        except (ValueError, TypeError, KeyError):
            blockers.append('TYPED_DECISION_REVIEW_INVALID')
    product = artifacts.get('product', {})
    if (product.get('symbol') != result.get('symbol')
            or product.get('suggested_state') != decision.get('suggested_state')
            or product.get('blockers') != decision.get('blockers')):
        blockers.append('PRODUCT_DECISION_PROJECTION_MISMATCH')
    return blockers


def audit_shadow_daily_input(*, root: Path, path: Path, expected_sha256: str,
                             now: datetime) -> dict:
    """An offline audit is never authorization or a countable Shadow session."""
    root = root.resolve()
    path = require_inside(root, path, 'daily input manifest')
    if sha256_file(path) != expected_sha256:
        raise ValueError('daily input manifest hash mismatch')
    manifest = load_json_object(path, 'daily input manifest')
    if manifest.get('schema_version') != 'shadow-daily-input-v1' or manifest.get('action') != 'no_order':
        raise ValueError('daily input scope mismatch')
    if now.utcoffset() is None:
        raise ValueError('audit clock requires timezone')
    generated = _timestamp(manifest['generated_at'])
    day = manifest['session_date']
    blockers = []
    if generated > now:
        raise ValueError('daily input generation is in the future')
    if generated.astimezone(CST).date().isoformat() != day or generated.astimezone(CST).time() < time(15, 5):
        blockers.append('SAME_DAY_POST_CLOSE_REQUIRED')
    symbols = manifest['symbols']
    if not symbols or len(set(symbols)) != len(symbols) or not set(symbols) <= {'000333', '600887', '601088'}:
        raise ValueError('daily input symbols outside authorized scope')
    bindings = manifest['bindings']
    if set(bindings) - set(ROLES):
        raise ValueError('unknown daily DAG artifact role')
    missing = sorted(set(ROLES) - set(bindings))
    blockers.extend('MISSING_DAG_ARTIFACT:' + role for role in missing)
    artifacts = {}
    hashes = {}
    for role in bindings:
        binding = bindings[role]
        source = require_inside(root, root / binding['path'], role)
        if sha256_file(source) != binding['sha256']:
            raise ValueError(f'daily {role} artifact hash mismatch')
        artifacts[role] = load_json_object(source, role)
        hashes[role] = binding['sha256']
        observed = _timestamp(binding['observed_at'])
        if observed > generated:
            raise ValueError(f'daily {role} observation after cutoff')
        if observed.astimezone(CST).date().isoformat() != day:
            blockers.append(f'{role.upper()}_NOT_OBSERVED_SAME_DAY')
    if 'quote' in bindings:
        quote_path = root / bindings['quote']['path']
        for symbol in symbols:
            quote = quote_snapshot_from_bundle_file(quote_path, root, symbol=symbol,
                ref_id='shadow-daily-' + symbol, expected_sha256=hashes['quote'], now=generated)
            if quote.status != 'verified_close' or quote.quote_date is None or quote.quote_date.isoformat() != day:
                blockers.append(f'B1_MATCHED_SAME_DAY_CLOSE_REQUIRED:{symbol}')
    event = artifacts.get('event', {})
    if event.get('action') != 'no_order' or event.get('simulation_only') is not False:
        blockers.append('REAL_PROSPECTIVE_EVENT_INPUT_REQUIRED')
    for field in ('observed_at', 'scan_as_of'):
        if event.get(field) is None:
            blockers.append('EVENT_SCAN_TIME_MISSING:' + field)
            continue
        point = _timestamp(event[field])
        if point > generated or point.astimezone(CST).date().isoformat() != day:
            blockers.append('EVENT_SCAN_NOT_CURRENT')
    if event.get('coverage_complete') is not True or set(event.get('symbols', [])) != set(symbols):
        blockers.append('EVENT_COVERAGE_INCOMPLETE')
    for source in event.get('source_bindings', []):
        original = require_inside(root, root / source['path'], 'event original')
        if sha256_file(original) != source['sha256'] or _timestamp(source['observed_at']) > generated:
            raise ValueError('event original hash/time mismatch')
    if not event.get('source_bindings'):
        blockers.append('EVENT_SOURCE_OR_EMPTY_SCAN_EVIDENCE_REQUIRED')
    receipt = artifacts.get('run_receipt', {})
    if receipt.get('dag_execution_complete') is False:
        blockers.append('DAG_EXECUTION_INCOMPLETE')
    if (receipt.get('action') != 'no_order' or receipt.get('session_date') != day
            or receipt.get('simulation_only') is not False
            or receipt.get('node_sequence') != list(DAG_NODES)
            or not receipt.get('run_id')
            or receipt.get('input_hashes') != {key: hashes[key] for key in ('quote', 'event') if key in hashes}
            or receipt.get('output_hashes') != {key: hashes[key] for key in ('research', 'model', 'decision', 'portfolio', 'product') if key in hashes}):
        blockers.append('COMPLETE_SOURCE_BOUND_DAG_RUN_RECEIPT_REQUIRED')
    for role in ('research', 'model', 'decision', 'portfolio', 'product'):
        if role not in artifacts:
            continue
        artifact = artifacts[role]
        if artifact.get('action') != 'no_order' or artifact.get('orders') or artifact.get('broker_called'):
            raise ValueError('daily DAG must not produce orders or call broker')
        if artifact.get('run_id') != receipt.get('run_id'):
            blockers.append(f'{role.upper()}_RUN_ID_MISMATCH')
        if artifact.get('session_date') != day:
            blockers.append(f'{role.upper()}_SESSION_MISMATCH')
        if artifact.get('generated_at') is None or _timestamp(artifact['generated_at']) > generated:
            blockers.append(f'{role.upper()}_OUTPUT_TIME_MISSING_OR_FUTURE')
    blockers.extend(_research_projection_blockers(artifacts, hashes, symbols, day))
    if sha256_file(path) != expected_sha256:
        raise ValueError('daily input manifest changed during audit')
    for role in bindings:
        if sha256_file(root / bindings[role]['path']) != hashes[role]:
            raise ValueError('daily input changed during audit')
    return dict(schema_version='shadow-daily-input-audit-v1', session_date=day,
        manifest_sha256=expected_sha256, binding_hashes=hashes,
        input_consistency_status='PASS' if not blockers else 'SHADOW_INPUT_INCOMPLETE',
        blockers=list(dict.fromkeys(blockers)), investment_decision_validity='NOT_ADMITTED',
        shadow_session_valid=False, verified_real_session_count=0,
        limitation='Offline artifact consistency does not prove actual execution, production authorization or independent contemporaneous intake.',
        action='no_order')
