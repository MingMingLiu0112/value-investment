"""Bounded Sina three-statement orchestration and source-bound E1 row replay."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import re
import time

import requests
from urllib.parse import urlencode

from .sina_income_original import ENDPOINT, SinaStatement, STATEMENT_SOURCES, collect_sina_statement_original
from .public_financial_snapshot import _path, _clock, _json, _sha, CHINA

VERSION = 'sina-financial-statements-v1'
ROLES = ('balance', 'income', 'cashflow')
MAX_SYMBOLS = 6


def _symbols(symbols):
    if (not isinstance(symbols, (list, tuple)) or not 1 <= len(symbols) <= MAX_SYMBOLS
            or len(set(symbols)) != len(symbols)
            or any(not isinstance(s, str) or not re.fullmatch(r'[036]\d{5}', s, re.ASCII) for s in symbols)):
        raise ValueError('one to six unique supported symbols required')
    return list(symbols)


def _period(period, now):
    if (not isinstance(period, str) or not re.fullmatch(r'\d{4}-12-31', period)
            or date.fromisoformat(period) >= now.date()):
        raise ValueError('completed FY period required')
    return f'{int(period[:4])-1}-12-31'


def _url(symbol, role):
    return ENDPOINT + '?' + urlencode(dict(paperCode=('sh' if symbol.startswith('6') else 'sz')+symbol,
        source=STATEMENT_SOURCES[SinaStatement(role)], type='0', page='1', num='16'))


def _bound(root, binding, max_bytes=2_000_000):
    path = _path(root, binding['path'])
    if path.stat().st_size > max_bytes:
        raise ValueError('source exceeds byte bound')
    raw = path.read_bytes()
    if _sha(raw) != binding['sha256']:
        raise ValueError('Sina source hash mismatch')
    return raw


def _report(payload, period, role, acquired, source_ref):
    result = payload['result']
    if result.get('status', {}).get('code') != 0:
        raise ValueError('Sina returned non-success status')
    data = result['data']
    reports = data['report_list']
    if not isinstance(reports, dict) or not 1 <= len(reports) <= 32:
        raise ValueError('Sina report count outside bound')
    key = period.replace('-', '')
    dates = [row.get('date_value') for row in data['report_date']]
    if dates.count(key) != 1 or key not in reports:
        raise ValueError('requested report period unavailable or ambiguous')
    report = reports[key]
    if report.get('rType') != '合并期末' or report.get('rCurrency') != 'CNY':
        raise ValueError('explicit consolidated CNY report required')
    published = datetime.strptime(report['publish_date'], '%Y%m%d').replace(tzinfo=CHINA)
    if published.date() < date.fromisoformat(period) or published > acquired:
        raise ValueError('report publication outside observation interval')
    if report.get('update_time') is not None:
        updated = datetime.fromtimestamp(report['update_time'], timezone.utc)
        if updated > acquired or updated.date() < date.fromisoformat(period):
            raise ValueError('report update outside observation interval')
    native = report['data']
    if not isinstance(native, list) or not 1 <= len(native) <= 512:
        raise ValueError('statement row count outside bound')
    rows = []
    for index, row in enumerate(native):
        if (not isinstance(row, dict) or row.get('item_source') != STATEMENT_SOURCES[SinaStatement(role)]
                or not isinstance(row.get('item_title'), str) or not row['item_title'].strip()
                or 'item_value' not in row):
            raise ValueError('statement row identity/source mismatch')
        raw_value = row['item_value']
        missing = raw_value is None or raw_value in ('', '--', '-')
        if missing:
            value = None
        else:
            try:
                number = Decimal(str(raw_value))
                if isinstance(raw_value, bool) or not number.is_finite():
                    raise ValueError('nonfinite statement amount')
                value = str(number)
            except (InvalidOperation, TypeError) as error:
                raise ValueError('invalid statement amount') from error
        rows.append(dict(label=row['item_title'], value=value, raw_value=raw_value,
            unit=row.get('item_unit') or report.get('rUnit'), currency=report['rCurrency'],
            unit_basis='EXPLICIT_PROVIDER_UNIT' if row.get('item_unit') or report.get('rUnit') else 'NOT_DECLARED_IN_JSON',
            period=period, field=row.get('item_field'), row_index=index,
            precision=row.get('item_precision'), raw=dict(row), missing=missing))
    return dict(rows=rows, source_ref=dict(source_ref, report_key=key),
                period=period, scope='consolidated', scope_evidence=report['rType'],
                currency=report['rCurrency'], metadata={k:v for k,v in report.items() if k!='data'},
                identity_basis='EXACT_REQUEST_PAPERCODE_NOT_BODY_ISSUER_ATTESTATION',
                assurance='E1_PROVIDER_OBSERVATION', formal_admission=False, complete_debt=None)


def _replay(root, descriptor, symbol, role, period, now):
    acquired = _clock(descriptor['acquired_at'])
    if acquired > now or descriptor['source_url'] != _url(symbol, role):
        raise ValueError('Sina request identity or cutoff mismatch')
    raw = _bound(root, descriptor)
    receipt = json.loads(_bound(root, descriptor['receipt'], 100_000))
    expected = dict(url=descriptor['source_url'], path=descriptor['path'], sha256=descriptor['sha256'],
                    acquired_at=descriptor['acquired_at'], bytes=len(raw), action='no_order')
    if any(receipt.get(k) != v for k,v in expected.items()):
        raise ValueError('Sina original differs from acquisition receipt')
    payload = json.loads(raw)
    current = _report(payload, period, role, acquired, descriptor)
    prior = _period(period, now)
    try:
        comparison = _report(payload, prior, role, acquired, descriptor)
        error = None
    except (ValueError, KeyError, TypeError) as failure:
        comparison = None
        error = dict(symbol=symbol, role=role, period=prior, error_type=type(failure).__name__, message=str(failure))
    return current, comparison, error


def _retryable_transport(error):
    response = getattr(error, 'response', None)
    if response is not None and 'Retry-After' in response.headers:
        return False
    if isinstance(error, requests.exceptions.SSLError):
        return False
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    return (isinstance(error, requests.HTTPError) and response is not None
            and 500 <= response.status_code <= 599)


def _collect_with_retry(root, folder, symbol, role, period):
    """At most two outer calls; preserve existing collector's own transport policy."""
    folder.mkdir(parents=True, exist_ok=False)
    entry = dict(symbol=symbol, role=role, status='FAILED', descriptor=None, attempts=[])
    for number in (1, 2):
        attempt_folder = folder / f'attempt-{number:02d}'
        record = dict(symbol=symbol, role=role, attempt=number,
                      started_at=datetime.now(timezone.utc).isoformat(),
                      action='no_order', descriptor=None)
        retry = False
        try:
            descriptor = collect_sina_statement_original(root=root, symbol=symbol,
                output_dir=attempt_folder, statement=SinaStatement(role), allow_network=True)
            record['descriptor'] = descriptor
            _replay(root, descriptor, symbol, role, period, datetime.now(timezone.utc))
            record['status'] = 'COMPLETE'
            entry.update(status='COMPLETE', descriptor=descriptor)
        except Exception as error:
            receipt_path = attempt_folder / 'acquisition.json'
            if record['descriptor'] is None and receipt_path.exists():
                raw = receipt_path.read_bytes(); receipt = json.loads(raw)
                record['descriptor'] = dict(path=receipt['path'], sha256=receipt['sha256'],
                    acquired_at=receipt['acquired_at'], source_url=receipt['url'],
                    receipt=dict(path=receipt_path.relative_to(root).as_posix(), sha256=_sha(raw)))
            failure = dict(symbol=symbol, role=role, error_type=type(error).__name__, message=str(error)[:500])
            retry = number == 1 and _retryable_transport(error)
            record.update(status='FAILED', error=failure, retry_scheduled=retry)
            entry.update(error=failure, descriptor=record['descriptor'])
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        path = folder / f'attempt-{number:02d}.json'
        raw = _json(record)
        with path.open('xb') as stream:
            stream.write(raw)
        entry['attempts'].append(dict(path=path.relative_to(root).as_posix(), sha256=_sha(raw)))
        if entry['status'] == 'COMPLETE':
            entry.pop('error', None)
            break
        if not retry:
            break
        time.sleep(1)
    return entry


