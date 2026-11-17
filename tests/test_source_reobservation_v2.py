"""TEST_ONLY exact-source transport; no signing/publication or investment approval."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_pending_candidate_replay import stale, binding, write
from test_source_reobservation import repair_inputs
from value_investment_agent.application.product import source_reobservation as v1
from value_investment_agent.application.product import source_reobservation_v2 as v2
from value_investment_agent.application.product.common import sha256_file


@pytest.fixture
def transport_inputs(repair_inputs):
    kwargs, package, old_candidate = repair_inputs
    root = kwargs['root']
    implementation = root / v2.IMPLEMENTATION
    implementation.write_bytes((Path(__file__).resolve().parents[1] / v2.IMPLEMENTATION).read_bytes())
    manifest_path = root / kwargs['reference_manifest_binding']['path']
    manifest = json.loads(manifest_path.read_bytes())
    script = root / kwargs['reference_script_binding']['path']
    original = 'D:/TEST_ONLY-OLD-ROOT/scripts/reference_recipe.py'
    manifest['script'] = dict(path=original, sha256=sha256_file(script))
    write(manifest_path, manifest)
    kwargs['reference_manifest_binding'] = binding(root, manifest_path)
    publication = root / 'runtime/TEST_ONLY-old-publication.json'
    payload = dict(symbol=kwargs['symbol'], action='no_order', old_business_content='MUST_NOT_COPY',
        approved=True, verified_source_recoveries=[dict(original_path=original,
            expected_sha256=sha256_file(script), recovered_path=script.relative_to(root).as_posix())])
    write(publication, payload)
    registry_path = root / kwargs['case_registry_binding']['path']
    registry = json.loads(registry_path.read_bytes())
    registry['cases'][kwargs['symbol']].update(publication_input=publication.relative_to(root).as_posix(),
        publication_input_sha256=sha256_file(publication))
    write(registry_path, registry)
    kwargs['case_registry_binding'] = binding(root, registry_path)
    return kwargs, publication, payload, old_candidate


def test_v1_normal_path_unchanged(repair_inputs):
    kwargs, _, _ = repair_inputs
    result = v1.prepare_source_reobservation(**kwargs)
    assert v1.verify_source_reobservation(root=kwargs['root'],
        binding=binding(kwargs['root'], kwargs['output_dir'] / 'manifest.json')) == result


def test_v2_preserves_exact_recovery_without_inheriting_publication(transport_inputs):
    kwargs, _, _, old = transport_inputs
    root = kwargs['root']
    before = old.read_bytes()
    with pytest.raises(ValueError, match=r'^(?:daily research asset must remain under the project root|Reobserved case registry bindings are invalid)$'):
        v1.prepare_source_reobservation(**kwargs)
    kwargs['output_dir'] = root / 'runtime/v2-transport'
    result = v2.prepare_source_reobservation(**kwargs)
    assert v2.verify_source_reobservation(root=root,
        binding=binding(root, kwargs['output_dir'] / 'manifest.json')) == result
    transport = json.loads((root / result['transport_binding']['path']).read_bytes())
    assert set(transport) == {'schema_version', 'symbol', 'action', 'scope', 'verified_source_recoveries'}
    assert 'approved' not in transport and 'old_business_content' not in transport
    case = json.loads((root / result['case_registry_binding']['path']).read_bytes())['cases'][kwargs['symbol']]
    assert case['publication_input'] == result['transport_binding']['path']
    assert old.read_bytes() == before
    assert json.loads((root / result['receipt_binding']['path']).read_bytes())['price_admitted'] is False


@pytest.mark.parametrize('change', ['duplicate', 'slash_alias', 'conflict', 'wrong_hash', 'outside', 'relative_escape', 'issuer', 'v1_drift', 'malformed'])
def test_invalid_transport_fails_before_output(transport_inputs, change):
    kwargs, publication, payload, _ = transport_inputs
    row = payload['verified_source_recoveries'][0]
    if change == 'duplicate':
        payload['verified_source_recoveries'].append(deepcopy(row))
    elif change == 'slash_alias':
        payload['verified_source_recoveries'].append(dict(row, original_path=row['original_path'].replace('/', '\\')))
    elif change == 'conflict':
        payload['verified_source_recoveries'].append(dict(row, expected_sha256='0' * 64))
    elif change == 'wrong_hash':
        row['expected_sha256'] = '0' * 64
    elif change == 'outside':
        row['recovered_path'] = str(kwargs['root'].parent / 'outside.py')
    elif change == 'relative_escape':
        row['recovered_path'] = '../outside.py'
    elif change == 'issuer':
        payload['symbol'] = '000002'
    elif change == 'malformed':
        row['expected_sha256'] = 'BAD'
    else:
        path = kwargs['root'] / v1.IMPLEMENTATION
        path.write_bytes(path.read_bytes() + b'\n')
    write(publication, payload)
    registry_path = kwargs['root'] / kwargs['case_registry_binding']['path']
    registry = json.loads(registry_path.read_bytes())
    registry['cases'][kwargs['symbol']]['publication_input_sha256'] = sha256_file(publication)
    write(registry_path, registry)
    kwargs['case_registry_binding'] = binding(kwargs['root'], registry_path)
    with pytest.raises(ValueError):
        v2.prepare_source_reobservation(**kwargs)
    assert not kwargs['output_dir'].exists()


@pytest.mark.parametrize('change', ['transport', 'registry', 'package'])
def test_rehashed_successor_does_not_define_its_own_contract(transport_inputs, change):
    kwargs, _, _, _ = transport_inputs
    root = kwargs['root']
    result = v2.prepare_source_reobservation(**kwargs)
    role = dict(transport='transport_binding', registry='case_registry_binding', package='package_binding')[change]
    path = root / result[role]['path']
    payload = json.loads(path.read_bytes())
    if change == 'transport':
        payload['approved'] = True
    elif change == 'registry':
        payload['cases'][kwargs['symbol']].pop('publication_input')
    else:
        payload['research_case']['thesis'] += ' TEST_ONLY tamper'
    write(path, payload)
    result[role] = binding(root, path)
    manifest = kwargs['output_dir'] / 'manifest.json'
    write(manifest, result)
    with pytest.raises(ValueError):
        v2.verify_source_reobservation(root=root, binding=binding(root, manifest))
