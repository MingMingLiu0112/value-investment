"""Partial is a source-replayed scope, never a substitute full-market universe."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import pytest
import requests

from test_official_universe import SATURDAY, v2_documents  # noqa: F401
from value_investment_agent.application.discovery import official_universe_collection as app
from value_investment_agent.infrastructure.screening import official_universe_v2 as lists


def request_identity(label):
    if label == 'SZSE_A':
        return lists.SZSE_URL + '?' + urlencode(dict(SHOWTYPE='xlsx', CATALOGID='1110', TABKEY='tab1')), None
    if label.startswith('SSE_'):
        return lists.SSE_URL + '?' + urlencode(dict(STOCK_TYPE=label[-1],
            sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L', COMPANY_STATUS='2,4,5,7,8',
            type='inParams', isPagination='true', **{'pageHelp.pageSize': '10000',
            'pageHelp.pageNo': '1', 'pageHelp.beginPage': '1', 'pageHelp.endPage': '1'})), None
    return lists.BSE_URL, dict(page=label[4:], typejb='T', **{'xxfcbj[]': '2'},
        xxzqdm='', sortfield='xxzqdm', sorttype='asc')


@pytest.fixture
def coverage_documents(v2_documents):
    docs = deepcopy(v2_documents)
    for doc in docs:
        url, data = request_identity(doc['label'])
        doc.update(request_url=url, request_data=data, url=url, http_status=200,
                   location=None, content_type='TEST_ONLY')
    return docs


def replay(docs, failures=()):
    return lists.replay_official_venue_coverage(docs, request_failures=list(failures),
        started_at=SATURDAY, available_at=SATURDAY + timedelta(seconds=2))


def damage_response(doc, status=307):
    doc.update(raw=b'<html>TEST_ONLY redirect</html>', http_status=status,
        location=lists.BSE_URL, content_type='text/html')
    doc['sha256'] = sha256(doc['raw']).hexdigest()


def assert_partial(payload, covered):
    assert payload['parser_version'] == lists.PARTIAL_VERSION
    assert payload['action'] == 'no_order'
    assert payload['complete'] is False
    assert payload['required_venues'] == ['SZSE', 'SSE', 'BSE']
    assert payload['covered_venues'] == covered
    assert payload['missing_venues'] == payload['failed_venues'] == [
        v for v in payload['required_venues'] if v not in covered]
    assert {r['exchange'] for r in payload['records']} == set(covered)
    assert payload['status'] == ('PARTIAL' if covered else 'UNAVAILABLE')
    for venue, result in payload['venue_coverage'].items():
        assert result['complete'] is (venue in covered)
        assert result['status'] == ('COMPLETE' if venue in covered else 'FAILED')
        assert (result['record_count'] is None) is (venue not in covered)
    assert payload['collection_timing']['quote_date_verified'] is False
    assert payload['collection_timing']['strict_contemporaneous_pit'] is False


def test_bse_redirect_preserves_sh_sz_and_failed_raw_provenance(coverage_documents):
    docs = coverage_documents[:4]
    damage_response(docs[-1])
    payload = replay(docs)
    assert_partial(payload, ['SZSE', 'SSE'])
    assert len(payload['records']) == 4003
    assert payload['effective_session'] == '2026-10-23'
    binding = payload['venue_coverage']['BSE']['source_bindings'][0]
    assert binding['http_status'] == 307
    assert binding['sha256'] == sha256(docs[-1]['raw']).hexdigest()
    assert binding['location'] == lists.BSE_URL
    assert 'raw' not in binding
    assert 'HTTP 307' in payload['venue_coverage']['BSE']['failures'][0]['reason']
    assert payload['venue_coverage']['SZSE']['provider_date_observed'] is False


@pytest.mark.parametrize('label,covered', [
    ('SZSE_A', ['SSE', 'BSE']), ('SSE_1', ['SZSE', 'BSE']),
    ('SSE_8', ['SZSE', 'BSE']), ('BSE_1', ['SZSE', 'SSE']),
])
def test_each_venue_failure_is_atomic_not_a_partial_board_or_page(coverage_documents, label, covered):
    damage_response(next(d for d in coverage_documents if d['label'] == label), 503)
    payload = replay(coverage_documents)
    assert_partial(payload, covered)
    if label == 'BSE_1':
        assert payload['venue_coverage']['BSE']['source_labels'] == ['BSE_0', 'BSE_1']


def test_all_success_remains_exact_full_v2_contract(coverage_documents):
    payload = replay(coverage_documents)
    assert payload == lists.replay_official_documents(coverage_documents,
        started_at=SATURDAY, available_at=SATURDAY + timedelta(seconds=2))
    assert payload['parser_version'] == lists.VERSION
    assert payload['complete'] is True
    assert 'covered_venues' not in payload


def test_all_failed_is_unavailable_not_a_complete_empty_market(coverage_documents):
    for doc in coverage_documents:
        damage_response(doc)
    assert_partial(replay(coverage_documents), [])


@pytest.mark.parametrize('fault', ['missing_page', 'wrong_page', 'changed_totals', 'count',
    'duplicate_code', 'future', 'stale', 'mixed', 'future_listing'])
def test_bse_coverage_keeps_original_guards_without_erasing_other_venues(coverage_documents, fault):
    doc = coverage_documents[-1]
    page = json.loads(doc['raw'])
    if fault == 'missing_page':
        coverage_documents.pop()
    else:
        if fault == 'wrong_page': page[0]['number'] = 0
        elif fault == 'changed_totals': page[0]['totalElements'] = 202
        elif fault == 'count': page[0]['numberOfElements'] = 99
        elif fault == 'duplicate_code': page[0]['content'][0]['xxzqdm'] = '920000'
        elif fault == 'future_listing': page[0]['content'][0]['fxssrq'] = '20261026'
        else: page[0]['content'][0]['xxjsrq'] = '20261026' if fault == 'future' else '20261022'
        doc['raw'] = json.dumps(page).encode()
        doc['sha256'] = sha256(doc['raw']).hexdigest()
    assert_partial(replay(coverage_documents), ['SZSE', 'SSE'])


def test_malformed_xlsx_is_a_failed_venue_not_a_global_abort(coverage_documents, monkeypatch):
    from value_investment_agent.official_universe import parse_szse
    monkeypatch.setattr(lists, 'parse_szse', parse_szse)
    assert_partial(replay(coverage_documents), ['SSE', 'BSE'])


@pytest.mark.parametrize('body', [b'null', b'[]', b'{}', b'<html>not a JSON list</html>'])
def test_malformed_sse_envelopes_do_not_erase_other_venues(coverage_documents, monkeypatch, body):
    from value_investment_agent.official_universe import parse_sse
    monkeypatch.setattr(lists, 'parse_sse', parse_sse)
    coverage_documents[1].update(raw=body, sha256=sha256(body).hexdigest())
    assert_partial(replay(coverage_documents), ['SZSE', 'BSE'])


def test_unchanged_minimum_population_guard(coverage_documents, monkeypatch):
    monkeypatch.setattr(lists, 'parse_szse', lambda raw: [])
    assert_partial(replay(coverage_documents), ['SSE', 'BSE'])


@pytest.mark.parametrize('fault', ['hash', 'duplicate', 'future_fetch', 'naive_fetch',
    'wrong_host', 'wrong_board', 'wrong_page_request', 'wrong_query', 'unknown_label',
    'response_board', 'response_path'])
def test_replay_rejects_false_source_identity_even_when_other_venues_work(coverage_documents, fault):
    if fault == 'hash': coverage_documents[0]['sha256'] = '0' * 64
    elif fault == 'duplicate': coverage_documents.append(deepcopy(coverage_documents[0]))
    elif fault == 'future_fetch': coverage_documents[0]['fetched_at'] = (SATURDAY + timedelta(seconds=3)).isoformat()
    elif fault == 'naive_fetch': coverage_documents[0]['fetched_at'] = '2026-10-24T01:50:01'
    elif fault == 'wrong_host': coverage_documents[0]['url'] = 'https://example.test/export'
    elif fault == 'wrong_board': coverage_documents[1]['request_url'] = coverage_documents[2]['request_url']
    elif fault == 'wrong_page_request': coverage_documents[-1]['request_data']['page'] = '0'
    elif fault == 'wrong_query': coverage_documents[0]['request_url'] += '&CATALOGID=other'
    elif fault == 'response_board': coverage_documents[1]['url'] = coverage_documents[2]['url']
    elif fault == 'response_path': coverage_documents[1]['url'] = 'https://query.sse.com.cn/not-the-list'
    else: coverage_documents[0]['label'] = 'UNKNOWN'
    with pytest.raises(ValueError):
        replay(coverage_documents)


def install_transport(monkeypatch, docs, failed=None, timeout=False):
    by_label = {d['label']: d for d in docs}
    calls = []

    class Response:
        def __init__(self, url, label):
            self.url = url
            self.status_code = 307 if label == failed else 200
            self.headers = {'Location': lists.BSE_URL, 'Content-Type': 'TEST_ONLY'}
            self.raw = b'<html>TEST_ONLY redirect</html>' if label == failed else by_label[label]['raw']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield self.raw

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, **kwargs):
            assert kwargs['allow_redirects'] is False
            assert kwargs['verify'] is True
            if url.startswith(lists.SZSE_URL): label = 'SZSE_A'
            elif url.startswith(lists.SSE_URL): label = 'SSE_' + parse_qs(url.split('?')[1])['STOCK_TYPE'][0]
            else: label = 'BSE_' + parse_qs(kwargs['data'].decode())['page'][0]
            calls.append(label)
            if label == failed and timeout:
                raise requests.Timeout('TEST_ONLY timeout')
            return Response(url, label)

    monkeypatch.setattr(lists.requests, 'Session', Session)
    return calls


@pytest.mark.parametrize('failed,covered,timeout', [
    ('BSE_0', ['SZSE', 'SSE'], False), ('BSE_1', ['SZSE', 'SSE'], False),
    ('SZSE_A', ['SSE', 'BSE'], False), ('SSE_1', ['SZSE', 'BSE'], True),
])
def test_real_collector_preserves_successes_no_redirect_retry_or_fake_timeout_raw(
        coverage_documents, tmp_path, monkeypatch, failed, covered, timeout):
    calls = install_transport(monkeypatch, coverage_documents, failed, timeout)
    payload = lists.collect_security_lists_with_coverage(tmp_path / 'raw', clock=lambda: SATURDAY)
    assert_partial(payload, covered)
    assert calls.count(failed) == 1
    assert ('BSE_1' in calls) is (failed != 'BSE_0')
    assert all(sha256(Path(d['local_path']).read_bytes()).hexdigest() == d['sha256'] for d in payload['sources'])
    if timeout:
        assert not any(d['label'] == failed for d in payload['sources'])
        assert payload['request_failures'][0]['label'] == failed
    else:
        assert next(d for d in payload['sources'] if d['label'] == failed)['http_status'] == 307
    app.verify_retained_official_input(payload, root=tmp_path)


def retained_partial(docs, tmp_path):
    docs = docs[:4]
    damage_response(docs[-1])
    for doc in docs:
        path = tmp_path / doc['label']
        path.write_bytes(doc['raw'])
        doc['local_path'] = str(path)
    return replay(docs)


@pytest.mark.parametrize('fault', [None, 'covered', 'missing', 'count', 'complete', 'record',
    'source_hash', 'raw_bytes', 'missing_raw', 'outside_root', 'version', 'removed_version',
    'relabel_v1', 'timing', 'status', 'failed_source_status', 'request_board'])
def test_retained_projection_requires_exact_raw_replay_not_resealed_metadata(
        coverage_documents, tmp_path, fault):
    payload = retained_partial(coverage_documents, tmp_path)
    if fault is None:
        app.verify_retained_official_input(payload, root=tmp_path)
        return
    if fault == 'covered': payload['covered_venues'].append('BSE')
    elif fault == 'missing': payload['missing_venues'] = []
    elif fault == 'count': payload['venue_coverage']['BSE']['record_count'] = 0
    elif fault == 'complete': payload['complete'] = True
    elif fault == 'record': payload['records'][0]['name'] = 'TAMPERED'
    elif fault == 'source_hash': payload['sources'][0]['sha256'] = '0' * 64
    elif fault == 'raw_bytes': Path(payload['sources'][0]['local_path']).write_bytes(b'TAMPERED')
    elif fault == 'missing_raw': Path(payload['sources'][0]['local_path']).unlink()
    elif fault == 'outside_root': payload['sources'][0]['local_path'] = str(tmp_path.parent / 'missing')
    elif fault == 'version': payload['parser_version'] = lists.VERSION
    elif fault == 'removed_version': del payload['parser_version']
    elif fault == 'relabel_v1': payload['parser_version'] = 'official-security-lists-v1'
    elif fault == 'timing': payload['collection_timing']['strict_contemporaneous_pit'] = True
    elif fault == 'status': payload['status'] = 'COMPLETE'
    elif fault == 'failed_source_status': payload['sources'][-1]['http_status'] = 200
    else: payload['sources'][1]['request_url'] = payload['sources'][2]['request_url']
    with pytest.raises(ValueError):
        app.verify_retained_official_input(payload, root=tmp_path)


def test_explicit_application_opt_in_archives_partial_and_original_receipt(
        coverage_documents, tmp_path, monkeypatch):
    install_transport(monkeypatch, coverage_documents, 'BSE_0')
    monkeypatch.setattr(app, 'verify_calendar_archives', lambda root: None)
    monkeypatch.setattr(app, 'collect_security_lists_with_coverage',
        lambda directory: lists.collect_security_lists_with_coverage(directory, clock=lambda: SATURDAY))
    directory = tmp_path / 'new'
    payload, ref = app.collect_official_m2_input(directory, tmp_path, allow_partial=True)
    assert_partial(payload, ['SZSE', 'SSE'])
    raw = (directory / 'official-universe.json').read_bytes()
    assert json.loads(raw) == payload
    assert 'incomplete' in ref.source_name
    assert ref.sha256 == sha256(raw).hexdigest()
    receipt = {'evidence_refs': [dict(id='official', path=ref.path, sha256=ref.sha256)]}
    assert app.read_receipt_bound_official_input(directory / 'official-universe.json',
        root=tmp_path, receipt=receipt) == raw
    app.verify_retained_official_input(payload, root=tmp_path)


@pytest.mark.parametrize('fault', [None, 'restamp', 'future', 'session', 'wrong_retained'])
def test_partial_session_is_only_a_label_not_quote_or_pit_admission(coverage_documents, fault):
    docs = coverage_documents[:4]
    damage_response(docs[-1])
    payload = replay(docs)
    now = SATURDAY + timedelta(seconds=3)
    retained = None
    if fault == 'restamp': now += timedelta(days=1)
    elif fault == 'future': now = SATURDAY
    elif fault == 'session': payload['effective_session'] = '2026-10-24'
    elif fault == 'wrong_retained': retained = '2026-10-24'
    if fault:
        with pytest.raises(ValueError): app.screening_quote_date(payload, now, retained_quote_date=retained)
    else:
        assert app.screening_quote_date(payload, now) == '2026-10-23'
        assert payload['complete'] is False


def test_partial_calendar_and_fresh_directory_guards(coverage_documents, tmp_path, monkeypatch):
    install_transport(monkeypatch, coverage_documents, 'BSE_0')
    with pytest.raises(ValueError):
        lists.collect_security_lists_with_coverage(tmp_path / 'absent',
            clock=lambda: SATURDAY.replace(tzinfo=None))
    assert not (tmp_path / 'absent').exists()
    (tmp_path / 'existing').mkdir()
    with pytest.raises(FileExistsError):
        lists.collect_security_lists_with_coverage(tmp_path / 'existing', clock=lambda: SATURDAY)


def test_complete_opt_in_collection_keeps_original_replay_contract(coverage_documents, tmp_path, monkeypatch):
    install_transport(monkeypatch, coverage_documents)
    payload = lists.collect_security_lists_with_coverage(tmp_path / 'raw', clock=lambda: SATURDAY)
    assert payload['parser_version'] == lists.VERSION
    assert payload['complete'] is True
    app.verify_retained_official_input(payload, root=tmp_path)


@pytest.mark.parametrize('fault', ['failure_future', 'failure_naive', 'failure_identity',
    'failure_duplicate', 'failure_with_raw', 'cross_day', 'backwards'])
def test_partial_failures_and_collection_clocks_remain_bound(coverage_documents, fault):
    docs = coverage_documents[1:]
    url, data = request_identity('SZSE_A')
    failure = dict(label='SZSE_A', request_url=url, request_data=data,
        observed_at=(SATURDAY + timedelta(seconds=1)).isoformat(),
        error_type='Timeout', reason='TEST_ONLY')
    failures = [failure]
    start, finish = SATURDAY, SATURDAY + timedelta(seconds=2)
    if fault == 'failure_future': failure['observed_at'] = (SATURDAY + timedelta(seconds=3)).isoformat()
    elif fault == 'failure_naive': failure['observed_at'] = '2026-10-24T01:50:01'
    elif fault == 'failure_identity': failure['request_url'] = lists.BSE_URL
    elif fault == 'failure_duplicate': failures.append(deepcopy(failure))
    elif fault == 'failure_with_raw': docs.append(coverage_documents[0])
    elif fault == 'cross_day': start = SATURDAY - timedelta(days=1)
    else: finish = start - timedelta(seconds=1)
    with pytest.raises(ValueError):
        lists.replay_official_venue_coverage(docs, request_failures=failures,
            started_at=start, available_at=finish)


def test_partial_cannot_skip_replay_by_downgrading_version_and_erasing_dates(coverage_documents, tmp_path):
    payload = retained_partial(coverage_documents, tmp_path)
    payload['parser_version'] = 'official-security-lists-v1'
    for key in ('collection_timing', 'available_at', 'effective_session'):
        del payload[key]
    with pytest.raises(ValueError, match='relabelled'):
        app.verify_retained_official_input(payload, root=tmp_path)


@pytest.mark.parametrize('remaining', ['all', 'complete_false', 'complete_missing', 'complete_integer',
    'partial_status', 'unavailable_status', 'partial_scope'])
def test_declared_legacy_rejects_partial_after_all_new_coverage_and_date_fields_removed(
        coverage_documents, tmp_path, remaining):
    payload = retained_partial(coverage_documents, tmp_path)
    payload['parser_version'] = 'official-security-lists-v1'
    for key in ('required_venues', 'covered_venues', 'missing_venues', 'failed_venues',
            'venue_coverage', 'request_failures', 'collection_timing', 'available_at', 'effective_session'):
        del payload[key]
    if remaining != 'all':
        payload.update(complete=True, scope='Historical full A-share list')
        payload.pop('status')
        if remaining == 'complete_false': payload['complete'] = False
        elif remaining == 'complete_missing': del payload['complete']
        elif remaining == 'complete_integer': payload['complete'] = 1
        elif remaining == 'partial_status': payload['status'] = 'PARTIAL'
        elif remaining == 'unavailable_status': payload['status'] = 'UNAVAILABLE'
        else: payload['scope'] = 'OBSERVED_VENUES_ONLY_NOT_ALL_A'
    # Source-contract rejection is independent of any original receipt hash.
    with pytest.raises(ValueError, match='Legacy official input must be complete'):
        app.official_input_version(payload)
    with pytest.raises(ValueError, match='Legacy official input must be complete'):
        app.verify_retained_official_input(payload, root=tmp_path)


def test_unversioned_legacy_cannot_relabel_partial_scope_even_with_complete_true(coverage_documents, tmp_path):
    payload = retained_partial(coverage_documents, tmp_path)
    legacy_keys = {'records', 'sources', 'fetched_at', 'exchange_counts', 'board_counts', 'scope', 'complete'}
    payload = {key: payload[key] for key in legacy_keys}
    payload['complete'] = True
    with pytest.raises(ValueError, match='Unsupported unversioned'):
        app.verify_retained_official_input(payload, root=tmp_path)


@pytest.mark.parametrize('declared', [False, True])
def test_complete_legacy_keeps_original_replay_and_retained_date_semantics(coverage_documents, tmp_path, declared):
    payload = replay(coverage_documents)
    for key in ('parser_version', 'collection_timing', 'available_at', 'effective_session'):
        del payload[key]
    if declared:
        payload['parser_version'] = 'official-security-lists-v1'
    assert app.official_input_version(payload) == 'official-security-lists-v1'
    app.verify_retained_official_input(payload, root=tmp_path)
    assert app.screening_quote_date(payload, SATURDAY, retained_quote_date='2026-09-23') == '2026-09-23'