def collect(root: Path, output_dir: Path, symbols: list[str], period: str,
            allow_network: bool = False) -> dict:
    """Reuse the bounded collector; at most two outer attempts per statement."""
    if allow_network is not True:
        raise ValueError('explicit public network authorization required')
    symbols = _symbols(symbols)
    started = datetime.now(timezone.utc)
    _period(period, started)
    root = Path(root).resolve()
    output = _path(root, Path(output_dir))
    if output == (root/'runtime').resolve():
        raise ValueError('new runtime child directory required')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema_version=VERSION, symbols=symbols, period=period, sources=[],
        action='no_order', assurance='E1_PROVIDER_OBSERVATIONS', formal_admission=False,
        started_at=started.isoformat(), errors=[])
    for symbol in symbols:
        for role in ROLES:
            entry = _collect_with_retry(root, output/symbol/role, symbol, role, period)
            if entry['status'] == 'FAILED':
                manifest['errors'].append(entry['error'])
            manifest['sources'].append(entry)
    manifest['available_at']=datetime.now(timezone.utc).isoformat()
    complete=sum(x['status']=='COMPLETE' for x in manifest['sources'])
    manifest['status']='COMPLETE' if complete==len(manifest['sources']) else 'PARTIAL' if complete else 'UNAVAILABLE'
    raw=_json(manifest);path=output/'manifest.json'
    with path.open('xb') as stream:stream.write(raw)
    return dict(path=path.relative_to(root).as_posix(),sha256=_sha(raw))



