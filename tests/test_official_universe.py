from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
import pytest

from value_investment_agent.official_universe import parse_szse, parse_sse, parse_bse_page, reconcile_security_lists


def test_szse_reads_past_wrong_a1_dimension():
    wb = Workbook()
    wb.active.append(['板块','A股代码','A股简称','A股上市日期'])
    wb.active.append(['创业板','302132','中航成飞','2010-08-27'])
    raw = BytesIO(); wb.save(raw)
    broken = BytesIO()
    with ZipFile(raw) as original, ZipFile(broken,'w',ZIP_DEFLATED) as edited:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = data.replace(b'ref="A1:D2"',b'ref="A1"')
            edited.writestr(item,data)
    rows = parse_szse(broken.getvalue())
    assert len(rows) == 1
    assert rows[0]['symbol'] == '302132'
    assert rows[0]['board'] == '创业板'


def test_sse_requires_declared_full_count_and_marks_cdr():
    data = {'result':[{'A_STOCK_CODE':'689009','SEC_NAME_CN':'九号公司','LIST_DATE':'20201029'}],
            'pageHelp':{'total':1}}
    assert parse_sse(json.dumps(data).encode(),'科创板')[0]['security_type'] == '境内存托凭证'
    data['pageHelp']['total'] = 2
    with pytest.raises(ValueError,match='incomplete'):
        parse_sse(json.dumps(data).encode(),'科创板')


def test_bse_callback_is_json_not_executed_code():
    raw = b'null([{"content":[],"numberOfElements":0}])'
    assert parse_bse_page(raw)['content'] == []
    with pytest.raises((ValueError,KeyError)):
        parse_bse_page(b'evil([{"content":[],"numberOfElements":0}])')
    with pytest.raises(ValueError,match='count'):
        parse_bse_page(b'null([{"content":[],"numberOfElements":1}])')


def sample():
    rows = [{'symbol':'600001','name':'样例','board':'主板'}]
    official = {'complete':True,'records':rows,'fetched_at':'2026-09-07T01:00:00+00:00','scope':'test','sources':[]}
    market = {'fetched_at':'2026-09-07T08:00:00+00:00','coverage':{'decisions':[dict(r) for r in rows]}}
    return official,market


def test_reconciliation_requires_same_date_codes_and_boards():
    official,market = sample()
    assert reconcile_security_lists(official,market)['reconciled']
    market['coverage']['decisions'][0]['board'] = '创业板'
    assert not reconcile_security_lists(official,market)['reconciled']
    market['fetched_at'] = '2026-09-08T01:00:00+00:00'
    assert reconcile_security_lists(official,market)['status'] == 'different_dates'


def test_reconciliation_exposes_missing_extra_and_duplicate_codes():
    official,market = sample()
    market['coverage']['decisions'][0]['symbol'] = '600002'
    result = reconcile_security_lists(official,market)
    assert result['missing_in_market'][0]['symbol'] == '600001'
    assert result['not_in_official'][0]['symbol'] == '600002'
    assert result['coverage_ratio'] == 0
    official['records'] *= 2
    with pytest.raises(ValueError,match='Duplicate'):
        reconcile_security_lists(official,market)


from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from copy import deepcopy
from value_investment_agent.domain.discovery.official_list_calendar import (
    completed_list_session, validate_list_timing,
)
from value_investment_agent.infrastructure.screening import official_universe_v2 as session_lists
from value_investment_agent.application.discovery.official_universe_collection import (
    screening_quote_date, verify_calendar_archives,
)


SATURDAY = datetime.fromisoformat('2026-10-24T01:50:00+08:00')


@pytest.mark.parametrize('stamp,expected', [
    ('2026-10-24T01:50:00+08:00', '2026-10-23'),
    ('2026-10-25T23:00:00+08:00', '2026-10-23'),
    ('2026-10-23T15:05:00+08:00', '2026-10-23'),
    ('2026-10-07T10:00:00+08:00', '2026-09-30'),
    ('2026-02-16T10:00:00+08:00', '2026-02-13'),
    ('2026-05-04T10:00:00+08:00', '2026-04-30'),
    ('2026-09-20T10:00:00+08:00', '2026-09-18'),
])
def test_official_list_calendar_uses_each_venues_2026_notice(stamp, expected):
    assert completed_list_session(datetime.fromisoformat(stamp)).isoformat() == expected


