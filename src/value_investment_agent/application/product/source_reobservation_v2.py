"""Versioned exact-byte recovery transport over the pinned v1 observation logic."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re

from . import source_reobservation as v1
from .common import load_json_object, normalize_symbol, require_inside, sha256_file, write_new_bytes, write_new_json
from .daily_assets import inspect_daily_case_assets
from .source_bound_inputs import source_catalog_sha256, verify_package_local_sources
from ...m1_valuation_package_builder import build_descriptor

SCHEMA = 'current-local-source-reobservation-v2'
SCOPE = v1.SCOPE
TRANSPORT_SCHEMA = 'verified-source-recovery-transport-v1'
IMPLEMENTATION = 'src/value_investment_agent/application/product/source_reobservation_v2.py'
V1_SHA256 = 'd2e5e61585321f6f10a07a5d31937dd37363c670264d8ed039d9c251598d8555'


def _pin(root):
    inherited = dict(path=v1.IMPLEMENTATION, sha256=V1_SHA256)
    v1._read(root, inherited)
    if sha256_file(Path(v1.__file__)) != V1_SHA256:
        raise ValueError('Loaded inherited observation implementation differs')
    current = v1._binding(root, root / IMPLEMENTATION)
    if current['sha256'] != sha256_file(Path(__file__)):
        raise ValueError('Loaded v2 observation implementation differs')
    return current, inherited


def _transport(root, case, symbol):
    rows = []
    if case.get('publication_input') is not None:
        binding = dict(path=case['publication_input'], sha256=case['publication_input_sha256'])
        original = load_json_object(v1._read(root, binding), 'prior recovery transport')
        if original.get('symbol', symbol) != symbol:
            raise ValueError('Recovery transport issuer mismatch')
        rows = original.get('verified_source_recoveries', [])
    if not isinstance(rows, list):
        raise ValueError('Recovery transport requires a list')
    seen, verified = set(), []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'original_path', 'expected_sha256', 'recovered_path'}:
            raise ValueError('Recovery transport requires exact locator/hash/target')
        original, digest, target = row['original_path'], row['expected_sha256'], row['recovered_path']
        identity = original.replace('\\', '/') if isinstance(original, str) else None
        if (not isinstance(original, str) or not original or identity in seen
                or not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None
                or not isinstance(target, str) or not target):
            raise ValueError('Duplicate/conflicting or invalid recovery identity')
        relative = Path(target)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Recovery target must be project relative')
        # original_path is an opaque identity: never resolve/open/stat it.
        actual = require_inside(root, root / relative, 'recovered transport original')
        if sha256_file(actual) != digest:
            raise ValueError('Recovered transport original hash mismatch')
        seen.add(identity)
        verified.append(deepcopy(row))
    return dict(schema_version=TRANSPORT_SCHEMA, symbol=symbol, action='no_order',
        scope='DATA_ONLY_EXACT_RECOVERY_NOT_PUBLICATION_OR_APPROVAL',
        verified_source_recoveries=verified)


def _inputs(root, registry_binding, symbol, policy_binding):
    registry = load_json_object(v1._read(root, registry_binding), 'prior case registry')
    transport = _transport(root, registry['cases'][symbol], symbol)
    inputs = v1._inputs(root, registry_binding, symbol, policy_binding)
    return inputs, transport


def _project(package, policy, receipt, receipt_binding):
    successor, successor_policy = v1._project(package, policy, receipt, receipt_binding)
    proof = receipt['inherited_implementation_binding']
    successor['sources'].append(dict(id='source-reobservation-v1-implementation', kind='research_artifact',
        location=proof['path'], local_path=proof['path'], sha256=proof['sha256'],
        retrieved_at=receipt['observed_at'], source_available_at=receipt['observed_at'], availability_basis=SCOPE))
    return successor, successor_policy


def _case(root, directory, old_case, package_binding, policy_binding, transport_binding):
    result = dict(package=package_binding['path'], package_sha256=package_binding['sha256'],
        valuation_proposal_policy=policy_binding['path'], valuation_proposal_policy_sha256=policy_binding['sha256'],
        schedule_request=old_case['schedule_request'], schedule_request_sha256=old_case['schedule_request_sha256'],
        publication_input=transport_binding['path'], publication_input_sha256=transport_binding['sha256'])
    recovery = None
    if old_case.get('recovery_manifest'):
        recovery = load_json_object(v1._read(root, dict(path=old_case['recovery_manifest'],
            sha256=old_case['recovery_manifest_sha256'])), 'retained recovery')
        recovery['package_sha256'] = package_binding['sha256']
        path = directory / 'original-recovery.json'
        result.update(recovery_manifest=path.relative_to(root).as_posix())
    return result, recovery


def prepare_source_reobservation(*, root: Path, case_registry_binding: dict, symbol: str,
        policy_binding: dict, source_ids: list[str], reference_manifest_binding: dict,
        reference_script_binding: dict, output_dir: Path) -> dict:
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    output_dir = require_inside(root / 'runtime', output_dir, 'v2 source reobservation')
    if output_dir.exists():
        raise FileExistsError('Source reobservation output must be new')
    implementation, inherited = _pin(root)
    (old_case, package_binding, package, policy, _), transport = _inputs(root, case_registry_binding, symbol, policy_binding)
    observations = v1._observations(root, package, source_ids, reference_manifest_binding, reference_script_binding)
    registry_bytes = v1._read(root, case_registry_binding).read_bytes()
    snapshot = output_dir / 'prior-case-registry.json'
    receipt = dict(schema_version=SCHEMA, action='no_order', scope=SCOPE, symbol=symbol,
        observed_at=datetime.now(timezone.utc).isoformat(), case_registry_binding=dict(
            path=snapshot.relative_to(root).as_posix(), sha256=case_registry_binding['sha256']),
        observed_case_registry=dict(original_path=case_registry_binding['path'], observed_sha256=case_registry_binding['sha256']),
        package_binding=package_binding, policy_binding=policy_binding, source_ids=source_ids,
        implementation_binding=implementation, inherited_implementation_binding=inherited,
        reference_manifest_binding=reference_manifest_binding, reference_script_binding=reference_script_binding,
        observations=observations, approval_changed=False, research_admitted=False, price_admitted=False)
    _pin(root)
    if _inputs(root, case_registry_binding, symbol, policy_binding)[1] != transport:
        raise ValueError('Recovery transport changed during observation')
    if v1._observations(root, package, source_ids, reference_manifest_binding, reference_script_binding) != observations:
        raise ValueError('Source proof changed during observation')
    write_new_bytes(snapshot, registry_bytes)
    receipt_path = output_dir / 'acquisition-receipt.json'
    write_new_json(receipt_path, receipt)
    rb = v1._binding(root, receipt_path)
    successor, successor_policy = _project(package, policy, receipt, rb)
    verify_package_local_sources(root, successor)
    build_descriptor(successor, root=root)
    package_path, policy_path = output_dir / 'package.json', output_dir / 'policy.json'
    write_new_json(package_path, successor)
    pb = v1._binding(root, package_path)
    successor_policy['source_package_sha256'] = pb['sha256']
    write_new_json(policy_path, successor_policy)
    polb = v1._binding(root, policy_path)
    tp = output_dir / 'transport-input.json'
    write_new_json(tp, transport)
    tb = v1._binding(root, tp)
    case, recovery = _case(root, output_dir, old_case, pb, polb, tb)
    if recovery is not None:
        write_new_json(output_dir / 'original-recovery.json', recovery)
        case['recovery_manifest_sha256'] = sha256_file(output_dir / 'original-recovery.json')
    registry_path = output_dir / 'case-registry.json'
    write_new_json(registry_path, dict(schema_version='daily-trade-assistant-cases-v1', action='no_order', cases={symbol: case}))
    result = dict(schema_version=SCHEMA, action='no_order', scope=SCOPE, symbol=symbol,
        receipt_binding=rb, package_binding=pb, policy_binding=polb,
        transport_binding=tb, case_registry_binding=v1._binding(root, registry_path),
        source_catalog_sha256=source_catalog_sha256(successor['sources']))
    write_new_json(output_dir / 'manifest.json', result)
    return verify_source_reobservation(root=root, binding=v1._binding(root, output_dir / 'manifest.json'))


def verify_source_reobservation(*, root: Path, binding: dict) -> dict:
    root = root.resolve()
    implementation, inherited = _pin(root)
    result = load_json_object(v1._read(root, binding), 'v2 observation manifest')
    receipt = load_json_object(v1._read(root, result['receipt_binding']), 'v2 observation receipt')
    if (receipt.get('schema_version') != SCHEMA or result.get('schema_version') != SCHEMA
            or receipt.get('scope') != SCOPE or result.get('scope') != SCOPE
            or receipt.get('action') != 'no_order' or result.get('action') != 'no_order'
            or receipt.get('symbol') != result.get('symbol')
            or receipt.get('implementation_binding') != implementation
            or receipt.get('inherited_implementation_binding') != inherited
            or any(receipt.get(key) is not False for key in ('approval_changed', 'research_admitted', 'price_admitted'))
            or receipt['case_registry_binding']['sha256'] != receipt['observed_case_registry']['observed_sha256']):
        raise ValueError('V2 observation identity/implementation/boundary mismatch')
    (old_case, pb, package, policy, _), transport = _inputs(root, receipt['case_registry_binding'], receipt['symbol'], receipt['policy_binding'])
    if (pb != receipt['package_binding']
            or v1._stamp(receipt['observed_at']) < v1._stamp(package['point_in_time']['computed_at'])
            or v1._observations(root, package, receipt['source_ids'], receipt['reference_manifest_binding'], receipt['reference_script_binding']) != receipt['observations']):
        raise ValueError('V2 original observations differ')
    expected, expected_policy = _project(package, policy, receipt, result['receipt_binding'])
    actual = load_json_object(v1._read(root, result['package_binding']), 'v2 package')
    expected_policy['source_package_sha256'] = result['package_binding']['sha256']
    if (actual != expected or load_json_object(v1._read(root, result['policy_binding']), 'v2 policy') != expected_policy
            or load_json_object(v1._read(root, result['transport_binding']), 'v2 transport') != transport
            or source_catalog_sha256(actual['sources']) != result['source_catalog_sha256']):
        raise ValueError('V2 successor or recovery transport differs from originals')
    build_descriptor(actual, root=root)
    directory = (root / binding['path']).parent
    case, recovery = _case(root, directory, old_case, result['package_binding'], result['policy_binding'], result['transport_binding'])
    if recovery is not None:
        recovery_path = directory / 'original-recovery.json'
        if load_json_object(recovery_path, 'v2 recovery') != recovery:
            raise ValueError('V2 recovery differs')
        case['recovery_manifest_sha256'] = sha256_file(recovery_path)
    registry = load_json_object(v1._read(root, result['case_registry_binding']), 'v2 cases')
    if registry != dict(schema_version='daily-trade-assistant-cases-v1', action='no_order', cases={receipt['symbol']: case}):
        raise ValueError('V2 successor registry differs')
    if inspect_daily_case_assets(root=root, case=case, agent_mode='none')['blockers']:
        raise ValueError('V2 successor assets unavailable')
    # Final closure: input/transport, raw observations, inherited code and every output.
    if (_inputs(root, receipt['case_registry_binding'], receipt['symbol'], receipt['policy_binding'])[1] != transport
            or v1._observations(root, package, receipt['source_ids'], receipt['reference_manifest_binding'], receipt['reference_script_binding']) != receipt['observations']):
        raise ValueError('V2 source closure changed')
    _pin(root)
    for ref in (binding, receipt['case_registry_binding'], receipt['policy_binding'],
                *[result[key] for key in ('receipt_binding', 'package_binding', 'policy_binding', 'transport_binding', 'case_registry_binding')]):
        v1._read(root, ref)
    return result
