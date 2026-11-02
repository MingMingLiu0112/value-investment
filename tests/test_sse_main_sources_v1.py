"""Direct source contract tests; no real network or shared pointer writes."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from value_investment_agent.infrastructure.screening import sse_main_sources_v1 as m


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


@pytest.fixture
def sources(monkeypatch, tmp_path):
    stamp = datetime.now(timezone.utc) - timedelta(seconds=1)
    rows = [dict(A_STOCK_CODE=str(600000 + n), SEC_NAME_CN='公司' + str(n),
                 LIST_DATE='2000-01-01') for n in range(1000)]
    raw = encode(dict(result=rows, pageHelp=dict(total=1000)))
    requests = []

    class Response:
        status_code = 200
        url = m.REQUEST['url']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield raw

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    monkeypatch.setattr(m.requests, 'Session', Session)
    payload = dict(fetched_at=stamp.isoformat(), rows=[{'code': '600001'}])
    for name in ('fetch_tencent_board_rank', 'fetch_sina_industry_quotes', 'fetch_eastmoney_dividends'):
        monkeypatch.setattr(m, name, lambda: (encode(payload), copy.deepcopy(payload)))
    financial = dict(points=[dict(symbol='600001', available_at=stamp.isoformat())])
    verified = []
    callbacks = dict(financial_builder=lambda **kw: copy.deepcopy(financial),
                     financial_verifier=lambda **kw: verified.append(kw))
    return tmp_path, tmp_path / 'runtime/sse-main-screening/new', requests, verified, raw, callbacks


def collect(sources):
    root, output, *_ = sources
    return m.collect_inputs(root, output, True, **sources[5])


def replay(sources, manifest):
    return m.verify_inputs(sources[0], manifest, datetime.now(timezone.utc),
                           financial_verifier=sources[5]['financial_verifier'])


def rewrite(root, binding, payload):
    raw = encode(payload)
    (root / binding['path']).write_bytes(raw)
    binding['sha256'] = hashlib.sha256(raw).hexdigest()


def test_intraday_contract_collect_replay_and_network_identity(sources):
    manifest = collect(sources)
    result = replay(sources, manifest)
    assert set(result) == set(m.ROLES)
    assert manifest['status'] == 'COMPLETE_INPUTS'
    assert result['official']['complete'] is False
    assert result['official']['quote_date_verified'] is False
    assert result['official']['scope'] == 'SSE_MAIN_A_ONLY'
    assert 'effective_session' not in result['official']
    assert len(result['official']['records']) == 1000
    url, args = sources[2][0]
    assert url == m.REQUEST['url'] and 'STOCK_TYPE=1' in url
    assert args['verify'] is True and args['allow_redirects'] is False
    assert args['timeout'] == (10, 20)
    assert args['headers']['Referer'] == m.REFERER
    assert len(sources[3]) == 2
    before = {p: p.read_bytes() for p in sources[1].iterdir() if p.is_file()}
    replay(sources, manifest)
    assert before == {p: p.read_bytes() for p in before}


def test_explicit_auth_and_new_directory_only(sources):
    root, output, *_ = sources
    with pytest.raises(ValueError, match='NETWORK'):
        m.collect_inputs(root, output, False, **sources[5])
    assert not output.exists()
    with pytest.raises(ValueError, match='DIRECTORY'):
        m.collect_inputs(root, root / 'outside', True, **sources[5])
    collect(sources)
    with pytest.raises(FileExistsError):
        collect(sources)


@pytest.mark.parametrize('role', m.ROLES)
def test_every_binding_hash_checked(sources, role):
    manifest = collect(sources)
    path = sources[0] / manifest['inputs'][role]['path']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='hash'):
        replay(sources, manifest)


@pytest.mark.parametrize('mutation', ['request', 'board', 'total', 'duplicate', 'future_listing', 'small', 'projection'])
def test_official_cold_replay_rejects_resigned_mutations(sources, mutation):
    manifest = collect(sources)
    binding = manifest['inputs']['official']
    root = sources[0]
    raw = json.loads((root / binding['raw']['path']).read_bytes())
    if mutation == 'request':
        binding['request_identity']['stock_type'] = '8'
    elif mutation in ('board', 'projection'):
        value = json.loads((root / binding['path']).read_bytes())
        if mutation == 'board': value['records'][0]['board'] = '科创板'
        else: value['complete'] = True
        rewrite(root, binding, value)
    else:
        if mutation == 'total': raw['pageHelp']['total'] += 1
        if mutation == 'duplicate': raw['result'][1] = raw['result'][0]
        if mutation == 'future_listing': raw['result'][0]['LIST_DATE'] = '2099-01-01'
        if mutation == 'small':
            raw['result'] = raw['result'][:2]
            raw['pageHelp']['total'] = 2
        rewrite(root, binding['raw'], raw)
    with pytest.raises(ValueError): replay(sources, manifest)


@pytest.mark.parametrize('mutation', ['naive', 'future', 'path', 'missing', 'payload_time'])
def test_bad_time_scope_and_missing_fail_closed(sources, mutation):
    manifest = collect(sources)
    binding = manifest['inputs']['tencent']
    if mutation == 'naive': manifest['started_at'] = '2026-01-01T00:00:00'
    if mutation == 'future': binding['fetched_at'] = '2099-01-01T00:00:00+00:00'
    if mutation == 'path': binding['path'] = '../outside.json'
    if mutation == 'missing': del manifest['inputs']['dividend']
    if mutation == 'payload_time':
        value = json.loads((sources[0] / binding['path']).read_bytes())
        value['fetched_at'] = '2099-01-01T00:00:00+00:00'
        rewrite(sources[0], binding, value)
    with pytest.raises(ValueError): replay(sources, manifest)


def test_partial_retains_raw_error_and_other_sources(sources, monkeypatch):
    def fail(): raise ValueError('provider unavailable')
    monkeypatch.setattr(m, 'fetch_sina_industry_quotes', fail)
    manifest = collect(sources)
    assert manifest['status'] == 'PARTIAL'
    assert any(e['source'] == 'sina' for e in manifest['errors'])
    assert (sources[1] / 'official-attempt-1.raw').exists()
    assert (sources[1] / 'inputs-manifest.json').exists()
    with pytest.raises(ValueError, match='INCOMPLETE'): replay(sources, manifest)


def test_mismatched_provider_bytes_retained_not_adopted(sources, monkeypatch):
    monkeypatch.setattr(m, 'fetch_tencent_board_rank', lambda: (b'{}', {'rows': [1]}))
    manifest = collect(sources)
    assert 'tencent' not in manifest['inputs']
    assert (sources[1] / 'tencent.json').read_bytes() == b'{}'


def test_financial_reverification_not_bypassed(sources, monkeypatch):
    manifest = collect(sources)
    def fail(**kw): raise ValueError('financial originals mismatch')
    sources[5]['financial_verifier'] = fail
    with pytest.raises(ValueError, match='financial originals'): replay(sources, manifest)


def test_no_sources_preserves_failed_manifest(sources, monkeypatch):
    def fail(*args, **kw): raise ValueError('unavailable')
    for name in ('_collect_official', 'fetch_tencent_board_rank', 'fetch_sina_industry_quotes',
                 'fetch_eastmoney_dividends'):
        monkeypatch.setattr(m, name, fail)
    sources[5]['financial_builder'] = fail
    with pytest.raises(ValueError, match='NO_USABLE'): collect(sources)
    manifest = json.loads((sources[1] / 'inputs-manifest.json').read_bytes())
    assert len(manifest['errors']) == 5 and manifest['inputs'] == {}


def test_official_stream_failure_bounded_and_received_bytes_retained(sources, monkeypatch):
    calls = []
    class Response:
        status_code = 200
        url = m.REQUEST['url']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size):
            yield b'partial official bytes'
            raise m.requests.exceptions.ConnectionError('stream interrupted')
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kw):
            calls.append(kw)
            return Response()
    monkeypatch.setattr(m.requests, 'Session', Session)
    monkeypatch.setattr(m.time, 'sleep', lambda value: None)
    manifest = collect(sources)
    assert len(calls) == 2 and 'official' not in manifest['inputs']
    for n in (1, 2):
        assert (sources[1] / f'official-attempt-{n}.raw').read_bytes() == b'partial official bytes'
    assert manifest['status'] == 'PARTIAL'


def test_official_redirect_body_archived_never_followed(sources, monkeypatch):
    class Response:
        status_code = 302
        url = m.REQUEST['url']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'redirect response'
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs):
            assert kwargs['allow_redirects'] is False
            return Response()
    monkeypatch.setattr(m.requests, 'Session', Session)
    monkeypatch.setattr(m.time, 'sleep', lambda value: None)
    manifest = collect(sources)
    assert 'official' not in manifest['inputs']
    assert (sources[1] / 'official-attempt-1.raw').read_bytes() == b'redirect response'


def test_financial_callbacks_required_and_no_application_import(sources):
    import ast
    from pathlib import Path
    tree = ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert 'application' not in (node.module or '').split('.')
        elif isinstance(node, ast.Import):
            assert all('application' not in alias.name.split('.') for alias in node.names)
    with pytest.raises(TypeError):
        m.collect_inputs(sources[0], sources[1], True)
    with pytest.raises(ValueError, match='CALLBACKS'):
        m.collect_inputs(sources[0], sources[1], True,
                         financial_builder=None, financial_verifier=lambda **kw: None)
    assert not sources[1].exists()
    with pytest.raises(TypeError):
        m.verify_inputs(sources[0], {}, datetime.now(timezone.utc))


def test_dividend_nan_normalizes_both_sides_and_preserves_bytes(sources, monkeypatch):
    value = dict(fetched_at=datetime.now(timezone.utc).isoformat(), rows=[[float('nan'), 1, None]])
    raw = encode(value)
    monkeypatch.setattr(m, 'fetch_eastmoney_dividends', lambda: (raw, value))
    manifest = collect(sources)
    assert manifest['inputs']['dividend']['decoder_version'] == m.DIVIDEND_DECODER
    assert replay(sources, manifest)['dividend']['rows'] == [[None, 1, None]]
    assert (sources[1] / 'dividend.json').read_bytes() == raw


@pytest.mark.parametrize('token', ['Infinity', '-Infinity', '1e999'])
def test_dividend_infinity_rejected(token):
    with pytest.raises(ValueError):
        m._decode('{"rows": [[' + token + ']]}', dividend=True)


def test_nan_other_roles_and_missing_decoder_rejected(sources):
    with pytest.raises(ValueError): m._decode('{"rows": [[NaN]]}')
    manifest = collect(sources)
    binding = manifest['inputs']['dividend']
    binding.pop('decoder_version')
    raw = b'{"rows":[[NaN]],"fetched_at":"2026-01-01T00:00:00+00:00"}'
    (sources[0] / binding['path']).write_bytes(raw)
    binding['sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='nonfinite'): replay(sources, manifest)


def test_dividend_normalization_does_not_hide_other_mismatch(sources, monkeypatch):
    value = dict(fetched_at=datetime.now(timezone.utc).isoformat(), rows=[[float('nan'), 1]])
    raw = encode(value)
    monkeypatch.setattr(m, 'fetch_eastmoney_dividends', lambda: (raw, dict(value, rows=[[float('nan'), 2]])))
    manifest = collect(sources)
    assert 'dividend' not in manifest['inputs']
    assert any(e['message'] == 'PROVIDER_RAW_PAYLOAD_MISMATCH_OR_EMPTY' for e in manifest['errors'])


def test_missing_cash_stays_missing_not_zero():
    from value_investment_agent.m2_market_data import parse_eastmoney_dividends
    from value_investment_agent.m2_discovery_engine import build_dividend_evidence
    row = ['600001', '公司', None, None, None, float('nan'), 3, None, None,
           None, None, None, None, '2026-01-01', None, None, None, None]
    decoded = m._decode(encode(dict(rows=[row], fiscal_year='2025')), dividend=True)
    parsed = parse_eastmoney_dividends(decoded)
    assert parsed[0]['cash_dps'] is None
    assert build_dividend_evidence(parsed, fetched_at=datetime.now(timezone.utc),
        raw_sha256='a' * 64, known_at=datetime.now(timezone.utc).date()) == {}


def test_recovery_new_manifest_keeps_original_error_times_and_hashes(sources):
    manifest = collect(sources)
    stamp = manifest['inputs']['official']['fetched_at']
    raw = encode(dict(fetched_at=stamp, rows=[[float('nan')]]))
    path = sources[1] / 'dividend.json'
    path.write_bytes(raw)
    manifest['inputs'].pop('dividend')
    manifest['status'] = 'PARTIAL'
    manifest['errors'] = [dict(source='dividend', message='nonfinite JSON: NaN')]
    old = sources[1] / 'inputs-manifest.json'
    old.write_bytes(encode(manifest))
    old_bytes = old.read_bytes()
    def ref(p): return dict(path=p.relative_to(sources[0]).as_posix(), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    out = sources[1].parent / 'recovered'
    result = m.recover_dividend_input(sources[0], ref(old), ref(path), out,
        datetime.now(timezone.utc), financial_verifier=sources[5]['financial_verifier'])
    assert result['errors'] == manifest['errors']
    assert result['started_at'] == manifest['started_at']
    assert result['finished_at'] == manifest['finished_at']
    assert result['inputs']['dividend']['fetched_at'] == stamp
    assert replay(sources, result)['dividend']['rows'] == [[None]]
    assert old.read_bytes() == old_bytes and path.read_bytes() == raw
    with pytest.raises(FileExistsError):
        m.recover_dividend_input(sources[0], ref(old), ref(path), out,
            datetime.now(timezone.utc), financial_verifier=sources[5]['financial_verifier'])


@pytest.mark.parametrize('symbol', ['688981', '689009', '900901'])
def test_official_main_request_cannot_relabel_non_main_a(sources, symbol):
    manifest = collect(sources)
    binding = manifest['inputs']['official']
    raw = json.loads((sources[0] / binding['raw']['path']).read_bytes())
    assert len(raw['result']) == raw['pageHelp']['total'] == 1000
    raw['result'][0]['A_STOCK_CODE'] = symbol
    rewrite(sources[0], binding['raw'], raw)
    # Even a consistently re-signed projection with a main-board label must fail.
    payload = json.loads((sources[0] / binding['path']).read_bytes())
    payload['records'][0]['symbol'] = symbol
    payload['records'][0]['board'] = '主板'
    rewrite(sources[0], binding, payload)
    with pytest.raises(ValueError, match='SECURITY_CODE_OUTSIDE_ALLOWED_RANGE'):
        replay(sources, manifest)


@pytest.mark.parametrize('symbol', ['600999', '601999', '603999', '605999'])
def test_main_a_prefix_guard_accepts_only_with_official_response(sources, symbol):
    raw = json.loads(sources[4])
    raw['result'][-1]['A_STOCK_CODE'] = symbol
    payload = m._official(encode(raw), datetime.now(timezone.utc).isoformat())
    assert any(row['symbol'] == symbol for row in payload['records'])
    assert payload['complete'] is False and payload['quote_date_verified'] is False
