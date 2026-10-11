"""Official query archive boundaries with synthetic response fixtures."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest
from value_investment_agent.application.product import daily_event_observation as service
from value_investment_agent.event_scan import event_scan_from_payload
import json


def index():
    return {'url':'https://www.cninfo.com.cn/new/hisAnnouncement/query',
        'parameters':{'stock':'600519,gssh0600519','seDate':'2020-01-01~2020-01-02'},
        'total_announcements':0,'announcements':[]}


def test_empty_official_window_does_not_approve_prior_events_or_advance_research(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'search_announcement_window',lambda *args,**kwargs:index())
    folder=tmp_path/'runtime/events'
    result=service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic issuer',
        start=date(2020,1,1),end=date(2020,1,2),output_dir=folder)
    assert result['announcement_count']==0 and result['pagination_complete'] is True
    assert result['materiality_approved'] is False and result['research_date_advanced'] is False
    assert result['index_representation']=='PARSED_OFFICIAL_QUERY_NOT_RAW_HTTP_BYTES'
    scan=event_scan_from_payload(json.loads((folder/'event-scan.json').read_text(encoding='utf-8')))
    assert scan.status=='PENDING_HUMAN_REVIEW' and scan.blockers
    with pytest.raises(FileExistsError):
        service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic issuer',
            start=date(2020,1,1),end=date(2020,1,2),output_dir=folder)


def test_wrong_symbol_or_window_never_generates_scan(tmp_path,monkeypatch):
    data=index(); data['parameters']['stock']='000651,test'
    monkeypatch.setattr(service,'search_announcement_window',lambda *args,**kwargs:data)
    with pytest.raises(ValueError,match='identity/window/count'):
        service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic issuer',
            start=date(2020,1,1),end=date(2020,1,2),output_dir=tmp_path/'runtime/events')
    assert not (tmp_path/'runtime/events/event-scan.json').exists()


def test_official_download_rejects_redirect_before_creating_original(tmp_path,monkeypatch):
    from value_investment_agent.infrastructure.filings import official_pdf
    class Response:
        status_code=302
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def raise_for_status(self): pass
    class Session:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,url,**kwargs):
            assert kwargs['allow_redirects'] is False
            return Response()
    monkeypatch.setattr(official_pdf.requests,'Session',Session)
    with pytest.raises(ValueError,match='redirects'):
        official_pdf.download_official_pdf('https://static.cninfo.com.cn/finalpage/test.pdf',tmp_path/'original.pdf')
    assert not (tmp_path/'original.pdf').exists()


def test_outside_date_window_rejects_before_downloading_original(tmp_path,monkeypatch):
    data=index();data['total_announcements']=1
    data['announcements']=[{'announcementTime':0,'secCode':'600519'}]
    monkeypatch.setattr(service,'search_announcement_window',lambda *args,**kwargs:data)
    monkeypatch.setattr(service,'download_disclosure_pdf',lambda *args:pytest.fail('invalid window downloaded'))
    with pytest.raises(ValueError,match='outside'):
        service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic issuer',
            start=date(2020,1,1),end=date(2020,1,2),output_dir=tmp_path/'runtime/events')


def test_beijing_midnight_preserves_calendar_day_without_intraday_assurance(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    data=index(); data['total_announcements']=1
    data['announcements']=[dict(secCode='600519',announcementId='123',announcementTitle='Synthetic',
        adjunctUrl='finalpage/2020-01-01/123.PDF',
        announcementTime=int(datetime(2020,1,1,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()*1000))]
    monkeypatch.setattr(service,'search_announcement_window',lambda *args,**kwargs:data)
    def download(url,path):
        document=PdfWriter(); document.add_blank_page(width=100,height=100)
        with path.open('wb') as handle: document.write(handle)
        return service.sha256_file(path)
    monkeypatch.setattr(service,'download_disclosure_pdf',download)
    result=service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic',
        start=date(2020,1,1),end=date(2020,1,2),output_dir=tmp_path/'runtime/events')
    assert result['announcement_count']==1 and result['materiality_approved'] is False
    assert result['timestamp_assurance']=='PROVIDER_DATE_METADATA_NOT_INTRADAY_AVAILABILITY'


@pytest.mark.parametrize('raw',[b'<html>challenge</html>',b'%PDF-1.7 truncated'])
def test_invalid_official_body_cannot_produce_complete_scan(tmp_path, monkeypatch,raw):
    data=index();data['total_announcements']=1
    data['announcements']=[dict(secCode='600519',announcementId='123',announcementTitle='Synthetic',
        adjunctUrl='finalpage/2020-01-01/123.PDF',announcementTime=1577808000000)]
    monkeypatch.setattr(service,'search_announcement_window',lambda *args,**kwargs:data)
    def download(url,path):
        path.write_bytes(raw); return service.sha256_file(path)
    monkeypatch.setattr(service,'download_disclosure_pdf',download)
    with pytest.raises(ValueError,match='complete PDF'):
        service.collect_daily_event_observation(root=tmp_path,symbol='600519',issuer_name='Synthetic',
            start=date(2020,1,1),end=date(2020,1,2),output_dir=tmp_path/'runtime/events')
    assert not (tmp_path/'runtime/events/event-scan.json').exists()


def raw_query(monkeypatch, *, tamper=None, pages=None):
    import hashlib
    from value_investment_agent import disclosures

    def search(symbol, start, end, issuer_name, *, raw_response_sink):
        data = index()
        bodies = pages or [b'{ "totalAnnouncement": 0, "announcements": [] }\r\n']
        rows = []
        for page, body in enumerate(bodies, 1):
            payload = json.loads(body)
            rows.extend(payload['announcements'])
            request = {**data['parameters'], 'pageNum': str(page)}
            raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method='POST', request=request,
                page=page, acquired_at=datetime.now(ZoneInfo('UTC')).isoformat(),
                sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)))
        data['announcements'] = rows
        data['total_announcements'] = len(rows)
        if tamper:
            tamper()
        return data

    monkeypatch.setattr(service, 'search_announcement_window', search)


def test_opt_in_zero_result_binds_actual_raw_bytes_without_approval(tmp_path, monkeypatch):
    raw_query(monkeypatch)
    folder = tmp_path/'runtime/events'
    result = service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
        start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    raw = folder/'raw-index/response-0001.bin'
    assert raw.read_bytes() == b'{ "totalAnnouncement": 0, "announcements": [] }\r\n'
    manifest = json.loads((folder/'raw-index-manifest.json').read_text(encoding='utf-8'))
    record = manifest['responses'][0]
    assert record['sha256'] == service.sha256_file(raw)
    assert record['page'] == 1 and record['request']['seDate'] == '2020-01-01~2020-01-02'
    assert result['index_representation'] == 'PARSED_OFFICIAL_QUERY_WITH_RECEIVED_RESPONSE_CONTENT'
    assert not result['materiality_approved'] and not result['model_revalidated']
    assert not result['research_date_advanced'] and result['action'] == 'no_order'
    scan = event_scan_from_payload(json.loads((folder/'event-scan.json').read_text(encoding='utf-8')))
    assert scan.status == 'PENDING_HUMAN_REVIEW'
    assert any(ref['path'].endswith('.bin') for ref in result['source_bindings'])


def test_opt_in_requires_raw_even_when_parsed_query_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'search_announcement_window', lambda *args, **kwargs: index())
    folder = tmp_path/'runtime/events'
    with pytest.raises(ValueError, match='raw pages missing'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not (folder/'event-scan.json').exists()


@pytest.mark.parametrize('target', ['response-0001.bin', 'response-0001.json'])
def test_raw_tamper_cannot_generate_scan(tmp_path, monkeypatch, target):
    folder = tmp_path/'runtime/events'
    raw_query(monkeypatch, tamper=lambda: (folder/'raw-index'/target).write_bytes(b'tampered'))
    with pytest.raises(ValueError, match='changed before scan'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not (folder/'event-scan.json').exists()


def test_raw_archive_preserves_disk_reserve(tmp_path, monkeypatch):
    from types import SimpleNamespace
    raw_query(monkeypatch)
    monkeypatch.setattr(service.shutil, 'disk_usage', lambda _: SimpleNamespace(free=2*1024**3))
    folder = tmp_path/'runtime/events'
    with pytest.raises(OSError, match='reserve'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not list(folder.rglob('*.bin')) and not (folder/'event-scan.json').exists()


@pytest.mark.parametrize('outside', [False, True])
def test_future_or_nonproject_path_fails_before_query(tmp_path, monkeypatch, outside):
    monkeypatch.setattr(service, 'search_announcement_window', lambda *args, **kwargs: pytest.fail('query ran'))
    folder = tmp_path/'outside' if outside else tmp_path/'runtime/events'
    end = date(2020,1,2) if outside else date(2999,1,1)
    with pytest.raises(ValueError, match='project root|future'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=end, output_dir=folder, retain_raw_index=True)
    assert not folder.exists()


def test_raw_page_order_or_body_mismatch_fails_before_pdf_download(tmp_path, monkeypatch):
    body = b'{"totalAnnouncement":1,"announcements":[{"secCode":"600519","announcementTime":1577808000000}]}'
    raw_query(monkeypatch, pages=[body])
    search = service.search_announcement_window

    def changed(*args, **kwargs):
        data = search(*args, **kwargs)
        data['announcements'][0]['announcementTime'] += 1000
        return data

    monkeypatch.setattr(service, 'search_announcement_window', changed)
    monkeypatch.setattr(service, 'download_disclosure_pdf', lambda *args: pytest.fail('download ran'))
    with pytest.raises(ValueError, match='inconsistent'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=tmp_path/'runtime/events', retain_raw_index=True)


@pytest.mark.parametrize('target', ['raw-index/response-0001.bin', 'raw-index-manifest.json'])
def test_tamper_during_pdf_acquisition_never_publishes_scan(tmp_path, monkeypatch, target):
    from pypdf import PdfWriter
    body = json.dumps({'totalAnnouncement':1, 'announcements':[dict(secCode='600519',
        announcementId='123', announcementTitle='Synthetic', adjunctUrl='finalpage/2020-01-01/123.PDF',
        announcementTime=1577808000000)]}).encode()
    raw_query(monkeypatch, pages=[body])
    folder = tmp_path/'runtime/events'

    def download(url, path):
        document = PdfWriter(); document.add_blank_page(width=100, height=100)
        with path.open('wb') as handle: document.write(handle)
        (folder/target).write_bytes(b'tampered')
        return service.sha256_file(path)

    monkeypatch.setattr(service, 'download_disclosure_pdf', download)
    with pytest.raises(ValueError, match='changed before scan'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not (folder/'event-scan.json').exists()


def test_future_acquisition_timestamp_rejected(tmp_path, monkeypatch):
    raw_query(monkeypatch)
    search = service.search_announcement_window

    def future(*args, raw_response_sink, **kwargs):
        def retain(body, metadata):
            metadata['acquired_at'] = '2999-01-01T00:00:00+00:00'
            raw_response_sink(body, metadata)
        return search(*args, raw_response_sink=retain, **kwargs)

    monkeypatch.setattr(service, 'search_announcement_window', future)
    folder = tmp_path/'runtime/events'
    with pytest.raises(ValueError, match='acquisition metadata'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not list(folder.rglob('*.bin')) and not (folder/'event-scan.json').exists()


def test_missing_raw_pagination_page_rejected(tmp_path, monkeypatch):
    row = dict(secCode='600519', announcementId='1', announcementTime=1577808000000)
    raw_query(monkeypatch, pages=[json.dumps({'totalAnnouncement':2, 'announcements':[row]}).encode()])
    search = service.search_announcement_window

    def missing(*args, **kwargs):
        data = search(*args, **kwargs)
        data['announcements'].append({**row, 'announcementId':'2'})
        data['total_announcements'] = 2
        return data

    monkeypatch.setattr(service, 'search_announcement_window', missing)
    monkeypatch.setattr(service, 'download_disclosure_pdf', lambda *args: pytest.fail('download ran'))
    folder = tmp_path/'runtime/events'
    with pytest.raises(ValueError, match='raw pages missing'):
        service.collect_daily_event_observation(root=tmp_path, symbol='600519', issuer_name='Synthetic',
            start=date(2020,1,1), end=date(2020,1,2), output_dir=folder, retain_raw_index=True)
    assert not (folder/'event-scan.json').exists()
