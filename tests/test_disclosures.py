from pathlib import Path
from urllib.error import URLError
from types import SimpleNamespace
import pytest

from value_investment_agent import disclosures


def announcement(title: str, url: str) -> dict:
    return {
        "announcementTitle": title,
        "adjunctUrl": url,
        "announcementTime": 1776355200000,
    }


def test_collects_only_full_latest_official_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        disclosures,
        "_request_json",
        lambda _: {"announcements": [
            announcement("Demo 2025年年度报告摘要", "summary.pdf"),
            announcement("Demo 2025年年度报告", "annual.pdf"),
            announcement("Demo 2026年半年度报告", "interim.pdf"),
            announcement("Demo 2026年第一季度报告", "q1.pdf"),
            announcement("Demo 2025年第三季度报告", "q3.pdf"),
            announcement("Demo 2025年年度报告（英文版）", "annual-en.pdf"),
        ]},
    )

    downloaded: list[str] = []

    def download(url: str, target: Path) -> str:
        downloaded.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"official PDF")
        return "a" * 64

    monkeypatch.setattr(disclosures, "_download", download)
    records = disclosures.collect_latest_reports(["600519"], tmp_path)

    assert {record["report_kind"] for record in records} == {"annual", "interim", "first_quarter", "third_quarter"}
    assert {record["report_period"] for record in records} == {"2025-12-31", "2026-06-30", "2026-03-31", "2025-09-30"}
    assert all(url.startswith("https://static.cninfo.com.cn/") for url in downloaded)
    assert all(record["source_name"] == disclosures.SOURCE_NAME for record in records)
    assert {record["report_assurance"] for record in records} == {
        "statutory_annual_report_audit_required",
        "statutory_interim_report_unaudited_or_reviewed",
        "statutory_quarterly_report_unaudited",
    }


