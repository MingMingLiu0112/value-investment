"""TEST_ONLY transport; actual originals are validated by an opt-in live run."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest
import requests

from value_investment_agent.infrastructure.filings import official_report_acquisition as adapter


@pytest.fixture
def transport(monkeypatch):
    state = dict(rows=[dict(secCode="000544", orgId="test-org", announcementId="123",
        announcementTitle="2025年年度报告", adjunctUrl="finalpage/2026-04-03/123.PDF",
        announcementTime=int(datetime(2026, 4, 3, tzinfo=adapter.CHINA).timestamp() * 1000))],
        cover="证券代码：000544\n中原环保股份有限公司\n2025年年度报告", calls=[], pdf_calls=[])

    def query(parameters, *, raw_response_sink):
        state['calls'].append(parameters)
        rows = state['rows'] if parameters.get('stock') else [dict(secCode='000544', orgId='test-org')]
        payload = dict(announcements=rows, totalAnnouncement=len(rows))
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        raw_response_sink(body, dict(url=adapter.disclosures.SEARCH_URL, request=parameters,
            sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body),
            acquired_at=datetime.now(timezone.utc).isoformat()))
        return payload

    def download(url, path):
        state['pdf_calls'].append(url)
        path.write_bytes(b'%PDF-TEST_ONLY\n%%EOF')
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr(adapter.disclosures, '_request_json', query)
    monkeypatch.setattr(adapter, 'download_official_pdf', download)
    monkeypatch.setattr(adapter, 'extract_pages', lambda *args, **kwargs: [state['cover']])
    monkeypatch.setattr(adapter.time, 'sleep', lambda _: None)
    return state


def acquire(root, **kwargs):
    return adapter.acquire_official_report(root=root, symbol='000544', issuer_name='中原环保',
        period=kwargs.pop('period', '2025-12-31'),
        output_dir=kwargs.pop('output_dir', root / 'runtime/new'),
        allow_network=kwargs.pop('allow_network', True), **kwargs)


def test_discovers_without_url_and_retains_raw_and_descriptor(tmp_path, transport):
    result = acquire(tmp_path)
    assert result['source']['period'] == '2025-12-31'
    assert result['source']['available_at'] == result['fetched_at']
    assert result['historical_available_at'] is None
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert result['published_date'] == '2026-04-03'
    assert len(result['index_bindings']) == 2
    assert transport['calls'][-1]['category'] == 'category_ndbg_szsh'
    assert transport['calls'][-1]['stock'] == '000544,test-org'
    for ref in result['index_bindings']:
        assert hashlib.sha256((tmp_path / ref['path']).read_bytes()).hexdigest() == ref['sha256']
    assert json.loads((tmp_path / 'runtime/new/receipt.json').read_bytes()) == result
    with pytest.raises(FileExistsError):
        acquire(tmp_path)


def test_interim_uses_exact_half_year(tmp_path, transport):
    transport['rows'][0].update(announcementTitle='2026年半年度报告',
        adjunctUrl='finalpage/2026-08-24/123.PDF',
        announcementTime=int(datetime(2026, 8, 24, tzinfo=adapter.CHINA).timestamp()*1000))
    transport['cover'] = '股票代码：000544\n中原环保股份有限公司2026年半年度报告'
    result = acquire(tmp_path, period='2026-06-30')
    assert result['report_kind'] == 'interim'
    assert transport['calls'][-1]['category'] == 'category_bndbg_szsh'


def test_labelled_table_without_colon(tmp_path, transport):
    transport['cover'] = '中原环保2025年年度报告\n股票简称 中原环保 股票代码 000544'
    assert acquire(tmp_path)['source']['symbol'] == '000544'


@pytest.mark.parametrize('wrong', [None, 'symbol', 'issuer', 'period', 'conflicting_symbol'])
def test_identity_table_on_page_nine_keeps_strict_checks(tmp_path, transport, monkeypatch, wrong):
    pages = ['TEST_ONLY front matter'] * 8 + [transport['cover']]
    if wrong == 'symbol':
        pages[-1] = pages[-1].replace('000544', '000151')
    elif wrong == 'issuer':
        pages[-1] = pages[-1].replace('中原环保', '另一家公司')
    elif wrong == 'period':
        pages[-1] = pages[-1].replace('2025年', '2024年')
    elif wrong == 'conflicting_symbol':
        pages[-1] += '\n证券代码：000151'
    limits = []

    def extract(path, *, limit):
        limits.append(limit)
        return pages[:limit]

    monkeypatch.setattr(adapter, 'extract_pages', extract)
    if wrong:
        with pytest.raises(ValueError, match='cover mismatch'):
            acquire(tmp_path)
    else:
        packet = acquire(tmp_path)
        monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
        assert retained(tmp_path, receipt_binding(tmp_path)) == packet
    assert limits and all(limit == 12 for limit in limits)


@pytest.mark.parametrize('change', [
    dict(secCode='600519'), dict(announcementTitle='2025年年度报告摘要'),
    dict(announcementTitle='2024年年度报告'),
    dict(adjunctUrl='https://example.invalid/123.PDF'),
    dict(adjunctUrl='finalpage/2026-04-03/999.PDF'),
    dict(adjunctUrl='finalpage/2026-04-04/123.PDF'),
    dict(announcementTime=0), dict(announcementTime=True),
])
def test_invalid_index_never_downloads(tmp_path, transport, change):
    transport['rows'][0].update(change)
    with pytest.raises(ValueError):
        acquire(tmp_path)
    assert not transport['pdf_calls']
    assert (tmp_path / 'runtime/new/failure.json').is_file()
    assert not (tmp_path / 'runtime/new/receipt.json').exists()


@pytest.mark.parametrize('cover', [
    '电话：0471-3000544\n中原环保2025年年度报告',
    '证券代码：600519\n中原环保2025年年度报告',
    '证券代码：000544\n另一家公司2025年年度报告',
    '证券代码：000544\n中原环保2024年年度报告',
    '证券代码：000544\n中原环保2025年年度报告摘要',
])
def test_pdf_identity_is_not_inferred_from_url(tmp_path, transport, cover):
    transport['cover'] = cover
    with pytest.raises(ValueError, match='cover mismatch'):
        acquire(tmp_path)
    assert (tmp_path / 'runtime/new/original.pdf').is_file()
    assert not (tmp_path / 'runtime/new/receipt.json').exists()


def test_revisions_are_ambiguous_not_silently_selected(tmp_path, transport):
    transport['rows'].append(dict(transport['rows'][0], announcementId='124',
        announcementTitle='2025年年度报告（更正版）', adjunctUrl='finalpage/2026-04-03/124.PDF'))
    with pytest.raises(ValueError, match='ambiguous'):
        acquire(tmp_path)
    assert not transport['pdf_calls']


def test_duplicate_index_rows_rejected(tmp_path, transport):
    transport['rows'] *= 2
    with pytest.raises(ValueError, match='duplicate'):
        acquire(tmp_path)


@pytest.mark.parametrize('period', ['2025-09-30', '2026-12-31', '2025-6-30'])
def test_invalid_or_future_period(tmp_path, transport, period):
    with pytest.raises(ValueError):
        acquire(tmp_path, period=period)
    assert not transport['calls']


def test_network_must_be_explicit_and_archive_contained(tmp_path, transport):
    with pytest.raises(ValueError, match='permission'):
        acquire(tmp_path, allow_network=False)
    with pytest.raises(ValueError, match='inside project runtime'):
        acquire(tmp_path, output_dir=tmp_path / 'elsewhere')
    assert not transport['calls']


def test_raw_index_changed_during_pdf_acquisition_rejected(tmp_path, transport, monkeypatch):
    original = adapter.download_official_pdf

    def mutate(url, path):
        digest = original(url, path)
        (path.parent / 'index-1.json').write_bytes(b'{}')
        return digest

    monkeypatch.setattr(adapter, 'download_official_pdf', mutate)
    with pytest.raises(ValueError, match='source drift'):
        acquire(tmp_path)


def test_raw_response_required(tmp_path, transport, monkeypatch):
    monkeypatch.setattr(adapter.disclosures, '_request_json', lambda *args, **kwargs: {})
    with pytest.raises(ValueError, match='missing raw'):
        acquire(tmp_path)


@pytest.mark.parametrize('mode', ['missing_page', 'changed_total', 'overflow', 'request_budget'])
def test_pagination_failures(tmp_path, transport, monkeypatch, mode):
    native = adapter.disclosures._request_json

    def query(parameters, *, raw_response_sink):
        if not parameters.get('stock'):
            return native(parameters, raw_response_sink=raw_response_sink)
        page = int(parameters['pageNum'])
        rows = [dict(transport['rows'][0], announcementId=str(page),
                     adjunctUrl=f'finalpage/2026-04-03/{page}.PDF')]
        total = 2
        if mode == 'missing_page' and page == 2:
            rows = []
        elif mode == 'changed_total' and page == 2:
            total = 3
        elif mode == 'overflow':
            total = 0
        elif mode == 'request_budget':
            total = 121
        payload = dict(announcements=rows, totalAnnouncement=total)
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=adapter.disclosures.SEARCH_URL, request=parameters,
            sha256=hashlib.sha256(body).hexdigest(),
            acquired_at=datetime.now(timezone.utc).isoformat()))
        return payload

    monkeypatch.setattr(adapter.disclosures, '_request_json', query)
    with pytest.raises(ValueError, match='pagination'):
        acquire(tmp_path)
    assert not transport['pdf_calls']


def test_future_raw_acquisition_clock_rejected(tmp_path, transport, monkeypatch):
    native = adapter.disclosures._request_json

    def query(parameters, *, raw_response_sink):
        def capture(body, metadata):
            raw_response_sink(body, dict(metadata, acquired_at='2999-01-01T00:00:00+00:00'))
        return native(parameters, raw_response_sink=capture)

    monkeypatch.setattr(adapter.disclosures, '_request_json', query)
    with pytest.raises(ValueError, match='clock'):
        acquire(tmp_path)


def receipt_binding(root):
    path = root / 'runtime/new/receipt.json'
    return dict(path=path.relative_to(root).as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def retained(root, binding, **kwargs):
    return adapter.load_retained_official_report(root=root, receipt_binding=binding,
        symbol=kwargs.get('symbol', '000544'), issuer_name=kwargs.get('issuer_name', '中原环保'),
        period=kwargs.get('period', '2025-12-31'))


def test_explicit_cache_replays_without_network_or_new_timestamps(tmp_path, transport, monkeypatch):
    packet = acquire(tmp_path)
    binding = receipt_binding(tmp_path)
    before = {p: p.read_bytes() for p in (tmp_path / 'runtime/new').iterdir()}
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
    monkeypatch.setattr(adapter.disclosures, '_request_json', lambda *a, **k: pytest.fail('cache did HTTP'))
    for _ in range(2):
        assert retained(tmp_path, binding) == packet
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize('target', ['receipt.json', 'index-1.json', 'index-2.json', 'original.pdf'])
def test_cache_corruption_is_not_silently_downloaded(tmp_path, transport, monkeypatch, target):
    acquire(tmp_path)
    binding = receipt_binding(tmp_path)
    (tmp_path / 'runtime/new' / target).write_bytes(b'corrupt')
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
    with pytest.raises(ValueError, match='binding invalid'):
        retained(tmp_path, binding)
    assert len(transport['pdf_calls']) == 1


@pytest.mark.parametrize('changes', [dict(symbol='600519'), dict(period='2024-12-31'),
                                    dict(issuer_name='其他公司')])
def test_cache_exact_issuer_and_period(tmp_path, transport, monkeypatch, changes):
    acquire(tmp_path)
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
    with pytest.raises(ValueError):
        retained(tmp_path, receipt_binding(tmp_path), **changes)


@pytest.mark.parametrize('change', [dict(formal_eligibility=True),
    dict(strict_historical_pit=True), dict(action='buy'), dict(report_kind='interim'),
    dict(fetched_at='2999-01-01T00:00:00+00:00')])
def test_resealed_cache_cannot_upgrade_or_change_clock(tmp_path, transport, monkeypatch, change):
    packet = acquire(tmp_path)
    packet.update(change)
    (tmp_path / 'runtime/new/receipt.json').write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
    with pytest.raises(ValueError):
        retained(tmp_path, receipt_binding(tmp_path))


def test_resealed_raw_request_mismatch_rejected(tmp_path, transport, monkeypatch):
    packet = acquire(tmp_path)
    packet['index_bindings'][-1]['metadata']['request']['category'] = 'category_bndbg_szsh'
    (tmp_path / 'runtime/new/receipt.json').write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)
    with pytest.raises(ValueError, match='request or clock'):
        retained(tmp_path, receipt_binding(tmp_path))


def test_final_cache_closure_recheck(tmp_path, transport, monkeypatch):
    acquire(tmp_path)
    binding = receipt_binding(tmp_path)
    monkeypatch.setattr(adapter, 'validate_pdf_original', lambda _: None)

    def cover(*args, **kwargs):
        (tmp_path / 'runtime/new/index-1.json').write_bytes(b'changed')
        return [transport['cover']]

    monkeypatch.setattr(adapter, 'extract_pages', cover)
    with pytest.raises(ValueError, match='changed during reuse'):
        retained(tmp_path, binding)


def test_timeout_retries_index_once(tmp_path, transport, monkeypatch):
    native = adapter.disclosures._request_json
    calls = []

    def query(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.Timeout('TEST_ONLY')
        return native(*args, **kwargs)

    monkeypatch.setattr(adapter.disclosures, '_request_json', query)
    packet = acquire(tmp_path)
    assert len(calls) == 3
    assert packet['request_attempts'][0]['status'] == 'FAILED'
    assert packet['request_attempts'][1]['attempt'] == 2


def test_pdf_connection_failure_keeps_partial_then_retries_once(tmp_path, transport, monkeypatch):
    native = adapter.download_official_pdf
    calls = []

    def download(url, path):
        calls.append(path)
        if len(calls) == 1:
            path.write_bytes(b'PARTIAL_TEST_ONLY')
            raise requests.ConnectionError('TEST_ONLY')
        return native(url, path)

    monkeypatch.setattr(adapter, 'download_official_pdf', download)
    packet = acquire(tmp_path)
    assert len(calls) == 2
    assert calls[0].read_bytes() == b'PARTIAL_TEST_ONLY'
    assert packet['source']['path'].endswith('original-retry-2.pdf')


@pytest.mark.parametrize('status,expected', [(403, 1), (429, 1), (503, 2)])
def test_http_retry_budget_and_access_denial(tmp_path, transport, monkeypatch, status, expected):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        response = requests.Response()
        response.status_code = status
        raise requests.HTTPError('TEST_ONLY', response=response)

    monkeypatch.setattr(adapter.disclosures, '_request_json', fail)
    with pytest.raises(requests.HTTPError):
        acquire(tmp_path)
    assert len(calls) == expected
    assert json.loads((tmp_path / 'runtime/new/failure.json').read_bytes())['status'] == 'FAILED'


@pytest.mark.parametrize('kind,period,digest', [
    ('FY2025', '2025-12-31', '55bac5078b18dfe1c7ff5bf79c90bf985e2635a7432c1aed2de579a63fe55002'),
    ('H12026', '2026-06-30', 'cf21f807e2c4f1d085dbfb6ec20151f0f0e54d58752dbebfea5f3f51271af958'),
])
def test_optin_actual_public_archive_cold_read(kind, period, digest):
    run = os.environ.get('OFFICIAL_REPORT_ACQUISITION_REAL_RUN')
    if not run:
        pytest.skip('Explicit retained actual-public run required; never downloads in pytest')
    root = Path(__file__).resolve().parents[1]
    directory = (root / run).resolve()
    assert directory.is_relative_to(root / 'runtime')
    result = json.loads((directory / kind / 'receipt.json').read_bytes())
    receipt = directory / kind / 'receipt.json'
    replayed = adapter.load_retained_official_report(root=root,
        receipt_binding=dict(path=receipt.relative_to(root).as_posix(),
                             sha256=hashlib.sha256(receipt.read_bytes()).hexdigest()),
        symbol='000544', issuer_name='中原环保', period=period)
    assert replayed == result
    source = result['source']
    assert source['symbol'] == '000544' and source['period'] == period
    assert source['sha256'] == digest
    pdf = root / source['path']
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == digest
    adapter._verify_cover(adapter.extract_pages(pdf, limit=6), symbol='000544',
        issuer_name='中原环保', period=period, kind=result['report_kind'])
    rows = []
    for ref in result['index_bindings']:
        raw = (root / ref['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref['sha256']
        if ref['metadata']['request'].get('stock'):
            rows.extend(json.loads(raw)['announcements'])
    row, published = adapter._select(rows, symbol='000544', period=period,
        kind=result['report_kind'], today=datetime.fromisoformat(result['started_at']).astimezone(adapter.CHINA).date())
    assert source['source_url'] == adapter.disclosures.PDF_BASE_URL + row['adjunctUrl']
    assert result['published_date'] == published.isoformat()
    assert source['available_at'] == result['fetched_at']
    assert not result['formal_eligibility'] and not result['strict_historical_pit']
    assert result['historical_available_at'] is None and result['action'] == 'no_order'


def test_optin_actual_000151_retained_identity_without_download():
    archive = os.environ.get('OFFICIAL_REPORT_ACQUISITION_000151_RUN')
    if not archive:
        pytest.skip('Explicit retained 000151 failed archive required; no network')
    root = Path(__file__).resolve().parents[1]
    directory = (root / archive).resolve()
    assert directory.is_relative_to(root / 'runtime')
    failure_path = directory / 'failure.json'
    failure = json.loads(failure_path.read_bytes())
    pdf = directory / 'original.pdf'
    paths = [failure_path, pdf]
    rows = []
    for ref in failure['index_bindings']:
        path = (root / ref['path']).resolve()
        assert path.is_relative_to(root / 'runtime')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == ref['sha256']
        paths.append(path)
        if ref['metadata']['request'].get('stock'):
            rows.extend(json.loads(path.read_bytes())['announcements'])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before[pdf] == 'b4db315e7d836f5608a8ee9979adf779a44bb960da130014acc106be8a5d25b4'
    row, _ = adapter._select(rows, symbol='000151', period='2025-12-31', kind='annual',
        today=datetime.fromisoformat(failure['completed_at']).astimezone(adapter.CHINA).date())
    assert row['announcementId'] == '1225113085'
    adapter.validate_pdf_original(pdf)
    pages = adapter.extract_pages(pdf, limit=adapter.IDENTITY_PAGE_LIMIT)
    args = dict(symbol='000151', issuer_name='中成股份', period='2025-12-31', kind='annual')
    with pytest.raises(ValueError, match='cover mismatch'):
        adapter._verify_cover(pages[:6], **args)
    adapter._verify_cover(pages, **args)
    for changes in [dict(symbol='600519'), dict(issuer_name='中原环保'), dict(period='2027-12-31')]:
        with pytest.raises(ValueError, match='cover mismatch'):
            adapter._verify_cover(pages, **dict(args, **changes))
    conflicting = list(pages)
    conflicting[8] += '\n证券代码：600519'
    with pytest.raises(ValueError, match='cover mismatch'):
        adapter._verify_cover(conflicting, **args)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before
