"""Recheck raw quote timestamps against retained, venue-specific calendars."""
import base64
import binascii
import hashlib
import html
import json
import re
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse


CHINA = timezone(timedelta(hours=8))
VERSION = 'quote-session-v2-szse-sse-raw-evidence'
CALENDAR_PATH = '/api/report/exchange/onepersistenthour/monthList'
SSE_2026_CLOSURE_NOTICE_PATH = '/disclosure/announcement/general/c/c_20251222_10802507.shtml'
SSE_2026_CLOSURE_NOTICE_URL = 'https://www.sse.com.cn' + SSE_2026_CLOSURE_NOTICE_PATH
SSE_2026_NOTICE_MARKERS = (
    '关于上海证券交易所2026年部分节假日休市安排的通知',
    '1月1日（星期四）至1月3日（星期六）休市',
    '2月15日（星期日）至2月23日（星期一）休市',
    '4月4日（星期六）至4月6日（星期一）休市',
    '5月1日（星期五）至5月5日（星期二）休市',
    '6月19日（星期五）至6月21日（星期日）休市',
    '9月25日（星期五）至9月27日（星期日）休市',
    '10月1日（星期四）至10月7日（星期三）休市',
)
SSE_2026_CLOSURE_RANGES = (
    (date(2026, 1, 1), date(2026, 1, 3)),
    (date(2026, 2, 15), date(2026, 2, 23)),
    (date(2026, 4, 4), date(2026, 4, 6)),
    (date(2026, 5, 1), date(2026, 5, 5)),
    (date(2026, 6, 19), date(2026, 6, 21)),
    (date(2026, 9, 25), date(2026, 9, 27)),
    (date(2026, 10, 1), date(2026, 10, 7)),
)
QUOTE_URLS = {'tencent': ('qt.gtimg.cn', '/q='),
              'sina': ('hq.sinajs.cn', '/list=')}
LABELS = {
    'missing_evidence': '缺少带实际日期的逐股行情及交易日历证据',
    'invalid_evidence': '行情日期或日历原始证据无效',
    'unsupported_calendar': '该交易所的官方日历尚未接入此门禁',
    'stale_quote': '实际报价交易日早于最近已完成交易日',
    'intraday_quote': '盘中报价不能充当最近已完成交易日的收盘价',
    'price_conflict': '逐股报价与决策价格不一致或双源差异超过0.01元',
    'untradeable_quote': '逐股报价未证明当日正常有成交',
    'matched_close': '带日期双源报价与最近已完成交易日一致',
}


