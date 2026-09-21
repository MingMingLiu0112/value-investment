"""Synthetic boundary tests; no fixture is real market or approval evidence."""
import base64
from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL,
    evaluate_quote_session,
    latest_sse_2026_session,
    next_sse_2026_session,
    latest_szse_session,
)


NOW = datetime(2026, 9, 7, 8, tzinfo=timezone.utc)


def document(raw, url, fetched=NOW.isoformat()):
    return {'source_url': url, 'fetched_at': fetched,
            'raw_base64': base64.b64encode(raw).decode('ascii'),
            'sha256': hashlib.sha256(raw).hexdigest()}


def evidence(price=60, day='2026-09-07', clock='15:00:00', symbol='000333'):
    identity = ('sz' if symbol.startswith(('0', '3')) else 'sh') + symbol
    tx = [''] * 31
    tx[2], tx[3], tx[5], tx[6], tx[30] = symbol, str(price), str(price), '100', day.replace('-', '') + clock.replace(':', '')
    sina = [''] * 33
    sina[1], sina[3], sina[8], sina[30], sina[31], sina[32] = str(price), str(price), '10000', day, clock, '00'
    rows = [{'jyrq': date(2026, 9, n).isoformat(),
             'jybz': '1' if date(2026, 9, n).weekday() < 5 and n != 25 else '0'}
            for n in range(1, monthrange(2026, 9)[1] + 1)]
    return {'symbol': symbol, 'calendar_exchange': 'SZSE', 'calendar_documents': [
        document(json.dumps({'data': rows, 'nowdate': '2026-09-07'}).encode(),
                 'https://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=2026-09')],
        'tencent': document(('v_' + identity + '="' + '~'.join(tx) + '";\n').encode(),
                            'https://qt.gtimg.cn/q=' + identity),
        'sina': document(('var hq_str_' + identity + '="' + ','.join(sina) + '";\n').encode(),
                         'https://hq.sinajs.cn/list=' + identity)}


def sse_evidence(price=1275.16, day='2026-09-11', clock='15:30:00'):
    packet = evidence(price=price, day=day, clock=clock, symbol='600519')
    fetched = day + 'T08:00:00+00:00'
    for key in ('tencent', 'sina'):
        item = packet[key]
        packet[key] = document(base64.b64decode(item['raw_base64']), item['source_url'], fetched)
    packet['calendar_exchange'] = 'SSE'
    notice = '''关于上海证券交易所2026年部分节假日休市安排的通知
    1月1日（星期四）至1月3日（星期六）休市
    2月15日（星期日）至2月23日（星期一）休市
    4月4日（星期六）至4月6日（星期一）休市
    5月1日（星期五）至5月5日（星期二）休市
    6月19日（星期五）至6月21日（星期日）休市
    9月25日（星期五）至9月27日（星期日）休市
    10月1日（星期四）至10月7日（星期三）休市'''.encode()
    packet['calendar_documents'] = [document(notice, SSE_2026_CLOSURE_NOTICE_URL, fetched)]
    return packet


def test_valid_same_session_close_passes_recomputed_evidence():
    result = evaluate_quote_session('000333', 60, evidence(), NOW)
    assert result['passed'] and result['expected_session'] == '2026-09-07'
    assert len(result['source_hashes']) == 3


def test_retrieved_today_but_older_trade_date_never_passes():
    result = evaluate_quote_session('000333', 60, evidence(day='2026-09-04'), NOW)
    assert not result['passed'] and result['status'] == 'stale_quote'


def test_today_intraday_quote_never_becomes_a_close():
    result = evaluate_quote_session('000333', 60, evidence(clock='10:00:00'), NOW)
    assert result['status'] == 'intraday_quote' and not result['passed']


def test_price_changed_or_one_cent_boundary_is_not_a_generic_two_percent_tolerance():
    assert evaluate_quote_session('000333', 59, evidence(), NOW)['status'] == 'price_conflict'
    packet = evidence()
    raw = base64.b64decode(packet['sina']['raw_base64']).replace(b',60,', b',60.02,')
    packet['sina'] = document(raw, packet['sina']['source_url'])
    assert evaluate_quote_session('000333', 60, packet, NOW)['status'] == 'price_conflict'