@pytest.mark.parametrize('stamp', [
    '2026-10-23T14:59:00+08:00', '2026-10-23T15:04:59+08:00',
    '2026-10-26T00:00:00+08:00', '2027-01-02T20:00:00+08:00',
    '2026-01-01T20:00:00+08:00', '2026-10-24T01:50:00',
])
def test_official_list_calendar_rejects_unfinished_or_uncovered(stamp):
    with pytest.raises(ValueError):
        completed_list_session(datetime.fromisoformat(stamp))


@pytest.fixture
def v2_documents(monkeypatch):
    # Parser implementations remain covered above; fake large SZSE/SSE rows here
    # keep this pagination/date fixture small without relaxing production coverage.
    def rows(start, n, exchange, board):
        return [dict(symbol=str(start+i), name='TEST_ONLY', exchange=exchange, board=board,
            listed_on='2020-01-01', security_type='A股') for i in range(n)]
    monkeypatch.setattr(session_lists, 'parse_szse', lambda raw: rows(100000, 2001, 'SZSE', '主板'))
    monkeypatch.setattr(session_lists, 'parse_sse', lambda raw, board:
        rows(600000, 2001, 'SSE', board) if board == '主板' else rows(688000, 1, 'SSE', board))
    documents = []
    def doc(label, raw):
        return dict(label=label, raw=raw, sha256=sha256(raw).hexdigest(),
            fetched_at=(SATURDAY+timedelta(seconds=1)).isoformat(), local_path='TEST_ONLY/' + label)
    for label in ('SZSE_A', 'SSE_1', 'SSE_8'):
        documents.append(doc(label, b'TEST_ONLY_PARSER_STUB'))
    for page in range(2):
        content = [dict(xxzqdm=str(920000+i), xxzqjc='TEST_ONLY', fxssrq='20200101', xxjsrq='20261023')
                   for i in (range(100) if page == 0 else range(100, 201))]
        payload = [dict(content=content, numberOfElements=len(content), number=page,
                        totalElements=201, totalPages=2)]
        documents.append(doc('BSE_' + str(page), json.dumps(payload).encode()))
    return documents


def _replay_v2(documents):
    return session_lists.replay_official_documents(documents,
        started_at=SATURDAY, available_at=SATURDAY+timedelta(seconds=2))


def test_weekend_v2_preserves_actual_acquisition_and_provider_dates(v2_documents):
    payload = _replay_v2(v2_documents)
    assert payload['parser_version'] == 'official-security-lists-v2-session-date'
    assert payload['effective_session'] == '2026-10-23'
    assert payload['fetched_at'] == payload['available_at'] == '2026-10-24T01:50:02+08:00'
    assert payload['exchange_counts']['BSE'] == 201
    assert {r['as_of'] for r in payload['records'] if r['exchange'] == 'BSE'} == {'2026-10-23'}
    assert payload['collection_timing']['quote_date_verified'] is False
    assert payload['collection_timing']['strict_contemporaneous_pit'] is False
    assert screening_quote_date(payload, SATURDAY+timedelta(seconds=3)) == '2026-10-23'
    assert screening_quote_date(dict(parser_version='official-security-lists-v1'), SATURDAY) == '2026-10-24'
    assert screening_quote_date(dict(parser_version='official-security-lists-v1'), SATURDAY,
        retained_quote_date='2026-09-23') == '2026-09-23'
    assert screening_quote_date(payload, SATURDAY+timedelta(seconds=3),
        retained_quote_date='2026-10-23') == '2026-10-23'
    with pytest.raises(ValueError, match='Retained v2'):
        screening_quote_date(payload, SATURDAY+timedelta(seconds=3), retained_quote_date='2026-10-24')


@pytest.mark.parametrize('fault', ['future', 'stale', 'mixed', 'non_session', 'missing_page',
    'wrong_page', 'changed_totals', 'count', 'duplicate_code', 'raw_hash', 'future_fetch', 'cross_day'])
