"""Synthetic transport fixtures; no network or financial admission in CI."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest
import requests

from value_investment_agent.application.discovery import public_financial_input as service
from value_investment_agent.financial_quality import _accepted
from value_investment_agent.infrastructure.screening import public_financial_snapshot as adapter


def row(symbol='600519', **changes):
    return dict(SECURITY_CODE=symbol, SECUCODE=symbol + ('.SH' if symbol.startswith('6') else '.SZ'),
                SECURITY_TYPE_CODE='058001001', REPORTDATE='2025-12-31 00:00:00',
                NOTICE_DATE='2026-04-01 00:00:00', UPDATE_DATE='2026-04-01 00:00:00',
                TOTAL_OPERATE_INCOME=100, PARENT_NETPROFIT=10, WEIGHTAVG_ROE=12.5,
                MGJYXJJE=0, **changes)


class Response:
    status_code = 200

    def __init__(self, url, payload):
        self.url = url
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.payload


class Session:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        payload = next(self.pages)
        if isinstance(payload, Exception):
            raise payload
        return Response(url, json.dumps(payload).encode())


def page(rows, count=None, pages=1):
    return dict(success=True, result=dict(data=rows, count=len(rows) if count is None else count, pages=pages))


def collect(tmp_path, monkeypatch, rows=None, pages=None):
    monkeypatch.setattr(adapter.time, 'sleep', lambda _: None)
    session = Session(pages or [page(rows or [row()])])
    binding = adapter.collect_public_annual_summary(root=tmp_path,
        output_dir=tmp_path / 'runtime/collection', period='2025-12-31', allow_network=True, session=session)
    return binding, session


def load(tmp_path, binding, **kwargs):
    return adapter.load_public_annual_summary(root=tmp_path, binding=binding,
        evaluation_at=kwargs.get('evaluation_at', datetime.now(timezone.utc)))


def test_real_bytes_not_promoted_to_verified_or_historical_facts(tmp_path, monkeypatch):
    binding, session = collect(tmp_path, monkeypatch)
    points, info = load(tmp_path, binding)
    assert len(points) == 4 and info['provider_rows'] == 1
    assert info['accepted_official_fact_count'] == 0
    assert all(not _accepted(p) and p['published_at'] is None for p in points)
    assert {p['field_name'] for p in points} == {'total_revenue', 'net_income', 'roe_weighted', 'operating_cash_flow_per_share'}
    assert next(p for p in points if p['field_name'] == 'operating_cash_flow_per_share')['value'] == '0'
    assert all(p['available_at'] == p['fetched_at'] for p in points)
    assert all(p['metadata']['historical_pit_eligible'] is False for p in points)
    assert len(session.calls) == 1 and session.calls[0][1]['allow_redirects'] is False
    assert load(tmp_path, binding) == (points, info)
    with pytest.raises(ValueError, match='cutoff'):
        load(tmp_path, binding, evaluation_at=datetime(2026, 4, 2, tzinfo=timezone.utc))


@pytest.mark.parametrize('mutation', ['manifest', 'raw', 'future_clock', 'source_url'])
def test_replay_rechecks_hash_and_identity(tmp_path, monkeypatch, mutation):
    binding, _ = collect(tmp_path, monkeypatch)
    path = tmp_path / binding['path']
    manifest = json.loads(path.read_bytes())
    if mutation == 'raw':
        (tmp_path / manifest['pages'][0]['path']).write_text('{}')
    elif mutation == 'manifest':
        path.write_text('{}')
    else:
        if mutation == 'future_clock':
            manifest['pages'][0]['acquired_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        else:
            manifest['pages'][0]['source_url'] = 'https://example.test/fake'
        raw = json.dumps(manifest).encode()
        path.write_bytes(raw)
        binding['sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        load(tmp_path, binding)


@pytest.mark.parametrize('kind', ['duplicate', 'short', 'drift', 'identity', 'period', 'timeout', 'provider_error', 'page_budget'])
def test_partial_or_invalid_source_never_produces_complete_manifest(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(adapter, 'PAGE_SIZE', 2)
    second = page([row('000333')], count=3, pages=2)
    first = page([row(), row('600887')], count=3, pages=2)
    if kind == 'duplicate':
        second['result']['data'] = [row()]
    elif kind == 'short':
        first['result']['data'] = [row()]
    elif kind == 'drift':
        second['result']['count'] = 4
    elif kind == 'identity':
        first['result']['data'][0]['SECUCODE'] = '600519.SZ'
    elif kind == 'period':
        first['result']['data'][0]['REPORTDATE'] = '2026-06-30 00:00:00'
    elif kind == 'timeout':
        second = requests.Timeout('test only')
    elif kind == 'provider_error':
        first = dict(success=False)
    elif kind == 'page_budget':
        first['result'].update(count=999999, pages=9999)
    with pytest.raises((ValueError, requests.Timeout)):
        collect(tmp_path, monkeypatch, pages=[first, second, second, second])
    manifest = json.loads((tmp_path / 'runtime/collection/manifest.json').read_bytes())
    assert manifest['status'] == 'FAILED' and manifest['formal_admission'] is False
    binding = dict(path='runtime/collection/manifest.json', sha256=hashlib.sha256(
        (tmp_path / 'runtime/collection/manifest.json').read_bytes()).hexdigest())
    with pytest.raises(ValueError):
        load(tmp_path, binding)


def test_complete_two_page_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, 'PAGE_SIZE', 2)
    binding, session = collect(tmp_path, monkeypatch, pages=[
        page([row(), row('600887')], count=3, pages=2), page([row('000333')], count=3, pages=2)])
    points, info = load(tmp_path, binding)
    assert len(session.calls) == 2 and info['provider_rows'] == 3 and len(points) == 12


def test_transient_transport_recovers_with_finite_backoff(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(adapter.time, 'sleep', sleeps.append)
    session = Session([requests.Timeout('TEST_ONLY'), requests.ConnectionError('TEST_ONLY'), page([row()])])
    binding = adapter.collect_public_annual_summary(root=tmp_path,
        output_dir=tmp_path / 'runtime/recovered', period='2025-12-31',
        allow_network=True, session=session)
    points, info = load(tmp_path, binding)
    assert len(session.calls) == 3 and sleeps == [1, 2]
    assert info['provider_rows'] == 1 and all(not _accepted(p) for p in points)


@pytest.mark.parametrize('status,expected_calls', [(403, 1), (404, 1), (429, 3), (503, 3)])
def test_http_retry_is_bounded_and_never_retries_denied_access(tmp_path, monkeypatch, status, expected_calls):
    sleeps = []
    monkeypatch.setattr(adapter.time, 'sleep', sleeps.append)
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError('TEST_ONLY', response=response)
    session = Session([error, error, error])
    with pytest.raises(requests.HTTPError):
        adapter.collect_public_annual_summary(root=tmp_path,
            output_dir=tmp_path / 'runtime/failed', period='2025-12-31',
            allow_network=True, session=session)
    assert len(session.calls) == expected_calls
    assert sleeps == ([1, 2] if expected_calls == 3 else [])
    manifest = json.loads((tmp_path / 'runtime/failed/manifest.json').read_bytes())
    assert manifest['status'] == 'FAILED' and not manifest['formal_admission']


def test_invalid_content_is_not_retried(tmp_path, monkeypatch):
    session = Session([dict(success=False), page([row()])])
    with pytest.raises(ValueError, match='success'):
        adapter.collect_public_annual_summary(root=tmp_path,
            output_dir=tmp_path / 'runtime/invalid', period='2025-12-31',
            allow_network=True, session=session)
    assert len(session.calls) == 1


@pytest.mark.parametrize('invalid', [None, '--', 'NaN', 'Infinity', True])
def test_missing_or_invalid_values_never_become_zero(tmp_path, monkeypatch, invalid):
    item = row()
    item['TOTAL_OPERATE_INCOME'] = invalid
    binding, _ = collect(tmp_path, monkeypatch, rows=[item])
    points, _ = load(tmp_path, binding)
    assert 'total_revenue' not in {p['field_name'] for p in points}


def test_future_provider_notice_excludes_row_without_backdating(tmp_path, monkeypatch):
    item = row()
    item['NOTICE_DATE'] = '2099-01-01 00:00:00'
    binding, _ = collect(tmp_path, monkeypatch, rows=[item])
    points, info = load(tmp_path, binding)
    assert points == [] and info['excluded_date_rows'] == 1


def test_explicit_permission_runtime_location_and_immutable_directory(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='permission'):
        adapter.collect_public_annual_summary(root=tmp_path, output_dir=tmp_path / 'runtime/a', period='2025-12-31')
    with pytest.raises(ValueError, match='runtime'):
        adapter.collect_public_annual_summary(root=tmp_path, output_dir=tmp_path / 'elsewhere', period='2025-12-31', allow_network=True)
    collect(tmp_path, monkeypatch)
    with pytest.raises(FileExistsError):
        collect(tmp_path, monkeypatch)


def test_supplement_preserves_retained_company_and_verifies_every_original(tmp_path, monkeypatch):
    binding, _ = collect(tmp_path, monkeypatch, rows=[row(), row('000333')])
    monkeypatch.setattr(service, 'collect_public_annual_summary', lambda **_: binding)
    retained = dict(symbol='600519', data_point_id='retained-official', field_name='net_income', value='999',
                    period_label='2024-12-31', validation_status='verified')
    (tmp_path / 'runtime/server-export-payload.json').write_text(json.dumps(dict(
        generated_at='2026-04-01T00:00:00+00:00', points=[retained])))
    payload = service.build_financial_input(root=tmp_path, output_dir=tmp_path / 'runtime/new', collect_public=True)
    assert payload['points'][0] == retained
    assert {p['symbol'] for p in payload['points'][1:]} == {'000333'}
    service.verify_public_supplement(root=tmp_path, payload=payload, evaluation_at=datetime.now(timezone.utc))
    changed = deepcopy(payload)
    changed['points'][1]['validation_status'] = 'verified'
    with pytest.raises(ValueError, match='originals'):
        service.verify_public_supplement(root=tmp_path, payload=changed, evaluation_at=datetime.now(timezone.utc))


def test_provider_failure_retains_existing_data_and_exposes_gap(tmp_path, monkeypatch):
    def fail(**kwargs):
        raise requests.Timeout('private URL must not leak into summary')
    monkeypatch.setattr(service, 'collect_public_annual_summary', fail)
    payload = service.build_financial_input(root=tmp_path, output_dir=tmp_path / 'runtime/new', collect_public=True)
    assert payload['points'] == [] and payload['status'] == 'NOT_AVAILABLE'
    assert payload['public_financial_input'] == dict(status='ACQUISITION_FAILED', error_type='Timeout', action='no_order')


def test_missing_same_period_fields_are_collected_without_replacing_retained_fact(tmp_path, monkeypatch):
    binding, _ = collect(tmp_path, monkeypatch)
    monkeypatch.setattr(service, 'collect_public_annual_summary', lambda **_: binding)
    retained = dict(symbol='600519', data_point_id='retained-official', field_name='net_income', value='999',
                    period_label='2025-12-31', validation_status='verified')
    (tmp_path / 'runtime/server-export-payload.json').write_text(json.dumps(dict(
        generated_at='2026-04-01T00:00:00+00:00', points=[retained])))
    payload = service.build_financial_input(root=tmp_path, output_dir=tmp_path / 'runtime/new', collect_public=True)
    assert payload['points'][0] == retained
    supplemental = payload['points'][1:]
    assert {p['field_name'] for p in supplemental} == {'total_revenue', 'roe_weighted', 'operating_cash_flow_per_share'}
    assert all(not _accepted(p) for p in supplemental)
    assert {p['period_label'] for p in supplemental} == {'2025-12-31'}
    service.verify_public_supplement(root=tmp_path, payload=payload, evaluation_at=datetime.now(timezone.utc))
    changed = deepcopy(payload)
    changed['public_financial_input']['supplement_policy'] = 'OVERWRITE_ALL'
    with pytest.raises(ValueError, match='policy'):
        service.verify_public_supplement(root=tmp_path, payload=changed, evaluation_at=datetime.now(timezone.utc))


def test_legacy_symbol_exclusion_export_keeps_its_original_replay(tmp_path, monkeypatch):
    binding, _ = collect(tmp_path, monkeypatch, rows=[row(), row('000333')])
    monkeypatch.setattr(service, 'collect_public_annual_summary', lambda **_: binding)
    payload = service.build_financial_input(root=tmp_path, output_dir=tmp_path / 'runtime/new', collect_public=True)
    payload['public_financial_input'].pop('supplement_policy')
    service.verify_public_supplement(root=tmp_path, payload=payload, evaluation_at=datetime.now(timezone.utc))
