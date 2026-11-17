"""Explicit statement evidence only; TEST_ONLY transport never admits facts."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from value_investment_agent.infrastructure.screening import sina_income_original as adapter


def payload(source='fzb'):
    return dict(result=dict(data=dict(report_list={
        '20251231': dict(rCurrency='CNY', rType='合并期末', publish_date='20260420',
            data=[dict(item_field='TEST_ONLY', item_source=source, item_title='测试项目',
                       item_unit='元', item_value='123.45'),
                  dict(item_field='TEST_ONLY_MISSING', item_source=source, item_value=None)])})))


@pytest.fixture
def http(monkeypatch):
    state = dict(raw=json.dumps(payload()).encode(), calls=[], statuses=[200],
                 headers={'Content-Type': 'application/json'}, errors=[], sleeps=[])

    class Response:
        def __init__(self, url, status):
            self.url = state.get('response_url', url)
            self.status_code = status
            self.headers = state['headers']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError('TEST_ONLY HTTP', response=self)

        def iter_content(self, size):
            if state.pop('stream_error_once', False):
                yield b'PARTIAL TEST_ONLY'
                raise requests.Timeout('TEST_ONLY interrupted transfer')
            for offset in range(0, len(state['raw']), size):
                yield state['raw'][offset:offset + size]

    class Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            state['calls'].append(dict(url=url, trust_env=self.trust_env, **kwargs))
            if state['errors']:
                error = state['errors'].pop(0)
                if error is not None:
                    raise error
            statuses = state['statuses']
            return Response(url, statuses.pop(0) if len(statuses) > 1 else statuses[0])

    monkeypatch.setattr(adapter.requests, 'Session', Session)
    monkeypatch.setattr(adapter.time, 'sleep', state['sleeps'].append)
    return state


def collect(root, statement='balance', **kwargs):
    return adapter.collect_sina_statement_original(root=root, symbol=kwargs.get('symbol', '000498'),
        output_dir=kwargs.get('output_dir', root / 'runtime/statement'), statement=statement,
        allow_network=kwargs.get('allow_network', True))


@pytest.mark.parametrize('statement,source', [('income', 'lrb'), ('balance', 'fzb'), ('cashflow', 'llb')])
def test_explicit_statement_original_and_unchanged_receipt_contract(tmp_path, http, statement, source):
    http['raw'] = json.dumps(payload(source), ensure_ascii=False, indent=3).encode()
    started = datetime.now(timezone.utc)
    descriptor = collect(tmp_path, statement)
    assert http['calls'] == [dict(url=adapter.ENDPOINT +
        f'?paperCode=sz000498&source={source}&type=0&page=1&num=16',
        trust_env=False, stream=True, allow_redirects=False, timeout=(10, 20))]
    assert descriptor['path'].endswith(f'/sina-{statement}.json')
    assert (tmp_path / descriptor['path']).read_bytes() == http['raw']
    assert descriptor['sha256'] == sha256(http['raw']).hexdigest()
    acquired = datetime.fromisoformat(descriptor['acquired_at'])
    assert started <= acquired <= datetime.now(timezone.utc)
    receipt_path = tmp_path / descriptor['receipt']['path']
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt == dict(url=descriptor['source_url'], path=descriptor['path'],
        sha256=descriptor['sha256'], acquired_at=descriptor['acquired_at'],
        bytes=len(http['raw']), action='no_order')
    assert descriptor['receipt']['sha256'] == sha256(receipt_path.read_bytes()).hexdigest()
    assert not any(key in descriptor for key in ('verified', 'known_at', 'available_at', 'approved'))
    with pytest.raises(FileExistsError):
        collect(tmp_path, statement)
    assert len(http['calls']) == 1


def test_legacy_income_wrapper_remains_lrb(tmp_path, http):
    http['raw'] = json.dumps(payload('lrb')).encode()
    descriptor = adapter.collect_sina_income_original(root=tmp_path, symbol='000498',
        output_dir=tmp_path / 'runtime/income', allow_network=True)
    assert descriptor['path'] == 'runtime/income/sina-income.json'
    assert parse_qs(urlparse(descriptor['source_url']).query)['source'] == ['lrb']


def test_income_retry_budget_remains_owned_by_existing_batch(tmp_path, http):
    http['errors'] = [requests.Timeout('TEST_ONLY'), None]
    with pytest.raises(requests.Timeout):
        adapter.collect_sina_income_original(root=tmp_path, symbol='000498',
            output_dir=tmp_path / 'runtime/income', allow_network=True)
    assert len(http['calls']) == 1 and not http['sleeps']


@pytest.mark.parametrize('statement', [None, 'fzb', 'lrb', 'llb', 'gjzb', 'BALANCE', '../income', True, {}])
def test_unknown_statement_rejected_before_request_even_offline(tmp_path, http, statement):
    with pytest.raises(ValueError, match='Unknown Sina statement'):
        collect(tmp_path, statement, allow_network=False)
    assert http['calls'] == [] and not (tmp_path / 'runtime').exists()


def test_offline_returns_none_without_artifacts(tmp_path, http):
    assert collect(tmp_path, allow_network=False) is None
    assert http['calls'] == [] and not (tmp_path / 'runtime').exists()


def test_explicit_enum_is_supported(tmp_path, http):
    assert collect(tmp_path, adapter.SinaStatement.BALANCE)['path'].endswith('sina-balance.json')


@pytest.mark.parametrize('kind', ['redirect', 'unexpected_url', 'html', 'declared_budget',
                                'stream_budget', 'invalid_json', 'shape', 'wrong_statement'])
def test_unsafe_responses_rejected_without_fallback(tmp_path, http, kind):
    if kind == 'redirect':
        http['statuses'] = [302]
    elif kind == 'unexpected_url':
        http['response_url'] = 'https://example.invalid/fzb'
    elif kind == 'html':
        http['headers']['Content-Type'] = 'text/html'
    elif kind == 'declared_budget':
        http['headers']['Content-Length'] = str(adapter.MAX_BYTES + 1)
    elif kind == 'stream_budget':
        http['raw'] = b' ' * (adapter.MAX_BYTES + 1)
    elif kind == 'invalid_json':
        http['raw'] = b'not json'
    elif kind == 'shape':
        http['raw'] = b'{"result":{"data":{"report_list":[]}}}'
    else:
        http['raw'] = json.dumps(payload('lrb')).encode()
    with pytest.raises(ValueError):
        collect(tmp_path)
    assert len(http['calls']) == 1
    if kind in {'invalid_json', 'shape', 'wrong_statement'}:
        assert (tmp_path / 'runtime/statement/sina-balance.json').read_bytes() == http['raw']
        assert (tmp_path / 'runtime/statement/acquisition.json').is_file()


@pytest.mark.parametrize('status,count', [(403, 1), (429, 1), (503, 2)])
def test_access_denial_and_retry_limits(tmp_path, http, status, count):
    http['statuses'] = [status]
    with pytest.raises(requests.HTTPError):
        collect(tmp_path)
    assert len(http['calls']) == count


def test_server_backoff_is_not_bypassed(tmp_path, http):
    http['statuses'] = [503]
    http['headers']['Retry-After'] = '120'
    with pytest.raises(requests.HTTPError):
        collect(tmp_path)
    assert len(http['calls']) == 1 and not http['sleeps']


@pytest.mark.parametrize('failure', ['timeout', 'connection', 'http_503', 'partial_stream'])
def test_transient_failure_retries_same_statement_and_discards_partial_buffer(tmp_path, http, failure):
    if failure == 'timeout':
        http['errors'] = [requests.Timeout('TEST_ONLY'), None]
    elif failure == 'connection':
        http['errors'] = [requests.ConnectionError('TEST_ONLY'), None]
    elif failure == 'http_503':
        http['statuses'] = [503, 200]
    else:
        http['stream_error_once'] = True
    descriptor = collect(tmp_path)
    assert len(http['calls']) == 2 and http['calls'][0] == http['calls'][1]
    assert http['sleeps'] == [1]
    assert (tmp_path / descriptor['path']).read_bytes() == http['raw']


def test_missing_unit_and_currency_are_not_inferred(tmp_path, http):
    packet = payload()
    report = packet['result']['data']['report_list']['20251231']
    del report['rCurrency']
    del report['data'][0]['item_unit']
    http['raw'] = json.dumps(packet).encode()
    descriptor = collect(tmp_path)
    assert json.loads((tmp_path / descriptor['path']).read_bytes()) == packet
    assert 'currency' not in descriptor and 'unit' not in descriptor


@pytest.mark.parametrize('source', ['fzb', 'llb'])
def test_optin_actual_000498_statement_archive(source):
    run = os.environ.get('SINA_STATEMENT_ACTUAL_RUN')
    if not run:
        pytest.skip('Explicit public retained run required; pytest never downloads')
    root = Path(__file__).resolve().parents[1]
    directory = (root / run).resolve()
    assert directory.is_relative_to(root / 'runtime')
    summary = json.loads((directory / 'verification.json').read_bytes())
    item = next(row for row in summary['items'] if row['source'] == source)
    descriptor = item['descriptor']
    raw_path = (root / descriptor['path']).resolve()
    receipt_path = (root / descriptor['receipt']['path']).resolve()
    assert raw_path.is_relative_to(root / 'runtime') and receipt_path.is_relative_to(root / 'runtime')
    raw, receipt_raw = raw_path.read_bytes(), receipt_path.read_bytes()
    assert sha256(raw).hexdigest() == descriptor['sha256']
    assert sha256(receipt_raw).hexdigest() == descriptor['receipt']['sha256']
    receipt = json.loads(receipt_raw)
    assert receipt['acquired_at'] == descriptor['acquired_at']
    assert receipt['action'] == 'no_order' and receipt['bytes'] == len(raw)
    query = parse_qs(urlparse(descriptor['source_url']).query)
    assert query['paperCode'] == ['sz000498'] and query['source'] == [source]
    reports = json.loads(raw)['result']['data']['report_list']
    assert '20251231' in reports and '20241231' in reports
    assert reports['20251231']['rCurrency'] == 'CNY'
    assert {row['item_source'] for row in reports['20251231']['data']} == {source}
    assert not summary['formal_eligibility'] and summary['historical_available_at'] is None
