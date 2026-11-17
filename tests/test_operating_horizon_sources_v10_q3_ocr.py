from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v10_q3_ocr as mod
from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService

NOW = datetime(2026, 11, 11, 5, tzinfo=timezone.utc)
BASE_HASH = '264b1fc273152769519db160dadc33f79a946e21784756b1c4e253d567ca0a07'
BASE_BINDING = {'path': f'runtime/operating-horizon-sources-v1/{BASE_HASH}.json',
                'sha256': BASE_HASH}
REAL_ROOT = Path('D:/GPTProject/value-investment/.tmp/vf1')


def _fixture(tmp_path, monkeypatch):
    base_as_of = '2026-11-11T03:26:23.992994+00:00'
    base = {'schema_version': mod.v1.VERSION, 'symbol': '600519',
            'financial_basis': '2026-06-30', 'source_binding': BASE_BINDING,
            'evidence': [{'id': 'FY-H1-parent-cash', 'field': 'parent_cfo'}],
            'supplemental_sources': [{'source_id': 'FY-H1'}], 'limitations': [],
            'action': 'no_order', 'formal_eligibility': False}
    real_bound = mod.v1._bound
    monkeypatch.setattr(mod.v1, '_bound', lambda root, binding: (
        {'schema_version': mod.v1.VERSION, 'symbol': '600519', 'as_of': base_as_of}
        if binding == BASE_BINDING else real_bound(root, binding)))
    monkeypatch.setattr(mod.v1, 'build_operating_horizon_source_context',
                        lambda **kwargs: dict(base))
    registry = tmp_path / mod.q3_read_model.REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('{"schema_version":"quarter-financial-ocr-registry-v1"}')
    folder = tmp_path / 'runtime/ocr'
    folder.mkdir(parents=True)
    entries = []
    for number in (1, 7):
        path = folder / f'page-{number}.ocr.json'
        path.write_text(json.dumps({'generated_at': '2026-11-11T04:44:35+00:00'}))
        entries.append({'ocr': path.name, 'ocr_sha256': sha256(path.read_bytes()).hexdigest()})
    receipt = folder / 'receipt.json'
    receipt.write_text(json.dumps({'files': entries}))
    bindings = {
        'original': {'path': 'runtime/source/600519-1225649896.pdf',
                     'sha256': 'a' * 64, 'source_url': 'https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF',
                     'available_at': '2026-11-11T02:53:26+00:00'},
        'receipt': {'path': 'runtime/ocr/receipt.json',
                    'sha256': sha256(receipt.read_bytes()).hexdigest()},
        'registration': {'path': 'runtime/source/event-scan.json', 'sha256': 'b' * 64}}
    observation = {'supported_scope': mod.SCOPE, 'period_basis': 'YTD_9M',
                   'formal_eligibility': False, 'valuation_admitted': False,
                   'facts': {'revenue_ytd_cny': '130970743649.04',
                             'attributable_profit_ytd_cny': '64467425981.95'}}
    monkeypatch.setattr(mod.q3_read_model, 'read_quarter_financial_ocr',
                        lambda *args: {'status': 'VERIFIED_OBSERVATION_ONLY',
                                       'supported_scope': mod.SCOPE,
                                       'source_bindings': bindings,
                                       'ytd_9m_observation': observation})
    return base, bindings, observation, receipt


def test_portable_two_field_context_preserves_fy_h1(tmp_path, monkeypatch):
    base, _, _, _ = _fixture(tmp_path, monkeypatch)
    result = mod.build_q3_ocr_source_context(
        root=tmp_path, symbol='600519', now=NOW, base_binding=BASE_BINDING)
    assert result['financial_basis'] == base['financial_basis']
    assert result['evidence'][0] == base['evidence'][0]
    assert [(row['field'], row['value']) for row in result['evidence'][1:]] == [
        ('revenue', '130970743649.04'), ('parent_profit', '64467425981.95')]
    assert all(row['period_basis'] == 'YTD_9M' for row in result['evidence'][1:])
    assert 'source_binding' not in result
    assert result['valuation_admitted'] is False and result['formal_eligibility'] is False
    assert not (tmp_path / 'runtime' / mod.VERSION).exists()


