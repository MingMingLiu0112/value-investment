from value_investment_agent import disclosures


def test_first_and_third_quarter_are_independently_queried(monkeypatch):
    records = {
        'category_ndbg_szsh': ('2025年年度报告', 'annual.pdf'),
        'category_bndbg_szsh': ('2026年半年度报告', 'interim.pdf'),
        'category_yjdbg_szsh': ('2026年第一季度报告', 'first.pdf'),
        'category_sjdbg_szsh': ('2025年第三季度报告', 'third.pdf'),
    }
    calls = []
    def request(params):
        calls.append(params['category'])
        title, url = records[params['category']]
        return {'announcements': [{'secCode': '600519', 'announcementTitle': title,
                                   'adjunctUrl': url, 'announcementTime': 1}]}
    monkeypatch.setattr(disclosures, '_request_json', request)
    monkeypatch.setattr(disclosures, '_discover_security_id', lambda *_: 'gssh0600519')
    selected = disclosures.search_latest_reports('600519')
    assert set(calls) == set(records)
    assert len(calls) == 4
    assert {row['adjunctUrl'] for row in selected} == {'annual.pdf', 'interim.pdf', 'first.pdf', 'third.pdf'}