def test_download_removes_partial_file_after_network_failure(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "annual.pdf"

    def fail_download(*_args, **_kwargs):
        raise URLError("timed out")

    monkeypatch.setattr(disclosures, "urlopen", fail_download)

    try:
        disclosures._download("https://example.invalid/annual.pdf", target)
    except URLError:
        pass
    else:
        raise AssertionError("network failure should propagate to the queue retry handler")

    assert not target.exists()
    assert not target.with_suffix(".pdf.part").exists()


def test_low_disk_blocks_network_download(monkeypatch, tmp_path):
    monkeypatch.setattr(disclosures.shutil,'disk_usage',lambda _: SimpleNamespace(free=1024))
    monkeypatch.setattr(disclosures,'urlopen',lambda *_a,**_k: pytest.fail('network must not start'))
    with pytest.raises(OSError,match='Low disk'):
        disclosures._download('https://example.invalid/report.pdf',tmp_path/'report.pdf')


def test_mainland_report_preferred_over_later_h_share_notice(monkeypatch):
    records=[announcement('H股公告-2026年半年度报告','h.pdf'),announcement('2026年半年度报告','a.pdf')]
    records[0]['announcementTime'] += 10000
    monkeypatch.setattr(disclosures,'_request_json',lambda _: {'announcements':records})
    monkeypatch.setattr(disclosures,'_discover_security_id',lambda *_: 'id')
    assert disclosures.search_latest_reports('601398')[0]['adjunctUrl']=='a.pdf'


def test_revised_url_does_not_reuse_an_old_period_file(monkeypatch,tmp_path):
    chosen=[announcement('2026年半年度报告','first.pdf')]
    monkeypatch.setattr(disclosures,'search_latest_reports',lambda *_:chosen)
    downloads=[]
    def download(url,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        raw=b'%PDF-'+url.encode()
        path.write_bytes(raw)
        downloads.append(path)
        return disclosures.hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(disclosures,'_download',download)
    first=disclosures.collect_latest_reports(['600036'],tmp_path)[0]
    chosen[0]=announcement('2026年半年度报告','revised.pdf')
    revised=disclosures.collect_latest_reports(['600036'],tmp_path)[0]
    assert first['local_path']!=revised['local_path']
    assert first['sha256']!=revised['sha256']
    assert len(downloads)==2
    disclosures.collect_latest_reports(['600036'],tmp_path)
    assert len(downloads)==2
@pytest.mark.parametrize('cover,expected', [
    ('公司代码：600754/900934 公司简称：锦江酒店\n2025 年年度报告', '2025-12-31'),
    ('公司代码：600755\n2025 年年度报告', None),
    ('2025 年年度报告', None),
    ('公司代码：600754\n2025 年年度报告摘要', None),
    ('公司代码：600754\n2025 年年度报告\n2024 年年度报告', None),
])
def test_undated_annual_cover_requires_unique_year_and_issuer(cover, expected):
    assert disclosures._annual_period_from_cover(cover, '600754') == expected


def test_abbreviated_annual_is_not_hidden_by_old_dated_report(monkeypatch, tmp_path):
    old = announcement('2019年年度报告', 'old.pdf')
    new = announcement('锦江酒店年报', 'new.pdf')
    new['secCode'] = '600754'
    new['announcementTime'] += 1000
    monkeypatch.setattr(disclosures, '_request_json', lambda _: {'announcements': [new, old]})
    monkeypatch.setattr(disclosures, '_discover_security_id', lambda *_: 'id')
    selected = disclosures.search_latest_reports('600754')
    assert {r['adjunctUrl'] for r in selected} == {'old.pdf', 'new.pdf'}
    monkeypatch.setattr(disclosures, 'search_latest_reports', lambda *_: [new])
    monkeypatch.setattr(disclosures, '_download', lambda *_: 'a' * 64)
    from value_investment_agent import pdf_text
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['公司代码：600754\n2025 年年度报告'])
    record = disclosures.collect_latest_reports(['600754'], tmp_path)[0]
    assert record['report_period'] == '2025-12-31'
    assert record['title'] == '锦江酒店年报'
    assert disclosures._report_kind('锦江酒店年报摘要') is None
def test_old_abbreviated_annual_does_not_disrupt_new_dated_report(monkeypatch):
    old = announcement('公司年报', 'old.pdf')
    old['secCode'] = '601857'
    latest = announcement('2025年年度报告', 'latest.pdf')
    latest['announcementTime'] += 1000
    monkeypatch.setattr(disclosures, '_request_json', lambda _: {'announcements': [old, latest]})
    monkeypatch.setattr(disclosures, '_discover_security_id', lambda *_: 'id')
    assert [r['adjunctUrl'] for r in disclosures.search_latest_reports('601857')] == ['latest.pdf']
def test_new_summary_triggers_uncategorized_full_report_lookup(monkeypatch):
    old = announcement('公司2024年年度报告', 'old.pdf')
    summary = announcement('公司2025年年度报告摘要', 'summary.pdf')
    full = dict(announcement('公司2025年年度报告', 'full.pdf'), secCode='600050')
    other = dict(announcement('公司2026年年度报告', 'other.pdf'), secCode='600958')
    opinion = dict(announcement('关于2026年年度报告的独立意见', 'opinion.pdf'), secCode='600050')
    supervision = dict(announcement('2026年持续督导年度报告书', 'supervision.pdf'), secCode='600050')
    calls = []

    def request(params):
        calls.append(params)
        if params.get('searchkey') == '年度报告':
            assert params['category'] == '' and params['isHLtitle'] == 'false'
            return {'announcements': [other, opinion, supervision, full]}
        return {'announcements': [old, summary]} if params['category'] == 'category_ndbg_szsh' else {}

    monkeypatch.setattr(disclosures, '_request_json', request)
    monkeypatch.setattr(disclosures, '_discover_security_id', lambda *_: 'id')
    assert [r['adjunctUrl'] for r in disclosures.search_latest_reports('600050')] == ['full.pdf']
    assert sum(p.get('searchkey') == '年度报告' for p in calls) == 1
def test_beijing_query_does_not_use_unsupported_column():
    assert disclosures._cninfo_security_id('920599')[0] == ''


def test_broker_identity_falls_back_to_annual_exact_code(monkeypatch):
    def request(params):
        if params['category'] == 'category_ndbg_szsh':
            return {'announcements': [
                {'secCode': '600000', 'orgId': 'wrong'},
                {'secCode': '601211', 'orgId': 'qsgn0000116'}]}
        return {'announcements': [{'secCode': '688521', 'orgId': 'sponsored-issuer'}]}
    monkeypatch.setattr(disclosures, '_request_json', request)
    assert disclosures._discover_security_id('601211', 'sse', 'fallback', '国泰海通') == 'qsgn0000116'


@pytest.mark.parametrize('symbol,name,org', [
    ('605098', 'XD action', 'gfbj0831891'), ('689009', 'Nine-WD', '9900039199')])
def test_display_name_failure_resolves_exact_security_code(monkeypatch, symbol, name, org):
    calls = []
    def request(params):
        calls.append(params)
        if params['searchkey'] == symbol:
            assert params['column'] == '' and params['stock'] == ''
            return {'announcements': [{'secCode': '600000', 'orgId': 'wrong'},
                                      {'secCode': symbol, 'orgId': org}]}
        return {'announcements': []}
    monkeypatch.setattr(disclosures, '_request_json', request)
    assert disclosures._discover_security_id(symbol, 'sse', 'fallback', name) == org
    assert len(calls) == 3


def test_code_identity_does_not_accept_conflicting_org_ids(monkeypatch):
    monkeypatch.setattr(disclosures, '_request_json', lambda params: {'announcements': [
        {'secCode': '605098', 'orgId': 'a'}, {'secCode': '605098', 'orgId': 'b'}]
        if params['searchkey'] == '605098' else []})
    assert disclosures._discover_security_id('605098', 'sse', 'fallback', 'XD action') == 'fallback'
