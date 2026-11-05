"""TEST_ONLY route contracts; synthetic read models do not claim real acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from value_investment_agent.presentation.web_api import value_workbench_routes as routes
from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
from value_investment_agent.infrastructure.agent_runtime import provider
from test_operating_cash_consumption_v1 import no_io_effects
from test_value_candidate_selection import source_package, NOW


@pytest.fixture
def case(tmp_path, monkeypatch):
    data = SimpleNamespace(reads=[], calls=[], failure=None, view=dict(
        status='PARTIAL', symbol='000568', action='no_order', formal_eligibility=False,
        evidence_downloads=[], marker='TEST_ONLY_READMODEL'))
    data.actual_reader = routes._read_workbench
    data.actual_service = routes._task_service
    data.actual_task_read = routes._task_read
    data.actual_task_list = routes._task_list
    data.actual_task_history = routes._task_history
    def read(project, symbol):
        data.reads.append((project, symbol))
        if data.failure is not None:
            raise data.failure
        return deepcopy(data.view)
    def forbidden(*a, **kw):
        raise AssertionError('TEST_ONLY: no paid provider or network')
    monkeypatch.setattr(routes, '_read_workbench', read)
    monkeypatch.setattr(provider, 'build_opener', forbidden)
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider, 'complete', forbidden)
    class TestOnlyTasks:
        def _result(self, method, **kwargs):
            data.calls.append((method, kwargs))
            if data.failure is not None:
                raise data.failure
            return dict(task_id='rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status='CANCELLED' if method == 'cancel' else 'QUEUED',
                        action='no_order', formal_eligibility=False)
        def create(self, **kwargs): return self._result('create', **kwargs)
        def run(self, task_id): return self._result('run', task_id=task_id)
        def read(self, task_id): return self._result('read', task_id=task_id)
        def history(self, task_id): return [self._result('history', task_id=task_id)]
        def list_for_symbol(self, symbol): return [self._result('list', symbol=symbol)]
        def cancel(self, task_id): return self._result('cancel', task_id=task_id)
        def retry(self, task_id): return self._result('retry', task_id=task_id)
        def resume(self, task_id): return self._result('resume', task_id=task_id)
    monkeypatch.setattr(routes, '_task_service', lambda project: TestOnlyTasks())
    monkeypatch.setattr(routes, '_task_read', lambda service, task_id: service.read(task_id))
    monkeypatch.setattr(routes, '_task_list', lambda service, symbol: service.list_for_symbol(symbol))
    monkeypatch.setattr(routes, '_task_history', lambda service, task_id: service.history(task_id))
    api = FastAPI()
    session = LocalOperatorSession(bootstrap_secret='TEST_ONLY-secret')
    routes.register_value_workbench_routes(api, project=tmp_path, sessions=session, port=8791)
    client = TestClient(api, base_url='http://127.0.0.1:8791', client=('127.0.0.1', 51000))
    client.headers.update({'host': '127.0.0.1:8791', 'origin': 'http://127.0.0.1:8791'})
    return client, session, data, tmp_path


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_public_read_no_account_no_auth_no_write_or_network(case):
    client, session, data, root = case
    before = snapshot(root)
    with client:
        with no_io_effects():
            for _ in range(2):
                response = client.get(routes.BASE, params={'symbol': '000568'})
                assert response.status_code == 200 and response.json() == data.view
                assert response.headers['cache-control'] == 'no-store'
    assert not session.unlocked and snapshot(root) == before
    assert data.reads == [(root, '000568'), (root, '000568')]
    assert not data.calls


def test_actual_euclid_readmodel_empty_public_root_is_read_only(case, monkeypatch):
    client, _, data, root = case
    monkeypatch.setattr(routes, '_read_workbench', data.actual_reader)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '?symbol=000568')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['schema_version'] == 'value-transparent-workbench-v1'
    assert body['action'] == 'no_order' and body['formal_eligibility'] is False
    assert next(row for row in body['sections'] if row['id'] == 'continuity')['status'] == 'PRIVATE_CONTEXT_REQUIRED'
    assert body['evidence_downloads'] == [] and snapshot(root) == before
    assert body['portfolio_entry'] == dict(href='/portfolio', workflow='EXISTING_PREPARE_CONFIRM',
        scope='NO_TRADE_RECORDED_BY_WORKBENCH')


@pytest.mark.parametrize('query', ['', 'symbol=bad', 'symbol=000568&path=private.json',
                                   'symbol=000568&symbol=600519'])
def test_bad_public_queries_never_read_sources(case, query):
    client, _, data, _ = case
    response = client.get(routes.BASE + '?' + query)
    assert response.status_code == 422 and response.json()['action'] == 'no_order'
    assert not data.reads


@pytest.mark.parametrize('error', [ValueError('TEST_ONLY_SOURCE_HASH_MISMATCH'),
                                  OSError('TEST_ONLY_SOURCE_MISSING'), ImportError('TEST_ONLY_NOT_READY')])
def test_reader_failure_precise_not_empty_success(case, error):
    client, _, data, _ = case
    data.failure = error
    response = client.get(routes.BASE, params={'symbol': '000568'})
    assert response.status_code == (503 if isinstance(error, ImportError) else 422)
    assert response.json()['reason'] == str(error)
    assert response.json()['status'] == 'UNASSESSABLE'
    assert response.json()['formal_eligibility'] is False


def write_catalog(root):
    source = root / 'src/TEST_ONLY.py'
    source.parent.mkdir()
    source.write_text("raise AssertionError('must not import native source')\ndef available(): pass\n", encoding='utf-8')
    path = root / 'config/value-mainline-modules-v1.json'
    path.parent.mkdir()
    payload = dict(schema_version='value-mainline-modules-v1', action='no_order', modules=[
        dict(module_id='B', title='TEST_ONLY', entrypoints=[
            dict(path='src/TEST_ONLY.py', entrypoint='available'),
            dict(path='src/TEST_ONLY.py', entrypoint='not_implemented'),
            dict(path='src/TEST_ONLY-missing.py', entrypoint='missing')])])
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_modules_report_source_presence_without_import_or_fake_runtime(case):
    client, _, data, root = case
    write_catalog(root)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/modules')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['runtime_status'] == 'NOT_READ'
    assert body['formal_eligibility'] is False and body['action'] == 'no_order'
    entries = body['modules'][0]['native_source_metadata']
    assert [row['inspection'] for row in entries] == [
        'SOURCE_DEFINITION_PRESENT', 'SOURCE_DEFINITION_NOT_FOUND', 'SOURCE_FILE_MISSING']
    assert all(row['runtime_status'] == 'NOT_READ' for row in entries)
    assert snapshot(root) == before and not data.reads


def test_catalog_failure_not_invented_modules(case):
    client, _, _, root = case
    path = write_catalog(root)
    path.write_bytes(b'TEST_ONLY_CORRUPT')
    response = client.get(routes.BASE + '/modules')
    assert response.status_code == 422 and response.json()['status'] == 'UNASSESSABLE'


def test_actual_module_catalog_static_metadata_not_runtime():
    root = Path(__file__).resolve().parents[2]
    with no_io_effects():
        result = routes._catalog(root)
    assert {row['module_id'] for row in result['modules']} == routes.MODULES
    assert all(row['runtime_status'] == 'NOT_READ' for row in result['modules'])
    assert result['catalog_binding']['sha256'] == sha256(
        (root / 'config/value-mainline-modules-v1.json').read_bytes()).hexdigest()


def evidence_fixture(data, root):
    path = root / 'runtime/TEST_ONLY-original.bin'
    path.parent.mkdir()
    path.write_bytes(b'TEST_ONLY NOT A REAL FINANCIAL ORIGINAL')
    data.view['evidence_downloads'] = [dict(id='TEST_ONLY-source', binding={
        'path': path.relative_to(root).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()})]
    return path


def test_download_only_aggregated_hash_verified_bytes(case):
    client, _, data, root = case
    path = evidence_fixture(data, root)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/evidence/TEST_ONLY-source?symbol=000568')
    assert response.status_code == 200 and response.content == path.read_bytes()
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert snapshot(root) == before


@pytest.mark.parametrize('damage', ['hash', 'unlisted', 'duplicate', 'escape', 'path_query'])
def test_download_rejects_unbound_tampered_or_arbitrary_path(case, damage):
    client, _, data, root = case
    path = evidence_fixture(data, root)
    endpoint = routes.BASE + '/evidence/TEST_ONLY-source?symbol=000568'
    if damage == 'hash':
        path.write_bytes(b'TEST_ONLY_TAMPER')
    elif damage == 'unlisted':
        data.view['evidence_downloads'] = []
    elif damage == 'duplicate':
        data.view['evidence_downloads'] *= 2
    elif damage == 'escape':
        data.view['evidence_downloads'][0]['binding']['path'] = '../private.json'
    else:
        endpoint += '&path=runtime/TEST_ONLY-original.bin'
    before = snapshot(root)
    response = client.get(endpoint)
    assert response.status_code == 404 and response.json()['status'] == 'UNASSESSABLE'
    assert snapshot(root) == before


def unlock(client, session):
    client.headers['x-local-session'] = session.unlock('TEST_ONLY-secret')


def task_body():
    return dict(module_id='B', operation='REPLAY_SELECTION', symbol='000568',
                request_key='TEST_ONLY-request', payload={'label': 'TEST_ONLY'})


@pytest.mark.parametrize('suffix', ['/tasks', '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/cancel',
                                   '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/retry', '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/resume'])
def test_task_writes_require_real_local_auth_before_service(case, suffix):
    client, _, data, root = case
    before = snapshot(root)
    response = client.post(routes.BASE + suffix, json=task_body())
    assert response.status_code == 401
    assert response.json()['status'] == 'LOCAL_AUTHORIZATION_REQUIRED'
    assert data.calls == [] and snapshot(root) == before


def test_wrong_origin_rejected_even_with_session(case):
    client, session, data, _ = case
    unlock(client, session)
    client.headers['origin'] = 'https://example.invalid'
    response = client.post(routes.BASE + '/tasks', json=task_body())
    assert response.status_code == 403 and response.json()['status'] == 'ORIGIN_REJECTED'
    assert data.calls == []


def test_authorized_create_dispatches_native_background_not_fake_success(case):
    client, session, data, _ = case
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks', json=task_body())
    assert response.status_code == 202 and response.json()['status'] == 'QUEUED'
    assert response.json()['formal_eligibility'] is False
    assert data.calls == [('create', {k:v for k,v in task_body().items() if k != 'module_id'}),
                          ('run', {'task_id': 'rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'})]


@pytest.mark.parametrize('changes', [{'module_id': 'S1'}, {'operation': 'approve'},
    {'symbol': 'bad'}, {'payload': []}, {'request_key': 'x'}, {'endpoint': 'https://example.invalid'},
    {'actor': 'admin'}, {'approved': True}, {'permission': 'G3'},
    {'operation': 'RECALCULATE_MAIN'}, {'timeout_seconds': True}])
def test_invalid_create_contract_never_reaches_service(case, changes):
    client, session, data, _ = case
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks', json={**task_body(), **changes})
    assert response.status_code == 422 and response.json()['action'] == 'no_order'
    assert data.calls == []


@pytest.mark.parametrize('raw', [b'[' , b'{"module_id":"B","module_id":"A"}',
                                b'{"inputs":NaN}', b' ' * (routes.MAX_BODY + 1)])
def test_oversize_duplicate_nonfinite_or_invalid_json_rejected(case, raw):
    client, session, data, _ = case
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks', content=raw,
                           headers={'content-type': 'application/json'})
    assert response.status_code == 422 and data.calls == []


@pytest.mark.parametrize('operation', ['cancel', 'retry', 'resume'])
def test_control_dispatch_and_background_allowlist(case, operation):
    client, session, data, _ = case
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/' + operation, json={})
    assert response.status_code == 200 and response.json()['action'] == 'no_order'
    assert [call[0] for call in data.calls] == ([operation] if operation == 'cancel' else [operation, 'run'])


@pytest.mark.parametrize('operation,body', [('approve', {}), ('__dict__', {}),
                                          ('cancel', {'action': 'approve'})])
def test_controls_cannot_become_arbitrary_methods_or_approval(case, operation, body):
    client, session, data, _ = case
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/' + operation, json=body)
    assert response.status_code == 409 and data.calls == []


def test_task_gets_only_read_and_history_no_restart_or_write(case):
    client, session, data, root = case
    unlock(client, session)
    before = snapshot(root)
    with client:
        with no_io_effects():
            for suffix in ('/tasks?symbol=000568', '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                           '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/history',
                           '/tasks/history/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'):
                response = client.get(routes.BASE + suffix)
                assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert [call[0] for call in data.calls] == ['list', 'read', 'history', 'history']
    assert snapshot(root) == before


@pytest.mark.parametrize('suffix', ['/tasks?symbol=000568', '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    '/tasks/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/history', '/tasks/history/rt-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'])
def test_unauthorized_task_reads_never_expose_opinions_or_assumptions(case, monkeypatch, suffix):
    client, _, data, root = case
    sensitive = {'opinion': 'TEST_ONLY_PRIVATE_NOTE', 'changes': ['TEST_ONLY_PRIVATE_CHANGE'],
                 'rationale': 'TEST_ONLY_PRIVATE_RATIONALE', 'originalstate': 'TEST_ONLY_PRIVATE_ORIGINAL'}
    def leak(*args):
        data.calls.append(('PRIVATE_TASK_READ', {}))
        return sensitive
    for helper in ('_task_read', '_task_list', '_task_history'):
        monkeypatch.setattr(routes, helper, leak)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + suffix)
    assert response.status_code == 401
    assert response.json()['status'] == 'LOCAL_AUTHORIZATION_REQUIRED'
    assert response.headers['cache-control'] == 'no-store'
    assert 'TEST_ONLY_PRIVATE_' not in response.text
    assert data.calls == [] and snapshot(root) == before


def test_denied_task_history_does_not_block_public_research_endpoints(case):
    client, _, data, root = case
    company_registries(root)
    (root / 'config/value-mainline-modules-v1.json').write_text(json.dumps(dict(
        schema_version='value-mainline-modules-v1', action='no_order', modules=[])), encoding='utf-8')
    assert client.get(routes.BASE + '/tasks?symbol=000568').status_code == 401
    for suffix in ('?symbol=000568', '/companies', '/modules?symbol=000568', '/task-inputs?symbol=000568'):
        response = client.get(routes.BASE + suffix)
        assert response.status_code == 200, response.text
        assert response.json()['action'] == 'no_order'
    assert data.calls == []


def test_task_failure_exact_reason_no_background(case):
    client, session, data, _ = case
    unlock(client, session)
    data.failure = ValueError('TEST_ONLY_REGISTERED_SOURCE_HASH_MISMATCH')
    response = client.post(routes.BASE + '/tasks', json=task_body())
    assert response.status_code == 422
    assert response.json()['reason'] == 'TEST_ONLY_REGISTERED_SOURCE_HASH_MISMATCH'
    assert [call[0] for call in data.calls] == ['create']


def test_actual_darwin_task_persistence_and_readonly_gets(case, source_package, monkeypatch):
    from value_investment_agent.application.research.transparent_task_v1 import TransparentTaskService
    client, session, data, root = case
    _, binding, _, _ = source_package
    for name in ('service', 'task_read', 'task_list', 'task_history'):
        monkeypatch.setattr(routes, '_' + ('task_service' if name == 'service' else name),
                            getattr(data, 'actual_' + name))
    executions = []
    def test_worker(self, spec, attempt):
        executions.append(spec['operation'])
        return dict(outcome='PARTIAL', action='no_order', formal_eligibility=False,
                    artifact_bindings=[], result={'scope': 'TEST_ONLY_WORKER_NOT_REAL_RESEARCH'})
    monkeypatch.setattr(TransparentTaskService, '_execute', test_worker)
    unlock(client, session)
    body = dict(task_body(), payload=dict(manifest_binding=binding, evaluation_at=NOW.isoformat(), limit=3))
    response = client.post(routes.BASE + '/tasks', json=body)
    assert response.status_code == 202, response.text
    task_id = response.json()['task_id']
    assert executions == ['REPLAY_SELECTION']
    before = snapshot(root)
    with client:
        with no_io_effects():
            read = client.get(routes.BASE + '/tasks/' + task_id)
            history = client.get(routes.BASE + '/tasks/' + task_id + '/history')
            listing = client.get(routes.BASE + '/tasks?symbol=000568')
    assert read.status_code == history.status_code == listing.status_code == 200
    assert read.json()['status'] == 'PARTIAL' and read.json()['operation'] == 'REPLAY_SELECTION'
    assert read.json()['native_metadata']['approval_changed'] is False
    assert len(history.json()['history']) >= 2 and len(listing.json()['items']) == 1
    assert snapshot(root) == before and executions == ['REPLAY_SELECTION']


def test_fresh_scan_is_distinct_operation_and_requires_explicit_network_authorization(case, monkeypatch):
    client, session, data, root = case
    monkeypatch.setattr(routes, '_task_service', data.actual_service)
    unlock(client, session)
    before = snapshot(root)
    response = client.post(routes.BASE + '/tasks', json=dict(task_body(), operation='FRESH_PUBLIC_SCAN',
        payload={'network_authorized': False, 'max_per_channel': 3}))
    assert response.status_code == 422
    assert response.json()['reason'] == 'EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED'
    assert snapshot(root) == before
    assert routes.OPERATION_MODULES['REPLAY_SELECTION'] == routes.OPERATION_MODULES['FRESH_PUBLIC_SCAN'] == 'B'


def test_actual_reader_generates_download_ids_only_from_evidence_section(case, monkeypatch):
    from value_investment_agent.application.product import value_transparent_workbench_v1 as aggregate
    client, _, data, root = case
    path = evidence_fixture(data, root)
    binding = data.view['evidence_downloads'][0]['binding']
    monkeypatch.setattr(routes, '_read_workbench', data.actual_reader)
    monkeypatch.setattr(aggregate, 'read_value_transparent_workbench', lambda **kw: dict(
        action='no_order', formal_eligibility=False, symbol=kw['symbol'], sections=[
            {'id': 'evidence', 'data': {'source_bindings': [binding]}}],
        evidence_downloads=[{'id': 'TEST_ONLY_UNTRUSTED_EXTRA', 'binding': binding}]))
    response = client.get(routes.BASE + '?symbol=000568')
    links = response.json()['evidence_downloads']
    assert len(links) == 1 and links[0]['id'] != 'TEST_ONLY_UNTRUSTED_EXTRA'
    downloaded = client.get(links[0]['url'])
    assert downloaded.status_code == 200 and downloaded.content == path.read_bytes()
    assert client.get(routes.BASE + '/evidence/TEST_ONLY_UNTRUSTED_EXTRA?symbol=000568').status_code == 404


def test_prepared_inputs_public_readonly_and_no_manual_binding_fields(case, monkeypatch):
    client, _, data, root = case
    calls = []
    spec = {'path': 'runtime/TEST_ONLY-spec.json', 'sha256': 'a'*64}
    prepared = dict(symbol='000568', action='no_order', operations=[
        dict(operation='RECALCULATE_MAIN', enabled=True, payload={
            'registry_binding': spec, 'spec_binding': spec}, user_fields=[]),
        dict(operation='FRESH_PUBLIC_SCAN', enabled=True,
            payload={'network_authorized': True, 'max_per_channel': 3},
            user_fields=[{'name': 'network_authorized', 'type': 'checkbox'}]),
        dict(operation='SIMULATE_ASSUMPTIONS', enabled=False, reason='TEST_ONLY_NO_VERIFIED_BASELINE',
             payload={'spec_binding': spec})])
    def prepare(*, symbol):
        calls.append(symbol)
        return deepcopy(prepared)
    monkeypatch.setattr(routes, '_task_service', lambda project: SimpleNamespace(prepare=prepare))
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/task-inputs?symbol=000568')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    body = response.json()
    rows = {row['operation']: row for row in body['operations']}
    assert rows['RECALCULATE_MAIN']['prepared_payload']['spec_binding'] == spec
    assert rows['RECALCULATE_MAIN']['user_fields'] == []
    assert rows['FRESH_PUBLIC_SCAN']['prepared_payload']['network_authorized'] is False
    assert prepared['operations'][1]['payload']['network_authorized'] is True
    assert rows['SIMULATE_ASSUMPTIONS']['enabled'] is False
    assert rows['SIMULATE_ASSUMPTIONS']['prepared_payload'] is rows['SIMULATE_ASSUMPTIONS']['payload'] is None
    assert body['tasks_started'] == 0 and calls == ['000568'] and data.calls == []
    assert snapshot(root) == before


@pytest.mark.parametrize('mode', ['missing', 'failure', 'no_payload', 'bad_scope'])
def test_preparation_missing_or_invalid_is_disabled_not_fake_run(case, monkeypatch, mode):
    client, _, data, _ = case
    def prepare(**kwargs):
        if mode == 'failure':
            raise ValueError('TEST_ONLY_CURRENT_SPEC_HASH_MISMATCH')
        return dict(action='no_order', symbol='600519' if mode == 'bad_scope' else '000568',
            operations=[dict(operation='RECALCULATE_MAIN', enabled=True, payload=None)])
    monkeypatch.setattr(routes, '_task_service', lambda project:
                        SimpleNamespace() if mode == 'missing' else SimpleNamespace(prepare=prepare))
    body = client.get(routes.BASE + '/task-inputs?symbol=000568').json()
    assert body['status'] == 'DISABLED' and body['tasks_started'] == 0
    assert all(row['enabled'] is False and row['prepared_payload'] is None and row['reason']
               for row in body['operations'])
    if mode == 'failure':
        assert body['operations'][0]['reason'] == 'TEST_ONLY_CURRENT_SPEC_HASH_MISMATCH'
    assert data.calls == []


def test_modules_symbol_includes_preparation_without_starting_task(case):
    client, _, data, root = case
    write_catalog(root)
    before = snapshot(root)
    response = client.get(routes.BASE + '/modules?symbol=000568')
    assert response.status_code == 200
    assert response.json()['task_inputs']['status'] == 'DISABLED'
    assert response.json()['task_inputs']['tasks_started'] == 0
    assert snapshot(root) == before and data.calls == []


def test_review_note_actual_task_uses_server_actor_and_never_approves(case, monkeypatch):
    from value_investment_agent.application.research import transparent_task_v1 as native
    client, session, data, root = case
    monkeypatch.setattr(routes, '_task_service', data.actual_service)
    monkeypatch.setattr(native.TransparentTaskService, '_execute',
                        lambda self, spec, attempt: native._dispatch(self, spec, attempt))
    target = root / 'runtime/value-TEST_ONLY/target.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(dict(symbol='000568', action='no_order', label='TEST_ONLY_RESEARCH')), encoding='utf-8')
    raw = target.read_bytes()
    pin = dict(path=target.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    body = dict(task_body(), module_id='G2', operation='REVIEW_NOTE',
                payload=dict(target_binding=pin, opinion='TEST_ONLY：仍需核实现金可达，不批准。'))
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks', json=body)
    assert response.status_code == 202, response.text
    service = native.TransparentTaskService(root)
    spec, state, _ = service._load(response.json()['task_id'], recover=False)
    assert spec['actor_context'] == native.REVIEW_ACTOR_CONTEXT
    assert spec['payload']['target_binding'] == pin and state['status'] == 'SUCCEEDED'
    manifest = service._bound(state['output_manifest'])
    note = service._bound(manifest['artifacts'][0])['result']
    assert note['scope'] == 'COMMENT_NOT_G3_APPROVAL'
    assert note['approval_changed'] is note['formal_eligibility'] is note['signed'] is False
    assert target.read_bytes() == raw
    forbidden = client.post(routes.BASE + '/tasks', json=dict(body, actor_context=native.REVIEW_ACTOR_CONTEXT))
    assert forbidden.status_code == 422 and forbidden.json()['reason'] == 'INVALID_TASK_CREATE_FIELDS'
    before = snapshot(root)
    for key, value in [('actor', 'admin'), ('approved', True), ('permission', 'G3'),
                       ('actor_context', native.REVIEW_ACTOR_CONTEXT)]:
        forbidden = client.post(routes.BASE + '/tasks', json=dict(body,
            payload=dict(body['payload'], **{key: value})))
        assert forbidden.status_code == 422
        assert forbidden.json()['reason'] == 'EXACT_NATIVE_INPUT_FIELDS_REQUIRED'
    assert snapshot(root) == before


def test_prepared_recalculation_binding_change_is_rejected_at_post(case, monkeypatch):
    from value_investment_agent.application.research import transparent_task_v1 as native
    from test_transparent_task_v1 import register_main_for_prepare
    client, session, data, root = case
    # TEST_ONLY metadata includes the real current implementation fingerprints;
    # native prepare/validation remain intact, with no financial acceptance claim.
    spec_binding, _ = register_main_for_prepare(root)
    spec = root / spec_binding['path']
    service = native.TransparentTaskService(root)
    monkeypatch.setattr(routes, '_task_service', lambda project: service)
    prepared = client.get(routes.BASE + '/task-inputs?symbol=000568').json()
    row = next(row for row in prepared['operations'] if row['operation'] == 'RECALCULATE_MAIN')
    assert row['enabled'] is True and row['user_fields'] == []
    spec.write_bytes(spec.read_bytes() + b' ')
    before = snapshot(root)
    unlock(client, session)
    response = client.post(routes.BASE + '/tasks', json=dict(task_body(), module_id='F1',
        operation='RECALCULATE_MAIN', payload=row['prepared_payload']))
    assert response.status_code == 422 and response.json()['reason'] == 'Task binding hash mismatch'
    assert snapshot(root) == before


def test_actual_darwin_prepare_empty_root_disables_unregistered_operations(case, monkeypatch):
    client, _, data, root = case
    monkeypatch.setattr(routes, '_task_service', data.actual_service)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/task-inputs?symbol=000568')
    assert response.status_code == 200
    body = response.json()
    rows = {row['operation']: row for row in body['operations']}
    assert rows['FRESH_PUBLIC_SCAN']['enabled'] is True
    assert rows['FRESH_PUBLIC_SCAN']['prepared_payload']['network_authorized'] is False
    assert rows['FRESH_PUBLIC_SCAN']['user_fields'] == ['network_authorized']
    for operation in ('RECALCULATE_MAIN', 'SIMULATE_ASSUMPTIONS', 'REVIEW_NOTE',
                      'VERIFY_EVIDENCE', 'REPLAY_SELECTION'):
        assert rows[operation]['enabled'] is False and rows[operation]['reason']
        assert rows[operation]['prepared_payload'] is None
    assert body['tasks_started'] == 0 and snapshot(root) == before


def test_actual_prepare_registered_main_builds_hidden_bindings_and_editable_fields(case, monkeypatch):
    from test_transparent_task_v1 import register_main_for_prepare
    from value_investment_agent.application.research.transparent_task_v1 import CASH_OVERRIDES
    client, _, data, root = case
    ref, source = register_main_for_prepare(root)
    monkeypatch.setattr(routes, '_task_service', data.actual_service)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/task-inputs?symbol=000568')
    body = response.json()
    rows = {row['operation']: row for row in body['operations']}
    assert rows['RECALCULATE_MAIN']['enabled'] is True
    assert rows['RECALCULATE_MAIN']['prepared_payload']['spec_binding'] == ref
    assert rows['RECALCULATE_MAIN']['user_fields'] == []
    assert rows['SIMULATE_ASSUMPTIONS']['user_fields'] == ['scenario', 'changes', 'rationale']
    assert set(body['simulation_fields']) == CASH_OVERRIDES
    assert rows['REVIEW_NOTE']['prepared_payload'] == {'target_binding': ref, 'opinion': ''}
    assert rows['REVIEW_NOTE']['user_fields'] == ['opinion']
    assert snapshot(root) == before and data.calls == []
    (root / source['path']).write_bytes(b'TEST_ONLY_CHANGED_SOURCE')
    rows = {row['operation']: row for row in client.get(routes.BASE + '/task-inputs?symbol=000568').json()['operations']}
    assert rows['RECALCULATE_MAIN']['enabled'] is False
    assert rows['RECALCULATE_MAIN']['prepared_payload'] is None
    assert rows['RECALCULATE_MAIN']['reason'] == 'MAIN_BASELINE_INVALID'


def test_real_public_task_input_preparation_without_new_tasks():
    location = os.environ.get('TRANSPARENT_TASK_REAL_ROOT')
    if location is None:
        pytest.skip('Set TRANSPARENT_TASK_REAL_ROOT for existing public registrations')
    assert location.strip()
    root = Path(location).resolve(strict=True)
    task_root = root / 'runtime/research-task-execution-v1/transparent-v1'
    before = set(task_root.iterdir()) if task_root.exists() else set()
    observed = {}
    with no_io_effects():
        for symbol in ('600519', '600887', '000568'):
            body = routes._task_inputs(root, symbol)
            rows = {row['operation']: row for row in body['operations']}
            assert body['tasks_started'] == 0 and rows['FRESH_PUBLIC_SCAN']['prepared_payload']['network_authorized'] is False
            assert rows['REPLAY_SELECTION']['enabled'], rows
            assert rows['REVIEW_NOTE']['enabled'], rows
            required = 'RECALCULATE_MAIN' if symbol == '000568' else 'VERIFY_EVIDENCE'
            assert rows[required]['enabled'], rows
            assert rows[required]['user_fields'] == []
            observed[symbol] = {operation: row['enabled'] for operation, row in rows.items()}
    assert (set(task_root.iterdir()) if task_root.exists() else set()) == before
    print(json.dumps({'real_preparation': observed, 'new_tasks': 0}, ensure_ascii=False))


def company_registries(root):
    directory = root / 'config'
    directory.mkdir()
    drafts = directory / 'current-research-drafts.json'
    operating = directory / 'current-operating-research-sources-v1.json'
    drafts.write_text(json.dumps(dict(schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={'600001': {'path': 'TEST_ONLY-not-opened', 'sha256': 'a'*64},
                            '600002': {'path': 'TEST_ONLY-not-opened', 'sha256': 'b'*64}})), encoding='utf-8')
    operating.write_text(json.dumps(dict(schema_version='current-operating-research-sources-v1', action='no_order',
        cases={'000001': {}, '600002': {}})), encoding='utf-8')
    return drafts, operating


def test_companies_union_registration_not_shortlist_or_research_success(case):
    client, _, data, root = case
    company_registries(root)
    before = snapshot(root)
    with client:
        with no_io_effects():
            response = client.get(routes.BASE + '/companies')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'REGISTERED_ENTRIES'
    assert [row['symbol'] for row in body['items']] == ['000001', '600001', '600002']
    for row in body['items']:
        assert row['name'] is None and row['status'] == 'REGISTERED_NOT_YET_REVALIDATED'
        assert row['research_verified'] is False and row['current_candidate'] is None
        assert row['formal_eligibility'] is False and row['url'].endswith(row['symbol'])
    assert len(body['items'][-1]['source_registries']) == 2
    assert data.reads == data.calls == [] and snapshot(root) == before


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'schema', 'action', 'symbol', 'duplicate'])
def test_one_registry_failure_keeps_other_source_partial_with_reason(case, damage):
    client, _, _, root = case
    drafts, _ = company_registries(root)
    payload = json.loads(drafts.read_bytes())
    if damage == 'missing':
        drafts.unlink()
    elif damage == 'corrupt':
        drafts.write_bytes(b'TEST_ONLY_BAD_REGISTRY')
    elif damage == 'duplicate':
        drafts.write_bytes(b'{"schema_version":"current-research-drafts-v1","action":"no_order","action":"approve"}')
    else:
        if damage == 'schema': payload['schema_version'] = 'TEST_ONLY_WRONG'
        if damage == 'action': payload['action'] = 'approve'
        if damage == 'symbol': payload['pending_candidates']['not-symbol'] = {}
        drafts.write_text(json.dumps(payload), encoding='utf-8')
    body = client.get(routes.BASE + '/companies').json()
    assert body['status'] == 'PARTIAL'
    assert [row['symbol'] for row in body['items']] == ['000001', '600002']
    failed = [row for row in body['sources'] if row['status'] == 'UNASSESSABLE']
    assert len(failed) == 1 and failed[0]['reason'] and failed[0]['error_type']


def test_both_registry_failures_not_fake_empty_success(case):
    client, _, _, _ = case
    body = client.get(routes.BASE + '/companies').json()
    assert body['status'] == 'UNASSESSABLE' and body['items'] == []
    assert len(body['sources']) == 2 and all(row['reason'] for row in body['sources'])


def test_actual_registered_company_entry_list_not_tied_to_current_shortlist():
    import os
    location = os.environ.get('TRANSPARENT_TASK_REAL_ROOT')
    root = Path(location).resolve() if location else Path(__file__).resolve().parents[2]
    expected = set()
    for name, field in (
            ('config/current-research-drafts.json', 'pending_candidates'),
            ('config/current-operating-research-sources-v1.json', 'cases')):
        expected.update(json.loads((root / name).read_bytes()).get(field, {}))
    with no_io_effects():
        body = routes._companies(root)
    assert body['status'] == 'REGISTERED_ENTRIES', body
    assert {row['symbol'] for row in body['items']} == expected
    if location:
        assert {'600519', '600887', '000568'} <= expected
    assert all(row['status'] == 'REGISTERED_NOT_YET_REVALIDATED' for row in body['items'])


def test_refresh_route_reuses_native_operation_contract(case, monkeypatch):
    from value_investment_agent.application.research import transparent_task_v1 as native
    client, session, data, root = case
    assert routes.OPERATION_MODULES is native.OPERATION_MODULES
    assert routes.OPERATION_MODULES['VALUE_RESEARCH_REFRESH']=='B'
    body=dict(module_id='B', operation='VALUE_RESEARCH_REFRESH',symbol='000568',
        request_key='TEST_ONLY_refresh_api',timeout_seconds=1800,
        payload=dict(source_mode='FRESH',network_authorized=True,tracking_budget=30,
            enrichment_batches=1,comparison_batches=1,operating_budget=0))
    assert client.post(routes.BASE+'/tasks',json=body).status_code==401
    assert not data.calls
    unlock(client,session)
    response=client.post(routes.BASE+'/tasks',json=body)
    assert response.status_code==202
    created=next(kw for method,kw in data.calls if method=='create')
    assert created['operation']=='VALUE_RESEARCH_REFRESH' and created['payload']==body['payload']
    assert created['timeout_seconds']==1800


def test_refresh_preparation_never_carries_network_authorization(case, monkeypatch):
    client, _, data, root = case
    class Service:
        def prepare(self,**kw):
            return dict(action='no_order',symbol=kw['symbol'],operations=[dict(
                operation='VALUE_RESEARCH_REFRESH',enabled=True,payload=dict(source_mode='FRESH',network_authorized=True))])
        def capabilities(self):return {}
    monkeypatch.setattr(routes,'_task_service',lambda project:Service())
    response=client.get(routes.BASE+'/task-inputs?symbol=000568')
    row=next(r for r in response.json()['operations'] if r['operation']=='VALUE_RESEARCH_REFRESH')
    assert row['enabled'] and row['prepared_payload']['network_authorized'] is False
    assert row['network_authorization_required'] is True
    assert not data.calls
