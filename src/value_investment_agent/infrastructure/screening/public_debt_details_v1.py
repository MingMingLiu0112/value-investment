"""Bounded full consolidated balance originals; E1 observations, never debt-scope admission."""
from datetime import date, datetime, timezone
from pathlib import Path
import re
import time
from urllib.parse import urlencode

import requests

from .public_financial_snapshot import (
    ENDPOINT, MAX_BYTES, CHINA,
    _read_response, _path, _clock, _json, _sha,
)
import json

VERSION = 'public-debt-details-v1'
PAGE_SIZE = 200
MAX_PAGES = 60
REPORTS = dict(balance='RPT_F10_FINANCE_GBALANCE')


def _period(period, at):
    if (not isinstance(period, str) or not re.fullmatch(r'\d{4}-12-31', period)
            or date.fromisoformat(period) >= at.date()):
        raise ValueError('completed annual period required')


def _url(role, period, page):
    return ENDPOINT + '?' + urlencode(dict(
        sortColumns='SECURITY_CODE', sortTypes='1', pageSize=str(PAGE_SIZE),
        pageNumber=str(page), reportName=REPORTS[role], columns='ALL',
        filter=f"(REPORT_DATE='{period}')(SECURITY_TYPE_CODE=\"058001001\")(SECURITY_CODE<=\"999999\")"))


def _parse_page(raw):
    from decimal import Decimal
    import math
    if len(raw) > MAX_BYTES:
        raise ValueError('financial response byte budget exceeded')
    payload = json.loads(raw, parse_float=Decimal,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(payload, dict) or payload.get('success') is not True:
        raise ValueError('financial provider did not return success')
    result = payload.get('result')
    if not isinstance(result, dict):
        raise ValueError('financial result missing')
    count, pages, rows = result.get('count'), result.get('pages'), result.get('data')
    if (type(count) is not int or type(pages) is not int
            or not 1 <= count <= PAGE_SIZE * MAX_PAGES
            or not 1 <= pages <= MAX_PAGES or math.ceil(count / PAGE_SIZE) != pages
            or not isinstance(rows, list) or not 1 <= len(rows) <= PAGE_SIZE):
        raise ValueError('financial pagination outside bounded contract')
    return count, pages, rows


def _identity(row, period, acquired):
    symbol = row.get('SECURITY_CODE')
    if (not isinstance(symbol, str) or not re.fullmatch(r'[034689][0-9]{5}', symbol)
            or row.get('SECUCODE') != symbol + ('.SH' if symbol.startswith('6') else '.SZ' if symbol.startswith(('0','3')) else '.BJ')
            or row.get('SECURITY_TYPE_CODE') != '058001001'
            or row.get('CURRENCY') != 'CNY'
            or row.get('ORG_TYPE') != '通用'
            or row.get('REPORT_TYPE') != '年报'
            or row.get('REPORT_DATE') != period + ' 00:00:00'):
        raise ValueError('statement identity/period mismatch')
    for field in ('NOTICE_DATE', 'UPDATE_DATE'):
        value = row.get(field)
        if field == 'UPDATE_DATE' and value is None:
            continue
        try:
            stamp = datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA)
        except (ValueError, TypeError) as error:
            raise ValueError('invalid provider date: ' + field) from error
        if stamp.date() < date.fromisoformat(period) or stamp > acquired:
            raise ValueError('provider date outside observation window: ' + field)
    return symbol


def _page(raw, *, period, acquired, number, expected, seen):
    count, pages, rows = _parse_page(raw)
    if expected is not None and (count, pages) != expected:
        raise ValueError('statement pagination totals changed')
    if number > pages or len(rows) != (PAGE_SIZE if number < pages else count - PAGE_SIZE * (pages - 1)):
        raise ValueError('statement page incomplete')
    result = []
    for index, row in enumerate(rows):
        symbol = _identity(row, period, acquired)
        if symbol in seen:
            raise ValueError('duplicate statement security identity')
        seen.add(symbol)
        result.append((symbol, row, index))
    return (count, pages), result


def collect(root: Path, output_dir: Path, period: str, allow_network: bool) -> dict:
    """One bounded full-balance pass, retaining failures and all returned page bytes."""
    if allow_network is not True:
        raise ValueError('explicit public network permission required')
    started = datetime.now(timezone.utc)
    _period(period, started)
    root = Path(root).resolve()
    output = _path(root, Path(output_dir))
    if output == (root / 'runtime').resolve():
        raise ValueError('fresh child directory required')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema_version=VERSION, period=period, action='no_order',
        assurance='E1_PROVIDER_OBSERVATIONS', formal_admission=False, complete_debt_verified=False,
        historical_pit_eligible=False, started_at=started.isoformat(), sources={}, errors=[])
    with requests.Session() as session:
        session.trust_env = True
        for role in REPORTS:
            folder = output / role
            folder.mkdir()
            source = dict(status='COLLECTING', report_name=REPORTS[role], pages=[])
            manifest['sources'][role] = source
            seen, expected = set(), None
            try:
                for number in range(1, MAX_PAGES + 1):
                    if number > 1:
                        time.sleep(1)
                    url = _url(role, period, number)
                    raw = bytes(_read_response(session, url))
                    acquired = datetime.now(timezone.utc)
                    path = folder / f'page-{number:03d}.json'
                    with path.open('xb') as stream:
                        stream.write(raw)
                    descriptor = dict(path=path.relative_to(root).as_posix(), sha256=_sha(raw),
                        source_url=url, acquired_at=acquired.isoformat(), page=number)
                    source['pages'].append(descriptor)
                    expected, _ = _page(raw, period=period, acquired=acquired,
                                       number=number, expected=expected, seen=seen)
                    if number == expected[1]:
                        break
                if expected is None or len(seen) != expected[0] or len(source['pages']) != expected[1]:
                    raise ValueError('statement coverage incomplete')
                source.update(status='COMPLETE', row_count=len(seen), declared_count=expected[0])
            except Exception as error:
                failure = dict(role=role, error_type=type(error).__name__,
                               message=str(error)[:500], observed_at=datetime.now(timezone.utc).isoformat())
                source.update(status='FAILED', error=failure)
                manifest['errors'].append(failure)
    complete = sum(source['status'] == 'COMPLETE' for source in manifest['sources'].values())
    manifest.update(status='COMPLETE' if complete == len(REPORTS) else 'PARTIAL' if complete else 'UNAVAILABLE',
                    available_at=datetime.now(timezone.utc).isoformat())
    path = output / 'manifest.json'
    raw = _json(manifest)
    with path.open('xb') as stream:
        stream.write(raw)
    return dict(path=path.relative_to(root).as_posix(), sha256=_sha(raw))