def test_weekend_v2_does_not_waive_page_date_and_source_guards(v2_documents, fault):
    docs = deepcopy(v2_documents)
    page = json.loads(docs[-1]['raw'])
    if fault in {'future', 'stale', 'mixed', 'non_session'}:
        stamp = {'future':'20261026', 'stale':'20261022', 'mixed':'20261022', 'non_session':'20261024'}[fault]
        page[0]['content'][0]['xxjsrq'] = stamp
    elif fault == 'missing_page': docs.pop()
    elif fault == 'wrong_page': page[0]['number'] = 0
    elif fault == 'changed_totals': page[0]['totalElements'] = 202
    elif fault == 'count': page[0]['numberOfElements'] = 99
    elif fault == 'duplicate_code': page[0]['content'][0]['xxzqdm'] = '920000'
    elif fault == 'raw_hash': docs[-1]['sha256'] = 'f'*64
    elif fault == 'future_fetch': docs[-1]['fetched_at'] = (SATURDAY+timedelta(seconds=3)).isoformat()
    elif fault == 'cross_day': docs[-1]['fetched_at'] = '2026-10-23T23:59:59+08:00'
    if fault in {'future', 'stale', 'mixed', 'non_session', 'wrong_page', 'changed_totals', 'count', 'duplicate_code'}:
        docs[-1]['raw'] = json.dumps(page).encode()
        docs[-1]['sha256'] = sha256(docs[-1]['raw']).hexdigest()
    with pytest.raises((ValueError, KeyError)):
        _replay_v2(docs)


def test_v2_rejects_cross_midnight_and_later_m2_restamp(v2_documents):
    with pytest.raises(ValueError):
        validate_list_timing(provider_dates=['2026-10-23'], fetched_at=['2026-10-24T00:00:01+08:00'],
            started_at=datetime.fromisoformat('2026-10-23T23:59:59+08:00'), available_at=SATURDAY)
    payload = _replay_v2(v2_documents)
    with pytest.raises(ValueError, match='session changed'):
        screening_quote_date(payload, SATURDAY+timedelta(days=1))
    payload['effective_session'] = '2026-10-24'
    with pytest.raises(ValueError):
        screening_quote_date(payload, SATURDAY+timedelta(seconds=3))


def test_legacy_collectors_and_calendar_membership_are_not_rewritten():
    from value_investment_agent import official_universe
    from value_investment_agent.domain.execution.exchange_calendar import SUPPORTED_VENUES
    assert official_universe.VERSION == 'official-security-lists-v1'
    assert 'BSE' not in SUPPORTED_VENUES
    verify_calendar_archives(Path(__file__).resolve().parents[1])


def test_v2_adapter_archives_actual_clock_and_complete_pages_without_fallback(v2_documents, tmp_path, monkeypatch):
    from urllib.parse import parse_qs
    class Response:
        status_code = 200
        def __init__(self, url, raw): self.url, self.raw = url, raw
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): yield self.raw
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, **kwargs):
            if url.startswith(session_lists.SZSE_URL): index = 0
            elif url.startswith(session_lists.SSE_URL): index = 1 if 'STOCK_TYPE=1' in url else 2
            else: index = 3 + int(parse_qs(kwargs['data'].decode())['page'][0])
            return Response(url, v2_documents[index]['raw'])
    monkeypatch.setattr(session_lists.requests, 'Session', Session)
    ticks = iter(SATURDAY+timedelta(seconds=i) for i in range(7))
    result = session_lists.collect_security_lists_v2(tmp_path/'raw', clock=lambda: next(ticks))
    assert result['available_at'] == '2026-10-24T01:50:06+08:00'
    assert result['effective_session'] == '2026-10-23'
    assert [r['fetched_at'] for r in result['sources']] == [
        (SATURDAY+timedelta(seconds=i)).isoformat() for i in range(1, 6)]
    assert all(sha256(Path(ref['local_path']).read_bytes()).hexdigest() == ref['sha256'] for ref in result['sources'])
    assert not list(tmp_path.rglob('*.part'))


