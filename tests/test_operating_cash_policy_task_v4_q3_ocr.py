from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research.agent_review import operating_cash_policy_task_v4_q3_ocr as mod

NOW = datetime(2026, 11, 11, 5, tzinfo=timezone.utc)


def _write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def _fixture(tmp_path, monkeypatch):
    cfg = dict(api_key_env='UNUSED_TEST_ONLY_KEY', model_id='TEST_ONLY_MODEL',
               authorization_reference='TEST_ONLY', daily_cost_limit='0',
               max_completion_tokens_cap=256)
    monkeypatch.setattr(mod.live, 'model_configuration', lambda root: cfg)
    manifest = dict(schema_version=mod.sources.VERSION, symbol=mod.sources.SUPPORTED_SYMBOL,
                    action='no_order', base_binding={'path': 'runtime/base.json', 'sha256': 'a' * 64},
                    q3_source_bindings={'receipt': {'path': 'runtime/ocr.json', 'sha256': 'b' * 64}},
                    implementation_sha256=mod.sources.implementation())
    raw = json.dumps(manifest, sort_keys=True).encode()
    digest = sha256(raw).hexdigest()
    pin = {'path': f'runtime/{mod.sources.VERSION}/{digest}.json', 'sha256': digest}
    path = tmp_path / pin['path']
    _write_new(path, raw)
    selection = {'schema_version': 'operating-q3-ocr-task-selection-v1', 'action': 'no_order',
                 'cases': {mod.sources.SUPPORTED_SYMBOL: {'base_binding': manifest['base_binding']}}}
    _write_new(tmp_path / mod.CONFIG, json.dumps(selection).encode())
    context = dict(symbol=mod.sources.SUPPORTED_SYMBOL, source_binding=pin,
                   snapshot_fingerprint='c' * 64, valuation_admitted=False,
                   evidence=[], financial_basis='2026-06-30', action='no_order')
    monkeypatch.setattr(mod.sources, 'build_operating_horizon_source_context',
                        lambda **kwargs: dict(context))
    monkeypatch.setattr(mod.OperatingCashPolicyTaskServiceV4, '_request',
                        lambda self, spec, context: SimpleNamespace(system='TEST_ONLY', user='TEST_ONLY',
                                                                    max_completion_tokens=256))
    return mod.OperatingCashPolicyTaskServiceV4(tmp_path, test_provider=object())


def test_test_only_create_read_retry_cancel_and_store_isolation(tmp_path, monkeypatch):
    service = _fixture(tmp_path, monkeypatch)
    args = dict(symbol=mod.sources.SUPPORTED_SYMBOL, request_key='Q3OCRTEST01',
                years=[2027], now=NOW)
    created = service.create(**args)
    assert created['status'] == 'QUEUED' and created['execution_mode'] == 'TEST_ONLY_LIVE_CONTRACT'
    assert created['workflow'] == mod.CONTRACT and created['new_llm_calls'] == 0
    assert service.read(created['task_id'])['status'] == 'QUEUED'
    assert service.create(**args)['task_id'] == created['task_id']
    with pytest.raises(PermissionError, match='V10_CASH_EQUIVALENT_SOURCE_ALREADY_RESEARCHED'):
        service.create(**dict(args, request_key='Q3OCRTEST02'))
    with pytest.raises(ValueError, match='V10_CASH_REQUEST_KEY_CONFLICT'):
        service.create(**dict(args, years=[2028]))
    retried = service.resume(created['task_id'], now=NOW)
    assert retried['status'] == 'QUEUED' and retried['provider_requests'] == 0
    cancelled = service.cancel(created['task_id'], now=NOW)
    assert cancelled['status'] == 'CANCELLED'
    assert service.read(created['task_id'])['status'] == 'CANCELLED'
    assert not (tmp_path / 'runtime/research-task-execution-v1/cash-policy-v1').exists()