def _verify_attempts(root, entry, start, finish):
    """Optional additive audit closure; legacy entries without attempts stay valid."""
    if 'attempts' not in entry:
        return
    bindings = entry['attempts']
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 2:
        raise ValueError('one or two attempt receipts required')
    previous_end = start
    for number, binding in enumerate(bindings, 1):
        if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
            raise ValueError('exact attempt binding required')
        record = json.loads(_bound(root, binding, 100_000))
        if (record.get('symbol') != entry['symbol'] or record.get('role') != entry['role']
                or type(record.get('attempt')) is not int or record['attempt'] != number
                or record.get('action') != 'no_order' or record.get('status') not in {'COMPLETE', 'FAILED'}):
            raise ValueError('attempt identity/sequence mismatch')
        begin, end = _clock(record['started_at']), _clock(record['finished_at'])
        if not start <= previous_end <= begin <= end <= finish:
            raise ValueError('attempt time outside manifest or sequence')
        previous_end = end
        descriptor = record['descriptor']
        if descriptor is not None:
            acquired = _clock(descriptor['acquired_at'])
            if not begin <= acquired <= end or descriptor['source_url'] != _url(entry['symbol'], entry['role']):
                raise ValueError('attempt source time/request mismatch')
            raw = _bound(root, descriptor)
            receipt = json.loads(_bound(root, descriptor['receipt'], 100_000))
            expected = dict(url=descriptor['source_url'], path=descriptor['path'],
                sha256=descriptor['sha256'], acquired_at=descriptor['acquired_at'],
                bytes=len(raw), action='no_order')
            if any(receipt.get(k) != v for k, v in expected.items()):
                raise ValueError('attempt source/acquisition receipt mismatch')
            # Failed response bytes may be invalid JSON; binding verification is sufficient here.
        if number < len(bindings):
            if record['status'] != 'FAILED' or record.get('retry_scheduled') is not True:
                raise ValueError('only failed retry-scheduled attempt can precede another')
        elif (record['status'] != entry['status'] or descriptor != entry['descriptor']
                or record.get('retry_scheduled', False) is not False):
            raise ValueError('final attempt differs from source entry')
        if record['status'] == 'COMPLETE':
            if descriptor is None or 'error' in record:
                raise ValueError('successful attempt needs descriptor and no error')
        else:
            error = record['error']
            if error.get('symbol') != entry['symbol'] or error.get('role') != entry['role']:
                raise ValueError('attempt error identity mismatch')
            if number == len(bindings) and error != entry['error']:
                raise ValueError('final attempt error differs from source entry')


def load(root: Path, binding: dict, evaluation_at: datetime) -> dict:
    """Read-only source replay. Blank values and repeated native lines are preserved."""
    root=Path(root).resolve()
    if evaluation_at.utcoffset() is None:
        raise ValueError('aware evaluation time required')
    manifest=json.loads(_bound(root,binding))
    if (manifest.get('schema_version')!=VERSION or manifest.get('action')!='no_order'
            or manifest.get('formal_admission') is not False
            or manifest.get('assurance')!='E1_PROVIDER_OBSERVATIONS'):
        raise ValueError('invalid Sina manifest contract')
    symbols=_symbols(manifest['symbols']);period=manifest['period'];prior=_period(period,evaluation_at)
    start,finish=_clock(manifest['started_at']),_clock(manifest['available_at'])
    if not start<=finish<=evaluation_at:raise ValueError('manifest cutoff mismatch')
    expected={(s,r) for s in symbols for r in ROLES}
    entries=manifest['sources']
    if len(entries)!=len(expected) or {(e['symbol'],e['role']) for e in entries}!=expected:
        raise ValueError('missing or duplicate symbol/statement')
    result=dict(symbols={s:dict(period=period,statements={},comparatives={prior:{}},errors=[]) for s in symbols},
        available_at=manifest['available_at'],status=manifest['status'],errors=[],action='no_order',
        assurance='E1_PROVIDER_OBSERVATIONS',formal_admission=False,complete_debt=None)
    failures=[];complete=0
    for entry in entries:
        symbol,role=entry['symbol'],entry['role'];descriptor=entry['descriptor']
        if entry['status'] not in {'COMPLETE','FAILED'}:raise ValueError('invalid source status')
        _verify_attempts(root, entry, start, finish)
        if descriptor is not None:
            if not start<=_clock(descriptor['acquired_at'])<=finish or descriptor['source_url']!=_url(symbol,role):
                raise ValueError('source time/request mismatch')
            _bound(root,descriptor);_bound(root,descriptor['receipt'],100_000)
        if entry['status']=='FAILED':
            failure=entry['error']
            if (failure['symbol'],failure['role'])!=(symbol,role):raise ValueError('error identity mismatch')
            failures.append(failure);result['symbols'][symbol]['errors'].append(failure)
            continue
        current,comparison,error=_replay(root,descriptor,symbol,role,period,evaluation_at)
        result['symbols'][symbol]['statements'][role]=current
        if comparison is not None:result['symbols'][symbol]['comparatives'][prior][role]=comparison
        if error:result['symbols'][symbol]['errors'].append(error);result['errors'].append(error)
        complete+=1
    status='COMPLETE' if complete==len(expected) else 'PARTIAL' if complete else 'UNAVAILABLE'
    if status!=manifest['status'] or failures!=manifest['errors']:raise ValueError('manifest status/errors mismatch')
    result['errors']=failures+result['errors']
    result['status']='PARTIAL' if result['errors'] and complete else status
    return result