def test_application_symbol_is_derived_from_fixed_source_contract():
    source = Path(mod.__file__).read_text(encoding='utf-8')
    assert "symbol != '600519'" not in source
    assert mod.SUPPORTED_SYMBOL == mod.q3_verifier.SUPPORTED_SCOPE.split('_')[2]


def test_dispatch_recognizes_only_the_exact_new_v10_namespace():
    assert NoticeAwareTaskService._version({
        'path': 'runtime/' + mod.VERSION + '/' + 'a' * 64 + '.json',
        'sha256': 'a' * 64}) == 'v10-q3-ocr'
    with pytest.raises(ValueError, match='NOTICE_TASK_SOURCE_VERSION_UNSUPPORTED'):
        NoticeAwareTaskService._version({
            'path': 'runtime/operating-horizon-sources-v10-unknown/' + 'a' * 64 + '.json',
            'sha256': 'a' * 64})


def test_versioned_manifest_create_replay_and_tamper(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    args = dict(root=tmp_path, symbol='600519', now=NOW)
    first = mod.build_operating_horizon_source_context(**args, base_binding=BASE_BINDING)
    pin = first['source_binding']
    assert pin['path'].startswith('runtime/' + mod.VERSION + '/')
    assert mod.build_operating_horizon_source_context(**args, binding=pin) == first
    with pytest.raises(ValueError, match='D2_Q3_EXPLICIT_BASE_BINDING_REQUIRED'):
        mod.build_operating_horizon_source_context(**args)
    with pytest.raises(ValueError, match='D2_Q3_V10_BINDING_REQUIRED'):
        mod.build_operating_horizon_source_context(**args, binding=BASE_BINDING)
    path = tmp_path / pin['path']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='HORIZON_SOURCE_HASH_CHANGED'):
        mod.build_operating_horizon_source_context(**args, binding=pin)


def test_portable_rejects_unverified_duplicate_and_future(tmp_path, monkeypatch):
    _, _, observation, receipt = _fixture(tmp_path, monkeypatch)
    arguments = dict(root=tmp_path, symbol='600519', now=NOW, base_binding=BASE_BINDING)
    with pytest.raises(ValueError, match='D2_Q3_FIXED_SOURCE'):
        mod.build_q3_ocr_source_context(**dict(arguments, symbol='000568'))
    observation['facts']['cfo_cny'] = '1'
    with pytest.raises(ValueError, match='D2_Q3_EXACT_TWO_FIELDS_REQUIRED'):
        mod.build_q3_ocr_source_context(**arguments)
    observation['facts'].pop('cfo_cny')
    receipt.write_text(receipt.read_text() + ' ')
    with pytest.raises(ValueError, match='D2_Q3_RECEIPT_CHANGED'):
        mod.build_q3_ocr_source_context(**arguments)


def test_portable_rejects_unverified_observation_and_pre_q3_clock(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    arguments = dict(root=tmp_path, symbol='600519', base_binding=BASE_BINDING)
    with pytest.raises(ValueError, match='D2_Q3_OBSERVATION_AFTER_CUTOFF'):
        mod.build_q3_ocr_source_context(
            **arguments, now=datetime(2026, 11, 11, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(mod.q3_read_model, 'read_quarter_financial_ocr',
                        lambda *args: {'status': 'UNASSESSABLE', 'ytd_9m_observation': None})
    with pytest.raises(ValueError, match='D2_Q3_OCR_OBSERVATION_NOT_VERIFIED'):
        mod.build_q3_ocr_source_context(**arguments, now=NOW)


def test_real_fy_h1_plus_q3_cold_replay():
    if not (REAL_ROOT / BASE_BINDING['path']).is_file():
        pytest.skip('sealed v1 base manifest unavailable')
    assert sha256((REAL_ROOT / BASE_BINDING['path']).read_bytes()).hexdigest() == BASE_HASH
    result = mod.build_q3_ocr_source_context(
        root=REAL_ROOT, symbol='600519', now=NOW, base_binding=BASE_BINDING)
    assert result['financial_basis'] == '2026-06-30'
    assert len(result['evidence']) == 71
    assert [(row['field'], row['value']) for row in result['evidence'][-2:]] == [
        ('revenue', '130970743649.04'), ('parent_profit', '64467425981.95')]
    assert result['schema_version'] == mod.VERSION and 'source_binding' not in result