def test_v10_stable_identity_ignores_clock_but_rejects_old_source(tmp_path, monkeypatch):
    service = _fixture(tmp_path, monkeypatch)
    pin = next((tmp_path / 'runtime' / mod.sources.VERSION).glob('*.json'))
    binding = {'path': pin.relative_to(tmp_path).as_posix(), 'sha256': sha256(pin.read_bytes()).hexdigest()}
    stable = service._stable_source_identity(binding)
    assert stable['schema_version'] == mod.sources.VERSION
    later = json.loads(pin.read_bytes())
    later['as_of'] = '2026-11-12T05:00:00+00:00'
    later_raw = json.dumps(later).encode()
    later_hash = sha256(later_raw).hexdigest()
    later_path = tmp_path / f'runtime/{mod.sources.VERSION}/{later_hash}.json'
    _write_new(later_path, later_raw)
    assert service._stable_source_identity({
        'path': later_path.relative_to(tmp_path).as_posix(), 'sha256': later_hash}) == stable
    with pytest.raises(ValueError, match='V10_CASH_SOURCE_IDENTITY_INVALID'):
        old = dict(stable, schema_version='operating-horizon-sources-v9')
        raw = json.dumps(old).encode()
        digest = sha256(raw).hexdigest()
        old_path = tmp_path / f'runtime/old/{digest}.json'
        _write_new(old_path, raw)
        service._stable_source_identity({'path': old_path.relative_to(tmp_path).as_posix(), 'sha256': digest})


def test_v10_implementation_fingerprint_includes_inherited_duplicate_guard(tmp_path, monkeypatch):
    original = mod.implementation()
    copied = tmp_path / 'cash_v3.py'
    copied.write_bytes(Path(mod.cash_v3.__file__).read_bytes())
    monkeypatch.setattr(mod.cash_v3, '__file__', str(copied))
    assert mod.implementation() == original
    copied.write_bytes(copied.read_bytes() + b'\n# TEST_ONLY changed inherited guard\n')
    assert mod.implementation() != original


def test_real_source_test_only_task_create_read_resume_cancel(tmp_path, monkeypatch):
    source_root = Path('D:/GPTProject/value-investment/.tmp/vf1')
    base_hash = '264b1fc273152769519db160dadc33f79a946e21784756b1c4e253d567ca0a07'
    manifest_name = f'runtime/operating-horizon-sources-v1/{base_hash}.json'
    if not (source_root / manifest_name).is_file():
        pytest.skip('sealed FY/H1 and Q3 source packet unavailable')
    names = {manifest_name, mod.CONFIG,
             'config/current-operating-horizon-sources-v1.json',
             'config/current-capital-observations-v1.json',
             'config/quarter-financial-ocr-v1.json'}
    manifest = json.loads((source_root / manifest_name).read_bytes())
    names.add(manifest['base_binding']['path'])
    for item in manifest['selection']['parent_cash_observation_receipts']:
        names.add(item['receipt_binding']['path'])
    for receipt_name in list(names):
        if not receipt_name.endswith('/receipt.json'):
            continue
        receipt = json.loads((source_root / receipt_name).read_bytes())
        names.add(receipt['source']['path'])
        names.update(ref['path'] for ref in receipt['index_bindings'])
    quarter_config = json.loads((source_root / 'config/quarter-financial-ocr-v1.json').read_bytes())
    capital = json.loads((source_root / 'config/current-capital-observations-v1.json').read_bytes())
    names.add(capital['cases'][mod.sources.SUPPORTED_SYMBOL]['sources'][0]['path'])
    case = quarter_config['cases'][mod.sources.SUPPORTED_SYMBOL]
    names.update((case['receipt']['path'], case['registration']['path']))
    quarter_receipt = json.loads((source_root / case['receipt']['path']).read_bytes())
    names.update((str(Path(case['receipt']['path']).parent / row[key]).replace('\\', '/')
                  for row in quarter_receipt['files'] for key in ('image', 'ocr')))
    local_config = Path(__file__).parents[1] / mod.CONFIG
    if any(not (source_root / name).is_file() for name in names if name != mod.CONFIG):
        pytest.skip('sealed source dependency unavailable')
    for name in names:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_config if name == mod.CONFIG else source_root / name, destination)
    cfg = dict(api_key_env='UNUSED_TEST_ONLY_KEY', model_id='TEST_ONLY_MODEL',
               authorization_reference='TEST_ONLY', daily_cost_limit='0',
               max_completion_tokens_cap=4096)
    monkeypatch.setattr(mod.live, 'model_configuration', lambda root: cfg)
    service = mod.OperatingCashPolicyTaskServiceV4(tmp_path, test_provider=object())
    created = service.create(symbol=mod.sources.SUPPORTED_SYMBOL,
                             request_key='REALQ3OCRTEST01', years=[2027], now=NOW)
    assert created['status'] == 'QUEUED' and created['provider_requests'] == 0
    assert service.read(created['task_id'])['status'] == 'QUEUED'
    assert service.resume(created['task_id'], now=NOW)['status'] == 'QUEUED'
    assert service.cancel(created['task_id'], now=NOW)['status'] == 'CANCELLED'
