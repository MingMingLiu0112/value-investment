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