def test_incomplete_calendar_rejects_before_any_network_or_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(session_lists.requests, 'Session', lambda: pytest.fail('No network before covered close'))
    with pytest.raises(ValueError):
        session_lists.collect_security_lists_v2(tmp_path/'never',
            clock=lambda: datetime.fromisoformat('2026-10-23T14:00:00+08:00'))
    assert not (tmp_path/'never').exists()


@pytest.mark.parametrize('fault', ['duplicate_document', 'future_listing', 'small_universe', 'naive_fetch'])
def test_v2_keeps_coverage_and_available_time_guards(v2_documents, fault):
    docs = deepcopy(v2_documents)
    if fault == 'duplicate_document':
        docs.append(deepcopy(docs[-1]))
    elif fault == 'naive_fetch':
        docs[0]['fetched_at'] = '2026-10-24T01:50:01'
    else:
        for doc in docs[3:]:
            page = json.loads(doc['raw'])
            if fault == 'future_listing':
                page[0]['content'][0]['fxssrq'] = '20261026'
            else:
                page[0]['totalElements'] = 199
                if page[0]['number'] == 1:
                    page[0]['content'] = page[0]['content'][:99]
                    page[0]['numberOfElements'] = 99
            doc['raw'] = json.dumps(page).encode()
            doc['sha256'] = sha256(doc['raw']).hexdigest()
    with pytest.raises(ValueError):
        _replay_v2(docs)


def test_application_does_not_copy_a_retained_fallback(tmp_path, monkeypatch):
    from value_investment_agent.application.discovery import official_universe_collection as app
    retained = tmp_path/'runtime/exchange-lists/official-universe.json'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'TEST_ONLY_DO_NOT_COPY')
    monkeypatch.setattr(app, 'verify_calendar_archives', lambda root: None)
    def failed(*args): raise ValueError('TEST_ONLY explicit date failure')
    monkeypatch.setattr(app, 'collect_security_lists_v2', failed)
    with pytest.raises(ValueError, match='date failure'):
        app.collect_official_m2_input(tmp_path/'runtime/new', tmp_path)
    assert retained.read_bytes() == b'TEST_ONLY_DO_NOT_COPY'
    assert not (tmp_path/'runtime/new/official-universe.json').exists()


@pytest.mark.parametrize('damage', [None, 'source_hash', 'company_name', 'missing_raw',
    'raw_bytes', 'pagination', 'missing_page', 'timing', 'unknown_version',
    'null_version', 'stripped_version', 'downgraded_version', 'linked_raw'])
