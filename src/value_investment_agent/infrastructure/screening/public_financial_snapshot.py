"""Retain paginated public annual summaries as E1 observations, never approvals.

Endpoint/field reference: akfamily/akshare stock_feature/stock_yjbb_em.py.
This adapter retains response bytes instead of relying on positional DataFrames.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode

import requests

VERSION = 'public-annual-summary-v1'
ENDPOINT = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
PAGE_SIZE = 500
MAX_PAGES = 24
MAX_BYTES = 2_000_000
CHINA = timezone(timedelta(hours=8))
FIELDS = {
    'TOTAL_OPERATE_INCOME': ('total_revenue', 'CNY'),
    'PARENT_NETPROFIT': ('net_income', 'CNY'),
    'WEIGHTAVG_ROE': ('roe_weighted', 'percent'),
    'XSMLL': ('gross_margin', 'percent'),
    'BASIC_EPS': ('eps_reported', 'CNY/share'),
    'BPS': ('bvps', 'CNY/share'),
    'MGJYXJJE': ('operating_cash_flow_per_share', 'CNY/share'),
    'YSTZ': ('total_revenue_yoy', 'percent'),
    'SJLTZ': ('parent_net_income_yoy', 'percent'),
}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _clock(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('financial acquisition clock must be timezone aware')
    return parsed


def _path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to((root / 'runtime').resolve()) or not path.is_relative_to(root):
        raise ValueError('financial evidence must remain in repository runtime')
    return path


def _url(period, page):
    return ENDPOINT + '?' + urlencode(dict(
        reportName='RPT_LICO_FN_CPD', columns='ALL', pageSize=str(PAGE_SIZE),
        pageNumber=str(page), sortColumns='SECURITY_CODE', sortTypes='1',
        filter=f'(REPORTDATE=\'{period}\')(SECURITY_TYPE_CODE="058001001")'))


def _parse_page(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('financial response byte budget exceeded')
    payload = json.loads(raw, parse_float=Decimal)
    if not isinstance(payload, dict) or payload.get('success') is not True:
        raise ValueError('financial provider did not return success')
    result = payload.get('result')
    if not isinstance(result, dict):
        raise ValueError('financial result is missing')
    count, pages, rows = result.get('count'), result.get('pages'), result.get('data')
    if (type(count) is not int or type(pages) is not int or not 1 <= pages <= MAX_PAGES
            or not 1 <= count <= MAX_PAGES * PAGE_SIZE or math.ceil(count / PAGE_SIZE) != pages
            or not isinstance(rows, list) or not 1 <= len(rows) <= PAGE_SIZE):
        raise ValueError('financial pagination outside bounded contract')
    return count, pages, rows


def _read_response(session, url):
    with session.get(url, timeout=(10, 25), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200 or response.url != url:
            raise ValueError('unexpected financial response identity')
        raw = bytearray()
        for chunk in response.iter_content(64 * 1024):
            if len(raw) + len(chunk) > MAX_BYTES:
                raise ValueError('financial response byte budget exceeded')
            raw.extend(chunk)
    return bytes(raw)


def collect_public_annual_summary(*, root: Path, output_dir: Path, period: str,
                                  allow_network: bool = False, session=None) -> dict:
    """One serial bounded collection; partial responses never become a complete export."""
    if allow_network is not True:
        raise ValueError('explicit public financial collection permission required')
    if not re.fullmatch(r'\d{4}-12-31', period) or date.fromisoformat(period) >= datetime.now(CHINA).date():
        raise ValueError('requires a completed annual period')
    root = root.resolve()
    output = _path(root, output_dir)
    if output.exists():
        raise FileExistsError('financial acquisition requires a fresh directory')
    output.mkdir(parents=True)
    owns_session = session is None
    session = session or requests.Session()
    manifest = dict(schema_version=VERSION, period=period, source='Eastmoney annual summary',
                    upstream='eastmoney', status='COLLECTING', pages=[], action='no_order',
                    assurance='E1_PROVIDER_OBSERVATIONS', formal_admission=False)
    try:
        count = pages = None
        seen = set()
        for number in range(1, MAX_PAGES + 1):
            if number > 1:
                time.sleep(1.0)
            url = _url(period, number)
            raw = _read_response(session, url)
            acquired = datetime.now(timezone.utc).isoformat()
            path = output / f'page-{number:03d}.json'
            with path.open('xb') as stream:
                stream.write(raw)
            descriptor = dict(path=path.relative_to(root).as_posix(), sha256=_sha(raw),
                              source_url=url, acquired_at=acquired, page=number)
            manifest['pages'].append(descriptor)
            current_count, current_pages, rows = _parse_page(raw)
            if count is None:
                count, pages = current_count, current_pages
            if (count, pages) != (current_count, current_pages):
                raise ValueError('financial pagination count changed')
            expected = PAGE_SIZE if number < pages else count - PAGE_SIZE * (pages - 1)
            if len(rows) != expected:
                raise ValueError('financial page incomplete')
            for row in rows:
                symbol = _validate_identity(row, period)
                if symbol in seen:
                    raise ValueError('duplicate financial security identity')
                seen.add(symbol)
            if number == pages:
                break
        manifest.update(status='COMPLETE', row_count=len(seen), declared_count=count,
                        generated_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        manifest.update(status='FAILED', error_type=type(error).__name__,
                        generated_at=datetime.now(timezone.utc).isoformat())
        raise
    finally:
        with (output / 'manifest.json').open('xb') as stream:
            stream.write(_json(manifest))
        if owns_session:
            session.close()
    return dict(path=(output / 'manifest.json').relative_to(root).as_posix(),
                sha256=_sha(_json(manifest)))


def _validate_identity(row, period):
    if not isinstance(row, dict):
        raise ValueError('invalid financial row')
    symbol, secucode = row.get('SECURITY_CODE'), row.get('SECUCODE')
    if (not isinstance(symbol, str) or not re.fullmatch(r'[034689]\d{5}', symbol)
            or secucode not in {symbol + '.SH', symbol + '.SZ', symbol + '.BJ'}
            or row.get('SECURITY_TYPE_CODE') != '058001001'
            or row.get('REPORTDATE') != period + ' 00:00:00'):
        raise ValueError('financial security/period identity mismatch')
    exchange = 'SH' if symbol.startswith('6') else 'SZ' if symbol.startswith(('0', '3')) else 'BJ'
    if secucode != symbol + '.' + exchange:
        raise ValueError('financial exchange identity mismatch')
    return symbol


def load_public_annual_summary(*, root: Path, binding: dict, evaluation_at: datetime) -> tuple[list, dict]:
    """Re-parse original bytes and PIT boundaries; a hash is not a financial approval."""
    root = root.resolve()
    if evaluation_at.tzinfo is None:
        raise ValueError('financial evaluation clock must be timezone aware')
    manifest_raw = _path(root, binding['path']).read_bytes()
    if _sha(manifest_raw) != binding['sha256']:
        raise ValueError('financial manifest hash mismatch')
    manifest = json.loads(manifest_raw)
    if (manifest.get('schema_version') != VERSION or manifest.get('status') != 'COMPLETE'
            or manifest.get('formal_admission') is not False or manifest.get('action') != 'no_order'
            or _clock(manifest['generated_at']) > evaluation_at):
        raise ValueError('financial manifest not eligible at cutoff')
    period, pages = manifest['period'], manifest['pages']
    if not re.fullmatch(r'\d{4}-12-31', period) or not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError('invalid annual manifest period/pages')
    points, seen, expected_count, missing, excluded = [], set(), None, 0, 0
    for number, descriptor in enumerate(pages, 1):
        if descriptor['page'] != number or descriptor['source_url'] != _url(period, number):
            raise ValueError('financial page source identity mismatch')
        acquired = _clock(descriptor['acquired_at'])
        if not date.fromisoformat(period) < acquired.date() or acquired > _clock(manifest['generated_at']):
            raise ValueError('financial acquisition outside period/cutoff')
        raw = _path(root, descriptor['path']).read_bytes()
        if _sha(raw) != descriptor['sha256']:
            raise ValueError('financial original hash mismatch')
        count, declared_pages, rows = _parse_page(raw)
        if expected_count is None:
            expected_count = count
        if count != expected_count or declared_pages != len(pages):
            raise ValueError('financial pagination mismatch')
        expected_rows = PAGE_SIZE if number < declared_pages else count - PAGE_SIZE * (declared_pages - 1)
        if len(rows) != expected_rows:
            raise ValueError('financial page incomplete')
        for row_index, row in enumerate(rows):
            symbol = _validate_identity(row, period)
            if symbol in seen:
                raise ValueError('duplicate financial security identity')
            seen.add(symbol)
            # Provider notice/update dates do not establish historical availability.
            dates = [row.get('NOTICE_DATE'), row.get('UPDATE_DATE')]
            try:
                notice, updated = (datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA)
                                   for value in dates)
                if min(notice.date(), updated.date()) < date.fromisoformat(period) or max(notice, updated) > acquired:
                    raise ValueError('provider date outside acquisition window')
            except (ValueError, TypeError):
                excluded += 1
                continue
            for label, (field, unit) in FIELDS.items():
                value = row.get(label)
                if value is None or value in ('', '--', '-'):
                    missing += 1
                    continue
                try:
                    decimal = Decimal(str(value))
                    if isinstance(value, bool) or not decimal.is_finite():
                        raise ValueError('nonfinite financial value')
                except (ValueError, InvalidOperation):
                    missing += 1
                    continue
                identity = _sha(_json([descriptor['sha256'], row_index, label]))
                points.append(dict(data_point_id='public-summary-' + identity, symbol=symbol,
                    field_name=field, value=str(decimal), unit=unit, currency='CNY', period_label=period,
                    source_id=descriptor['sha256'], source_name='Eastmoney annual financial summary',
                    source_url=descriptor['source_url'], raw_file_hash=descriptor['sha256'],
                    published_at=None, available_at=acquired.isoformat(), fetched_at=acquired.isoformat(),
                    created_at=acquired.isoformat(), parser_version=VERSION,
                    validation_status='unverified', metadata=dict(
                        assurance='E1_PROVIDER_OBSERVATION', automatic_cross_source_verification=False,
                        formal_admission=False, historical_pit_eligible=False,
                        availability_basis='FIRST_OBSERVED_NOT_HISTORICAL_NOTICE',
                        provider_notice_date=row['NOTICE_DATE'], provider_update_date=row['UPDATE_DATE'],
                        source_line_item=label, source_row=row_index, source_binding=descriptor,
                        statement_scope='PROVIDER_SUMMARY_NOT_STATUTORY_VERIFIED', period_basis='FY')))
    if len(seen) != expected_count or expected_count != manifest['row_count'] or expected_count != manifest['declared_count']:
        raise ValueError('financial total coverage mismatch')
    return points, dict(status='PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS', period=period,
        provider_rows=len(seen), observation_count=len(points), missing_fields=missing,
        excluded_date_rows=excluded, generated_at=manifest['generated_at'],
        accepted_official_fact_count=0, action='no_order', manifest=binding)
