"""Official exchange security lists and same-date, per-code market reconciliation."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlencode

from openpyxl import load_workbook
import requests

VERSION = 'official-security-lists-v1'
CHINA = timezone(timedelta(hours=8))
SZSE_URL = 'https://www.szse.cn/api/report/ShowReport'
SSE_URL = 'https://query.sse.com.cn/sseQuery/commonQuery.do'
BSE_URL = 'https://www.bse.cn/nqxxController/nqxxCnzq.do'


def _code(value):
    if isinstance(value, (int, float)) and int(value) == value:
        value = str(int(value))
    value = str(value).strip().zfill(6)
    if not re.fullmatch(r'\d{6}', value):
        raise ValueError(f'Invalid exchange security code: {value}')
    return value


def _date(value):
    text = str(value).strip()
    if re.fullmatch(r'\d{8}', text):
        return datetime.strptime(text, '%Y%m%d').date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _unique(rows):
    if len({r['symbol'] for r in rows}) != len(rows):
        raise ValueError('Duplicate exchange codes: pagination or source inconsistency')
    return rows


def parse_szse(raw):
    wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    try:
        ws = wb.active
        # The official export declares A1 despite containing thousands of rows.
        ws.reset_dimensions()
        iterator = iter(ws.values)
        header = next(iterator)
        required = ['板块','A股代码','A股简称','A股上市日期']
        if not all(f in header for f in required):
            raise ValueError('SZSE stock-list columns changed')
        rows = []
        for cells in iterator:
            if not any(cells):
                continue
            row = dict(zip(header, cells))
            if row['板块'] not in {'主板', '创业板'}:
                raise ValueError('Unrecognized official SZSE board')
            rows.append({'symbol':_code(row['A股代码']), 'name':str(row['A股简称']).strip(),
                         'board':row['板块'], 'exchange':'SZSE', 'listed_on':_date(row['A股上市日期']),
                         'security_type':'A股', 'official_industry':row.get('所属行业')})
        return _unique(rows)
    finally:
        wb.close()


def parse_sse(raw, board):
    data = json.loads(raw)
    records = data['result']
    if data.get('actionErrors') or len(records) != int(data['pageHelp']['total']):
        raise ValueError('SSE response is incomplete or reports errors')
    rows = []
    for r in records:
        code = _code(r['A_STOCK_CODE'])
        rows.append({'symbol':code,'name':r['SEC_NAME_CN'],'board':board,'exchange':'SSE',
                     'listed_on':_date(r['LIST_DATE']), 'official_industry':r.get('CSRC_CODE_DESC'),
                     'security_type':'境内存托凭证' if code.startswith('689') else 'A股'})
    return _unique(rows)


def parse_bse_page(raw):
    text = raw.decode('utf-8').strip()
    # The official endpoint returns JSON inside a literal null(...) callback.
    if text.startswith('null(') and text.endswith(')'):
        text = text[5:-1]
    data = json.loads(text)
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError('BSE response envelope changed')
    page = data[0]
    if len(page['content']) != int(page['numberOfElements']):
        raise ValueError('BSE page element count mismatch')
    return page


def collect_security_lists(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    sources = []

    def fetch(label, url, *, params=None, data=None, referer=None):
        if params:
            url += '?' + urlencode(params)
        headers = {'User-Agent':'Mozilla/5.0'}
        if referer:
            headers['Referer'] = referer
        body = urlencode(data).encode() if data is not None else None
        if body:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        with session.request('POST' if body else 'GET',url,data=body,headers=headers,
                             timeout=(15,30),stream=True) as response:
            response.raise_for_status()
            chunks = bytearray()
            for chunk in response.iter_content(65536):
                chunks.extend(chunk)
                if len(chunks) > 8 * 1024**2:
                    raise ValueError('Exchange response exceeds bounded archive size')
            raw = bytes(chunks)
            final_url = response.url
        digest = hashlib.sha256(raw).hexdigest()
        path = directory / f'{digest}.bin'
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Retained exchange response hash mismatch')
        else:
            if shutil.disk_usage(directory).free - len(raw) < 2 * 1024**3:
                raise OSError('Preserve 2 GiB database disk reserve')
            temporary = path.with_suffix('.part')
            temporary.write_bytes(raw)
            temporary.replace(path)
        sources.append({'label':label,'url':final_url,'request_url':url,'request_data':data,'sha256':digest,
                        'local_path':str(path),'fetched_at':datetime.now(timezone.utc).isoformat()})
        return raw

    szse = parse_szse(fetch('SZSE_A',SZSE_URL,params={'SHOWTYPE':'xlsx','CATALOGID':'1110','TABKEY':'tab1'}))
    sse = []
    for kind, board in [('1','主板'),('8','科创板')]:
        params = {'STOCK_TYPE':kind,'sqlId':'COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L',
                  'COMPANY_STATUS':'2,4,5,7,8','type':'inParams','isPagination':'true',
                  'pageHelp.pageSize':'10000','pageHelp.pageNo':'1','pageHelp.beginPage':'1','pageHelp.endPage':'1'}
        sse.extend(parse_sse(fetch('SSE_'+kind,SSE_URL,params=params,
                                  referer='https://www.sse.com.cn/assortment/stock/list/share/'),board))
    bse = []
    declared = None
    page_count = 1
    index = 0
    while index < page_count:
        page = parse_bse_page(fetch(f'BSE_{index}',BSE_URL,data={
            'page':str(index),'typejb':'T','xxfcbj[]':'2','xxzqdm':'','sortfield':'xxzqdm','sorttype':'asc'}))
        current = (int(page['totalElements']), int(page['totalPages']))
        if declared is not None and current != declared:
            raise ValueError('BSE totals changed during pagination')
        declared = current
        page_count = current[1]
        if not 1 <= page_count <= 200 or int(page['number']) != index:
            raise ValueError('BSE pagination bounds or sequence invalid')
        for r in page['content']:
            bse.append({'symbol':_code(r['xxzqdm']),'name':r['xxzqjc'],'board':'北交所','exchange':'BSE',
                        'listed_on':_date(r['fxssrq']),'as_of':_date(r['xxjsrq']),
                        'listing_date_basis':'精选层平移公司此日期为精选层挂牌日期；其他为本所上市日期',
                        'security_type':'A股','official_industry':r.get('xxhyzl')})
        index += 1
    if len(bse) != declared[0] or len({r['as_of'] for r in bse}) != 1:
        raise ValueError('BSE final count/date mismatch')
    records = _unique(szse + sse + bse)
    if len(szse) < 2000 or len(sse) < 2000 or len(bse) < 200:
        raise ValueError('Exchange universe unexpectedly small; refuse coverage claim')
    if len({datetime.fromisoformat(s['fetched_at']).astimezone(CHINA).date() for s in sources}) != 1:
        raise ValueError('Exchange collection crossed dates; repeat a coherent snapshot')
    if {r['as_of'] for r in bse} != {str(datetime.now(CHINA).date())}:
        raise ValueError('BSE list is not dated today; cannot call the combined universe current')
    session.close()
    return {'parser_version':VERSION,'records':records,'sources':sources,
            'fetched_at':datetime.now(timezone.utc).isoformat(),
            'exchange_counts':dict(Counter(r['exchange'] for r in records)),
            'board_counts':dict(Counter(r['board'] for r in records)),
            'scope':'沪深A股、科创板境内存托凭证、北交所股票', 'complete':True}


def reconcile_security_lists(official, market):
    result = {'status':'pending','reconciled':False}
    if (not official or not market or not official.get('complete')
            or not (market.get('coverage') or {}).get('decisions')):
        return result
    official_date = datetime.fromisoformat(str(official['fetched_at'])).astimezone(CHINA).date()
    market_date = datetime.fromisoformat(str(market['fetched_at'])).astimezone(CHINA).date()
    result.update(official_date=str(official_date), market_date=str(market_date))
    if official_date != market_date:
        result['status'] = 'different_dates'
        return result
    expected = {r['symbol']:r for r in _unique(official['records'])}
    received = {r['symbol']:r for r in _unique(market['coverage']['decisions'])}
    if not expected or not received:
        return result
    missing = [expected[s] for s in sorted(expected.keys() - received.keys())]
    extra = [received[s] for s in sorted(received.keys() - expected.keys())]
    boards = [{'symbol':s,'official':expected[s]['board'],'market':received[s]['board']}
              for s in sorted(expected.keys() & received.keys()) if expected[s]['board'] != received[s]['board']]
    matched = len(expected.keys() & received.keys())
    passed = not (missing or extra or boards)
    result.update(status='matched' if passed else 'differences',reconciled=passed,
                  expected_count=len(expected),matched_count=matched,coverage_ratio=matched/len(expected),
                  missing_in_market=missing,not_in_official=extra,board_conflicts=boards,scope=official['scope'],
                  sources=official['sources'])
    return result


def refresh_official_universe():
    from .db import _store_document, begin_run, connect, end_run, record_failed_run
    from .settings import get_settings
    settings = get_settings()
    directory = settings.evidence_directory / 'security_lists'
    with connect(settings.database_url) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(hashtext('official-security-lists')) AS locked").fetchone()['locked']:
            return {'status':'already_running'}
        run_id = begin_run(connection,'refresh-security-universe')
        connection.commit()
        try:
            result = collect_security_lists(directory)
            raw = json.dumps(result,ensure_ascii=False,sort_keys=True).encode()
            digest = hashlib.sha256(raw).hexdigest()
            path = directory / f'{digest}.json'
            if shutil.disk_usage(directory).free - len(raw) < 2 * 1024**3:
                raise OSError('Preserve 2 GiB database disk reserve')
            temporary = path.with_suffix('.part')
            temporary.write_bytes(raw)
            temporary.replace(path)
            _store_document(connection,source_name='沪深北交易所官方证券清单',
                source_url=' | '.join([SZSE_URL,SSE_URL,BSE_URL]),published_at=None,
                fetched_at=datetime.fromisoformat(result['fetched_at']),parser_version=VERSION,
                raw_payload=raw,local_path=str(path),metadata={'scope':'official_security_universe','universe':result})
            end_run(connection,run_id,'succeeded',{'exchange_counts':result['exchange_counts'],'sha256':digest})
            return {'status':'succeeded','exchange_counts':result['exchange_counts'],'sha256':digest}
        except Exception as error:
            record_failed_run(connection,run_id,'refresh-security-universe',{'error':str(error)})
            raise