def test_intraday_signal_cannot_use_a_current_day_close_from_the_future():
    now = datetime(2026, 9, 7, 2, tzinfo=timezone.utc)
    assert evaluate_quote_session('000333', 60, evidence(), now)['status'] == 'invalid_evidence'


def test_weekend_uses_friday_and_explicit_weekday_holiday_is_respected():
    packet = evidence()
    saturday = datetime(2026, 9, 12, 8, tzinfo=timezone.utc)
    assert latest_szse_session(packet['calendar_documents'], saturday)[0] == '2026-09-11'
    for item in packet['calendar_documents']:
        body = json.loads(base64.b64decode(item['raw_base64']))
        body['nowdate'] = '2026-09-25'
        item.update(document(json.dumps(body).encode(), item['source_url'], '2026-09-25T08:00:00+00:00'))
    holiday = datetime(2026, 9, 25, 8, tzinfo=timezone.utc)
    assert latest_szse_session(packet['calendar_documents'], holiday)[0] == '2026-09-24'


@pytest.mark.parametrize('mutation', ['hash', 'date', 'duplicate', 'truncated', 'malformed', 'url'])
def test_calendar_tampering_or_missing_days_fail_closed(mutation):
    packet = evidence()
    doc = packet['calendar_documents'][0]
    body = json.loads(base64.b64decode(doc['raw_base64']))
    if mutation == 'hash':
        doc['sha256'] = '0' * 64
    elif mutation == 'url':
        doc['source_url'] = doc['source_url'].replace('www.szse.cn', 'example.test')
    else:
        if mutation == 'date': body['nowdate'] = '2026-09-06'
        if mutation == 'duplicate': body['data'].append(body['data'][0])
        if mutation == 'truncated': body['data'].pop()
        if mutation == 'malformed': body = []
        doc.update(document(json.dumps(body).encode(), doc['source_url']))
    assert evaluate_quote_session('000333', 60, packet, NOW)['status'] == 'invalid_evidence'


def test_calendar_never_assumed_to_cover_a_different_exchange():
    result = evaluate_quote_session('600519', 60, evidence(symbol='600519'), NOW)
    assert result['status'] == 'unsupported_calendar'
    assert result['provider_times']


def test_sse_2026_official_closure_notice_validates_moutai_close():
    now = datetime(2026, 9, 11, 8, tzinfo=timezone.utc)
    result = evaluate_quote_session('600519', 1275.16, sse_evidence(), now)
    assert result['passed'] and result['expected_session'] == '2026-09-11'
    assert len(result['source_hashes']) == 3


def test_sse_notice_respects_mid_autumn_closure_and_refuses_other_years():
    packet = sse_evidence(day='2026-09-24')
    holiday = datetime(2026, 9, 25, 8, tzinfo=timezone.utc)
    assert latest_sse_2026_session(packet['calendar_documents'], holiday)[0] == '2026-09-24'
    with pytest.raises(ValueError, match='another year'):
        latest_sse_2026_session(packet['calendar_documents'], datetime(2027, 1, 4, 8, tzinfo=timezone.utc))


def test_sse_notice_proves_next_session_date_but_not_a_future_fill():
    packet = sse_evidence(day='2026-09-16')
    now = datetime(2026, 9, 16, 8, tzinfo=timezone.utc)
    assert next_sse_2026_session(packet['calendar_documents'], date(2026, 9, 16), now)[0] == '2026-09-17'
    assert next_sse_2026_session(packet['calendar_documents'], date(2026, 9, 24), now)[0] == '2026-09-28'


def test_retained_raw_bytes_are_required_and_cached_pass_is_not_trusted():
    packet = evidence()
    packet['passed'] = True
    del packet['tencent']['raw_base64']
    assert not evaluate_quote_session('000333', 60, packet, NOW)['passed']
    assert not evaluate_quote_session('000333', 60, None, NOW)['passed']


def test_duplicate_quote_and_embedded_code_are_rejected_without_execution():
    for suffix in ('duplicate', 'unexpected'):
        packet = deepcopy(evidence())
        doc = packet['tencent']
        raw = base64.b64decode(doc['raw_base64'])
        raw += raw if suffix == 'duplicate' else b'alert(1);'
        doc.update(document(raw, doc['source_url']))
        assert evaluate_quote_session('000333', 60, packet, NOW)['status'] == 'invalid_evidence'
