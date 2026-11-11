"""Intraday official SSE main-board observations; never close/PIT admission."""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from ...official_universe import SSE_URL, parse_sse
from ...m2_market_data import (fetch_tencent_board_rank, fetch_sina_industry_quotes,
                              fetch_eastmoney_dividends)

VERSION = 'SSE_MAIN_A_OBSERVED_V1'
SCOPE = 'SSE_MAIN_A_ONLY'
ROLES = ('official', 'tencent', 'sina', 'dividend', 'financial')
MIN_RECORDS = 1000
# Secondary identity guard only: membership still requires the bound official STOCK_TYPE=1 response.
MAIN_A_PREFIXES = ('600', '601', '603', '605')
DIVIDEND_DECODER = 'EASTMONEY_DIVIDEND_NAN_AS_MISSING_V1'
REFERER = 'https://www.sse.com.cn/assortment/stock/list/share/'
PARAMS = dict(STOCK_TYPE='1', sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L',
              COMPANY_STATUS='2,4,5,7,8', type='inParams', isPagination='true',
              **{'pageHelp.pageSize': '10000', 'pageHelp.pageNo': '1',
                 'pageHelp.beginPage': '1', 'pageHelp.endPage': '1'})
REQUEST = dict(method='GET', url=SSE_URL + '?' + urlencode(PARAMS),
               referer=REFERER, stock_type='1', board='主板')


def _now():
    return datetime.now(timezone.utc)


def _stamp(value, now):
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.utcoffset() is None or now.utcoffset() is None or stamp > now:
            raise ValueError('naive or future source time')
        return stamp
    except (TypeError, AttributeError) as error:
        raise ValueError('invalid source time') from error


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf-8')


