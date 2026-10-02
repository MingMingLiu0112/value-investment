"""Check source-bound daily inputs, separately from M6 authorization/counting."""
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

from ..application.product.common import load_json_object, require_inside, sha256_file
from ..quote_session_conversion import quote_snapshot_from_bundle_file

ROLES = ('quote', 'event', 'research', 'model', 'decision', 'portfolio', 'product', 'run_receipt')
DAG_NODES = ('research', 'model_validity', 'price_bridge', 'decision_gate', 'portfolio_gate', 'product')
CST = timezone(timedelta(hours=8))


def _timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('daily input timestamp requires timezone')
    return result


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
    if missing:
        for role, binding in bindings.items():
            source = require_inside(root, root / binding['path'], role)
            if sha256_file(source) != binding['sha256']:
                raise ValueError('partial daily artifact hash mismatch')
        return dict(schema_version='shadow-daily-input-audit-v1', session_date=day,
            input_consistency_status='SHADOW_INPUT_INCOMPLETE',
            blockers=blockers + ['MISSING_DAG_ARTIFACT:' + role for role in missing],
            manifest_sha256=expected_sha256, investment_decision_validity='NOT_ADMITTED',
            shadow_session_valid=False, verified_real_session_count=0, action='no_order')
    artifacts = {}
    hashes = {}
    for role in ROLES:
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
    quote_path = root / bindings['quote']['path']
    for symbol in symbols:
        quote = quote_snapshot_from_bundle_file(quote_path, root, symbol=symbol,
            ref_id='shadow-daily-' + symbol, expected_sha256=hashes['quote'], now=generated)
        if quote.status != 'verified_close' or quote.quote_date.isoformat() != day:
            blockers.append(f'B1_MATCHED_SAME_DAY_CLOSE_REQUIRED:{symbol}')
    event = artifacts['event']
    if event.get('action') != 'no_order' or event.get('simulation_only') is not False:
        blockers.append('REAL_PROSPECTIVE_EVENT_INPUT_REQUIRED')
    for field in ('observed_at', 'scan_as_of'):
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
    receipt = artifacts['run_receipt']
    if receipt.get('dag_execution_complete') is False:
        blockers.append('DAG_EXECUTION_INCOMPLETE')
    if (receipt.get('action') != 'no_order' or receipt.get('session_date') != day
            or receipt.get('simulation_only') is not False
            or receipt.get('node_sequence') != list(DAG_NODES)
            or not receipt.get('run_id')
            or receipt.get('input_hashes') != {key: hashes[key] for key in ('quote', 'event')}
            or receipt.get('output_hashes') != {key: hashes[key] for key in ('research', 'model', 'decision', 'portfolio', 'product')}):
        blockers.append('COMPLETE_SOURCE_BOUND_DAG_RUN_RECEIPT_REQUIRED')
    for role in ('research', 'model', 'decision', 'portfolio', 'product'):
        artifact = artifacts[role]
        if artifact.get('action') != 'no_order' or artifact.get('orders') or artifact.get('broker_called'):
            raise ValueError('daily DAG must not produce orders or call broker')
        if artifact.get('run_id') != receipt.get('run_id'):
            blockers.append(f'{role.upper()}_RUN_ID_MISMATCH')
        if artifact.get('session_date') != day:
            blockers.append(f'{role.upper()}_SESSION_MISMATCH')
        if artifact.get('generated_at') is None or _timestamp(artifact['generated_at']) > generated:
            blockers.append(f'{role.upper()}_OUTPUT_TIME_MISSING_OR_FUTURE')
    if sha256_file(path) != expected_sha256:
        raise ValueError('daily input manifest changed during audit')
    for role in ROLES:
        if sha256_file(root / bindings[role]['path']) != hashes[role]:
            raise ValueError('daily input changed during audit')
    return dict(schema_version='shadow-daily-input-audit-v1', session_date=day,
        manifest_sha256=expected_sha256, binding_hashes=hashes,
        input_consistency_status='PASS' if not blockers else 'SHADOW_INPUT_INCOMPLETE',
        blockers=list(dict.fromkeys(blockers)), investment_decision_validity='NOT_ADMITTED',
        shadow_session_valid=False, verified_real_session_count=0,
        limitation='Offline artifact consistency does not prove actual execution, production authorization or independent contemporaneous intake.',
        action='no_order')