def load(root: Path, binding: dict, evaluation_at: datetime) -> dict:
    """Cold replay every bound page. Corruption raises, failed roles stay empty/explicit."""
    root = Path(root).resolve()
    if evaluation_at.utcoffset() is None:
        raise ValueError('aware evaluation time required')
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('exact manifest binding required')
    if Path(binding['path']).is_absolute() or '..' in Path(binding['path']).parts:
        raise ValueError('relative manifest binding required')
    raw = _path(root, binding['path']).read_bytes()
    if _sha(raw) != binding['sha256']:
        raise ValueError('statement manifest hash mismatch')
    manifest = json.loads(raw)
    if (manifest.get('schema_version') != VERSION or manifest.get('action') != 'no_order'
            or manifest.get('assurance') != 'E1_PROVIDER_OBSERVATIONS'
            or manifest.get('formal_admission') is not False
            or manifest.get('complete_debt_verified') is not False
            or manifest.get('historical_pit_eligible') is not False
            or set(manifest['sources']) != set(REPORTS)):
        raise ValueError('invalid debt-details contract')
    started, finished = _clock(manifest['started_at']), _clock(manifest['available_at'])
    if not started <= finished <= evaluation_at:
        raise ValueError('statement observation outside cutoff')
    period = manifest['period']
    _period(period, started)
    result = dict(balance={}, status=manifest['status'], period=period,
                  available_at=manifest['available_at'], errors=manifest['errors'],
                  action='no_order', assurance='E1_PROVIDER_OBSERVATIONS', formal_admission=False,
                  complete_debt_verified=False, historical_pit_eligible=False,
                  universe_scope='PROVIDER_ALL_A_INCLUDING_DELISTED_NOT_CURRENT_SSE_MAIN',
                  source_status={})
    errors, completed = [], 0
    for role, report in REPORTS.items():
        source = manifest['sources'][role]
        if source['report_name'] != report or source['status'] not in {'COMPLETE', 'FAILED'}:
            raise ValueError('invalid role/report status')
        if not isinstance(source['pages'], list) or len(source['pages']) > MAX_PAGES:
            raise ValueError('statement page bound exceeded')
        result['source_status'][role] = source['status']
        seen, expected = set(), None
        for number, descriptor in enumerate(source['pages'], 1):
            if descriptor['page'] != number or descriptor['source_url'] != _url(role, period, number):
                raise ValueError('statement request identity mismatch')
            acquired = _clock(descriptor['acquired_at'])
            if not started <= acquired <= finished:
                raise ValueError('page acquisition outside collection interval')
            if Path(descriptor['path']).is_absolute() or '..' in Path(descriptor['path']).parts:
                raise ValueError('relative page binding required')
            page_raw = _path(root, descriptor['path']).read_bytes()
            if _sha(page_raw) != descriptor['sha256']:
                raise ValueError('statement page hash mismatch')
            if source['status'] == 'FAILED':
                continue  # Archive may contain the error response; never promote its partial rows.
            expected, rows = _page(page_raw, period=period, acquired=acquired,
                                  number=number, expected=expected, seen=seen)
            for symbol, row, index in rows:
                result[role][symbol] = dict(raw=row, source_ref=dict(descriptor, row_index=index,
                    role=role, report_name=report, manifest=dict(binding),
                    availability_basis='FIRST_OBSERVED_NOT_HISTORICAL_NOTICE'))
        if source['status'] == 'COMPLETE':
            if (expected is None or expected[1] != len(source['pages'])
                    or expected[0] != len(seen) or len(seen) != source['row_count']
                    or len(seen) != source['declared_count']):
                raise ValueError('statement total coverage mismatch')
            completed += 1
        else:
            failure = source['error']
            if failure['role'] != role or not started <= _clock(failure['observed_at']) <= finished:
                raise ValueError('invalid role failure evidence')
            errors.append(failure)
    status = 'COMPLETE' if completed == len(REPORTS) else 'PARTIAL' if completed else 'UNAVAILABLE'
    if manifest['status'] != status or errors != manifest['errors']:
        raise ValueError('statement status/error mismatch')
    return result