def _decode(raw, *, dividend=False):
    def reject(value):
        if dividend and value == 'NaN':
            return None
        raise ValueError('nonfinite JSON: ' + value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('nonfinite JSON number')
        return number
    return json.loads(raw, parse_constant=reject, parse_float=finite, object_pairs_hook=unique)


def _dividend_date_string(value):
    """Match the provider's default=str only for its date-like values.

    pandas.NaT is a datetime subclass: str(NaT) remains the raw "NaT"
    missing-date marker, never a fabricated date or numeric zero.
    """
    if isinstance(value, (date, datetime)):
        return str(value)
    raise TypeError('Unsupported dividend payload object: ' + type(value).__name__)


def _path(root, value):
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts or '\\' in str(value):
        raise ValueError('source path must be project relative')
    result = (root / relative).resolve()
    if not result.is_relative_to((root / 'runtime/sse-main-screening').resolve()):
        raise ValueError('source outside SSE runtime')
    return result


def _save(root, directory, name, raw, fetched_at):
    target = directory / name
    with target.open('xb') as stream:
        stream.write(raw)
    return dict(path=target.relative_to(root).as_posix(),
                sha256=hashlib.sha256(raw).hexdigest(), fetched_at=fetched_at)


def _read(root, binding, now):
    _stamp(binding['fetched_at'], now)
    raw = _path(root, binding['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('source hash mismatch')
    return raw


def _official(raw, fetched_at):
    # Strict JSON and native page total/identity checks precede projection.
    _decode(raw)
    rows = parse_sse(raw, '主板')
    if not MIN_RECORDS <= len(rows) <= 10000:
        raise ValueError('SSE main-board record count outside production bounds')
    if any(len(row['symbol']) != 6 or not row['symbol'].isascii()
           or not row['symbol'].isdigit()
           or not row['symbol'].startswith(MAIN_A_PREFIXES) for row in rows):
        raise ValueError('SSE_MAIN_A_SECURITY_CODE_OUTSIDE_ALLOWED_RANGE')
    day = datetime.fromisoformat(fetched_at).astimezone(ZoneInfo('Asia/Shanghai')).date()
    if any(row['listed_on'] > day.isoformat() or row['exchange'] != 'SSE'
           or row['board'] != '主板' or row['security_type'] != 'A股'
           or not row['name'].strip() for row in rows):
        raise ValueError('SSE identity or future listing date invalid')
    return dict(parser_version=VERSION, scope=SCOPE, complete=False, records=rows,
                fetched_at=fetched_at, available_at=fetched_at, action='no_order',
                observation_basis='INTRADAY_LIST_OBSERVATION_NOT_VERIFIED_CLOSE',
                quote_date_verified=False, strict_contemporaneous_pit=False)


def _collect_official(root, directory, errors):
    with requests.Session() as session:
        session.trust_env = True
        for attempt in range(1, 3):
            raw = bytearray()
            try:
                with session.get(REQUEST['url'], headers={'Referer': REFERER,
                        'User-Agent': 'Mozilla/5.0'}, timeout=(10, 20),
                        verify=True, allow_redirects=False, stream=True) as response:
                    raw = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_content(65536):
                        raw.extend(chunk)
                        if len(raw) > 8 * 1024**2 or time.monotonic() - started > 40:
                            # Preserve received bytes even on a rejected response.
                            _save(root, directory, f'official-attempt-{attempt}.raw',
                                  bytes(raw), _now().isoformat())
                            raise ValueError('SSE response size/time bound exceeded')
                    fetched = _now().isoformat()
                    binding = _save(root, directory, f'official-attempt-{attempt}.raw', bytes(raw), fetched)
                    if response.status_code != 200 or response.url != REQUEST['url']:
                        raise ValueError('SSE requires exact HTTPS request and HTTP 200 without redirect')
                    payload = _official(bytes(raw), fetched)
                    result = _save(root, directory, 'official.json', _json(payload), fetched)
                    result.update(raw=binding, request_identity=dict(REQUEST))
                    return result
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                retained = directory / f'official-attempt-{attempt}.raw'
                if raw and not retained.exists():
                    _save(root, directory, retained.name, bytes(raw), _now().isoformat())
                errors.append(dict(source='official', attempt=attempt,
                    error_type=type(error).__name__, message=str(error)[:500], observed_at=_now().isoformat()))
                if attempt < 2:
                    time.sleep(0.5)
    raise ValueError('SSE_ACQUISITION_FAILED_AFTER_2_ATTEMPTS')


def collect_inputs(root: Path, output_dir: Path, allow_network: bool, *,
                   financial_builder, financial_verifier) -> dict:
    """Create a new evidence directory. Partial results retain errors; no fallback."""
    if not callable(financial_builder) or not callable(financial_verifier):
        raise ValueError('EXPLICIT_FINANCIAL_CALLBACKS_REQUIRED')
    if allow_network is not True:
        raise ValueError('EXPLICIT_NETWORK_AUTHORIZATION_REQUIRED')
    root = Path(root).resolve()
    directory = Path(output_dir)
    directory = (directory if directory.is_absolute() else root / directory).resolve()
    base = (root / 'runtime/sse-main-screening').resolve()
    if directory == base or not directory.is_relative_to(base):
        raise ValueError('NEW_OUTPUT_DIRECTORY_REQUIRED_UNDER_SSE_RUNTIME')
    directory.mkdir(parents=True, exist_ok=False)
    result = dict(schema_version=VERSION, scope=SCOPE, action='no_order',
                  started_at=_now().isoformat(), inputs={}, errors=[])
    for role in ROLES:
        try:
            if role == 'official':
                binding = _collect_official(root, directory, result['errors'])
            elif role == 'financial':
                # The public annual-summary provider covers more than this
                # screen.  Bind its observations to the exact official SSE
                # source collected above, so missing providers are visible as
                # coverage gaps rather than silent out-of-scope rows.
                from .public_financial_snapshot import sse_main_board_scope
                official = json.loads((root / result['inputs']['official']['path']).read_bytes())
                scope = sse_main_board_scope(
                    records=official['records'],
                    source_sha256=result['inputs']['official']['raw']['sha256'],
                )
                payload = financial_builder(root=root, output_dir=directory,
                    collect_public=True, public_scope=scope)
                fetched = _now().isoformat()
                binding = _save(root, directory, role + '.json', _json(payload), fetched)
                financial_verifier(root=root, payload=payload, evaluation_at=_now())
                if not payload.get('points'):
                    raise ValueError('FINANCIAL_POINTS_UNAVAILABLE')
                if payload.get('public_financial_input', {}).get('status') == 'ACQUISITION_FAILED':
                    result['errors'].append(dict(source=role, error_type='AcquisitionFailed',
                        message='PUBLIC_FINANCIAL_SUPPLEMENT_FAILED_RETAINED_POINTS_ONLY', observed_at=fetched))
            else:
                fetch = {'tencent': fetch_tencent_board_rank, 'sina': fetch_sina_industry_quotes,
                         'dividend': fetch_eastmoney_dividends}[role]
                raw, payload = fetch()
                fetched = _now().isoformat()
                binding = _save(root, directory, role + '.json', raw, fetched)
                if role == 'dividend':
                    binding['decoder_version'] = DIVIDEND_DECODER
                    # Normalize both representations, never rewrite the acquired bytes.
                    decoded = _decode(raw, dividend=True)
                    payload = _decode(json.dumps(payload, ensure_ascii=False, allow_nan=True,
                                                 default=_dividend_date_string), dividend=True)
                else:
                    decoded = _decode(raw)
                if decoded != payload or not payload.get('rows'):
                    raise ValueError('PROVIDER_RAW_PAYLOAD_MISMATCH_OR_EMPTY')
                _stamp(payload['fetched_at'], _now())
            result['inputs'][role] = binding
        except Exception as error:
            result['errors'].append(dict(source=role, error_type=type(error).__name__,
                message=str(error)[:500], observed_at=_now().isoformat()))
    result.update(finished_at=_now().isoformat(),
                  status='COMPLETE_INPUTS' if len(result['inputs']) == 5 and not result['errors'] else 'PARTIAL')
    _save(root, directory, 'inputs-manifest.json', _json(result), result['finished_at'])
    if not result['inputs']:
        raise ValueError('NO_USABLE_SOURCES: see inputs-manifest.json')
    return result


def verify_inputs(root: Path, manifest_inputs: dict, now: datetime, *,
                  financial_verifier) -> dict:
    """Read-only replay. Accept the collect result; never create missing inputs."""
    if not callable(financial_verifier):
        raise ValueError('EXPLICIT_FINANCIAL_VERIFIER_REQUIRED')
    root = Path(root).resolve()
    if (manifest_inputs.get('schema_version') != VERSION or manifest_inputs.get('scope') != SCOPE
            or manifest_inputs.get('action') != 'no_order'):
        raise ValueError('UNSUPPORTED_SSE_SOURCE_CONTRACT')
    start = _stamp(manifest_inputs['started_at'], now)
    finish = _stamp(manifest_inputs['finished_at'], now)
    if start > finish or set(manifest_inputs['inputs']) != set(ROLES):
        raise ValueError('INCOMPLETE_SOURCE_INPUTS_OR_INVALID_INTERVAL')
    output = {}
    for role in ROLES:
        binding = manifest_inputs['inputs'][role]
        acquired = _stamp(binding['fetched_at'], now)
        if not start <= acquired <= finish:
            raise ValueError('source outside collection interval')
        decoder = binding.get('decoder_version')
        if decoder is not None and (role != 'dividend' or decoder != DIVIDEND_DECODER):
            raise ValueError('UNSUPPORTED_ROLE_DECODER')
        payload = _decode(_read(root, binding, now),
                          dividend=role == 'dividend' and decoder == DIVIDEND_DECODER)
        if role == 'official':
            if binding.get('request_identity') != REQUEST or binding['raw']['fetched_at'] != binding['fetched_at']:
                raise ValueError('OFFICIAL_REQUEST_IDENTITY_MISMATCH')
            if _official(_read(root, binding['raw'], now), binding['fetched_at']) != payload:
                raise ValueError('OFFICIAL_PROJECTION_MISMATCH')
        elif role == 'financial':
            for point in payload.get('points', []):
                for field in ('available_at', 'fetched_at', 'created_at', 'published_at'):
                    if point.get(field) is not None:
                        _stamp(point[field], now)
            financial_verifier(root=root, payload=payload, evaluation_at=now)
            if not payload.get('points'):
                raise ValueError('FINANCIAL_POINTS_UNAVAILABLE')
        else:
            if not payload.get('rows') or _stamp(payload['fetched_at'], now) > acquired:
                raise ValueError('EMPTY_OR_FUTURE_PROVIDER_PAYLOAD')
            for response in payload.get('original_responses', []):
                _stamp(response['fetched_at'], now)
        output[role] = payload
    return output


def recover_dividend_input(root: Path, previous_manifest_binding: dict, dividend_binding: dict,
                           output_dir: Path, now: datetime, *, financial_verifier) -> dict:
    """Explicit offline repair of the NaN-only acquisition failure into a new manifest.

    Both input bindings are {path, sha256}. Source bytes/times and old manifest
    remain untouched. The original errors are retained, not reclassified as success.
    """
    root = Path(root).resolve()
    def bound(ref):
        if set(ref) != {'path', 'sha256'}:
            raise ValueError('EXACT_RECOVERY_BINDING_REQUIRED')
        return _read(root, dict(ref, fetched_at=now.isoformat()), now)
    previous = _decode(bound(previous_manifest_binding))
    if (set(previous.get('inputs', {})) != set(ROLES) - {'dividend'}
            or not any(e.get('source') == 'dividend' and e.get('message') == 'nonfinite JSON: NaN'
                       for e in previous.get('errors', []))):
        raise ValueError('NOT_A_DIVIDEND_NAN_ONLY_MISSING_ROLE')
    source_path = _path(root, dividend_binding['path'])
    if source_path != _path(root, previous_manifest_binding['path']).parent / 'dividend.json':
        raise ValueError('RECOVERY_MUST_USE_SAME_COLLECTION_DIVIDEND_RAW')
    raw = bound(dividend_binding)
    payload = _decode(raw, dividend=True)
    fetched = payload['fetched_at']
    _stamp(fetched, now)
    result = dict(previous, inputs=dict(previous['inputs']))
    result['inputs']['dividend'] = dict(dividend_binding, fetched_at=fetched,
                                         decoder_version=DIVIDEND_DECODER)
    result['recovery'] = dict(decoder_version=DIVIDEND_DECODER,
        previous_manifest=dict(previous_manifest_binding), recovered_at=now.isoformat(),
        scope='OFFLINE_DECODE_RECOVERY_NOT_NEW_ACQUISITION', action='no_order')
    verify_inputs(root, result, now, financial_verifier=financial_verifier)
    directory = Path(output_dir)
    directory = (directory if directory.is_absolute() else root / directory).resolve()
    base = (root / 'runtime/sse-main-screening').resolve()
    if directory == base or not directory.is_relative_to(base):
        raise ValueError('NEW_OUTPUT_DIRECTORY_REQUIRED_UNDER_SSE_RUNTIME')
    directory.mkdir(parents=True, exist_ok=False)
    _save(root, directory, 'inputs-manifest.json', _json(result), now.isoformat())
    return result