def test_v2_m2_receipt_session_label_does_not_restamp_fetched_time(
        v2_documents, tmp_path, monkeypatch, capsys, damage):
    import sys
    from test_m2_opportunity_discovery import RUN_M2, _tencent_payload, _sina_payload, _dividend_payload
    from value_investment_agent.m2_opportunity_discovery import EvidenceReference
    for document in v2_documents:
        path = tmp_path/'runtime/raw'/document['label']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document['raw'])
        document['local_path'] = str(path)
    payload = _replay_v2(v2_documents)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = SATURDAY+timedelta(seconds=10)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    def official(directory, project):
        raw = RUN_M2._json_bytes(payload)
        path = RUN_M2._write(directory, 'official-universe.json', raw)
        return payload, EvidenceReference(id='official', path=path.relative_to(project).as_posix(),
            sha256=sha256(raw).hexdigest(), source_name='TEST_ONLY', source_url='https://example.test',
            fetched_at=datetime.fromisoformat(payload['fetched_at']))
    def market(value):
        value = dict(value, fetched_at=SATURDAY.isoformat())
        return RUN_M2._json_bytes(value), value
    monkeypatch.setattr(RUN_M2, 'datetime', Clock)
    monkeypatch.setattr(RUN_M2, '_collect_official', official)
    monkeypatch.setattr(RUN_M2, 'fetch_tencent_board_rank', lambda: market(_tencent_payload()))
    monkeypatch.setattr(RUN_M2, 'fetch_sina_industry_quotes', lambda: market(_sina_payload()))
    monkeypatch.setattr(RUN_M2, 'fetch_eastmoney_dividends', lambda **kwargs: market(_dividend_payload()))
    output = tmp_path/'runtime/new'
    summary = RUN_M2.run_once(root=tmp_path, output_dir=output, wps_dir=None, max_per_channel=50,
        skip_dividend=False, reuse_inputs=False, skip_workbook=True)
    receipt = json.loads((output/'receipt.json').read_bytes())
    assert summary['rule_version'] == 'm2-evidence-screen-v3'
    assert summary['quote_date'] == '2026-10-23'
    assert summary['as_of'] == '2026-10-24'
    assert datetime.fromisoformat(summary['generated_at']) == SATURDAY+timedelta(seconds=10)
    assert summary['quote_date_verification'] == 'UNVERIFIED_PROVIDER_TRADE_DATE'
    ref = next(ref for ref in receipt['evidence_refs'] if ref['id'] == 'official')
    assert ref['fetched_at'] == payload['fetched_at']
    assert summary['replay']['raw_inputs_match'] is True
    original_receipt = (output/'receipt.json').read_bytes()
    retained = json.loads((output/'official-universe.json').read_bytes())
    if damage == 'source_hash':
        retained['sources'][0]['sha256'] = '0'*64
    elif damage == 'company_name':
        retained['records'][0]['name'] = 'TEST_ONLY_TAMPERED'
    elif damage == 'missing_raw':
        Path(retained['sources'][0]['local_path']).unlink()
    elif damage == 'raw_bytes':
        Path(retained['sources'][-1]['local_path']).write_bytes(b'TAMPERED')
    elif damage == 'pagination':
        source = retained['sources'][-1]
        path = Path(source['local_path'])
        page = json.loads(path.read_bytes())
        page[0]['totalPages'] = 3
        raw = json.dumps(page).encode()
        path.write_bytes(raw)
        source['sha256'] = sha256(raw).hexdigest()
    elif damage == 'missing_page':
        retained['sources'].pop()
    elif damage == 'timing':
        retained['collection_timing']['fetched_at'] = SATURDAY.isoformat()
    elif damage == 'unknown_version':
        retained['parser_version'] = 'official-security-lists-v999'
    elif damage == 'null_version':
        retained['parser_version'] = None
    elif damage == 'stripped_version':
        del retained['parser_version']
    elif damage == 'downgraded_version':
        retained['parser_version'] = 'official-security-lists-v1'
    elif damage == 'linked_raw':
        target = Path(retained['sources'][0]['local_path'])
        link = target.with_suffix('.link')
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip('Host does not permit symlink creation')
        retained['sources'][0]['local_path'] = str(link)
    # Re-serialize the JSON: recalculating its hash must not replace raw verification.
    (output/'official-universe.json').write_bytes(RUN_M2._json_bytes(retained))
    def no_network(*args, **kwargs):
        pytest.fail('Retained CLI replay must not collect data')
    for name in ('_collect_official', 'fetch_tencent_board_rank',
                 'fetch_sina_industry_quotes', 'fetch_eastmoney_dividends'):
        monkeypatch.setattr(RUN_M2, name, no_network)
    monkeypatch.setattr(RUN_M2, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['run_m2_opportunity_discovery.py', '--reuse-inputs',
        '--output-dir', str(output), '--no-wps', '--no-workbook'])
    if damage:
        with pytest.raises(ValueError):
            RUN_M2.main()
        assert (output/'receipt.json').read_bytes() == original_receipt
    else:
        assert RUN_M2.main() == 0
        replay = json.loads(capsys.readouterr().out)
        assert replay['generated_at'] == summary['generated_at']
        assert replay['quote_date'] == '2026-10-23'
        assert replay['rule_version'] == summary['rule_version']
        assert replay['replay']['raw_inputs_match'] is True
        assert replay['quote_date_verification'] == 'UNVERIFIED_PROVIDER_TRADE_DATE'


@pytest.mark.parametrize('version', ['official-security-lists-v999', 'test', None, 2, ''])
def test_quote_date_rejects_unknown_declared_versions(version):
    with pytest.raises(ValueError, match='Unsupported'):
        screening_quote_date({'parser_version': version}, SATURDAY)