def _stamp(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if stamp.utcoffset() is None:
        raise ValueError('Timezone-aware evidence timestamps required')
    return stamp.astimezone(CHINA)


def _number(value):
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError('Positive finite quote value required')
    return result


def _raw(document, now, *, host, path_prefix, max_age):
    if not isinstance(document, dict):
        raise ValueError('Raw evidence document required')
    url = urlparse(document['source_url'])
    if (url.scheme != 'https' or url.hostname != host or url.username or url.password
            or not url.path.startswith(path_prefix)):
        raise ValueError('Unexpected source URL')
    fetched = _stamp(document['fetched_at'])
    if fetched > now + timedelta(minutes=5) or fetched < now - max_age:
        raise ValueError('Evidence download time is invalid or stale')
    encoded = document['raw_base64']
    if not isinstance(encoded, str) or len(encoded) > 1_400_000:
        raise ValueError('Evidence response too large')
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != document['sha256']:
        raise ValueError('Raw evidence SHA-256 mismatch')
    return raw, fetched, url


def parse_quote(document, provider, symbol, now):
    host, prefix = QUOTE_URLS[provider]
    raw, fetched, url = _raw(document, now, host=host, path_prefix=prefix,
                             max_age=timedelta(days=10))
    text = raw.decode('gb18030')
    assignment = 'v_' if provider == 'tencent' else 'var hq_str_'
    pattern = re.compile(re.escape(assignment) + r'((?:sh|sz|bj)\d{6})="([^"\r\n]*)";')
    parsed = {}
    position = 0
    for match in pattern.finditer(text):
        if text[position:match.start()].strip():
            raise ValueError('Unexpected quote response content')
        identity = match[1]
        if identity in parsed:
            raise ValueError('Duplicate quote identity')
        parsed[identity] = match[2]
        position = match.end()
    if text[position:].strip() or not parsed:
        raise ValueError('Unexpected or empty quote response')
    exchange = 'sz' if symbol.startswith(('0', '3')) else 'sh' if symbol.startswith('6') else 'bj'
    identity = exchange + symbol
    if identity not in url.path[len(prefix):].split(',') or identity not in parsed:
        raise ValueError('Requested quote identity missing')
    fields = parsed[identity].split('~' if provider == 'tencent' else ',')
    if provider == 'tencent':
        if len(fields) < 31 or fields[2] != symbol or not re.fullmatch(r'\d{14}', fields[30]):
            raise ValueError('Invalid Tencent identity or timestamp layout')
        stamp = datetime.strptime(fields[30], '%Y%m%d%H%M%S').replace(tzinfo=CHINA)
        price, opening, volume, normal = _number(fields[3]), _number(fields[5]), Decimal(fields[6]), True
    else:
        if len(fields) < 33:
            raise ValueError('Invalid Sina timestamp layout')
        stamp = datetime.strptime(fields[30] + ' ' + fields[31], '%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA)
        price, opening, volume, normal = _number(fields[3]), _number(fields[1]), Decimal(fields[8]), fields[32] == '00'
    if stamp > fetched + timedelta(minutes=5) or stamp > now + timedelta(minutes=5):
        raise ValueError('Quote is later than observation time')
    return {'provider': provider, 'symbol': symbol, 'observed_trade_at': stamp.isoformat(),
            'price': price, 'opening_price': opening, 'normal_with_volume': normal and volume.is_finite() and volume > 0,
            'source_url': document['source_url'], 'sha256': document['sha256']}


def latest_szse_session(documents, now):
    if not isinstance(documents, list) or not documents or len(documents) > 3:
        raise ValueError('Bounded official monthly calendar documents required')
    dates = {}
    hashes = []
    for document in documents:
        raw, fetched, url = _raw(document, now, host='www.szse.cn', path_prefix=CALENDAR_PATH,
                                max_age=timedelta(days=7))
        query = parse_qs(url.query)
        if url.path != CALENDAR_PATH or len(query.get('month', [])) != 1:
            raise ValueError('Explicit requested calendar month required')
        month = query['month'][0]
        if not re.fullmatch(r'\d{4}-\d{2}', month):
            raise ValueError('Invalid calendar month')
        year, number = map(int, month.split('-'))
        expected = {date(year, number, day) for day in range(1, monthrange(year, number)[1] + 1)}
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('Invalid calendar response shape')
        if payload.get('nowdate') != fetched.date().isoformat():
            raise ValueError('Calendar response date differs from download day')
        rows = payload['data']
        month_dates = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Invalid calendar row')
            day = date.fromisoformat(row['jyrq'])
            if day not in expected or day in month_dates or row.get('jybz') not in ('0', '1'):
                raise ValueError('Incomplete, duplicate or invalid official calendar dates')
            month_dates[day] = row['jybz'] == '1'
        if set(month_dates) != expected or set(month_dates) & set(dates):
            raise ValueError('Calendar month incomplete or repeated')
        dates.update(month_dates)
        hashes.append(document['sha256'])
    if now.date() not in dates:
        raise ValueError('Current calendar date not covered')
    # Five minutes after the regular 15:00 close is an operational publication buffer.
    cursor = now.date() if now.time() >= time(15, 5) else now.date() - timedelta(days=1)
    while cursor in dates:
        if dates[cursor]:
            return cursor.isoformat(), hashes
        cursor -= timedelta(days=1)
    raise ValueError('Latest completed session not covered by official calendar')


def latest_sse_2026_session(documents, now):
    """Derive a 2026 SSE session only from the pinned official closure notice.

    SSE publishes this annual notice rather than the SZSE's daily machine
    calendar.  The derivation is intentionally year-bounded and requires the
    exact URL and all announced closure ranges before applying the normal
    Monday-Friday market schedule.  It must never be reused for another year.
    """
    if not isinstance(documents, list) or len(documents) != 1:
        raise ValueError('Exactly one official SSE 2026 closure notice is required')
    raw, _, url = _raw(documents[0], now, host='www.sse.com.cn',
                       path_prefix=SSE_2026_CLOSURE_NOTICE_PATH, max_age=timedelta(days=366))
    if url.path != SSE_2026_CLOSURE_NOTICE_PATH or url.query:
        raise ValueError('Unexpected SSE closure-notice URL')
    compact = re.sub(r'\s+', '', html.unescape(raw.decode('utf-8', errors='strict')))
    if not all(marker in compact for marker in SSE_2026_NOTICE_MARKERS):
        raise ValueError('Incomplete or unexpected SSE 2026 closure notice')
    local_now = _stamp(now)
    if local_now.year != 2026:
        raise ValueError('SSE 2026 closure notice cannot validate another year')
    closures = {
        day
        for start, end in SSE_2026_CLOSURE_RANGES
        for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    }
    cursor = local_now.date() if local_now.time() >= time(15, 5) else local_now.date() - timedelta(days=1)
    while cursor.year == 2026:
        if cursor.weekday() < 5 and cursor not in closures:
            return cursor.isoformat(), [documents[0]['sha256']]
        cursor -= timedelta(days=1)
    raise ValueError('Latest completed SSE session is outside 2026 notice coverage')


def next_sse_2026_session(documents, after, now):
    """Return the next SSE session from the same pinned 2026 closure notice.

    Date membership is deliberately separated from execution readiness.  This
    establishes only that a session is scheduled; a later open-price/status
    observation remains required before a simulated fill is possible.
    """
    if not isinstance(after, date) or isinstance(after, datetime):
        raise ValueError('A date-only completed session is required')
    if after.year != 2026:
        raise ValueError('SSE 2026 closure notice cannot validate another year')
    if not isinstance(documents, list) or len(documents) != 1:
        raise ValueError('Exactly one official SSE 2026 closure notice is required')
    raw, _, url = _raw(documents[0], _stamp(now), host='www.sse.com.cn',
                       path_prefix=SSE_2026_CLOSURE_NOTICE_PATH, max_age=timedelta(days=366))
    if url.path != SSE_2026_CLOSURE_NOTICE_PATH or url.query:
        raise ValueError('Unexpected SSE closure-notice URL')
    compact = re.sub(r'\s+', '', html.unescape(raw.decode('utf-8', errors='strict')))
    if not all(marker in compact for marker in SSE_2026_NOTICE_MARKERS):
        raise ValueError('Incomplete or unexpected SSE 2026 closure notice')
    closures = {
        day
        for start, end in SSE_2026_CLOSURE_RANGES
        for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    }
    cursor = after + timedelta(days=1)
    while cursor.year == 2026:
        if cursor.weekday() < 5 and cursor not in closures:
            return cursor.isoformat(), [documents[0]['sha256']]
        cursor += timedelta(days=1)
    raise ValueError('Next SSE session is outside 2026 notice coverage')


def evaluate_quote_session(symbol, price, evidence, now, *, documents=None):
    result = {'version': VERSION, 'status': 'missing_evidence', 'passed': False,
              'expected_session': None, 'provider_times': {}, 'source_hashes': []}
    if evidence is None:
        return dict(result, reason=LABELS[result['status']])
    try:
        now = _stamp(now)
        if not re.fullmatch(r'\d{6}', symbol) or not isinstance(evidence, dict):
            raise ValueError('Quote evidence identity required')
        if 'document_refs' in evidence:
            from .quote_session_collection import resolve_session_reference
            evidence = resolve_session_reference(evidence, documents)
        if evidence.get('symbol') != symbol:
            raise ValueError('Evidence symbol differs from decision')
        quotes = [parse_quote(evidence[provider], provider, symbol, now)
                  for provider in ('tencent', 'sina')]
        result['provider_times'] = {q['provider']: q['observed_trade_at'] for q in quotes}
        result['source_hashes'] = [q['sha256'] for q in quotes]
        venue = evidence.get('calendar_exchange')
        if venue == 'SZSE' and symbol.startswith(('0', '3')):
            session, hashes = latest_szse_session(evidence['calendar_documents'], now)
            result['expected_session'] = session
            result['source_hashes'] += hashes
            times = [_stamp(q['observed_trade_at']) for q in quotes]
            if any(t.date().isoformat() > session or t.time() < time(15) for t in times):
                result['status'] = 'intraday_quote'
            elif any(t.date().isoformat() < session for t in times):
                result['status'] = 'stale_quote'
            elif not all(q['normal_with_volume'] for q in quotes):
                result['status'] = 'untradeable_quote'
            elif (_number(price) != quotes[0]['price']
                  or abs(quotes[0]['price'] - quotes[1]['price']) > Decimal('.01')):
                result['status'] = 'price_conflict'
            else:
                result.update(status='matched_close', passed=True)
        elif venue == 'SSE' and symbol.startswith('6') and evidence.get('calendar_documents'):
            session, hashes = latest_sse_2026_session(evidence['calendar_documents'], now)
            result['expected_session'] = session
            result['source_hashes'] += hashes
            times = [_stamp(q['observed_trade_at']) for q in quotes]
            if any(t.date().isoformat() > session or t.time() < time(15) for t in times):
                result['status'] = 'intraday_quote'
            elif any(t.date().isoformat() < session for t in times):
                result['status'] = 'stale_quote'
            elif not all(q['normal_with_volume'] for q in quotes):
                result['status'] = 'untradeable_quote'
            elif (_number(price) != quotes[0]['price']
                  or abs(quotes[0]['price'] - quotes[1]['price']) > Decimal('.01')):
                result['status'] = 'price_conflict'
            else:
                result.update(status='matched_close', passed=True)
        else:
            result['status'] = 'unsupported_calendar'
    except (KeyError, TypeError, ValueError, InvalidOperation, UnicodeError, binascii.Error) as error:
        result.update(status='invalid_evidence', detail=str(error))
    return dict(result, reason=LABELS[result['status']])
