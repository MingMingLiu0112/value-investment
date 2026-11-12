from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil

import pytest

from value_investment_agent.application.research import quarter_financial_read_model_v1 as model
from value_investment_agent.application.research.quarter_financial_ocr_v1 import SUPPORTED_SCOPE

NOW = datetime(2026, 11, 11, 5, tzinfo=timezone.utc)
SOURCE = {'path': 'runtime/source/600519-1225649896.pdf', 'sha256': 'a' * 64,
          'source_url': 'https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF',
          'available_at': '2026-11-11T02:53:26.730420+00:00',
          'report_period': '2026-09-30', 'kind': 'q3'}


def _write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def _registry(root):
    _write(root, 'config/current-capital-observations-v1.json',
           {'schema_version': 'current-capital-observations-v1', 'action': 'no_order',
            'cases': {'600519': {'sources': [SOURCE]}}})
    _write(root, model.REGISTRY, {'schema_version': 'quarter-financial-ocr-registry-v1',
           'action': 'no_order', 'cases': {'600519': {
               'capital_source_sha256': SOURCE['sha256'],
               'receipt': {'path': 'runtime/ocr/receipt.json', 'sha256': 'b' * 64},
               'registration': {'path': 'runtime/source/event-scan.json', 'sha256': 'c' * 64}}}})


def test_unregistered_is_not_started_and_read_is_read_only(tmp_path):
    before = list(tmp_path.rglob('*'))
    body = model.read_quarter_financial_ocr(tmp_path, '600519', NOW)
    assert body['status'] == 'NOT_STARTED'
    assert body['ytd_9m_observation'] is None
    assert body['valuation_admitted'] is False
    assert body['supported_scope'] == SUPPORTED_SCOPE
    assert model.read_quarter_financial_ocr(tmp_path, '000568', NOW)['status'] == 'NOT_SUPPORTED'
    assert list(tmp_path.rglob('*')) == before


def test_registered_observation_has_observation_only_status(tmp_path, monkeypatch):
    _registry(tmp_path)
    calls = []

    def replay(**kwargs):
        calls.append(kwargs)
        return {'symbol': '600519', 'status': 'VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION',
                'supported_scope': SUPPORTED_SCOPE,
                'period_basis': 'YTD_9M', 'facts': {'revenue_ytd_cny': '130970743649.04'},
                'valuation_admitted': False}

    monkeypatch.setattr(model, 'replay_quarter_financial_ocr', replay)
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    result = model.read_quarter_financial_ocr(tmp_path, '600519', NOW)
    assert result['status'] == 'VERIFIED_OBSERVATION_ONLY'
    assert result['ytd_9m_observation']['period_basis'] == 'YTD_9M'
    assert result['supported_scope'] == SUPPORTED_SCOPE
    assert result['valuation_admitted'] is False and result['current_comparison_changed'] is False
    assert result['ytd_9m_observation']['supported_scope'] == SUPPORTED_SCOPE
    assert result['source_bindings']['original']['sha256'] == SOURCE['sha256']
    assert calls[0]['registered_available_at'].isoformat() == SOURCE['available_at']
    assert calls[0]['original_path'] == tmp_path / SOURCE['path']
    assert {str(p): sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()} == before


def test_missing_evidence_and_unsafe_path_fail_closed(tmp_path):
    _registry(tmp_path)
    result = model.read_quarter_financial_ocr(tmp_path, '600519', NOW)
    assert result['status'] == 'UNASSESSABLE' and result['ytd_9m_observation'] is None
    path = tmp_path / model.REGISTRY
    value = json.loads(path.read_text())
    value['cases']['600519']['receipt']['path'] = '../elsewhere/receipt.json'
    path.write_text(json.dumps(value))
    result = model.read_quarter_financial_ocr(tmp_path, '600519', NOW)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'INVALID_REGISTERED_PATH'


def test_local_registered_q3_read_model_cold_replay(tmp_path):
    project = tmp_path
    source_root = project / 'runtime/value-alignment-event-observation/600519-20261030-20261110-20261111T025324Z'
    ocr_root = project / 'runtime/value-q3-pdfium-ocr-600519-20261111'
    sealed = Path('D:/GPTProject/value-investment/.tmp/vf1/runtime')
    source = sealed / 'value-alignment-event-observation/600519-20261030-20261110-20261111T025324Z'
    ocr = sealed / 'value-q3-pdfium-ocr-600519-20261111'
    required = [source / '600519-1225649896.pdf', source / 'event-scan.json',
                *(ocr / name for name in ('receipt.json', 'page-1.png', 'page-7.png',
                                          'page-1.ocr.json', 'page-7.ocr.json'))]
    if not all(path.is_file() for path in required):
        pytest.skip('local sealed Q3 integration inputs unavailable')
    for name in ('current-capital-observations-v1.json', 'quarter-financial-ocr-v1.json'):
        dest = project / 'config' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).parents[1] / 'config' / name, dest)
    source_root.mkdir(parents=True)
    ocr_root.mkdir(parents=True)
    for path in required:
        shutil.copy2(path, source_root / path.name if path.parent == source else ocr_root / path.name)
    result = model.read_quarter_financial_ocr(project, '600519', NOW)
    assert result['status'] == 'VERIFIED_OBSERVATION_ONLY'
    assert result['ytd_9m_observation']['facts'] == {
        'revenue_ytd_cny': '130970743649.04',
        'attributable_profit_ytd_cny': '64467425981.95'}
    assert result['valuation_admitted'] is False and result['current_comparison_changed'] is False