def test_unversioned_legacy_requires_explicit_complete_shape(v2_documents):
    legacy = _replay_v2(v2_documents)
    for key in ('parser_version', 'collection_timing', 'available_at', 'effective_session'):
        del legacy[key]
    assert screening_quote_date(legacy, SATURDAY, retained_quote_date='2026-09-23') == '2026-09-23'
    del legacy['sources']
    with pytest.raises(ValueError, match='unversioned'):
        screening_quote_date(legacy, SATURDAY)


@pytest.mark.skipif(not __import__('os').environ.get('OFFICIAL_LIST_REPLAY_ROOT'),
    reason='Explicit retained public list root not supplied')
@pytest.mark.parametrize('damage', [None, 'source_hash', 'company_name'])
def test_v2_readonly_reparse_of_retained_official_bytes(tmp_path, monkeypatch, damage):
    import os
    import sys
    from test_m2_opportunity_discovery import RUN_M2
    from value_investment_agent.application.discovery.official_universe_collection import (
        verify_retained_official_input,
    )
    root = Path(os.environ['OFFICIAL_LIST_REPLAY_ROOT'])
    # Explicit sealed input; no mtime selection, copying, collection or restamp.
    path = root/'runtime/daily-marketwide/20261023T1229185986655Z/official-universe.json'
    original = path.read_bytes()
    assert sha256(original).hexdigest() == 'f500d22bd3ad16f3a139950608b4f0e21cd391f7682b62ed395a56b5011dc98b'
    payload = json.loads(original)
    documents = []
    for ref in payload['sources']:
        raw = Path(ref['local_path']).read_bytes()
        assert sha256(raw).hexdigest() == ref['sha256']
        documents.append(dict(ref, raw=raw))
    # Earliest observed response is a replay lower bound, NOT the unavailable
    # original request start. This does not register a new acquired snapshot.
    observed = min(datetime.fromisoformat(r['fetched_at']) for r in documents)
    rebuilt = session_lists.replay_official_documents(documents, started_at=observed,
        available_at=datetime.fromisoformat(payload['fetched_at']))
    assert rebuilt['records'] == payload['records']
    assert rebuilt['fetched_at'] == payload['fetched_at']
    assert rebuilt['exchange_counts'] == {'BSE':353,'SSE':2318,'SZSE':2906}
    assert rebuilt['effective_session'] == '2026-10-23'
    assert completed_list_session(SATURDAY).isoformat() == rebuilt['effective_session']
    verify_retained_official_input(rebuilt, root=root)
    if damage is not None:
        # TEST_ONLY V2 reconstruction of explicit old bytes, not a new collection.
        # Exercise the real --reuse-inputs CLI before any output/reference writes.
        output = tmp_path/'historical-cli-negative'
        output.mkdir()
        for name in ('receipt.json', 'tencent-market.json', 'sina-industry-quotes.json',
                     'eastmoney-dividends.json', 'retained-financial-points.json'):
            (output/name).write_bytes((path.parent/name).read_bytes())
        if damage == 'source_hash':
            rebuilt['sources'][0]['sha256'] = '0'*64
        else:
            rebuilt['records'][0]['name'] = 'TEST_ONLY_TAMPERED'
        (output/'official-universe.json').write_bytes(RUN_M2._json_bytes(rebuilt))
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        def no_network(*args, **kwargs):
            pytest.fail('Retained actual-source CLI must not collect data')
        for name in ('_collect_official', 'fetch_tencent_board_rank',
                     'fetch_sina_industry_quotes', 'fetch_eastmoney_dividends'):
            monkeypatch.setattr(RUN_M2, name, no_network)
        monkeypatch.setattr(RUN_M2, 'ROOT', root)
        monkeypatch.setattr(sys, 'argv', ['run_m2_opportunity_discovery.py', '--reuse-inputs',
            '--output-dir', str(output), '--no-wps', '--no-workbook'])
        with pytest.raises(ValueError, match='raw hash mismatch|differs from raw replay'):
            RUN_M2.main()
        assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert path.read_bytes() == original
