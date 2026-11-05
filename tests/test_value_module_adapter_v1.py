"""TEST_ONLY mechanisms and explicit opt-in public-original replay; no paid calls."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
from copy import deepcopy
from uuid import uuid4

import pytest

from test_value_candidate_selection import source_package, NOW
from value_investment_agent.application.discovery import value_module_adapter_v1 as app
from value_investment_agent.domain.research.module_run_v1 import ModuleAdapter, ModuleRunCodec


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from value_investment_agent.infrastructure.agent_runtime import provider
    def denied(*a, **k):
        raise AssertionError('TEST_ONLY: network/paid transport forbidden')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(provider, 'build_opener', denied)
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider, 'complete', denied)


def inputs(binding):
    return dict(manifest_binding=binding, evaluation_at=NOW.isoformat(), limit=3)


def snapshot(root):
    return {p.relative_to(root).as_posix(): (sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_explicit_native_inputs_ignore_dirty_current_pointer(source_package):
    root, binding, _, _ = source_package
    pointer = root / '.tmp/daily-workbench-latest-run.json'
    pointer.parent.mkdir()
    pointer.write_bytes(b'TEST_ONLY deliberately invalid current pointer')
    before = snapshot(root)
    payload = inputs(binding)
    assert app.validate(root=root, payload=payload) == payload
    actual, scan = app._native(root, payload)
    expected = app.select_value_candidates(root=root, manifest_binding=binding, now=NOW, limit=3)
    assert actual == expected and scan['status'] == 'SOURCE_REVALIDATED'
    assert actual['formal_eligibility'] is False and actual['buy_eligible'] is False
    assert actual['coverage']['official_fact_admission_count'] == 0
    assert snapshot(root) == before


@pytest.mark.parametrize('change', [
    {'limit': True}, {'limit': 0}, {'limit': 201}, {'limit': 1.5},
    {'evaluation_at': '2026-10-23'}, {'evaluation_at': '2099-01-01T00:00:00+00:00'},
    {'symbol': 'bad'}, {'current_pointer': 'TEST_ONLY'},
    {'manifest_binding': {'path': '../escape.json', 'sha256': 'a'*64}},
    {'manifest_binding': {'path': 'runtime/daily-marketwide/test/manifest.json', 'sha256': 'a'*64}},
])
def test_invalid_explicit_input_rejected_without_write(source_package, change):
    root, binding, _, _ = source_package
    before = snapshot(root)
    with pytest.raises((ValueError, FileNotFoundError)):
        app.validate(root=root, payload={**inputs(binding), **change})
    assert snapshot(root) == before


@pytest.mark.parametrize('source', ['official', 'tencent', 'sina', 'financial', 'receipt', 'policy'])
def test_native_source_damage_never_becomes_empty_success(source_package, source):
    root, binding, manifest, _ = source_package
    path = root / manifest['files'][source]['path']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        app._native(root, inputs(binding))


def real_root():
    configured = os.environ.get('VALUE_MODULE_REAL_ROOT')
    if configured is None:
        if os.environ.get('VALUE_MODULE_REAL_REQUIRED') == '1':
            pytest.fail('VALUE_MODULE_REAL_REQUIRED requires public-original root')
        pytest.skip('Real public-original replay opt-in: VALUE_MODULE_REAL_ROOT')
    assert configured.strip(), 'Explicit real root cannot be empty'
    return Path(configured).resolve(strict=True)


def real_inputs(root):
    path = root / 'runtime/daily-marketwide/g1-restored-20261028-v4/manifest.json'
    assert path.is_file(), 'Required public original manifest missing'
    return dict(manifest_binding={'path': path.relative_to(root).as_posix(),
        'sha256': sha256(path.read_bytes()).hexdigest()},
        evaluation_at=datetime.now(timezone.utc).isoformat(), limit=30)


@pytest.fixture
def execution(source_package, monkeypatch):
    root, binding, manifest, _ = source_package
    code = dict(code_commit='a'*40, workspace_dirty=True, implementation_sha256={'TEST_ONLY': 'b'*64},
        adapter_version=app.VERSION, rule_version=app.RULE_VERSION, test_only=True)
    monkeypatch.setattr(app, '_code_identity', lambda root: deepcopy(code))
    return root, inputs(binding), manifest, code


def record_binding(root, directory):
    return app._binding(root, root / directory / 'module-run.json')


def test_eight_interfaces_native_output_and_immutable_replay(execution):
    root, payload, _, _ = execution
    adapter = app.ValueModuleAdapter(root)
    assert isinstance(adapter, ModuleAdapter)
    assert adapter.input_schema['required'] == ['manifest_binding', 'evaluation_at', 'limit']
    assert adapter.output_schema['properties']['schema_version']['const'] == 'module-run-v1'
    assert adapter.validate(payload) == payload
    assert adapter.health_check()['source_status'] == 'NOT_CHECKED'
    before = snapshot(root)
    record = adapter.run(payload, output_dir='runtime/TEST_ONLY-run')
    assert record.status == 'PARTIAL' and record.symbol is None
    assert record.metrics['assurance'] == 'TEST_ONLY'
    assert record.metrics['formal_eligibility'] is record.metrics['buy_eligible'] is False
    assert record.metrics['coverage']['official_fact_admission_count'] == 0
    assert record.created_at <= record.started_at <= record.finished_at
    assert ModuleRunCodec.from_payload(ModuleRunCodec.to_payload(record)).as_dict() == record.as_dict()
    native = app.select_value_candidates(root=root, manifest_binding=payload['manifest_binding'], now=NOW, limit=3)
    output = root / 'runtime/TEST_ONLY-run/selection.json'
    assert output.read_bytes() == app.encode_json_bytes(native)
    binding = record_binding(root, 'runtime/TEST_ONLY-run')
    assert adapter.get_run(binding).as_dict() == record.as_dict()
    repeated = adapter.replay(binding, output_dir='runtime/TEST_ONLY-replay')
    assert repeated.run_type == 'REPLAY' and repeated.parent_run_ids == [record.run_id]
    assert repeated.run_id != record.run_id
    assert repeated.input_manifest == record.input_manifest
    assert (root / 'runtime/TEST_ONLY-replay/selection.json').read_bytes() == output.read_bytes()
    assert adapter.explain(binding)['execution_scope'] == 'BATCH'
    for name, value in before.items():
        assert snapshot(root)[name] == value
    assert set(snapshot(root)) - set(before) == {
        'runtime/TEST_ONLY-run/selection.json', 'runtime/TEST_ONLY-run/module-run.json',
        'runtime/TEST_ONLY-replay/selection.json', 'runtime/TEST_ONLY-replay/module-run.json'}


def test_symbol_is_query_focus_never_false_single_issuer_execution(execution):
    root, payload, _, _ = execution
    payload['symbol'] = '600001'
    record = app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-focus')
    assert record.symbol is None and record.metrics['requested_symbol'] == '600001'
    assert record.metrics['execution_scope'] == 'BATCH'
    native = json.loads((root / 'runtime/TEST_ONLY-focus/selection.json').read_bytes())
    assert len(native['items']) == 4
    binding = record_binding(root, 'runtime/TEST_ONLY-focus')
    detail = app.explain(root=root, binding=binding)
    assert detail['execution_scope'] == 'BATCH' and detail['symbol_filter_only'] is True
    assert [row['symbol'] for row in detail['items']] == ['600001']
    missing = app.explain(root=root, binding=binding, symbol='999999')
    assert missing['items'] == [] and missing['symbol_status'] == 'NOT_IN_OBSERVED_SCOPE'
    assert missing['buy_eligible'] is False


@pytest.mark.parametrize('damage', ['record_hash', 'selection_hash', 'code_commit', 'implementation', 'rule'])
def test_record_output_or_code_drift_rejects_before_replay_write(execution, damage):
    root, payload, _, code = execution
    app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-drift')
    binding = record_binding(root, 'runtime/TEST_ONLY-drift')
    if damage == 'record_hash':
        binding['sha256'] = '0'*64
    elif damage == 'selection_hash':
        target = root / 'runtime/TEST_ONLY-drift/selection.json'
        target.write_bytes(target.read_bytes() + b' ')
    elif damage == 'code_commit':
        code['code_commit'] = 'f'*40
    elif damage == 'implementation':
        code['implementation_sha256']['TEST_ONLY'] = 'f'*64
    else:
        code['rule_version'] = 'TEST_ONLY_NEW_RULE'
    before = snapshot(root)
    with pytest.raises(ValueError):
        app.replay(root=root, binding=binding, output_dir='runtime/TEST_ONLY-denied')
    assert snapshot(root) == before


def test_source_damage_replay_failed_not_cached_empty_success(execution):
    root, payload, manifest, _ = execution
    app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-source')
    binding = record_binding(root, 'runtime/TEST_ONLY-source')
    original = app.get_run(root=root, binding=binding)
    path = root / manifest['files']['financial']['path']
    path.write_bytes(path.read_bytes() + b' ')
    # Historical record remains readable; only a new replay checks today's bytes.
    assert app.get_run(root=root, binding=binding).as_dict() == original.as_dict()
    failed = app.replay(root=root, binding=binding, output_dir='runtime/TEST_ONLY-failed')
    assert failed.status == 'FAILED' and failed.errors
    assert failed.output_manifest['items'] == [] and failed.source_refs == []
    assert failed.metrics['coverage'] is None
    assert not (root / 'runtime/TEST_ONLY-failed/selection.json').exists()


@pytest.mark.parametrize('output', ['../escape', '.tmp/not-runtime', 'runtime', 'runtime/daily-marketwide/test'])
def test_output_must_be_new_runtime_directory(execution, output):
    root, payload, _, _ = execution
    before = snapshot(root)
    with pytest.raises(ValueError):
        app.run(root=root, payload=payload, output_dir=output)
    assert snapshot(root) == before


def test_existing_empty_directory_and_repeat_run_not_overwritten(execution):
    root, payload, _, _ = execution
    empty = root / 'runtime/TEST_ONLY-empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='NEW_RUNTIME'):
        app.run(root=root, payload=payload, output_dir=empty)
    app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-once')
    before = snapshot(root)
    with pytest.raises(ValueError, match='NEW_RUNTIME'):
        app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-once')
    assert snapshot(root) == before


def test_verified_zero_shortlist_is_not_source_failure(execution, monkeypatch):
    root, payload, _, _ = execution
    selection, scan = app._native(root, payload)
    # TEST_ONLY transport case, not new ranking policy or genuine zero-market claim.
    selection['shortlist'] = []
    selection['coverage']['shortlist_count'] = 0
    monkeypatch.setattr(app, '_native', lambda *a: (deepcopy(selection), deepcopy(scan)))
    record = app.run(root=root, payload=payload, output_dir='runtime/TEST_ONLY-zero')
    assert record.status == 'PARTIAL' and record.errors == []
    assert record.metrics['coverage']['shortlist_count'] == 0
    assert (root / 'runtime/TEST_ONLY-zero/selection.json').is_file()


def test_real_public_manifest_native_replay_without_current_dependency():
    root = real_root()
    payload = real_inputs(root)
    manifest = app.validate(root=root, payload=payload)
    result, scan = app._native(root, manifest)
    refs = result['source_bindings']
    before = {ref['path']: sha256((root / ref['path']).read_bytes()).hexdigest() for ref in refs}
    repeated, repeated_scan = app._native(root, manifest)
    assert repeated == result and repeated_scan == scan
    assert before == {ref['path']: sha256((root / ref['path']).read_bytes()).hexdigest() for ref in refs}
    assert all(before[ref['path']] == ref['sha256'] for ref in refs)
    assert scan['status'] == 'SOURCE_REVALIDATED'
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert result['buy_eligible'] is False and result['coverage']['official_fact_admission_count'] == 0
    scope = result.get('screening_scope', {})
    print(json.dumps({'real_native_replay': 'VERIFIED', 'coverage': result['coverage'],
        'screening_scope': {key: scope.get(key) for key in
            ('all_a_complete', 'covered_venues', 'failed_venues', 'effective_session')},
        'blockers': result['blockers']}, ensure_ascii=False))


def test_real_explicit_manifest_module_run_and_replay():
    root = real_root()
    payload = real_inputs(root)
    prefix = 'runtime/value-module-adapter-acceptance/' + uuid4().hex
    # Public pointer hashes only; never load accounts or private workspaces.
    protected = [root / '.tmp/daily-workbench-latest-run.json', root / 'config/current-research-drafts.json']
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
    adapter = app.ValueModuleAdapter(root)
    record = adapter.run(payload, output_dir=prefix + '/original')
    assert record.status == 'PARTIAL', record.as_dict()
    assert record.symbol is None and record.metrics['execution_scope'] == 'BATCH'
    assert record.metrics['assurance'] == 'REAL_PUBLIC_REPLAY'
    assert record.metrics['coverage']['universe_count'] == 5224
    assert record.metrics['coverage']['official_fact_admission_count'] == 0
    assert record.metrics['financial_source_admitted'] is False
    binding = record_binding(root, prefix + '/original')
    assert adapter.get_run(binding).as_dict() == record.as_dict()
    replayed = adapter.replay(binding, output_dir=prefix + '/replay')
    assert replayed.status == 'PARTIAL' and replayed.parent_run_ids == [record.run_id]
    assert replayed.input_manifest == record.input_manifest
    assert (root / prefix / 'original/selection.json').read_bytes() == (root / prefix / 'replay/selection.json').read_bytes()
    assert before == {str(p): sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
    assert adapter.explain(binding, symbol='000568')['execution_scope'] == 'BATCH'
    print(json.dumps({'actual_module_run': binding, 'replay': record_binding(root, prefix + '/replay'),
        'status': record.status, 'coverage': record.metrics['coverage'], 'code_commit': record.code_commit}, ensure_ascii=False))
